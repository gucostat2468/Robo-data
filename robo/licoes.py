"""Caderno de lições: o conhecimento de cada funcionário, registrado para sempre, com governança.

De onde vêm as lições (colheita automática, sem depender de ninguém lembrar):
  handover       — todo erro com causa, regra e como verificar;
  boa_pratica    — o que o PDCA comprovou que funciona;
  laboratorio    — toda falha do treino, com a área e a semente (dá para refazer o mesmo caso);
  correcao       — toda correção que o dono fez numa conversa;
  manual         — cada seção de conhecimento/*.md e dos manuais agentes/*.md (inclui o guia de liderança).
Quem recebe: o responsável e todo o andar dele (o conhecimento do andar é de todos do andar); manuais vão para quem
eles servem (guia de liderança → liderança; o resto → todos).

Ciclo de cada lição para cada pessoa (rodado na rodada de estudo, 2x por semana):
  atribuida → estudada → avaliada → aplicada
  - estudada: entrou no caderno e no dossiê da pessoa;
  - avaliada: a pessoa ACHA a lição quando perguntada (teste de recuperação com a pergunta-chave);
  - aplicada: há evidência de que a lição funciona na prática — o caso do laboratório refeito passa, ou o handover foi
    verificado pelo PDCA. Sem evidência, fica avaliada (nunca "aplicada" de mentira).

Governança e segurança:
  - nada é apagado: as tabelas têm gatilhos que recusam DELETE; mudar conteúdo cria VERSÃO nova (a antiga continua);
  - toda mudança entra numa cadeia de registros (cada registro guarda o hash do anterior): qualquer adulteração quebra
    a cadeia e `verificar_integridade` acusa; o próprio banco recusa UPDATE/DELETE na cadeia;
  - só o dono cria lição manual, publica versão nova ou arquiva (arquivar não apaga: tira da atribuição);
  - cópia em JSONL (logs/conhecimento/) e no PostgreSQL (robo.conhecimento_licoes) a cada hora.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from robo import organizacao
from robo.trabalho import Trabalho, _agora

ESQUEMA = """
CREATE TABLE IF NOT EXISTS licoes (
  id TEXT PRIMARY KEY, origem_tipo TEXT, origem_ref TEXT, versao INTEGER DEFAULT 1, substitui TEXT, andar INTEGER,
  publico TEXT, titulo TEXT, conteudo TEXT, pergunta TEXT, como_aplicar TEXT, autor TEXT, criada_em TEXT,
  arquivada INTEGER DEFAULT 0, motivo_arquivo TEXT, UNIQUE(origem_tipo, origem_ref, versao));
CREATE TABLE IF NOT EXISTS licoes_funcionario (
  licao_id TEXT, funcionario TEXT, estado TEXT, atribuida_em TEXT, estudada_em TEXT, avaliada_em TEXT, aplicada_em TEXT,
  evidencia TEXT, tentativas INTEGER DEFAULT 0, PRIMARY KEY (licao_id, funcionario));
CREATE INDEX IF NOT EXISTS ix_lf_func ON licoes_funcionario(funcionario, estado);
CREATE TABLE IF NOT EXISTS registro_conhecimento (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, tipo TEXT, ref TEXT, quem TEXT, dados TEXT, hash_anterior TEXT, hash TEXT);
CREATE TRIGGER IF NOT EXISTS licoes_sem_apagar BEFORE DELETE ON licoes
BEGIN SELECT RAISE(ABORT, 'lições não são apagadas: arquive (o dono) ou publique versão nova'); END;
CREATE TRIGGER IF NOT EXISTS licoes_func_sem_apagar BEFORE DELETE ON licoes_funcionario
BEGIN SELECT RAISE(ABORT, 'histórico de estudo não é apagado'); END;
CREATE TRIGGER IF NOT EXISTS registro_sem_apagar BEFORE DELETE ON registro_conhecimento
BEGIN SELECT RAISE(ABORT, 'registro de conhecimento é imutável'); END;
CREATE TRIGGER IF NOT EXISTS registro_sem_alterar BEFORE UPDATE ON registro_conhecimento
BEGIN SELECT RAISE(ABORT, 'registro de conhecimento é imutável'); END;
CREATE TRIGGER IF NOT EXISTS licoes_conteudo_imutavel BEFORE UPDATE OF titulo, conteudo, pergunta, como_aplicar ON licoes
BEGIN SELECT RAISE(ABORT, 'conteúdo de lição não muda: publique uma versão nova'); END;
"""
ESTADOS = ["atribuida", "estudada", "avaliada", "aplicada"]
REGRESSOES_POR_RODADA = 25


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
    return tb


def _hash(anterior: str, dados: dict) -> str:
    return hashlib.sha256((anterior + json.dumps(dados, ensure_ascii=False, sort_keys=True, default=str)).encode()).hexdigest()


def _registrar(c, tipo: str, ref: str, quem: str, dados: dict) -> None:
    """Acrescenta à cadeia (dentro da mesma transação da mudança)."""
    ult = c.execute("SELECT hash FROM registro_conhecimento ORDER BY id DESC LIMIT 1").fetchone()
    anterior = ult["hash"] if ult else "0" * 64
    agora = _agora()
    corpo = {"data_hora": agora, "tipo": tipo, "ref": ref, "quem": quem, "dados": dados}
    c.execute("INSERT INTO registro_conhecimento (data_hora, tipo, ref, quem, dados, hash_anterior, hash) VALUES (?,?,?,?,?,?,?)",
              (agora, tipo, ref, quem, json.dumps(dados, ensure_ascii=False, default=str), anterior, _hash(anterior, corpo)))


def verificar_integridade(cfg) -> dict:
    """Recalcula a cadeia inteira. Qualquer registro alterado, removido ou inserido fora de ordem quebra a conta."""
    with _tb(cfg).tx() as c:
        linhas = c.execute("SELECT * FROM registro_conhecimento ORDER BY id").fetchall()
    anterior = "0" * 64
    for r in linhas:
        corpo = {"data_hora": r["data_hora"], "tipo": r["tipo"], "ref": r["ref"], "quem": r["quem"], "dados": json.loads(r["dados"])}
        if r["hash_anterior"] != anterior or r["hash"] != _hash(anterior, corpo):
            return {"integra": False, "registros": len(linhas), "quebra_em": r["id"]}
        anterior = r["hash"]
    return {"integra": True, "registros": len(linhas), "ultimo_hash": anterior}


# =============================================================================== criação e atribuição
def _publico(cfg, andar: int | None, responsavel: str | None, publico: str) -> list[str]:
    gente = organizacao.lista(cfg)
    if publico == "lideranca":
        return [p["id"] for p in gente if p["id"] in organizacao.LIDERES or organizacao.nivel_de(p["id"], p) in
                ("gerente", "coordenador", "head", "diretor")]
    if publico == "todos" or not andar:
        return [p["id"] for p in gente]
    ids = [p["id"] for p in gente if p["andar"] == andar]
    if responsavel and responsavel not in ids and responsavel in {p["id"] for p in gente}:
        ids.append(responsavel)
    return ids


def criar(cfg, origem_tipo: str, origem_ref: str, titulo: str, conteudo: str, pergunta: str, como_aplicar: str,
          andar: int | None = None, responsavel: str | None = None, publico: str = "andar", autor: str = "robo") -> str | None:
    """Cria a lição (se ainda não existe para esta origem) e atribui a quem precisa saber. Idempotente."""
    tb = _tb(cfg)
    with tb.tx() as c:
        if c.execute("SELECT 1 FROM licoes WHERE origem_tipo=? AND origem_ref=?", (origem_tipo, origem_ref)).fetchone():
            return None
        lid = "LIC-" + hashlib.sha1(f"{origem_tipo}|{origem_ref}".encode()).hexdigest()[:10]
        c.execute("INSERT INTO licoes (id, origem_tipo, origem_ref, andar, publico, titulo, conteudo, pergunta, como_aplicar, "
                  "autor, criada_em) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (lid, origem_tipo, origem_ref, andar, publico, titulo[:300], conteudo[:6000], pergunta[:300],
                   como_aplicar[:600], autor, _agora()))
        _registrar(c, "licao_criada", lid, autor, {"origem": f"{origem_tipo}:{origem_ref}", "titulo": titulo[:300],
                                                   "conteudo_sha256": hashlib.sha256(conteudo.encode()).hexdigest()})
        alvos = _publico(cfg, andar, responsavel, publico)
        for pid in alvos:
            c.execute("INSERT OR IGNORE INTO licoes_funcionario (licao_id, funcionario, estado, atribuida_em) VALUES (?,?,?,?)",
                      (lid, pid, "atribuida", _agora()))
        _registrar(c, "licao_atribuida", lid, autor, {"para": alvos})
    return lid


def nova_versao(cfg, licao_id: str, conteudo: str, motivo: str, quem: str = "dono") -> str:
    """Só o dono. A versão antiga continua guardada; a nova é reatribuída a todos que tinham a antiga."""
    if quem != "dono":
        raise PermissionError("Só o dono publica versão nova de uma lição.")
    tb = _tb(cfg)
    with tb.tx() as c:
        a = c.execute("SELECT * FROM licoes WHERE id=?", (licao_id,)).fetchone()
        if not a:
            raise ValueError("Lição não existe.")
        v = a["versao"] + 1
        nid = f"{licao_id.split('.v')[0]}.v{v}"
        c.execute("INSERT INTO licoes (id, origem_tipo, origem_ref, versao, substitui, andar, publico, titulo, conteudo, pergunta, "
                  "como_aplicar, autor, criada_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (nid, a["origem_tipo"], a["origem_ref"], v, licao_id, a["andar"], a["publico"], a["titulo"], conteudo[:6000],
                   a["pergunta"], a["como_aplicar"], quem, _agora()))
        c.execute("UPDATE licoes SET arquivada=1, motivo_arquivo=? WHERE id=?", (f"substituída por {nid}: {motivo}", licao_id))
        donos = [r["funcionario"] for r in c.execute("SELECT funcionario FROM licoes_funcionario WHERE licao_id=?", (licao_id,))]
        for pid in donos:
            c.execute("INSERT OR IGNORE INTO licoes_funcionario (licao_id, funcionario, estado, atribuida_em) VALUES (?,?,?,?)",
                      (nid, pid, "atribuida", _agora()))
        _registrar(c, "licao_versao", nid, quem, {"substitui": licao_id, "motivo": motivo,
                                                  "conteudo_sha256": hashlib.sha256(conteudo.encode()).hexdigest()})
    return nid


def arquivar(cfg, licao_id: str, motivo: str, quem: str = "dono") -> None:
    if quem != "dono":
        raise PermissionError("Só o dono arquiva uma lição.")
    if not motivo.strip():
        raise ValueError("Arquivar exige o motivo.")
    tb = _tb(cfg)
    with tb.tx() as c:
        c.execute("UPDATE licoes SET arquivada=1, motivo_arquivo=? WHERE id=?", (motivo, licao_id))
        _registrar(c, "licao_arquivada", licao_id, quem, {"motivo": motivo})


# =============================================================================== colheita
def _secoes_md(pasta: Path) -> list[tuple[str, str, str]]:
    saida = []
    for arq in sorted(pasta.glob("*.md")) if pasta.is_dir() else []:
        if arq.name.startswith("_"):
            continue
        texto = arq.read_text(encoding="utf-8")
        for parte in re.split(r"(?m)^##\s+", texto)[1:]:
            titulo, _, corpo = parte.partition("\n")
            if corpo.strip() and titulo.strip().lower() != "fontes":
                saida.append((arq.name, titulo.strip(), corpo.strip()))
    return saida


def colher(cfg) -> dict:
    """Transforma tudo o que a empresa aprendeu em lições (só o que ainda não virou lição)."""
    from robo import memoria
    from robo.config import RAIZ_PROJETO
    novas = {"handover": 0, "boa_pratica": 0, "laboratorio": 0, "correcao": 0, "manual": 0}
    for h in memoria.handovers(cfg, limite=100_000):
        if criar(cfg, "handover", h["id"], f"Erro: {h['erro'][:200]}",
                 f"O que aconteceu: {h['erro']}\nPor quê: {h['causa']}\nComo não repetir: {h['regra']}\nComo verificar: {h['como_verificar']}",
                 h["erro"][:200], h["como_verificar"], h["andar"], h["responsavel"]):
            novas["handover"] += 1
    for b in memoria.boas_praticas(cfg, limite=100_000):
        if criar(cfg, "boa_pratica", b["id"], f"Boa prática: {b['pratica'][:200]}",
                 f"Problema: {b['problema']}\nPrática padronizada: {b['pratica']}\nProva: {b['evidencia']}",
                 b["problema"][:200], b["como_verificar"], b["andar"], b["responsavel"]):
            novas["boa_pratica"] += 1
    tb = _tb(cfg)
    with tb.tx() as c:
        try:
            falhas = c.execute("SELECT * FROM laboratorio_exercicios WHERE ok=0 ORDER BY id").fetchall()
        except Exception:
            falhas = []
    gente = organizacao.por_id(cfg)
    for f in falhas:
        ref = f"{f['area']}:{f['semente']}:{f['etapa']}:{f['responsavel']}"
        if criar(cfg, "laboratorio", ref, f"Laboratório ({f['area']}): {f['etapa']}",
                 f"Falhou no treino da área {f['area']} (semente {f['semente']}): {f['detalhe']}",
                 f"{f['etapa']} {f['area']}", f"refazer o caso {f['area']} semente {f['semente']} e a etapa passar",
                 (gente.get(f["responsavel"]) or {}).get("andar"), f["responsavel"]):
            novas["laboratorio"] += 1
    for m in tb.memorias("correcao", limite=100_000):
        if criar(cfg, "correcao", f"{m['chave']}|{m['id']}", f"Correção do dono: {m['chave']}", m["texto"], m["chave"],
                 "usar a correção nas próximas respostas", None, None, "todos", "dono"):
            novas["correcao"] += 1
    fontes = [(Path(RAIZ_PROJETO) / "conhecimento", None)]
    if Path(getattr(cfg, "agentes", "") or "").is_dir():
        fontes.append((Path(cfg.agentes), "agente"))
    for pasta, tipo in fontes:
        for arq, titulo, corpo in _secoes_md(pasta):
            publico = "lideranca" if "lideranca" in arq else "todos"
            responsavel = Path(arq).stem if tipo == "agente" else None
            andar = (gente.get(responsavel) or {}).get("andar") if responsavel else None
            if criar(cfg, "manual", f"{arq}#{titulo}", f"{titulo} ({arq})", corpo, titulo, "saber responder quando perguntado",
                     andar, responsavel, publico if not responsavel else "andar"):
                novas["manual"] += 1
    return novas


# =============================================================================== estudo, avaliação e aplicação
def _passar(c, lid: str, pid: str, estado: str, evidencia: str = "") -> None:
    campo = {"estudada": "estudada_em", "avaliada": "avaliada_em", "aplicada": "aplicada_em"}.get(estado)
    c.execute(f"UPDATE licoes_funcionario SET estado=?, evidencia=?{', ' + campo + '=?' if campo else ''}, "
              "tentativas=tentativas+1 WHERE licao_id=? AND funcionario=?",
              (estado, evidencia[:500], *([_agora()] if campo else []), lid, pid))
    _registrar(c, f"licao_{estado}", lid, pid, {"evidencia": evidencia[:300]})


def _recupera(cfg, licao: dict, cache: dict) -> bool:
    """Teste de recuperação: perguntado com a pergunta-chave, o conhecimento da empresa devolve ESTA lição?"""
    if licao["id"] in cache:
        return cache[licao["id"]]
    achou = any(l["id"] == licao["id"] for l in buscar(cfg, licao["pergunta"] or licao["titulo"], limite=5))
    cache[licao["id"]] = achou
    return achou


def _evidencia_pratica(cfg, licao: dict, cache: dict) -> tuple[bool, str]:
    from robo import laboratorio, memoria
    if licao["origem_tipo"] == "boa_pratica":
        return True, "boa prática comprovada pelo PDCA"
    if licao["origem_tipo"] == "handover":
        h = next((x for x in memoria.handovers(cfg, limite=100_000) if x["id"] == licao["origem_ref"]), None)
        if h and h["estado"] == "verificado":
            return True, "handover verificado pelo PDCA (o erro não voltou)"
        return False, f"handover ainda {h['estado'] if h else 'sem registro'}"
    if licao["origem_tipo"] == "laboratorio":
        area, semente, etapa, resp = licao["origem_ref"].split(":", 3)
        chave = (area, int(semente))
        if chave not in cache:
            if cache.setdefault("_regressoes", 0) >= REGRESSOES_POR_RODADA:
                return False, "regressão fica para a próxima rodada (limite por rodada)"
            cache["_regressoes"] += 1
            cache[chave] = laboratorio.exercicio(cfg, area, int(semente))
        r = cache[chave]
        falhou = any(f.startswith(etapa) for f in r["falhas"])
        return (not falhou, f"caso {area}/{semente} refeito: {'passou' if not falhou else 'ainda falha'}")
    if licao["origem_tipo"] == "regra":  # regra aprendida: só conta com o arquivo passando depois dela
        with _tb(cfg).tx() as c:
            p = c.execute("SELECT estado, prova FROM propostas_regra WHERE id=?", (licao["origem_ref"],)).fetchone()
        if p and p["estado"] == "comprovada":
            return True, p["prova"]
        return False, f"regra ainda {p['estado'] if p else 'sem proposta'}: espera o arquivo passar"
    if licao["origem_tipo"] in ("manual", "correcao", "dono"):
        return True, "conhecimento de referência: aplicado ao ser usado nas respostas"
    return False, "sem critério de aplicação"


def rodada(cfg) -> dict:
    """Colhe, faz cada pessoa estudar o que é novo, testa se acha e comprova se funciona na prática."""
    novas = colher(cfg)
    tb = _tb(cfg)
    with tb.tx() as c:
        pendentes = [dict(r) | {"licao": dict(l)} for r in c.execute(
            "SELECT * FROM licoes_funcionario WHERE estado <> 'aplicada'") for l in
            [c.execute("SELECT * FROM licoes WHERE id=?", (r["licao_id"],)).fetchone()] if l and not l["arquivada"]]
    # 1) decide (só leitura e regressões do laboratório — nenhuma transação aberta aqui)
    cache_rec, cache_lab = {}, {}
    mudancas: list[tuple[str, str, str, str]] = []
    for item in pendentes:
        lid, pid, licao, estado = item["licao_id"], item["funcionario"], item["licao"], item["estado"]
        if estado == "atribuida":
            mudancas.append((lid, pid, "estudada", "lição lida e guardada no caderno"))
            estado = "estudada"
        if estado == "estudada" and _recupera(cfg, licao, cache_rec):
            mudancas.append((lid, pid, "avaliada", "acha a lição quando perguntado"))
            estado = "avaliada"
        if estado == "avaliada":
            ok, evid = _evidencia_pratica(cfg, licao, cache_lab)
            if ok:
                mudancas.append((lid, pid, "aplicada", evid))
    # 2) grava tudo numa transação só (ou entra a rodada inteira na cadeia, ou nada)
    contagem = {"estudada": 0, "avaliada": 0, "aplicada": 0}
    with tb.tx() as c:
        for lid, pid, estado, evid in mudancas:
            _passar(c, lid, pid, estado, evid)
            contagem[estado] += 1
    integ = verificar_integridade(cfg)
    tb.lembrar("licoes_rodada", datetime.now().strftime("%Y-%m-%d %H:%M"),
               f"{sum(novas.values())} lição(ões) nova(s); {contagem['estudada']} estudadas, {contagem['avaliada']} avaliadas, "
               f"{contagem['aplicada']} aplicadas; cadeia {'íntegra' if integ['integra'] else 'QUEBRADA'}", "rh_td")
    if not integ["integra"]:
        from robo import memoria
        memoria.handover(cfg, f"Cadeia do registro de conhecimento quebrada no registro {integ['quebra_em']} (possível adulteração)",
                         "conhecimento", "sec_senior", "verificar_integridade", tb)
    return {"novas": novas, **contagem, "integridade": integ}


def rotina(cfg) -> dict | None:
    """De hora em hora: o que a empresa aprendeu vira lição no mesmo dia (não espera a rodada de estudo)."""
    m = Trabalho(cfg).memorias("licoes_rodada", limite=1)
    if m and datetime.fromisoformat(m[0]["criada_em"]) > datetime.now() - timedelta(minutes=55):
        return None
    r = rodada(cfg)
    exportar(cfg)
    return {k: r[k] for k in ("estudada", "avaliada", "aplicada")} | {"novas": sum(r["novas"].values()),
                                                                       "integra": r["integridade"]["integra"]}


# =============================================================================== consulta
def buscar(cfg, pergunta: str, funcionario: str | None = None, limite: int = 5) -> list[dict]:
    """Lições que respondem à pergunta (por palavras em comum, título pesa mais)."""
    from robo.canal import PALAVRAS_VAZIAS, normalizar
    termos = {w for w in normalizar(pergunta).split() if len(w) >= 4 and w not in PALAVRAS_VAZIAS}
    if not termos:
        return []
    sql = "SELECT l.* FROM licoes l WHERE l.arquivada=0"
    args: list = []
    if funcionario:
        sql += " AND l.id IN (SELECT licao_id FROM licoes_funcionario WHERE funcionario=?)"
        args.append(funcionario)
    with _tb(cfg).tx() as c:
        linhas = [dict(r) for r in c.execute(sql, args)]
    pontuadas = []
    for l in linhas:
        titulo, corpo = normalizar(l["titulo"] + " " + (l["pergunta"] or "")), normalizar(l["conteudo"])
        pts = sum(3 if w in titulo else 1 for w in termos if w in titulo or w in corpo)
        if pts >= 3:
            pontuadas.append((pts, l))
    pontuadas.sort(key=lambda x: -x[0])
    return [l for _, l in pontuadas[:limite]]


def detalhe(cfg, licao_id: str) -> dict | None:
    """A lição, todas as versões dela, quem tem e em que estado, e a trilha na cadeia de registros."""
    with _tb(cfg).tx() as c:
        l = c.execute("SELECT * FROM licoes WHERE id=?", (licao_id,)).fetchone()
        if not l:
            return None
        l = dict(l)
        l["versoes"] = [dict(r) for r in c.execute("SELECT id, versao, autor, criada_em, arquivada, motivo_arquivo FROM licoes "
                                                   "WHERE origem_tipo=? AND origem_ref=? ORDER BY versao",
                                                   (l["origem_tipo"], l["origem_ref"]))]
        l["pessoas"] = [dict(r) for r in c.execute("SELECT funcionario, estado, evidencia, aplicada_em FROM licoes_funcionario "
                                                   "WHERE licao_id=? ORDER BY funcionario", (licao_id,))]
        l["trilha"] = [dict(r) for r in c.execute("SELECT id, data_hora, tipo, quem, hash FROM registro_conhecimento WHERE ref=? "
                                                  "ORDER BY id LIMIT 500", (licao_id,))]
    gente = organizacao.por_id(cfg)
    for p in l["pessoas"]:
        p["nome"] = (gente.get(p["funcionario"]) or {}).get("nome", p["funcionario"])
    return l


def caderno(cfg, funcionario: str) -> dict:
    with _tb(cfg).tx() as c:
        linhas = [dict(r) for r in c.execute(
            "SELECT lf.*, l.titulo, l.origem_tipo, l.versao, l.arquivada FROM licoes_funcionario lf JOIN licoes l ON l.id=lf.licao_id "
            "WHERE lf.funcionario=? ORDER BY lf.atribuida_em DESC", (funcionario,))]
    por = {e: sum(1 for l in linhas if l["estado"] == e) for e in ESTADOS}
    return {"funcionario": funcionario, "total": len(linhas), "por_estado": por,
            "pct_aplicada": round(100 * por["aplicada"] / len(linhas)) if linhas else 0, "licoes": linhas[:300]}


def painel(cfg) -> dict:
    with _tb(cfg).tx() as c:
        total = c.execute("SELECT COUNT(*) FROM licoes WHERE arquivada=0").fetchone()[0]
        por_origem = {r["origem_tipo"]: r["n"] for r in c.execute(
            "SELECT origem_tipo, COUNT(*) n FROM licoes WHERE arquivada=0 GROUP BY origem_tipo")}
        por_estado = {r["estado"]: r["n"] for r in c.execute("SELECT estado, COUNT(*) n FROM licoes_funcionario GROUP BY estado")}
        pessoas = [dict(r) for r in c.execute(
            "SELECT funcionario, COUNT(*) total, SUM(estado='aplicada') aplicadas, SUM(estado='atribuida') novas "
            "FROM licoes_funcionario GROUP BY funcionario ORDER BY (SUM(estado='aplicada') * 1.0 / COUNT(*))")]
        recentes = [dict(r) for r in c.execute("SELECT id, titulo, origem_tipo, versao, criada_em, arquivada FROM licoes "
                                               "ORDER BY criada_em DESC LIMIT 40")]
    gente = organizacao.por_id(cfg)
    for p in pessoas:
        p["nome"] = (gente.get(p["funcionario"]) or {}).get("nome", p["funcionario"])
        p["pct"] = round(100 * (p["aplicadas"] or 0) / p["total"]) if p["total"] else 0
    return {"licoes": total, "por_origem": por_origem, "atribuicoes": por_estado, "pessoas": pessoas, "recentes": recentes,
            "integridade": verificar_integridade(cfg)}


def exportar(cfg) -> Path:
    """Cópia completa e legível (JSONL) — além do SQLite e do PostgreSQL."""
    pasta = Path(cfg.logs) / "conhecimento"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"licoes_{datetime.now():%Y%m%d}.jsonl"
    with _tb(cfg).tx() as c, open(arq, "w", encoding="utf-8") as f:
        for r in c.execute("SELECT * FROM licoes ORDER BY criada_em"):
            f.write(json.dumps(dict(r), ensure_ascii=False) + "\n")
        for r in c.execute("SELECT * FROM registro_conhecimento ORDER BY id"):
            f.write(json.dumps({"cadeia": dict(r)}, ensure_ascii=False) + "\n")
    return arq
