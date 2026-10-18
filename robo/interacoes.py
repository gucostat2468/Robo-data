"""Interação entre funcionários: pedidos de ajuda, respostas e trocas de experiência.

Toda conversa entre eles nasce de um FATO registrado (erro no laboratório, handover, pedido do dono, acerto que vale
ensinar) — não há conversa de enfeite. Cada fala:
  - fica em logs/trabalho.db → interacoes (quem, para quem, o quê, sobre qual registro);
  - aparece no canal do andar com @menção;
  - vira um balão em cima da pessoa no escritório 3D (evento ao vivo).
A resposta usa o conhecimento da empresa (manuais, boas práticas, handovers). Se não houver solução registrada, a
pessoa diz isso — e o assunto vai para a reunião do andar.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from robo import organizacao
from robo.trabalho import Trabalho, _agora

ESQUEMA = """CREATE TABLE IF NOT EXISTS interacoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, de TEXT, para TEXT, tipo TEXT, texto TEXT, ref TEXT);
CREATE INDEX IF NOT EXISTS ix_inter_data ON interacoes(id);"""


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
    return tb


def balao(etapa: str, texto: str, **extra) -> None:
    """Balão no escritório 3D (se o painel estiver aberto)."""
    from robo import orquestrador
    if orquestrador.AO_EVENTO:
        try:
            orquestrador.AO_EVENTO(etapa, extra.pop("rotulo", "conversa"), fala=texto[:140], **extra)
        except Exception:
            pass


def falar(cfg, de: str, para: str | None, texto: str, tipo: str, ref: str = "", postar: bool = True) -> None:
    tb = _tb(cfg)
    with tb.tx() as c:
        c.execute("INSERT INTO interacoes (data_hora, de, para, tipo, texto, ref) VALUES (?,?,?,?,?,?)",
                  (_agora(), de, para, tipo, texto[:2000], ref))
    gente = organizacao.por_id(cfg)
    if postar:
        try:
            from robo.canal import Canal
            nome_para = (gente.get(para) or {}).get("nome") if para else None
            canal = (gente.get(de) or {}).get("canal", "geral")
            Canal(cfg).postar(de, (f"@{nome_para} " if nome_para else "") + texto, canal, tipo="mensagem")
        except Exception:
            pass
    balao(de, texto, para=para or "", tipo_fala=tipo)


def _quem_ajuda(cfg, quem: str, problema: str) -> str | None:
    from robo import bibliotecas, lideranca
    t = problema.lower()
    if any(k in t for k in ("warning", "deprecia", "biblioteca", "pandas", "numpy", "openpyxl", "psycopg", "yaml", "sqlite")):
        candidato = bibliotecas.especialista_do_aviso(problema)
    else:
        p = organizacao.por_id(cfg).get(quem) or {}
        candidato = lideranca.HEAD_DO_ANDAR.get(p.get("andar"), None) or organizacao.gestor_de(quem)
    if candidato == quem or candidato in (None, "dono"):
        candidato = organizacao.gestor_de(quem)
    return candidato if candidato and candidato != quem and candidato != "dono" else None


def pedir_ajuda(cfg, quem: str, problema: str, ref: str = "") -> dict | None:
    """O responsável pede ajuda a quem sabe; quem sabe responde com o que a empresa já aprendeu (ou diz que não tem)."""
    from robo import ferramentas, memoria
    ajudante = _quem_ajuda(cfg, quem, problema)
    if not ajudante:
        return None
    gente = organizacao.por_id(cfg)
    nome = lambda x: (gente.get(x) or {}).get("nome", x)  # noqa: E731
    falar(cfg, quem, ajudante, f"Errei aqui e preciso da sua ajuda: {problema}", "pedido", ref)
    k = ferramentas.executar("conhecimento", cfg, pergunta=problema, quem=ajudante)
    if k["ok"]:
        resposta = f"{nome(quem)}, já passamos por isso. {k['texto'][:400]} (fonte: {k['evidencia']})"
        memoria.experiencia(cfg, ajudante, "colaboracao", f"Ajudou {nome(quem)} com conhecimento registrado", "interacao", ref)
        memoria.experiencia(cfg, quem, "aprendizado", f"Aprendeu com {nome(ajudante)}: {k['texto'][:150]}", "interacao", ref)
    else:
        resposta = (f"{nome(quem)}, não temos solução registrada para isso ainda — não vou chutar. Fica no {ref or 'handover'} "
                    "e levo para a reunião do andar; quando resolvermos, vira boa prática.")
    falar(cfg, ajudante, quem, resposta, "resposta", ref)
    return {"de": quem, "para": ajudante, "resposta": resposta, "com_conhecimento": k["ok"]}


def trocar_experiencias(cfg, dias: int = 7, limite: int = 6) -> list[dict]:
    """Quem acertou ensina quem errou na mesma área (pares tirados da memória da semana)."""
    from robo import memoria
    desde = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    gente = organizacao.por_id(cfg)
    exps = memoria.experiencias(cfg, desde=desde, limite=20_000)
    erros: dict[str, list] = {}
    acertos: dict[str, list] = {}
    for e in exps:
        (erros if e["tipo"] == "erro" else acertos if e["tipo"] == "acerto" else {}).setdefault(e["funcionario"], []).append(e)
    trocas = []
    for aprendiz, lista in erros.items():
        a = gente.get(aprendiz)
        if not a:
            continue
        assunto = lista[0]["resumo"]
        chave = assunto.split(":")[-1].strip()[:40].lower()
        mentores = [m for m, acs in acertos.items() if m != aprendiz and m not in erros and m in gente
                    and gente[m]["andar"] == a["andar"] and any(chave and chave in x["resumo"].lower() for x in acs)]
        if not mentores:
            mentores = [m for m in acertos if m != aprendiz and m not in erros and m in gente and gente[m]["andar"] == a["andar"]]
        if not mentores:
            continue
        mentor = mentores[0]
        exemplo = next((x for x in acertos[mentor] if chave and chave in x["resumo"].lower()), acertos[mentor][0])
        texto = (f"{a['nome']}, vi que você teve dificuldade em “{assunto[:90]}”. Eu acertei “{exemplo['resumo'][:90]}” — "
                 "vamos rever juntos o caso e o que mudou?")
        falar(cfg, mentor, aprendiz, texto, "troca", exemplo.get("referencia") or "")
        memoria.experiencia(cfg, mentor, "colaboracao", f"Mentoria para {a['nome']}", "interacao", exemplo.get("referencia") or "")
        memoria.experiencia(cfg, aprendiz, "aprendizado", f"Troca de experiência com {gente[mentor]['nome']}", "interacao", "")
        trocas.append({"mentor": mentor, "aprendiz": aprendiz, "assunto": assunto})
        if len(trocas) >= limite:
            break
    return trocas


def recentes(cfg, limite: int = 50) -> list[dict]:
    tb = _tb(cfg)
    gente = organizacao.por_id(cfg)
    with tb.tx() as c:
        linhas = [dict(r) for r in c.execute("SELECT * FROM interacoes ORDER BY id DESC LIMIT ?", (limite,))]
    for l in linhas:
        l["de_nome"] = (gente.get(l["de"]) or {}).get("nome", l["de"])
        l["para_nome"] = (gente.get(l["para"]) or {}).get("nome", l["para"]) if l["para"] else ""
    return linhas
