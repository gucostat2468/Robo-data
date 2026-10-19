"""Quem faz o quê: o escopo de cada funcionário e o ÚLTIMO trabalho que ele de fato deixou registrado.

Responde à pergunta do dono "o que cada um anda fazendo?" só com o que está no banco (logs/trabalho.db) e na última
ronda de TI. Nada é estimado: quem não tem registro aparece como "nenhum registro ainda" — e isso é um alerta para a
liderança, não um número a esconder.

Fontes (cada uma só entra se a tabela existir):
  treino_tentativas, interacoes, mentorias, treino_casos (designer e revisor), treino_certificacoes (revisor),
  auditorias, ideias_registro (Iara registra), paineis_versoes (autor e conferente), laboratorio_exercicios,
  uso_ferramentas, canal_mensagens, handover_eventos, rh_movimentos (quem propôs e quem validou),
  rotinas_execucoes (pelo responsável da rotina em robo/rotinas.py), experiencias e a última ronda de TI.

Situação: "trabalhando" (último registro há menos de 2 h), "ativo hoje" (menos de 24 h), "ocioso" (24 h ou mais)
e "sem registro" (nunca deixou registro).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from robo.trabalho import Trabalho

TRABALHANDO_H = 2
OCIOSO_H = 24

# (tabela, coluna de quem fez, coluna de quando, colunas para o texto, como escrever o texto)
FONTES = [
    ("treino_tentativas", "funcionario", "data_hora", "competencia, nivel, acertou",
     lambda r, n: f"Treino: {n['comp'](r['competencia'])} nível {r['nivel']} — {'acertou' if r['acertou'] else 'errou'}"),
    ("interacoes", "de", "data_hora", "para, tipo, texto",
     lambda r, n: f"Conversa com {n['pessoa'](r['para'])} ({r['tipo']}): {(r['texto'] or '')[:140]}"),
    ("mentorias", "mentor", "data_hora", "aprendiz, competencia, situacao",
     lambda r, n: f"Mentoria para {n['pessoa'](r['aprendiz'])} em {n['comp'](r['competencia'])} ({r['situacao'] or 'aberta'})"),
    ("treino_casos", "designer", "criado_em", "competencia, nivel, estado",
     lambda r, n: f"Preparou caso de treino {n['comp'](r['competencia'])} nível {r['nivel']} ({r['estado']})"),
    ("treino_casos", "revisor", "revisado_em", "competencia, nivel, estado",
     lambda r, n: f"Revisou caso de treino {n['comp'](r['competencia'])} nível {r['nivel']}: {r['estado']}"),
    ("treino_certificacoes", "revisor", "data_hora", "designer, competencia, ok",
     lambda r, n: f"Revisou o exame de {n['pessoa'](r['designer'])} em {n['comp'](r['competencia'])}: "
                  f"{'aprovado' if r['ok'] else 'reprovado'}"),
    ("auditorias", "head", "data_hora", "area, aprovada, conferidos",
     lambda r, n: f"Auditoria por amostragem ({r['area']}): {r['conferidos']} conferido(s), "
                  f"{'aprovada' if r['aprovada'] else 'com achados'}"),
    ("ideias_registro", "'canal_iara'", "data_hora", "titulo",
     lambda r, n: f"Registrou a ideia: {r['titulo']}"),
    ("paineis_versoes", "autor", "data_hora", "id, situacao",
     lambda r, n: f"Montou os painéis (versão {r['id']}, {str(r['situacao']).replace('_', ' ')})"),
    ("paineis_versoes", "conferente", "data_hora", "id, situacao, divergencias",
     lambda r, n: f"Conferiu os painéis (versão {r['id']}): "
                  f"{'barrou por divergência' if r['situacao'] == 'reprovado' else 'números batem'}"),
    ("laboratorio_exercicios", "responsavel", "data_hora", "area, etapa, ok",
     lambda r, n: f"Laboratório ({r['area']}), etapa {r['etapa']}: {'certo' if r['ok'] else 'errou'}"),
    ("uso_ferramentas", "quem", "data_hora", "ferramenta, ok",
     lambda r, n: f"Usou a ferramenta {r['ferramenta']}: {'ok' if r['ok'] else 'falhou'}"),
    ("canal_mensagens", "autor", "data_hora", "canal, texto",
     lambda r, n: f"Postou no #{r['canal']}: {(r['texto'] or '')[:140]}"),
    ("handover_eventos", "quem", "data_hora", "handover_id, tipo",
     lambda r, n: f"Handover {r['handover_id']}: {r['tipo']}"),
    ("rh_movimentos", "proposto_por", "data_hora", "funcionario, tipo",
     lambda r, n: f"Propôs {r['tipo']} de {n['pessoa'](r['funcionario'])}"),
    ("rh_movimentos", "validado_por", "data_hora", "funcionario, tipo, situacao",
     lambda r, n: f"Validou {r['tipo']} de {n['pessoa'](r['funcionario'])} ({r['situacao']})"),
    ("experiencias", "funcionario", "data_hora", "tipo, resumo",
     lambda r, n: f"{(r['resumo'] or r['tipo'] or '')[:160]}"),
]


def _quando(texto) -> datetime | None:
    if not texto:
        return None
    try:
        return datetime.fromisoformat(str(texto).replace(" ", "T")[:19])
    except ValueError:
        return None


def _colunas(c, tabela: str) -> set[str]:
    return {r[1] for r in c.execute(f'PRAGMA table_info("{tabela}")')}


def registros(cfg, agora: datetime | None = None) -> dict[str, dict]:
    """pid → {"ultimo": {quando, o_que, fonte}, "em_24h": n, "fontes": {fonte: n em 24 h}} — só o que está registrado."""
    from robo import organizacao
    from robo.rotinas import ROTINAS
    from robo.treino_casos import CATALOGO
    agora = agora or datetime.now()
    gente = organizacao.por_id(cfg)
    nomes = {"comp": lambda x: CATALOGO[x].nome if x in CATALOGO else (x or ""),
             "pessoa": lambda x: "você (dono)" if x == "dono" else (gente.get(x) or {}).get("nome", x or "?")}
    desde = (agora - timedelta(hours=OCIOSO_H)).isoformat(timespec="seconds")
    saida: dict[str, dict] = {}

    def anotar(pid, quando, o_que, fonte, n24=0):
        if not pid:
            return
        d = saida.setdefault(pid, {"ultimo": None, "em_24h": 0, "fontes": {}})
        if n24:
            d["em_24h"] += n24
            d["fontes"][fonte] = d["fontes"].get(fonte, 0) + n24
        q = _quando(quando)
        if q and (d["ultimo"] is None or q > d["ultimo"]["_q"]):
            d["ultimo"] = {"_q": q, "quando": q.isoformat(timespec="seconds"), "o_que": o_que, "fonte": fonte}

    with Trabalho(cfg).tx() as c:
        tabelas = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for tabela, quem, quando, cols, texto in FONTES:
            if tabela not in tabelas:
                continue
            existentes = _colunas(c, tabela)
            pedidas = [x.strip() for x in cols.split(",")]
            if quando not in existentes or (not quem.startswith("'") and quem not in existentes) \
                    or any(x not in existentes for x in pedidas):
                continue
            filtro = f"{quem} IS NOT NULL AND {quem} <> '' AND {quando} IS NOT NULL AND {quando} <> ''"
            sql = (f"SELECT quem, quando, {cols} FROM (SELECT {quem} AS quem, {quando} AS quando, {cols}, ROW_NUMBER() OVER "
                   f"(PARTITION BY {quem} ORDER BY {quando} DESC) AS rn FROM \"{tabela}\" WHERE {filtro}) WHERE rn = 1")
            contagem = {r[0]: r[1] for r in c.execute(
                f"SELECT {quem}, COUNT(*) FROM \"{tabela}\" WHERE {filtro} AND replace({quando}, ' ', 'T') >= ? "
                f"GROUP BY {quem}", (desde,))}
            for r in c.execute(sql):
                try:
                    o_que = texto(r, nomes)
                except Exception:
                    o_que = tabela
                anotar(r["quem"], r["quando"], o_que, tabela, contagem.get(r["quem"], 0))
        if "rotinas_execucoes" in tabelas:
            contagem = {r[0]: r[1] for r in c.execute(
                "SELECT nome, COUNT(*) FROM rotinas_execucoes WHERE replace(fim, ' ', 'T') >= ? GROUP BY nome", (desde,))}
            for r in c.execute("SELECT nome, fim, status, detalhe FROM (SELECT nome, fim, status, detalhe, ROW_NUMBER() OVER "
                               "(PARTITION BY nome ORDER BY fim DESC) AS rn FROM rotinas_execucoes WHERE fim IS NOT NULL) "
                               "WHERE rn = 1"):
                resp = (ROTINAS.get(r["nome"]) or (None,))[0]
                anotar(resp, r["fim"], f"Rotina {r['nome']}: {r['status']}" + (f" — {r['detalhe'][:120]}" if r["detalhe"] else ""),
                       "rotinas_execucoes", contagem.get(r["nome"], 0))
    try:  # 5º andar: cada pessoa da TI tem a sua verificação na ronda (a cada 30 min)
        from robo import ti
        ronda = ti.ultima_ronda(cfg) or {}
        recente = (_quando(ronda.get("data_hora")) or datetime.min) >= agora - timedelta(hours=OCIOSO_H)
        for i in ronda.get("itens") or []:
            achados = i.get("achados") or []
            anotar(i["id"], ronda.get("data_hora"),
                   f"Ronda de TI: {_verificacao_ti(i['id'])} — " + ("OK, nada a apontar" if not achados else "; ".join(achados)[:200]),
                   "ronda_ti", 1 if recente else 0)
    except Exception:
        pass
    for d in saida.values():
        if d["ultimo"]:
            d["ultimo"].pop("_q", None)
    return saida


def _verificacao_ti(pid: str) -> str:
    from robo import ti
    p = ti.POR_ID.get(pid) or {}
    return "; ".join(p.get("escopo") or [])[:160] or pid


def situacao(ultimo: dict | None, agora: datetime) -> str:
    if not ultimo:
        return "sem_registro"
    idade = agora - datetime.fromisoformat(ultimo["quando"])
    if idade < timedelta(hours=TRABALHANDO_H):
        return "trabalhando"
    if idade < timedelta(hours=OCIOSO_H):
        return "ativo_hoje"
    return "ocioso"


def quadro(cfg, agora: datetime | None = None) -> dict:
    """Todas as pessoas do organograma, com escopo e último trabalho registrado, + o resumo por andar."""
    from robo import organizacao
    from robo.rotinas import ROTINAS
    agora = agora or datetime.now()
    regs = registros(cfg, agora)
    rotinas_de: dict[str, list[str]] = {}
    for nome, (resp, desc, horas) in ROTINAS.items():
        a_cada = f"{round(horas * 60)} min" if horas < 1 else (f"{horas:g} h" if horas < 24 else f"{horas / 24:g} dia(s)")
        rotinas_de.setdefault(resp, []).append(f"{nome} (a cada {a_cada}): {desc}")
    pessoas = []
    for p in organizacao.lista(cfg):
        ct = organizacao.contrato(p["id"], cfg) or {}
        r = regs.get(p["id"]) or {}
        ultimo = r.get("ultimo")
        escopo = list(ct.get("responsabilidades") or []) or [x for x in (ct.get("objetivo") or p.get("descricao") or "").split("; ") if x]
        pessoas.append({
            "id": p["id"], "nome": p["nome"], "cargo": ct.get("cargo") or p.get("papel"), "andar": int(p.get("andar") or 0),
            "nivel": ct.get("nivel_nome") or ct.get("nivel") or "", "gestor": ct.get("gestor_nome") or "",
            "cor": p.get("cor"), "escopo": escopo, "ferramentas": ct.get("ferramentas") or [],
            "rotinas": rotinas_de.get(p["id"], []), "ultimo": ultimo, "em_24h": r.get("em_24h", 0),
            "fontes_24h": r.get("fontes", {}), "situacao": situacao(ultimo, agora),
        })
    andares = {}
    for x in pessoas:
        a = andares.setdefault(x["andar"], {"andar": x["andar"], "nome": organizacao.NOME_ANDAR.get(x["andar"], ""),
                                             "pessoas": 0, "trabalhando": 0, "ativo_hoje": 0, "ocioso": 0, "sem_registro": 0})
        a["pessoas"] += 1
        a[x["situacao"]] += 1
    parados = [{"id": x["id"], "nome": x["nome"], "andar": x["andar"], "cargo": x["cargo"], "situacao": x["situacao"],
                "gestor": x["gestor"]} for x in pessoas if x["situacao"] in ("ocioso", "sem_registro")]
    return {"gerado_em": agora.isoformat(timespec="seconds"), "pessoas": pessoas,
            "andares": [andares[a] for a in sorted(andares)], "parados": parados,
            "regra": f"trabalhando = registro há menos de {TRABALHANDO_H} h; ativo hoje = menos de {OCIOSO_H} h; "
                     f"ocioso = {OCIOSO_H} h ou mais; sem registro = nunca registrou trabalho"}
