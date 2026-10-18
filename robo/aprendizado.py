"""Aprendizado operacional: o erro de hoje vira regra aprovada, e a regra muda o comportamento amanhã.

Diferença entre registrar e aprender:
  - registrar = o erro fica na memória e no caderno de lições (já existia);
  - aprender  = o comportamento do robô MUDA por causa do erro, e há prova de que mudou.

Ciclo (com governança — ninguém aprova a própria proposta):
  1. Uma planilha é reprovada por um motivo que uma regra resolve:
       - coluna obrigatória que veio com outro nome  → proposta de SINÔNIMO (ex.: 'nota_recomendacao' = 'nota_nps');
       - valor fora da lista permitida, PARECIDO com um permitido ('Sp.', 'Sao Paolo') → proposta de CORREÇÃO DE VALOR
                                                       (de → para): o robô passa a corrigir sozinho, e o relatório conta quantas;
       - valor fora da lista permitida, sem parecido  → proposta de NOVO VALOR PERMITIDO.
     O que NÃO vira regra aprendida, de propósito: valor fora da FAIXA (ex.: nota 99 no NPS) e valor que não converte para
     o TIPO. Nesses casos a reprovação protege o dado; uma regra que "faz passar" esconderia o defeito.
  2. O funcionário responsável pela área registra a proposta (autor) com a evidência (arquivo, linhas, exemplos).
  3. Só o DONO aprova ou recusa (com motivo). Aprovada, a regra passa a valer na hora (sem editar o config.yaml à mão)
     e o arquivo reprovado volta para a fila.
  4. Prova: quando aquele arquivo passa depois da regra, a proposta vira COMPROVADA (com o id da execução) e a lição
     correspondente vira "aplicada". Se reprovar de novo pelo mesmo motivo, vira NÃO RESOLVEU e a regra é DESATIVADA
     sozinha (regra que não resolve não fica valendo em silêncio). O dono também pode desativar uma regra (com motivo).
Tudo em logs/trabalho.db (propostas_regra, regras_aprendidas), sem apagar (gatilhos), e copiado para o PostgreSQL.
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
from pathlib import Path

from robo.trabalho import Trabalho, _agora, novo_id

ESQUEMA = """
CREATE TABLE IF NOT EXISTS propostas_regra (
  id TEXT PRIMARY KEY, criada_em TEXT, arquivo TEXT, arquivo_erros TEXT, padrao TEXT, tipo TEXT, coluna TEXT, valor TEXT,
  motivo TEXT, evidencia TEXT, alerta TEXT, autor TEXT, estado TEXT DEFAULT 'pendente', decidido_por TEXT, decidido_em TEXT,
  motivo_decisao TEXT, comprovada_em TEXT, prova TEXT, para TEXT, UNIQUE(padrao, tipo, coluna, valor));
CREATE TABLE IF NOT EXISTS regras_aprendidas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, proposta_id TEXT, padrao TEXT, tipo TEXT, coluna TEXT, valor TEXT,
  aprovada_por TEXT, aprovada_em TEXT, ativa INTEGER DEFAULT 1, para TEXT, desativada_em TEXT, desativada_por TEXT,
  motivo_desativacao TEXT);
CREATE TRIGGER IF NOT EXISTS propostas_sem_apagar BEFORE DELETE ON propostas_regra
BEGIN SELECT RAISE(ABORT, 'propostas de regra são permanentes'); END;
CREATE TRIGGER IF NOT EXISTS regras_aprendidas_sem_apagar BEFORE DELETE ON regras_aprendidas
BEGIN SELECT RAISE(ABORT, 'regras aprendidas não são apagadas: desative'); END;
"""
TIPOS = {"sinonimo": "Sinônimo de coluna", "valor_permitido": "Novo valor permitido",
         "mapeamento": "Correção de valor (de → para)"}
COLUNAS_NOVAS = {"propostas_regra": ["para"],
                 "regras_aprendidas": ["para", "desativada_em", "desativada_por", "motivo_desativacao"]}
RE_SUGESTAO = re.compile(r"^(?P<col>.+?) \(você quis dizer '(?P<parecida>.+?)'")
RE_VALOR = re.compile(r"^linha \d+: '(?P<valor>.*)'$")
_bancos_prontos: set[str] = set()


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    if str(tb.arquivo) not in _bancos_prontos:
        with tb.tx() as c:
            c.executescript(ESQUEMA)
            for tabela, colunas in COLUNAS_NOVAS.items():  # bancos criados antes destes campos
                existentes = {r[1] for r in c.execute(f"PRAGMA table_info({tabela})")}
                for col in colunas:
                    if col not in existentes:
                        c.execute(f"ALTER TABLE {tabela} ADD COLUMN {col} TEXT")
        _bancos_prontos.add(str(tb.arquivo))
    return tb


# =============================================================================== regras ativas (usadas pelo pipeline)
def regras_ativas(cfg, padrao: str) -> dict:
    """Overlay da regra: {'sinonimos': {coluna: [alternativas]}, 'valores_permitidos': {coluna: [valores]},
    'mapear_valores': {coluna: {de: para}}}."""
    try:
        with _tb(cfg).tx() as c:
            linhas = c.execute("SELECT tipo, coluna, valor, para FROM regras_aprendidas WHERE ativa=1 AND padrao=? ORDER BY id",
                               (padrao,)).fetchall()
    except Exception:  # sem banco de trabalho (ex.: pasta de logs ainda não existe): sem overlay
        return {}
    extra: dict = {}
    for r in linhas:
        if r["tipo"] == "mapeamento":
            extra.setdefault("mapear_valores", {}).setdefault(r["coluna"], {})[r["valor"]] = r["para"]
            continue
        chave = "sinonimos" if r["tipo"] == "sinonimo" else "valores_permitidos"
        extra.setdefault(chave, {}).setdefault(r["coluna"], []).append(r["valor"])
    return extra


def aplicar_overlay(regra: dict, extra: dict) -> dict:
    if not extra:
        return regra
    nova = dict(regra)
    sin = {k: (list(v) if isinstance(v, (list, tuple)) else [v]) for k, v in (regra.get("sinonimos") or {}).items()}
    for col, alts in (extra.get("sinonimos") or {}).items():
        sin[col] = sin.get(col, []) + [a for a in alts if a not in sin.get(col, [])]
    if sin:
        nova["sinonimos"] = sin
    perm = {k: list(v) for k, v in (regra.get("valores_permitidos") or {}).items()}
    for col, vals in (extra.get("valores_permitidos") or {}).items():
        if col in perm:  # só amplia uma lista que já existe na regra
            perm[col] = perm[col] + [v for v in vals if v not in perm[col]]
    if perm:
        nova["valores_permitidos"] = perm
    mapa = {k: dict(v) for k, v in (regra.get("mapear_valores") or {}).items()}
    for col, pares in (extra.get("mapear_valores") or {}).items():
        mapa[col] = {**pares, **mapa.get(col, {})}  # o que está escrito no config.yaml prevalece
    if mapa:
        nova["mapear_valores"] = mapa
    return nova


# =============================================================================== propostas
def propor(cfg, r) -> list[str]:
    """Depois de uma reprovação: registra as propostas de regra que resolveriam o motivo (se houver regra que case)."""
    from robo import memoria, organizacao
    from robo.limpeza import normalizar_nome_coluna
    regra = cfg.regra_para(r.arquivo.name)
    padrao = str(regra.get("padrao") or "")
    if not padrao or r.status != "reprovado":
        return []
    criadas = []
    tb = _tb(cfg)
    gente = organizacao.por_id(cfg)
    for o in r.relatorio.erros:
        if o.mensagem == "Colunas obrigatórias ausentes":
            for ex in o.exemplos:
                m = RE_SUGESTAO.match(ex)
                if not m:
                    continue
                col, par = normalizar_nome_coluna(m["col"]), m["parecida"]
                criadas += _registrar(cfg, tb, r, padrao, "sinonimo", col, par,
                                      f"A coluna obrigatória '{col}' não veio; veio '{par}', que parece ser o mesmo dado.",
                                      f"{r.arquivo.name}: colunas do arquivo incluem '{par}'", "", gente)
        elif o.mensagem == "Valores fora da lista permitida" and o.coluna:
            permitidos = [str(v) for v in (regra.get("valores_permitidos") or {}).get(o.coluna, [])]
            for ex in o.exemplos:
                m = RE_VALOR.match(ex)
                if not m or not m["valor"].strip():
                    continue
                valor = m["valor"].strip()
                evid = f"{r.arquivo.name}: {o.quantidade} linha(s), ex.: {', '.join(o.exemplos[:3])}"
                para = _parecido(valor, permitidos)
                if para:  # parece o mesmo valor escrito errado → corrigir, não ampliar a lista
                    criadas += _registrar(cfg, tb, r, padrao, "mapeamento", o.coluna, valor,
                                          f"O valor '{valor}' na coluna '{o.coluna}' parece '{para}' escrito de outro jeito. "
                                          f"Aprovada, o robô troca '{valor}' por '{para}' e conta no relatório.", evid,
                                          "Confira: se forem coisas DIFERENTES, recuse (e o valor continua barrado).", gente, para)
                else:
                    criadas += _registrar(cfg, tb, r, padrao, "valor_permitido", o.coluna, valor,
                                          f"O valor '{valor}' apareceu na coluna '{o.coluna}' e não está na lista permitida.",
                                          evid, "", gente)
    if criadas:
        memoria.experiencia(cfg, _autor(criadas[0], tb), "aprendizado", f"Propus {len(criadas)} regra(s) para não reprovar "
                            f"{r.arquivo.name} de novo pelo mesmo motivo", "aprendizado", ",".join(criadas))
    return criadas


def _chave_valor(v) -> str:
    from robo.limpeza import sem_acento
    return re.sub(r"[^a-z0-9]+", " ", sem_acento(str(v)).lower()).strip()


def _parecido(valor: str, permitidos: list[str]) -> str | None:
    """O permitido que este valor provavelmente quis dizer ('Sp.' → 'SP'; 'Sao Paolo' → 'São Paulo'), ou None."""
    chaves = {_chave_valor(p): p for p in permitidos}
    k = _chave_valor(valor)
    if not k:
        return None
    if k in chaves:  # só pontuação/espaço diferente
        return chaves[k]
    achou = difflib.get_close_matches(k, list(chaves), n=1, cutoff=0.8)
    return chaves[achou[0]] if achou else None


def _autor(pid_ou_proposta: str, tb: Trabalho) -> str:
    with tb.tx() as c:
        r = c.execute("SELECT autor FROM propostas_regra WHERE id=?", (pid_ou_proposta,)).fetchone()
    return r["autor"] if r else pid_ou_proposta


def _registrar(cfg, tb, r, padrao, tipo, coluna, valor, motivo, evidencia, alerta, gente, para=None) -> list[str]:
    from robo import memoria
    _, resp, *_ = memoria.categorizar(motivo if tipo == "sinonimo" else "Valores fora da lista permitida")
    autor = resp if resp in gente else "coord_engenharia"
    with tb.tx() as c:
        ja = c.execute("SELECT id, estado FROM propostas_regra WHERE padrao=? AND tipo=? AND coluna=? AND valor=?",
                       (padrao, tipo, coluna, valor)).fetchone()
        if ja:
            return []
        pid = novo_id("REG")
        c.execute("INSERT INTO propostas_regra (id, criada_em, arquivo, arquivo_erros, padrao, tipo, coluna, valor, motivo, "
                  "evidencia, alerta, autor, para) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (pid, _agora(), r.arquivo.name, str(r.destino_original or ""), padrao, tipo, coluna, valor, motivo,
                   evidencia, alerta, autor, para))
    return [pid]


def listar(cfg, estado: str | None = None, limite: int = 200) -> list[dict]:
    from robo import organizacao
    sql, args = "SELECT * FROM propostas_regra WHERE 1=1", []
    if estado:
        sql += " AND estado=?"
        args.append(estado)
    with _tb(cfg).tx() as c:
        linhas = [dict(x) for x in c.execute(sql + " ORDER BY criada_em DESC LIMIT ?", args + [int(limite)])]
        regras = {r["proposta_id"]: dict(r) for r in c.execute(
            "SELECT id regra_id, proposta_id, ativa, desativada_em, desativada_por, motivo_desativacao FROM regras_aprendidas")}
    gente = organizacao.por_id(cfg)
    for x in linhas:
        x.update({k: v for k, v in (regras.get(x["id"]) or {}).items() if k != "proposta_id"})
        x["autor_nome"] = (gente.get(x["autor"]) or {}).get("nome", x["autor"])
        x["tipo_nome"] = TIPOS.get(x["tipo"], x["tipo"])
    return linhas


# =============================================================================== decisão (só o dono) e reenvio
def decidir(cfg, proposta_id: str, aprovar: bool, quem: str = "dono", motivo: str = "") -> dict:
    from robo import licoes, memoria
    if quem != "dono":
        raise PermissionError("Só o dono aprova ou recusa uma regra nova (ninguém aprova a própria proposta).")
    tb = _tb(cfg)
    with tb.tx() as c:
        p = c.execute("SELECT * FROM propostas_regra WHERE id=?", (proposta_id,)).fetchone()
        if not p:
            raise ValueError("Proposta não existe.")
        if p["estado"] != "pendente":
            raise ValueError(f"Esta proposta já foi decidida ({p['estado']}).")
        if not aprovar and not motivo.strip():
            raise ValueError("Recusar exige o motivo (ele vira aprendizado também).")
        c.execute("UPDATE propostas_regra SET estado=?, decidido_por=?, decidido_em=?, motivo_decisao=? WHERE id=?",
                  ("aprovada" if aprovar else "recusada", quem, _agora(), motivo[:500], proposta_id))
        if aprovar:
            c.execute("INSERT INTO regras_aprendidas (proposta_id, padrao, tipo, coluna, valor, para, aprovada_por, aprovada_em) "
                      "VALUES (?,?,?,?,?,?,?,?)", (proposta_id, p["padrao"], p["tipo"], p["coluna"], p["valor"], p["para"],
                                                   quem, _agora()))
    p = dict(p)
    andar = 1
    titulo = f"Regra aprendida ({TIPOS[p['tipo']]}): {_descrever(p)} em {p['padrao']}"
    if aprovar:
        licoes.criar(cfg, "regra", proposta_id, titulo,
                     f"{p['motivo']}\nDecisão: aprovada pelo dono.\nA partir de agora, arquivos '{p['padrao']}' aceitam isso "
                     f"automaticamente.\nEvidência: {p['evidencia']}", f"{p['coluna']} {p['valor']}",
                     "o arquivo que reprovou passa depois da regra", andar, p["autor"])
        memoria.experiencia(cfg, p["autor"], "acerto", f"Proposta de regra aprovada: {titulo}", "aprendizado", proposta_id)
        reenviado = reenviar(cfg, p["arquivo_erros"]) if p["arquivo_erros"] else None
    else:
        memoria.experiencia(cfg, p["autor"], "aprendizado", f"Proposta recusada pelo dono: {titulo}. Motivo: {motivo}",
                            "aprendizado", proposta_id)
        reenviado = None
    return {"ok": True, "estado": "aprovada" if aprovar else "recusada", "reenviado": reenviado}


def _descrever(p) -> str:
    if p["tipo"] == "mapeamento":
        return f"{p['coluna']}: '{p['valor']}' → '{p.get('para')}'"
    return f"{p['coluna']} ← '{p['valor']}'"


def desativar(cfg, proposta_id: str, quem: str = "dono", motivo: str = "") -> dict:
    """Tira uma regra aprendida de vigor (não apaga: fica o registro de quando, quem e por quê).
    Só o dono desativa pelo painel; o 'sistema' desativa sozinho quando a regra comprovadamente não resolveu."""
    from robo import memoria
    if quem not in ("dono", "sistema"):
        raise PermissionError("Só o dono desativa uma regra aprendida.")
    if not motivo.strip():
        raise ValueError("Desativar exige o motivo.")
    tb = _tb(cfg)
    with tb.tx() as c:
        r = c.execute("SELECT r.*, p.autor FROM regras_aprendidas r JOIN propostas_regra p ON p.id=r.proposta_id "
                      "WHERE r.proposta_id=?", (proposta_id,)).fetchone()
        if not r:
            raise ValueError("Não há regra aprovada para esta proposta.")
        if not r["ativa"]:
            raise ValueError(f"Esta regra já está desativada (desde {r['desativada_em']}).")
        c.execute("UPDATE regras_aprendidas SET ativa=0, desativada_em=?, desativada_por=?, motivo_desativacao=? WHERE id=?",
                  (_agora(), quem, motivo[:500], r["id"]))
    memoria.experiencia(cfg, r["autor"], "aprendizado", f"Regra desativada ({_descrever(dict(r))} em {r['padrao']}) por "
                        f"{'você' if quem == 'dono' else 'não ter resolvido'}: {motivo[:200]}", "aprendizado", proposta_id)
    return {"ok": True, "desativada": proposta_id}


def reenviar(cfg, arquivo_erros: str) -> str | None:
    """Devolve um arquivo reprovado para a fila (Bases-Limpeza). Não sobrescreve nada que já esteja lá."""
    arq = Path(arquivo_erros)
    if not arq.is_file() or arq.parent.resolve() != Path(cfg.erros).resolve():
        return None
    destino = Path(cfg.entrada) / re.sub(r"^\d{8}_\d{6}_", "", arq.name)
    if destino.exists():
        return None
    shutil.move(str(arq), str(destino))
    arq.with_name(f"{arq.stem}_ERROS.txt").unlink(missing_ok=True)
    return destino.name


# =============================================================================== prova (o comportamento mudou?)
def comprovar(cfg, r) -> list[str]:
    """Depois de cada processamento: propostas aprovadas daquele arquivo viram comprovadas (passou) ou 'não resolveu'."""
    tb = _tb(cfg)
    with tb.tx() as c:
        abertas = c.execute("SELECT * FROM propostas_regra WHERE estado='aprovada' AND arquivo=?", (r.arquivo.name,)).fetchall()
    mudou = []
    for p in abertas:
        if r.status == "sucesso":
            novo, prova = "comprovada", f"execução {r.id}: aprovada depois da regra"
        elif r.status == "reprovado":
            mesmo = any((p["tipo"] == "sinonimo" and o.mensagem == "Colunas obrigatórias ausentes" and
                         any(e.startswith(p["coluna"] + " ") or e == p["coluna"] for e in o.exemplos)) or
                        (p["tipo"] in ("valor_permitido", "mapeamento") and o.mensagem == "Valores fora da lista permitida" and
                         o.coluna == p["coluna"] and any(f"'{p['valor']}'" in e for e in o.exemplos))
                        for o in r.relatorio.erros)
            if not mesmo:
                continue  # reprovou por OUTRO motivo: a regra pode ter funcionado; espera a próxima
            novo, prova = "nao_resolveu", f"execução {r.id}: reprovou de novo pelo mesmo motivo"
        else:
            continue
        with tb.tx() as c:
            c.execute("UPDATE propostas_regra SET estado=?, comprovada_em=?, prova=? WHERE id=?", (novo, _agora(), prova, p["id"]))
        if novo == "nao_resolveu":  # regra que não resolve não fica valendo em silêncio
            try:
                desativar(cfg, p["id"], "sistema", prova)
            except ValueError:
                pass  # já estava desativada
        mudou.append(p["id"])
    return mudou


def resumo(cfg) -> dict:
    with _tb(cfg).tx() as c:
        por = {r["estado"]: r["n"] for r in c.execute("SELECT estado, COUNT(*) n FROM propostas_regra GROUP BY estado")}
        ativas = c.execute("SELECT COUNT(*) FROM regras_aprendidas WHERE ativa=1").fetchone()[0]
    return {"por_estado": por, "regras_ativas": ativas}


def para_json(x) -> str:
    return json.dumps(x, ensure_ascii=False)
