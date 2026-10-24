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
  - cópia em JSONL (logs/conhecimento/) e no PostgreSQL (robo.memoria_licoes, robo.memoria_licoes_funcionario,
    robo.memoria_registro_conhecimento) a cada hora; uma âncora fora do banco (logs/conhecimento/ancora.jsonl) denuncia
    se alguém apagar os últimos registros da cadeia.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
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
CREATE TABLE IF NOT EXISTS licoes_uso (
  id INTEGER PRIMARY KEY AUTOINCREMENT, licao_id TEXT, funcionario TEXT, data_hora TEXT, contexto TEXT);
CREATE INDEX IF NOT EXISTS ix_licoes_uso ON licoes_uso(licao_id, funcionario);
CREATE TRIGGER IF NOT EXISTS licoes_uso_sem_apagar BEFORE DELETE ON licoes_uso
BEGIN SELECT RAISE(ABORT, 'uso de lição é registro permanente'); END;
"""
ESTADOS = ["atribuida", "estudada", "avaliada", "aplicada"]
REGRESSOES_POR_RODADA = 25


_prontos: set[str] = set()


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    if str(tb.arquivo) not in _prontos or not tb.arquivo.exists():
        with tb.tx() as c:
            c.executescript(ESQUEMA)
            from robo.trabalho import proteger
            proteger(c)
        _prontos.add(str(tb.arquivo))
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
    """Três conferências:
    1. a cadeia: cada registro guarda o hash do anterior — alterar, remover ou inserir fora de ordem quebra a conta;
    2. a âncora fora do banco (logs/conhecimento/ancora.jsonl): se a cadeia ficou MENOR ou o hash de um ponto ancorado
       mudou, alguém apagou ou trocou o fim da cadeia (o que a conferência 1 sozinha não vê);
    3. as tabelas batem com a cadeia: o estado de cada lição de cada pessoa é o do último evento registrado."""
    with _tb(cfg).tx() as c:
        linhas = c.execute("SELECT * FROM registro_conhecimento ORDER BY id").fetchall()
        estados = {(r["licao_id"], r["funcionario"]): r["estado"] for r in c.execute(
            "SELECT licao_id, funcionario, estado FROM licoes_funcionario")}
    anterior = "0" * 64
    por_id = {}
    esperado: dict[tuple, str] = {}
    for r in linhas:
        dados = json.loads(r["dados"])
        corpo = {"data_hora": r["data_hora"], "tipo": r["tipo"], "ref": r["ref"], "quem": r["quem"], "dados": dados}
        if r["hash_anterior"] != anterior or r["hash"] != _hash(anterior, corpo):
            return {"integra": False, "registros": len(linhas), "quebra_em": r["id"],
                    "motivo": f"registro {r['id']} alterado ou fora de ordem"}
        anterior = r["hash"]
        por_id[r["id"]] = r["hash"]
        if r["tipo"] == "licao_atribuida":
            for pid in dados.get("para") or []:
                esperado.setdefault((r["ref"], pid), "atribuida")
        elif r["tipo"] in ("licao_estudada", "licao_avaliada", "licao_aplicada"):
            esperado[(r["ref"], r["quem"])] = r["tipo"].removeprefix("licao_")
        elif r["tipo"] == "licao_regrediu":
            esperado[(r["ref"], r["quem"])] = "avaliada"
    for ancora in _ancoras(cfg):
        if ancora["registros"] > len(linhas) or por_id.get(ancora["ultimo_id"]) != ancora["ultimo_hash"]:
            return {"integra": False, "registros": len(linhas), "quebra_em": ancora["ultimo_id"],
                    "motivo": f"a âncora de {ancora['data_hora'][:16]} registrou {ancora['registros']} registros e hash "
                              f"{ancora['ultimo_hash'][:12]}…; a cadeia atual não confere (fim apagado ou trocado)"}
    divergentes = [k for k, v in estados.items() if esperado.get(k, v) != v or k not in esperado]
    if divergentes:
        lid, pid = divergentes[0]
        return {"integra": False, "registros": len(linhas), "quebra_em": None, "divergencias": len(divergentes),
                "motivo": f"{len(divergentes)} estado(s) de lição sem registro na cadeia (ex.: {lid} de {pid} está "
                          f"'{estados[divergentes[0]]}', a cadeia diz '{esperado.get(divergentes[0], 'nada')}')"}
    return {"integra": True, "registros": len(linhas), "ultimo_hash": anterior,
            "ultimo_id": linhas[-1]["id"] if linhas else 0}


def _ancoras(cfg) -> list[dict]:
    arq = Path(cfg.logs) / "conhecimento" / "ancora.jsonl"
    if not arq.exists():
        return []
    saida = []
    for linha in arq.read_text(encoding="utf-8").splitlines()[-50:]:
        try:
            saida.append(json.loads(linha))
        except ValueError:
            continue
    return saida


def ancorar(cfg) -> dict | None:
    """Grava fora do banco o ponto atual da cadeia (número de registros e hash do último)."""
    v = verificar_integridade(cfg)
    if not v["integra"] or not v["registros"]:
        return None
    pasta = Path(cfg.logs) / "conhecimento"
    pasta.mkdir(parents=True, exist_ok=True)
    ancora = {"data_hora": _agora(), "registros": v["registros"], "ultimo_id": v["ultimo_id"], "ultimo_hash": v["ultimo_hash"]}
    with open(pasta / "ancora.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ancora) + "\n")
    return ancora


# =============================================================================== criação e atribuição
def _publico(cfg, andar: int | None, responsavel: str | None, publico: str, gente: list | None = None) -> list[str]:
    gente = gente if gente is not None else organizacao.lista(cfg)
    if publico == "lideranca":
        return [p["id"] for p in gente if p["id"] in organizacao.LIDERES or organizacao.nivel_de(p["id"], p) in
                ("gerente", "coordenador", "head", "diretor")]
    if publico == "pessoa":  # lição de um erro de uma pessoa (treino): vai só para ela
        return [responsavel] if responsavel else []
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


def atribuir(cfg, origem_tipo: str, origem_ref: str, pid: str, autor: str = "robo") -> bool:
    """Atribui uma lição que já existe a mais uma pessoa (ex.: outra pessoa errou a mesma coisa no treino)."""
    tb = _tb(cfg)
    with tb.tx() as c:
        l = c.execute("SELECT id FROM licoes WHERE origem_tipo=? AND origem_ref=? AND arquivada=0 ORDER BY versao DESC LIMIT 1",
                      (origem_tipo, origem_ref)).fetchone()
        if not l or c.execute("SELECT 1 FROM licoes_funcionario WHERE licao_id=? AND funcionario=?", (l["id"], pid)).fetchone():
            return False
        c.execute("INSERT INTO licoes_funcionario (licao_id, funcionario, estado, atribuida_em) VALUES (?,?,?,?)",
                  (l["id"], pid, "atribuida", _agora()))
        _registrar(c, "licao_atribuida", l["id"], autor, {"para": [pid]})
    return True


def nova_versao(cfg, licao_id: str, conteudo: str, motivo: str, quem: str = "dono", _origem: str = "") -> str:
    """Só o dono (ou a edição que o próprio dono fez no arquivo .md). A versão antiga continua guardada; a nova é
    reatribuída a todos que tinham a antiga."""
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
        _registrar(c, "licao_versao", nid, quem, {"substitui": licao_id, "motivo": motivo, "origem": _origem or "painel",
                                                  "conteudo_sha256": hashlib.sha256(conteudo.encode()).hexdigest()})
        _registrar(c, "licao_atribuida", nid, quem, {"para": donos})
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


def _etapa_base(etapa: str) -> str:
    """'Revisão da biblioteca numpy 2.5.3' → 'Revisão da biblioteca numpy' (a versão muda; o assunto não)."""
    return re.sub(r"\s+\d+(\.\d+)+\S*$", "", etapa.strip())


def colher(cfg) -> dict:
    """Transforma tudo o que a empresa aprendeu em lições (só o que ainda não virou lição)."""
    from robo.config import RAIZ_PROJETO
    novas = {"handover": 0, "boa_pratica": 0, "laboratorio": 0, "correcao": 0, "manual": 0, "versoes": 0}
    tb = _tb(cfg)
    with tb.tx() as c:  # leitura direta (memoria.handovers() reclassifica e explica: caro e desnecessário aqui)
        hs = [dict(r) for r in c.execute("SELECT * FROM handovers ORDER BY criado_em")]
        bps = [dict(r) for r in c.execute("SELECT * FROM boas_praticas ORDER BY criada_em")]
        try:
            falhas = [dict(r) for r in c.execute(
                "SELECT area, etapa, responsavel, MAX(id) id, MAX(semente) semente, MAX(detalhe) detalhe "
                "FROM laboratorio_exercicios WHERE ok=0 GROUP BY area, etapa, responsavel")]
        except Exception:
            falhas = []
    for h in hs:
        if criar(cfg, "handover", h["id"], f"Erro: {h['erro'][:200]}",
                 f"O que aconteceu: {h['erro']}\nPor quê: {h['causa']}\nComo não repetir: {h['regra']}\nComo verificar: {h['como_verificar']}",
                 h["erro"][:200], h["como_verificar"], h["andar"], h["responsavel"]):
            novas["handover"] += 1
    for b in bps:
        if criar(cfg, "boa_pratica", b["id"], f"Boa prática: {b['pratica'][:200]}",
                 f"Problema: {b['problema']}\nPrática padronizada: {b['pratica']}\nProva: {b['evidencia']}",
                 b["problema"][:200], b["como_verificar"], b["andar"], b["responsavel"]):
            novas["boa_pratica"] += 1
    gente = organizacao.por_id(cfg)
    vistas = set()
    for f in falhas:  # uma lição por (área, etapa, responsável) — não uma por semente (antes: ~144 lições/dia)
        etapa = _etapa_base(f["etapa"])
        ref = f"{f['area']}:{etapa}:{f['responsavel']}"
        if ref in vistas:
            continue
        vistas.add(ref)
        if criar(cfg, "laboratorio", ref, f"Laboratório ({f['area']}): {etapa}",
                 f"Falhou no treino da área {f['area']} (última semente {f['semente']}): {f['detalhe']}",
                 f"{etapa} {f['area']}", f"refazer o último caso que falhou ({f['area']}) e a etapa passar",
                 (gente.get(f["responsavel"]) or {}).get("andar"), f["responsavel"]):
            novas["laboratorio"] += 1
    try:  # erros REAIS da esteira (memória de acertos e erros): uma lição por (competência, causa)
        with tb.tx() as c:
            esteira = [dict(r) for r in c.execute(
                "SELECT competencia, causa, MAX(correcao) correcao, MAX(funcionario) funcionario, COUNT(*) n FROM aprendizados "
                "WHERE resultado='erro' AND origem='pipeline' AND causa <> '' GROUP BY competencia, causa")]
    except Exception:
        esteira = []
    for e in esteira:
        ref = f"{e['competencia']}:{e['causa'][:120]}"
        if criar(cfg, "esteira", ref, f"Esteira barrou: {e['causa'][:160]}",
                 f"O que barrou ({e['n']} vez(es)): {e['causa']}\nComo corrigir: {e['correcao'] or 'ver o relatório do arquivo'}",
                 e["causa"][:200], "o mesmo motivo não barrar de novo (replay da memória)",
                 (gente.get(e["funcionario"]) or {}).get("andar"), e["funcionario"]):
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
            ref = f"{arq}#{titulo}"
            if criar(cfg, "manual", ref, f"{titulo} ({arq})", corpo, titulo, "usar a lição numa resposta",
                     andar, responsavel, publico if not responsavel else "andar"):
                novas["manual"] += 1
            elif _versao_do_manual(cfg, ref, corpo):  # o dono editou o .md: a lição ganha versão nova (a antiga fica)
                novas["versoes"] += 1
    return novas


def _versao_do_manual(cfg, ref: str, corpo: str) -> bool:
    with _tb(cfg).tx() as c:
        atual = c.execute("SELECT id, conteudo FROM licoes WHERE origem_tipo='manual' AND origem_ref=? AND arquivada=0 "
                          "ORDER BY versao DESC LIMIT 1", (ref,)).fetchone()
    if not atual or atual["conteudo"] == corpo[:6000]:
        return False
    nova_versao(cfg, atual["id"], corpo, "o arquivo .md foi editado", quem="dono", _origem="arquivo .md editado pelo dono")
    return True


# =============================================================================== estudo, avaliação e aplicação
def _passar(c, lid: str, pid: str, de: str, estado: str, evidencia: str = "") -> bool:
    """Muda o estado só se ele ainda for o esperado (duas rodadas ao mesmo tempo não aplicam nada em dobro)."""
    campo = {"estudada": "estudada_em", "avaliada": "avaliada_em", "aplicada": "aplicada_em"}.get(estado)
    cur = c.execute(f"UPDATE licoes_funcionario SET estado=?, evidencia=?{', ' + campo + '=?' if campo else ''}, "
                    "tentativas=tentativas+1 WHERE licao_id=? AND funcionario=? AND estado=?",
                    (estado, evidencia[:500], *([_agora()] if campo else []), lid, pid, de))
    if not cur.rowcount:
        return False
    _registrar(c, f"licao_{estado}", lid, pid, {"evidencia": evidencia[:300]})
    return True


def _recupera(cfg, licao: dict, cache: dict) -> bool:
    """Teste de recuperação: perguntado com a pergunta-chave (ou o título), o conhecimento da empresa devolve ESTA
    lição entre os resultados? (Lições de texto parecido não se escondem umas às outras: olhamos 50 resultados.)"""
    if licao["id"] in cache:
        return cache[licao["id"]]
    achou = any(any(l["id"] == licao["id"] for l in buscar(cfg, q, limite=50))
                for q in (licao["pergunta"], licao["titulo"], licao["conteudo"][:300]) if q)
    cache[licao["id"]] = achou
    return achou


def registrar_uso(cfg, licao_id: str, funcionario: str | None, contexto: str = "") -> None:
    """A lição foi usada de verdade numa resposta (é a prova de 'aplicada' para manuais e correções)."""
    if not funcionario:
        return
    with _tb(cfg).tx() as c:
        c.execute("INSERT INTO licoes_uso (licao_id, funcionario, data_hora, contexto) VALUES (?,?,?,?)",
                  (licao_id, funcionario, _agora(), contexto[:300]))


def registrar_uso_por_origem(cfg, origem_tipo: str, origem_ref: str, funcionario: str | None, contexto: str = "") -> None:
    if not funcionario:
        return
    with _tb(cfg).tx() as c:
        l = c.execute("SELECT id FROM licoes WHERE origem_tipo=? AND origem_ref=? AND arquivada=0 ORDER BY versao DESC LIMIT 1",
                      (origem_tipo, origem_ref)).fetchone()
    if l:
        registrar_uso(cfg, l["id"], funcionario, contexto)


def _evidencia_pratica(cfg, licao: dict, pid: str, ctx: dict) -> tuple[bool, str]:
    from robo import laboratorio
    tipo, ref = licao["origem_tipo"], licao["origem_ref"]
    if tipo == "boa_pratica":
        bp = ctx["boas"].get(ref)
        if bp and bp.get("valida", 1):
            return True, f"boa prática comprovada pelo PDCA: {bp['evidencia']}"
        return False, "boa prática invalidada (o erro voltou)" if bp else "boa prática sem registro"
    if tipo == "handover":
        estado = ctx["handovers"].get(ref)
        if estado == "verificado":
            return True, "handover verificado pelo PDCA (com prova de que o erro não voltou)"
        return False, f"handover ainda {estado or 'sem registro'}"
    if tipo == "laboratorio":
        partes = ref.split(":")
        # o nome da etapa pode ter ':' ("Limpar: tirar Total…"): área é a 1ª parte e responsável a última
        if len(partes) >= 4 and partes[1].isdigit():  # formato antigo: area:semente:etapa:responsavel
            area, semente, etapa, resp = partes[0], int(partes[1]), _etapa_base(":".join(partes[2:-1])), partes[-1]
            nivel = 1
        else:
            area, etapa, resp = partes[0], ":".join(partes[1:-1]), partes[-1]
            with _tb(cfg).tx() as c:
                ult = c.execute("SELECT semente, COALESCE(nivel, 1) nivel FROM laboratorio_exercicios WHERE ok=0 AND area=? "
                                "AND responsavel=? AND etapa LIKE ? ORDER BY id DESC LIMIT 1", (area, resp, etapa + "%")).fetchone()
            if not ult:
                return False, "caso que falhou não encontrado"
            semente, nivel = int(ult["semente"]), int(ult["nivel"])
        lib = etapa.removeprefix("Revisão da biblioteca ").strip() if etapa.startswith("Revisão da biblioteca") else None
        chave = (area, semente, lib, nivel)
        if chave not in ctx["lab"]:
            if ctx["regressoes"] >= REGRESSOES_POR_RODADA:
                return False, "reconferência fica para a próxima rodada (limite por rodada)"
            ctx["regressoes"] += 1
            ctx["lab"][chave] = laboratorio.exercicio(cfg, area, semente, gravar=False, biblioteca=lib, nivel=nivel)
        r = ctx["lab"][chave]
        falhou = any(_etapa_base(x["etapa"]) == etapa and not x["ok"] for x in r.get("resultados", []))
        return (not falhou, f"caso {area}/{semente} nível {nivel} refeito ({_agora()[:16]}): "
                            f"{'passou' if not falhou else 'ainda falha'}")
    if tipo == "treino":  # erro no treino: só conta quando a pessoa acerta a mesma competência no mesmo nível ou acima
        comp, nivel = ref.split(":")[0], int(ref.split(":")[1])
        with _tb(cfg).tx() as c:
            desde = c.execute("SELECT atribuida_em FROM licoes_funcionario WHERE licao_id=? AND funcionario=?",
                              (licao["id"], pid)).fetchone()
            t = c.execute("SELECT id, caso_id, nivel FROM treino_tentativas WHERE funcionario=? AND competencia=? AND nivel>=? "
                          "AND acertou=1 AND data_hora>=? ORDER BY id LIMIT 1",
                          (pid, comp, nivel, desde["atribuida_em"] if desde else "")).fetchone() \
                if c.execute("SELECT 1 FROM sqlite_master WHERE name='treino_tentativas'").fetchone() else None
        if t:
            return True, f"acertou {comp} no nível {t['nivel']} depois da lição (tentativa T{t['id']}, caso {t['caso_id']})"
        return False, f"ainda não acertou {comp} no nível {nivel} depois da lição"
    if tipo == "regra":  # regra aprendida: só conta com o arquivo passando depois dela
        with _tb(cfg).tx() as c:
            p = c.execute("SELECT estado, prova FROM propostas_regra WHERE id=?", (ref,)).fetchone()
        if p and p["estado"] == "comprovada":
            return True, p["prova"]
        return False, f"regra ainda {p['estado'] if p else 'sem proposta'}: espera o arquivo passar"
    if tipo in ("manual", "correcao", "dono"):  # conhecimento de referência: aplicada = a PESSOA usou numa resposta
        uso = ctx["usos"].get((licao["id"], pid))
        if uso:
            return True, f"usada numa resposta em {uso[:16]}"
        return False, "ainda não foi usada numa resposta"
    return False, "sem critério de aplicação"


_rodando: set[str] = set()
_trava_rodadas = threading.Lock()


def _atribuir_faltantes(cfg, c) -> int:
    """Quem entrou depois (contratado) também recebe as lições que já existiam."""
    novos = 0
    gente = organizacao.lista(cfg)
    ids_validos = {p["id"] for p in gente}
    licoes_ativas = [dict(r) for r in c.execute("SELECT id, andar, publico FROM licoes WHERE arquivada=0")]
    ja = {}
    for r in c.execute("SELECT licao_id, funcionario FROM licoes_funcionario"):
        ja.setdefault(r["licao_id"], set()).add(r["funcionario"])
    for l in licoes_ativas:
        responsavel = None
        alvos = set(_publico(cfg, l["andar"], responsavel, l["publico"] or "andar", gente)) & ids_validos
        faltam = sorted(alvos - ja.get(l["id"], set()))
        if not faltam:
            continue
        for pid in faltam:
            c.execute("INSERT OR IGNORE INTO licoes_funcionario (licao_id, funcionario, estado, atribuida_em) VALUES (?,?,?,?)",
                      (l["id"], pid, "atribuida", _agora()))
        _registrar(c, "licao_atribuida", l["id"], "robo", {"para": faltam, "motivo": "funcionário novo"})
        novos += len(faltam)
    return novos


def rodada(cfg) -> dict:
    """Colhe, faz cada pessoa estudar o que é novo, testa se acha e comprova se funciona na prática."""
    tb = _tb(cfg)
    chave = str(tb.arquivo)
    with _trava_rodadas:
        if chave in _rodando:
            return {"em_andamento": True, "novas": {}, "estudada": 0, "avaliada": 0, "aplicada": 0,
                    "integridade": verificar_integridade(cfg)}
        _rodando.add(chave)
    try:
        return _rodada(cfg, tb)
    finally:
        with _trava_rodadas:
            _rodando.discard(chave)


def _rodada(cfg, tb) -> dict:
    novas = colher(cfg)
    with tb.tx() as c:
        novas["atribuicoes_novas"] = _atribuir_faltantes(cfg, c)
        pendentes = [dict(r) | {"licao": dict(l)} for r in c.execute(
            "SELECT * FROM licoes_funcionario WHERE estado <> 'aplicada'") for l in
            [c.execute("SELECT * FROM licoes WHERE id=?", (r["licao_id"],)).fetchone()] if l and not l["arquivada"]]
        ctx = {"handovers": {r["id"]: r["estado"] for r in c.execute("SELECT id, estado FROM handovers")},
               "boas": {r["id"]: dict(r) for r in c.execute("SELECT * FROM boas_praticas")},
               "usos": {(r["licao_id"], r["funcionario"]): r["ult"] for r in c.execute(
                   "SELECT licao_id, funcionario, MAX(data_hora) ult FROM licoes_uso GROUP BY licao_id, funcionario")},
               "lab": {}, "regressoes": 0}
    # 1) decide (só leitura; reconferências do laboratório sem efeito colateral — nenhuma transação aberta aqui)
    cache_rec = {}
    mudancas: list[tuple[str, str, str, str, str]] = []
    for item in pendentes:
        lid, pid, licao, estado = item["licao_id"], item["funcionario"], item["licao"], item["estado"]
        if estado == "atribuida":
            mudancas.append((lid, pid, "atribuida", "estudada", "lição lida e guardada no caderno"))
            estado = "estudada"
        if estado == "estudada" and _recupera(cfg, licao, cache_rec):
            mudancas.append((lid, pid, "estudada", "avaliada", "acha a lição quando perguntado"))
            estado = "avaliada"
        if estado == "avaliada":
            try:
                ok, evid = _evidencia_pratica(cfg, licao, pid, ctx)
            except Exception as e:  # uma lição com problema não derruba a rodada de todo mundo — mas fica registrada
                import traceback
                from robo import erros
                erros.registrar(cfg, "licoes", "_evidencia_pratica", type(e).__name__,
                                f"lição {lid} ({licao['origem_tipo']}): {e}", traceback.format_exc())
                ok = False
            if ok:
                mudancas.append((lid, pid, "avaliada", "aplicada", evid))
    # 2) grava tudo numa transação só (ou entra a rodada inteira na cadeia, ou nada)
    contagem = {"estudada": 0, "avaliada": 0, "aplicada": 0}
    with tb.tx() as c:
        for lid, pid, de, estado, evid in mudancas:
            if _passar(c, lid, pid, de, estado, evid):
                contagem[estado] += 1
    integ = verificar_integridade(cfg)
    tb.lembrar("licoes_rodada", datetime.now().strftime("%Y-%m-%d %H:%M"),
               f"{sum(v for k, v in novas.items())} novidade(s); {contagem['estudada']} estudadas, {contagem['avaliada']} "
               f"avaliadas, {contagem['aplicada']} aplicadas; cadeia {'íntegra' if integ['integra'] else 'QUEBRADA'}", "rh_td")
    if not integ["integra"]:
        from robo import memoria
        memoria.handover(cfg, f"Cadeia do registro de conhecimento com problema: {integ.get('motivo', '')} (possível adulteração)",
                         "conhecimento", "sec_senior", "verificar_integridade", tb)
    return {"novas": novas, **contagem, "integridade": integ}


def rotina(cfg) -> dict | None:
    """De hora em hora: o que a empresa aprendeu vira lição no mesmo dia (não espera a rodada de estudo)."""
    m = Trabalho(cfg).memorias("licoes_rodada", limite=1)
    if m and datetime.fromisoformat(m[0]["criada_em"]) > datetime.now() - timedelta(minutes=55):
        return None
    r = rodada(cfg)
    exportar(cfg)
    saida = {k: r[k] for k in ("estudada", "avaliada", "aplicada")} | {"novas": sum(r["novas"].values()),
                                                                        "integra": r["integridade"]["integra"]}
    rp = replay_diario(cfg)
    if rp:
        saida["replay"] = rp
    return saida


def replay_diario(cfg) -> dict | None:
    """Uma vez por dia: refaz os últimos erros REAIS da esteira (aprendizados.replay) para provar se a lição virou
    comportamento. Antes existia e nenhuma rotina chamava."""
    tb = Trabalho(cfg)
    m = tb.memorias("aprendizados_replay_dia", limite=1)
    if m and datetime.fromisoformat(m[0]["criada_em"]) > datetime.now() - timedelta(hours=24):
        return None
    from robo import aprendizados
    r = aprendizados.replay(cfg, limite=10)
    tb.lembrar("aprendizados_replay_dia", datetime.now().strftime("%Y-%m-%d"),
               f"{r['testados']} erro(s) real(is) refeito(s), {r['reincidiram']} ainda acontecem", "coord_engenharia")
    return r


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
        for r in c.execute("SELECT * FROM licoes_funcionario ORDER BY licao_id, funcionario"):
            f.write(json.dumps({"caderno": dict(r)}, ensure_ascii=False) + "\n")
        for r in c.execute("SELECT * FROM licoes_uso ORDER BY id"):
            f.write(json.dumps({"uso": dict(r)}, ensure_ascii=False) + "\n")
        for r in c.execute("SELECT * FROM registro_conhecimento ORDER BY id"):
            f.write(json.dumps({"cadeia": dict(r)}, ensure_ascii=False) + "\n")
    ancorar(cfg)
    return arq
