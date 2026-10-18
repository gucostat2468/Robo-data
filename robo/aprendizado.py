"""Aprendizado operacional: o erro de hoje vira regra aprovada, e a regra muda o comportamento amanhã.

Diferença entre registrar e aprender:
  - registrar = o erro fica na memória e no caderno de lições (já existia);
  - aprender  = o comportamento do robô MUDA por causa do erro, e há prova de que mudou.

Ciclo (com governança — ninguém aprova a própria proposta):
  1. Uma planilha é reprovada por um motivo que uma regra resolve:
       - coluna obrigatória que veio com outro nome  → proposta de SINÔNIMO (ex.: 'nota_recomendacao' = 'nota_nps');
       - valor fora da lista permitida               → proposta de NOVO VALOR PERMITIDO (você confirma que não é erro
                                                       de digitação — se parecer erro de digitação, a proposta avisa).
  2. O funcionário responsável pela área registra a proposta (autor) com a evidência (arquivo, linhas, exemplos).
  3. Só o DONO aprova ou recusa (com motivo). Aprovada, a regra passa a valer na hora (sem editar o config.yaml à mão)
     e o arquivo reprovado volta para a fila.
  4. Prova: quando aquele arquivo passa depois da regra, a proposta vira COMPROVADA (com o id da execução) e a lição
     correspondente vira "aplicada". Se reprovar de novo pelo mesmo motivo, vira NÃO RESOLVEU — e isso também fica.
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
  motivo_decisao TEXT, comprovada_em TEXT, prova TEXT, UNIQUE(padrao, tipo, coluna, valor));
CREATE TABLE IF NOT EXISTS regras_aprendidas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, proposta_id TEXT, padrao TEXT, tipo TEXT, coluna TEXT, valor TEXT,
  aprovada_por TEXT, aprovada_em TEXT, ativa INTEGER DEFAULT 1);
CREATE TRIGGER IF NOT EXISTS propostas_sem_apagar BEFORE DELETE ON propostas_regra
BEGIN SELECT RAISE(ABORT, 'propostas de regra são permanentes'); END;
CREATE TRIGGER IF NOT EXISTS regras_aprendidas_sem_apagar BEFORE DELETE ON regras_aprendidas
BEGIN SELECT RAISE(ABORT, 'regras aprendidas não são apagadas: desative'); END;
"""
TIPOS = {"sinonimo": "Sinônimo de coluna", "valor_permitido": "Novo valor permitido"}
RE_SUGESTAO = re.compile(r"^(?P<col>.+?) \(você quis dizer '(?P<parecida>.+?)'")
RE_VALOR = re.compile(r"^linha \d+: '(?P<valor>.*)'$")
_bancos_prontos: set[str] = set()


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    if str(tb.arquivo) not in _bancos_prontos:
        with tb.tx() as c:
            c.executescript(ESQUEMA)
        _bancos_prontos.add(str(tb.arquivo))
    return tb


# =============================================================================== regras ativas (usadas pelo pipeline)
def regras_ativas(cfg, padrao: str) -> dict:
    """Overlay da regra: {'sinonimos': {coluna: [alternativas]}, 'valores_permitidos': {coluna: [valores]}}."""
    try:
        with _tb(cfg).tx() as c:
            linhas = c.execute("SELECT tipo, coluna, valor FROM regras_aprendidas WHERE ativa=1 AND padrao=? ORDER BY id",
                               (padrao,)).fetchall()
    except Exception:  # sem banco de trabalho (ex.: pasta de logs ainda não existe): sem overlay
        return {}
    extra: dict = {}
    for r in linhas:
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
                parecido = difflib.get_close_matches(valor.lower(), [p.lower() for p in permitidos], n=1, cutoff=0.75)
                alerta = (f"ATENÇÃO: '{valor}' parece erro de digitação de '{parecido[0]}'. Se for, RECUSE e corrija na origem."
                          if parecido else "")
                criadas += _registrar(cfg, tb, r, padrao, "valor_permitido", o.coluna, valor,
                                      f"O valor '{valor}' apareceu na coluna '{o.coluna}' e não está na lista permitida.",
                                      f"{r.arquivo.name}: {o.quantidade} linha(s), ex.: {', '.join(o.exemplos[:3])}", alerta, gente)
    if criadas:
        memoria.experiencia(cfg, _autor(criadas[0], tb), "aprendizado", f"Propus {len(criadas)} regra(s) para não reprovar "
                            f"{r.arquivo.name} de novo pelo mesmo motivo", "aprendizado", ",".join(criadas))
    return criadas


def _autor(pid_ou_proposta: str, tb: Trabalho) -> str:
    with tb.tx() as c:
        r = c.execute("SELECT autor FROM propostas_regra WHERE id=?", (pid_ou_proposta,)).fetchone()
    return r["autor"] if r else pid_ou_proposta


def _registrar(cfg, tb, r, padrao, tipo, coluna, valor, motivo, evidencia, alerta, gente) -> list[str]:
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
                  "evidencia, alerta, autor) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (pid, _agora(), r.arquivo.name, str(r.destino_original or ""), padrao, tipo, coluna, valor, motivo,
                   evidencia, alerta, autor))
    return [pid]


def listar(cfg, estado: str | None = None, limite: int = 200) -> list[dict]:
    from robo import organizacao
    sql, args = "SELECT * FROM propostas_regra WHERE 1=1", []
    if estado:
        sql += " AND estado=?"
        args.append(estado)
    with _tb(cfg).tx() as c:
        linhas = [dict(x) for x in c.execute(sql + " ORDER BY criada_em DESC LIMIT ?", args + [int(limite)])]
    gente = organizacao.por_id(cfg)
    for x in linhas:
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
            c.execute("INSERT INTO regras_aprendidas (proposta_id, padrao, tipo, coluna, valor, aprovada_por, aprovada_em) "
                      "VALUES (?,?,?,?,?,?,?)", (proposta_id, p["padrao"], p["tipo"], p["coluna"], p["valor"], quem, _agora()))
    p = dict(p)
    andar = 1
    titulo = f"Regra aprendida ({TIPOS[p['tipo']]}): {p['coluna']} ← '{p['valor']}' em {p['padrao']}"
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
                        (p["tipo"] == "valor_permitido" and o.mensagem == "Valores fora da lista permitida" and
                         o.coluna == p["coluna"] and any(f"'{p['valor']}'" in e for e in o.exemplos))
                        for o in r.relatorio.erros)
            if not mesmo:
                continue  # reprovou por OUTRO motivo: a regra pode ter funcionado; espera a próxima
            novo, prova = "nao_resolveu", f"execução {r.id}: reprovou de novo pelo mesmo motivo"
        else:
            continue
        with tb.tx() as c:
            c.execute("UPDATE propostas_regra SET estado=?, comprovada_em=?, prova=? WHERE id=?", (novo, _agora(), prova, p["id"]))
        mudou.append(p["id"])
    return mudou


def resumo(cfg) -> dict:
    with _tb(cfg).tx() as c:
        por = {r["estado"]: r["n"] for r in c.execute("SELECT estado, COUNT(*) n FROM propostas_regra GROUP BY estado")}
        ativas = c.execute("SELECT COUNT(*) FROM regras_aprendidas WHERE ativa=1").fetchone()[0]
    return {"por_estado": por, "regras_ativas": ativas}


def para_json(x) -> str:
    return json.dumps(x, ensure_ascii=False)
