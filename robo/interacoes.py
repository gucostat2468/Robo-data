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

import logging
from datetime import datetime, timedelta

from robo import organizacao
from robo.trabalho import Trabalho, _agora

log = logging.getLogger("robo")

ESQUEMA = """CREATE TABLE IF NOT EXISTS interacoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, de TEXT, para TEXT, tipo TEXT, texto TEXT, ref TEXT);
CREATE INDEX IF NOT EXISTS ix_inter_data ON interacoes(id);
CREATE INDEX IF NOT EXISTS ix_inter_ref ON interacoes(ref);
CREATE TABLE IF NOT EXISTS mentorias (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, mentor TEXT, aprendiz TEXT, competencia TEXT, nivel INTEGER,
  tentativa_erro_id INTEGER, licao_id TEXT, situacao TEXT, fechada_em TEXT, tentativa_resultado_id INTEGER);
CREATE INDEX IF NOT EXISTS ix_mentoria_aprendiz ON mentorias(aprendiz, competencia, situacao);
CREATE TRIGGER IF NOT EXISTS mentorias_so_situacao
  BEFORE UPDATE OF data_hora, mentor, aprendiz, competencia, nivel, tentativa_erro_id, licao_id ON mentorias
  BEGIN SELECT RAISE(ABORT, 'mentorias: só a situação muda; quem, o quê e a evidência são permanentes'); END;"""


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        from robo.trabalho import proteger
        proteger(c)
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


# =============================================================================== mentoria nascida do erro de treino
def _ja_falado(c, ref: str) -> bool:
    return bool(ref) and c.execute("SELECT 1 FROM interacoes WHERE ref=? LIMIT 1", (ref,)).fetchone() is not None


def escolher_mentor(cfg, aprendiz: str, comp: str, nivel: int, excluir: set | None = None) -> str | None:
    """Mentor por dado: quem acertou a MESMA competência em nível >= o do erro, o mais recente; primeiro do mesmo andar,
    depois de qualquer andar. Nunca o próprio aprendiz; a Sala de Casos só se não houver mais ninguém (aí, o designer)."""
    from robo import treino
    excluir = set(excluir or ()) | {aprendiz}
    gente = organizacao.por_id(cfg)
    andar = (gente.get(aprendiz) or {}).get("andar")
    with _tb(cfg).tx() as c:
        linhas = c.execute("SELECT funcionario, MAX(id) AS ult FROM treino_tentativas WHERE competencia=? AND nivel>=? AND acertou=1 "
                           "GROUP BY funcionario ORDER BY ult DESC", (comp, int(nivel))).fetchall()
    candidatos = [r["funcionario"] for r in linhas if r["funcionario"] not in excluir and r["funcionario"] in gente
                  and r["funcionario"] not in treino.EQUIPE_SALA]
    mesmo = [x for x in candidatos if gente[x].get("andar") == andar]
    if mesmo or candidatos:
        return (mesmo or candidatos)[0]
    designer = treino.CATALOGO[comp].designer if comp in treino.CATALOGO else None
    return designer if designer and designer not in excluir else None


def apos_tentativa(cfg, tentativa: dict) -> dict:
    """Chamado pelo treino depois de cada tentativa registrada. Fecha a mentoria aberta (ajudou / não ajudou) e, se a
    pessoa errou, abre outra com um mentor escolhido pelos registros. Também compartilha quando a pessoa sobe de nível.
    Falha aqui nunca derruba o treino: fica no log (e no registro de erros do sistema)."""
    saida = {"fechada": None, "aberta": None, "troca": None}
    try:
        saida["fechada"] = _fechar_mentoria(cfg, tentativa)
        if not tentativa["acertou"]:
            saida["aberta"] = _abrir_mentoria(cfg, tentativa)
        m = tentativa.get("mudanca_nivel")
        if m and m["para"] > m["de"]:
            saida["troca"] = compartilhar_subida(cfg, tentativa["funcionario"], tentativa["competencia"], m["de"], m["para"])
    except Exception:
        log.exception("Interações: não consegui registrar a conversa da tentativa %s", tentativa.get("tentativa"))
    return saida


def _nome(gente, pid) -> str:
    return (gente.get(pid) or {}).get("nome", pid)


def _nome_comp(comp: str) -> str:
    from robo import treino
    return treino.CATALOGO[comp].nome if comp in treino.CATALOGO else comp


def _fechar_mentoria(cfg, t: dict) -> dict | None:
    """Regra: a PRÓXIMA tentativa do aprendiz na mesma competência, em nível >= o da mentoria, decide se ajudou."""
    from robo import memoria
    with _tb(cfg).tx() as c:
        m = c.execute("SELECT * FROM mentorias WHERE aprendiz=? AND competencia=? AND situacao='aberta' AND nivel<=? "
                      "ORDER BY id LIMIT 1", (t["funcionario"], t["competencia"], int(t["nivel"]))).fetchone()
        if not m or int(m["tentativa_erro_id"]) == int(t["tentativa"]):
            return None
        situacao = "ajudou" if t["acertou"] else "nao_ajudou"
        c.execute("UPDATE mentorias SET situacao=?, fechada_em=?, tentativa_resultado_id=? WHERE id=?",
                  (situacao, _agora(), t["tentativa"], m["id"]))
    gente = organizacao.por_id(cfg)
    ref = f"mentoria:{m['id']}:fechada"
    if situacao == "ajudou":
        memoria.experiencia(cfg, m["mentor"], "colaboracao", f"Mentoria ajudou {_nome(gente, m['aprendiz'])} a acertar "
                            f"{_nome_comp(t['competencia'])} nível {t['nivel']}", "interacao", f"M{m['id']}#T{t['tentativa']}")
        falar(cfg, m["aprendiz"], m["mentor"], f"Acertei {_nome_comp(t['competencia'])} no nível {t['nivel']} (T{t['tentativa']}) "
              f"depois da nossa conversa sobre a T{m['tentativa_erro_id']}. Obrigado(a)!", "agradecimento", ref)
    else:
        falar(cfg, m["aprendiz"], m["mentor"], f"Errei de novo {_nome_comp(t['competencia'])} no nível {t['nivel']} "
              f"(T{t['tentativa']}): {str(t.get('detalhe') or '')[:160]}. Vou pedir outra visão.", "retorno", ref)
    return {"mentoria": m["id"], "situacao": situacao}


def _abrir_mentoria(cfg, t: dict) -> dict | None:
    from robo import licoes, lideranca
    pid, comp, nivel = t["funcionario"], t["competencia"], int(t["nivel"])
    licoes._tb(cfg)  # o caderno de lições existe mesmo antes da primeira lição
    with _tb(cfg).tx() as c:
        if c.execute("SELECT 1 FROM mentorias WHERE aprendiz=? AND competencia=? AND situacao='aberta'", (pid, comp)).fetchone():
            return None  # já há uma mentoria em andamento: espera o resultado dela
        nao_ajudaram = {r["mentor"] for r in c.execute("SELECT mentor FROM mentorias WHERE aprendiz=? AND competencia=? "
                                                       "AND situacao='nao_ajudou'", (pid, comp))}
        licao = c.execute("SELECT id, titulo FROM licoes WHERE origem_tipo='treino' AND origem_ref=? ORDER BY versao DESC LIMIT 1",
                          (f"{comp}:{nivel}:{t.get('tipo_erro')}",)).fetchone()
    gente = organizacao.por_id(cfg)
    mentor = escolher_mentor(cfg, pid, comp, nivel, nao_ajudaram)
    ref = f"treino:T{t['tentativa']}"
    if not mentor:
        head = lideranca.HEAD_DO_ANDAR.get((gente.get(pid) or {}).get("andar"))
        falar(cfg, pid, head, f"Errei {_nome_comp(comp)} no nível {nivel} (T{t['tentativa']}) e ninguém acertou esse nível ainda "
              "— não tenho com quem aprender. Preciso que isso entre na pauta do andar.", "sem_mentor", ref)
        return {"mentor": None, "head": head}
    with _tb(cfg).tx() as c:
        ult = c.execute("SELECT id, nivel, detalhe FROM treino_tentativas WHERE funcionario=? AND competencia=? AND acertou=1 "
                        "ORDER BY id DESC LIMIT 1", (mentor, comp)).fetchone()
        cur = c.execute("INSERT INTO mentorias (data_hora, mentor, aprendiz, competencia, nivel, tentativa_erro_id, licao_id, "
                        "situacao) VALUES (?,?,?,?,?,?,?, 'aberta')",
                        (_agora(), mentor, pid, comp, nivel, t["tentativa"], licao["id"] if licao else None))
        mid = cur.lastrowid
    falar(cfg, pid, mentor, f"Errei {_nome_comp(comp)} no nível {nivel} (T{t['tentativa']}): {str(t.get('detalhe') or '')[:200]}. "
          "Você acertou essa competência — pode me ajudar?", "pedido", ref)
    partes = [f"{_nome(gente, pid)}, vamos lá."]
    if licao:
        partes.append(f"Leia a lição {licao['id']} («{licao['titulo'][:120]}»), que já está no seu caderno.")
    if ult:
        partes.append(f"No meu acerto T{ult['id']} (nível {ult['nivel']}) o resultado foi: {str(ult['detalhe'] or '')[:220]}.")
    partes.append("Compare com o que você entregou; a sua próxima tentativa mostra se a conversa ajudou.")
    falar(cfg, mentor, pid, " ".join(partes), "mentoria", f"mentoria:{mid}")
    return {"mentoria": mid, "mentor": mentor, "licao": licao["id"] if licao else None,
            "tentativa_mentor": ult["id"] if ult else None}


def compartilhar_subida(cfg, pid: str, comp: str, de: int, para: int) -> dict | None:
    """Subiu de nível: conta a um colega do andar que está num nível abaixo (o que está há mais tempo nele) o que fez
    diferença — números das últimas 5 tentativas e os tipos de erro que ficaram para trás."""
    gente = organizacao.por_id(cfg)
    andar = (gente.get(pid) or {}).get("andar")
    with _tb(cfg).tx() as c:
        pares = [r for r in c.execute("SELECT funcionario, nivel, desde FROM treino_niveis WHERE competencia=? AND nivel<? "
                                      "AND funcionario<>? ORDER BY desde, funcionario", (comp, para, pid))
                 if r["funcionario"] in gente and gente[r["funcionario"]].get("andar") == andar]
        if not pares:
            return None
        ult5 = c.execute("SELECT id, acertou FROM treino_tentativas WHERE funcionario=? AND competencia=? ORDER BY id DESC LIMIT 5",
                         (pid, comp)).fetchall()
        superados = [r["tipo_erro"] for r in c.execute(
            "SELECT DISTINCT tipo_erro FROM treino_tentativas WHERE funcionario=? AND competencia=? AND acertou=0 "
            "AND tipo_erro IS NOT NULL", (pid, comp))]
        evento = c.execute("SELECT MAX(id) FROM treino_niveis_eventos WHERE funcionario=? AND competencia=?", (pid, comp)).fetchone()[0]
        ref = f"subiu:{pid}:{comp}:{para}:{evento}"
        if _ja_falado(c, ref):
            return None
    colega = pares[0]["funcionario"]
    texto = (f"{_nome(gente, colega)}, subi para o nível {para} em {_nome_comp(comp)} "
             f"({sum(r['acertou'] for r in ult5)} de {len(ult5)} certas nas últimas: "
             + ", ".join(f"T{r['id']}{'✓' if r['acertou'] else '✗'}" for r in ult5) + "). "
             + (f"O que eu superei: {', '.join(x.replace('_', ' ') for x in superados)}. " if superados else "Não errei nenhuma. ")
             + f"Você está no nível {pares[0]['nivel']} — quer revisar comigo?")
    falar(cfg, pid, colega, texto, "troca", ref)
    return {"para": colega, "ref": ref}


# =============================================================================== conversas entre áreas por fatos
def conversas_por_fatos(cfg) -> list[dict]:
    """Conversas que nascem de registros: (a) SLA das rotinas → a Bianca fala com o responsável da rotina; (b) acerto de
    uma competência num andar abaixo de 70% nas últimas 20 tentativas → o head do andar pede ao designer do caso que
    revise se o problema é do caso ou da ferramenta. Cada fato fala uma vez só (ref única)."""
    from robo import lideranca, orquestracao, treino
    from robo.rotinas import ROTINAS
    feitas = []
    try:
        sla = orquestracao.analisar_sla(cfg)
    except Exception:
        log.exception("Interações: SLA indisponível")
        sla = {"detalhes": {}, "atrasadas": [], "com_erro": [], "lentas": []}
    with _tb(cfg).tx() as c:
        for nome, motivos in sla["detalhes"].items():
            resp = ROTINAS.get(nome, ("",))[0]
            if not resp or resp == "airflow_pleno":
                continue
            ult = c.execute("SELECT MAX(id) FROM rotinas_execucoes WHERE nome=?", (nome,)).fetchone()[0]
            verif = c.execute("SELECT ultima_verificacao FROM rotinas_estado WHERE nome=?", (nome,)).fetchone()
            chaves = []
            if nome in sla["atrasadas"]:
                chaves.append(f"atraso:{verif[0] if verif else 'nunca'}")
            if nome in sla["com_erro"] or nome in sla["lentas"]:
                chaves.append(f"exec:{ult}")
            ref = f"sla:{nome}:" + "|".join(chaves)
            if _ja_falado(c, ref):
                continue
            feitas.append(("airflow_pleno", resp, f"A rotina {nome}, que é sua, está fora do SLA: {'; '.join(motivos)}. "
                           "Pode olhar? Fica registrado até voltar ao normal.", "cobranca", ref))
        for r in c.execute("SELECT DISTINCT andar, competencia FROM treino_tentativas WHERE andar IS NOT NULL").fetchall():
            janela = c.execute("SELECT id, acertou FROM treino_tentativas WHERE andar=? AND competencia=? ORDER BY id DESC LIMIT 20",
                               (r["andar"], r["competencia"])).fetchall()
            if len(janela) < 20:
                continue
            taxa = sum(x["acertou"] for x in janela) / len(janela)
            if taxa >= 0.7:
                continue
            total = c.execute("SELECT COUNT(*) FROM treino_tentativas WHERE andar=? AND competencia=?",
                              (r["andar"], r["competencia"])).fetchone()[0]
            ref = f"acuracia:{r['andar']}:{r['competencia']}:{total // 20}"  # no máximo uma conversa a cada 20 tentativas
            head = lideranca.HEAD_DO_ANDAR.get(r["andar"])
            designer = treino.CATALOGO[r["competencia"]].designer if r["competencia"] in treino.CATALOGO else None
            if not head or not designer or _ja_falado(c, ref):
                continue
            feitas.append((head, designer, f"No {r['andar']}º andar, {_nome_comp(r['competencia'])} está com {taxa:.0%} de acerto "
                           f"nas últimas 20 tentativas (T{janela[-1]['id']}–T{janela[0]['id']}). Pode revisar se o problema está "
                           "nos casos ou na ferramenta antes de cobrarmos as pessoas?", "revisao", ref))
    for de, para, texto, tipo, ref in feitas:
        falar(cfg, de, para, texto, tipo, ref)
    return [{"de": d, "para": p, "tipo": t, "ref": rf} for d, p, _, t, rf in feitas]


def resumo(cfg) -> dict:
    """Para o celular e o painel: volume de conversas por tipo, mentores que mais ajudam e mentorias em aberto."""
    agora = datetime.now()
    d1 = (agora - timedelta(hours=24)).isoformat(timespec="seconds")
    d7 = (agora - timedelta(days=7)).isoformat(timespec="seconds")
    gente = organizacao.por_id(cfg)
    with _tb(cfg).tx() as c:
        por_tipo_24h = {r["tipo"]: r["n"] for r in c.execute(
            "SELECT tipo, COUNT(*) n FROM interacoes WHERE data_hora>=? GROUP BY tipo", (d1,))}
        por_tipo_7d = {r["tipo"]: r["n"] for r in c.execute(
            "SELECT tipo, COUNT(*) n FROM interacoes WHERE data_hora>=? GROUP BY tipo", (d7,))}
        mentores = [dict(r) for r in c.execute(
            "SELECT mentor, SUM(situacao='ajudou') ajudou, SUM(situacao IN ('ajudou','nao_ajudou')) fechadas FROM mentorias "
            "GROUP BY mentor HAVING fechadas > 0 ORDER BY 1.0 * ajudou / fechadas DESC, fechadas DESC LIMIT 5")]
        abertas = [dict(r) for r in c.execute("SELECT id, data_hora, mentor, aprendiz, competencia, nivel FROM mentorias "
                                             "WHERE situacao='aberta' ORDER BY id DESC LIMIT 20")]
        n_abertas = c.execute("SELECT COUNT(*) FROM mentorias WHERE situacao='aberta'").fetchone()[0]
    for m in mentores:
        m["nome"], m["taxa"] = _nome(gente, m["mentor"]), round(m["ajudou"] / m["fechadas"], 2)
    for m in abertas:
        m["mentor_nome"], m["aprendiz_nome"] = _nome(gente, m["mentor"]), _nome(gente, m["aprendiz"])
    return {"ultimas_24h": sum(por_tipo_24h.values()), "por_tipo_24h": por_tipo_24h, "ultimos_7d": sum(por_tipo_7d.values()),
            "por_tipo_7d": por_tipo_7d, "melhores_mentores": mentores, "mentorias_abertas": n_abertas,
            "abertas": abertas, "recentes": recentes(cfg, 10)}
