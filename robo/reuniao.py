"""Reunião semanal da liderança: o que deu certo, o que deu errado e o plano de ação, andar por andar.

Tudo sai de dados registrados na semana (histórico do pipeline, tarefas, experiências e handovers); nada é escrito à
mão nem inventado. A ata fica em logs/trabalho.db (tabela reunioes) e em logs/reunioes/AAAA-MM-DD.md, o resumo vai para
o canal #lideranca e cada ação vira item do backlog da Estratégia (com o líder do andar como responsável).

Desempenho:
  - insuficiente na 1ª reunião → plano de melhoria (PDI): treinamento da trilha + reavaliação na reunião seguinte;
  - insuficiente de novo → a liderança PROPÕE o desligamento; só o dono decide (aprovação na central);
  - só contratados podem ser desligados; cargo fixo com desempenho ruim é defeito de código → handover para a TI.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from robo import memoria, organizacao
from robo.trabalho import Trabalho, _agora

log = logging.getLogger("robo")
DIAS = 7


def _historico_periodo(cfg, desde: datetime, ate: datetime) -> list[dict]:
    from robo import historico
    ini, fim = desde.isoformat(sep=" ", timespec="seconds"), ate.isoformat(sep=" ", timespec="seconds")
    return [h for h in historico.ler(cfg.logs) if ini <= str(h.get("data_hora", "")).replace("T", " ") <= fim]


def _handovers_do_historico(cfg, hist: list[dict], tb: Trabalho) -> None:
    """Toda planilha reprovada da semana tem os seus erros como handover, mesmo as processadas antes de existir a
    memória (ou com o painel fechado). Não duplica: o mesmo erro da mesma base só soma recorrência uma vez por
    execução, porque a execução fica marcada como já lida."""
    from robo import historico
    ja = {m["chave"] for m in tb.memorias("handover_execucao", limite=100_000)}
    for h in hist:
        if h.get("status") != "reprovado" or not h.get("id") or h["id"] in ja:
            continue
        exe = historico.ler_execucao(Path(cfg.logs), h["id"]) or {}
        base = memoria._base(h.get("arquivo", ""))
        for o in exe.get("ocorrencias") or []:
            if o.get("nivel") == "ERRO":
                texto = o["mensagem"] + (f" (coluna {o['coluna']})" if o.get("coluna") else "")
                memoria.handover(cfg, texto, base, "validacao", ", ".join(o.get("exemplos") or [])[:300], tb)
        tb.lembrar("handover_execucao", h["id"], f"Erros de {h.get('arquivo')} viraram handover", "reuniao_semanal")


def _ultima(tb: Trabalho) -> dict | None:
    with tb.tx() as c:
        r = c.execute("SELECT * FROM reunioes ORDER BY fim DESC, rowid DESC LIMIT 1").fetchone()
    return dict(r) | {"ata": json.loads(r["ata"])} if r else None


def gerar(cfg, ate: datetime | None = None, publicar: bool = True, registrar: bool = True) -> dict:
    """registrar=False é a reunião AO VIVO: mesmos números, calculados agora, sem gravar ata, sem decidir PDI e sem
    abrir proposta de desligamento (essas decisões só na reunião semanal oficial)."""
    ate = ate or datetime.now()
    desde = ate - timedelta(days=DIAS)
    tb = Trabalho(cfg)
    anterior = _ultima(tb)
    em_pdi_antes = set((anterior or {}).get("ata", {}).get("pdi", [])) if anterior else set()
    hist = _historico_periodo(cfg, desde, ate)
    _handovers_do_historico(cfg, hist, tb)
    tarefas = [t for t in tb.listar(dias=None, limite=5000) if desde.isoformat() <= t["criada_em"] <= ate.isoformat(timespec="seconds")
               and t["tipo"] != "conversa"]
    desemp = {d["id"]: d for d in memoria.desempenho(cfg, DIAS, ate)}
    gente = organizacao.por_id(cfg)
    andares = []
    acoes_todas = []
    for andar in sorted(organizacao.NOME_ANDAR):
        lider = organizacao.lider_do_andar(andar)
        membros = [p for p in gente.values() if p["andar"] == andar]
        ids = {p["id"] for p in membros}
        t_andar = [t for t in tarefas if t.get("andar") == andar or (t["origem"] == "automatica" and andar == 1)]
        certo, errado = [], []
        if andar == 1:
            ok = [h for h in hist if h.get("status") == "sucesso"]
            ruim = [h for h in hist if h.get("status") == "reprovado"]
            if ok:
                certo.append(f"{len(ok)} planilha(s) publicada(s), {sum(int(h.get('linhas_saida') or 0) for h in ok):,} linhas"
                             .replace(",", "."))
            if ruim:
                errado.append(f"{len(ruim)} planilha(s) reprovada(s): " + ", ".join(sorted({h['arquivo'] for h in ruim})[:5]))
        concl = [t for t in t_andar if t["estado"] == "concluida"]
        parc = [t for t in t_andar if t["estado"] == "concluida_parcialmente"]
        falhas = [t for t in t_andar if t["estado"] == "falhou" and t["origem"] != "automatica"]
        if concl:
            certo.append(f"{len(concl)} tarefa(s) concluída(s) e aprovada(s) na revisão")
        if parc:
            errado.append(f"{len(parc)} tarefa(s) concluída(s) só em parte: " + "; ".join(t["titulo"][:60] for t in parc[:3]))
        if falhas:
            errado.append(f"{len(falhas)} tarefa(s) falharam: " + "; ".join(t["titulo"][:60] for t in falhas[:3]))
        destaques = sorted((desemp[i] for i in ids if i in desemp and desemp[i]["acertos"]), key=lambda d: -d["acertos"])[:3]
        certo += [f"{d['nome']}: {d['acertos']} acerto(s)" for d in destaques]
        hos = memoria.handovers(cfg, andar, abertos=True, limite=50)
        semana = [h for h in hos if h["ultima_ocorrencia"] >= desde.isoformat()]
        errado += [f"{h['erro'][:120]} ({h['recorrencias']}x) — por quê: {h['por_que_aconteceu'][:160]} "
                   f"Por que não foi resolvido: {h['por_que_nao_resolvido']}"
                   + (f" ESCALADO para {h['escalado_para']} (repetiu {h['recorrencias']} vezes)." if h["escalado"] else "")
                   for h in semana[:5]]
        acoes = []
        for h in semana[:5]:
            resp = h["responsavel"] if h["responsavel"] in gente else lider
            acoes.append({"acao": h["regra"], "motivo": f"{h['id']}: {h['erro'][:150]}", "responsavel": resp,
                          "quem_precisa_agir": h["quem_precisa_agir"], "simples": h["simples"],
                          "responsavel_nome": (gente.get(resp) or {}).get("nome", resp),
                          "verificacao": h["como_verificar"], "prazo": (ate + timedelta(days=DIAS)).strftime("%d/%m/%Y"),
                          "handover": h["id"], "andar": andar})
        andamento = [t for t in tb.listar(andar=andar, limite=200) if t["estado"] not in
                     ("concluida", "concluida_parcialmente", "falhou", "cancelada") and t["tipo"] != "conversa"]
        andares.append({"andar": andar, "nome": organizacao.NOME_ANDAR[andar], "lider": lider,
                        "pdca": memoria.resumo_pdca(cfg, andar),
                        "agora": [f"{t['id']} — {t['titulo'][:80]} ({t['estado_nome']})" for t in andamento[:10]],
                        "lider_nome": (gente.get(lider) or {}).get("nome", lider), "deu_certo": certo or ["Sem entrega registrada na semana"],
                        "deu_errado": errado or ["Nenhum erro registrado na semana"], "plano_de_acao": acoes})
        acoes_todas += acoes

    insuf = [d for d in desemp.values() if d["situacao"] == "insuficiente"]
    pdi, propostas, defeitos = [], [], []
    if not registrar:
        return {"id": None, "ao_vivo": True, "inicio": desde.isoformat(timespec="seconds"),
                "fim": ate.isoformat(timespec="seconds"), "andares": andares,
                "em_risco": [{"id": d["id"], "nome": d["nome"], "taxa": d["taxa"], "andar": d["andar"]} for d in insuf]}
    for d in insuf:
        if not d["pode_ser_desligado"]:
            defeitos.append(d["id"])
            memoria.handover(cfg, f"Desempenho insuficiente de cargo fixo {d['nome']} ({d['taxa']}% de acerto): "
                                  + "; ".join(d["ultimos_erros"]), d["id"], "reuniao_semanal", tb=tb)
        elif d["id"] in em_pdi_antes:
            propostas.append(d["id"])
        else:
            pdi.append(d["id"])
    aprovacoes = []
    if propostas:
        sid = tb.criar_solicitacao("tarefa", "Desligamentos propostos na reunião semanal", "Desempenho insuficiente em duas reuniões "
                                   "seguidas: " + ", ".join(propostas), "automatica", "canal_helena", 4, "alta", modelo="desligamento")
        tb.mudar_estado(sid, "em_triagem", "canal_helena")
        tb.mudar_estado(sid, "planejada", "canal_helena", plano={"desligar": propostas})
        tb.mudar_estado(sid, "aguardando_aprovacao", "canal_helena")
        for pid in propostas:
            d = desemp[pid]
            aprovacoes.append(tb.pedir_aprovacao(sid, f"Desligar {d['nome']}: {d['taxa']}% de acerto em {d['eventos']} evento(s), "
                                                      "já esteve em plano de melhoria", "alto", "canal_helena",
                                                 etapa_id=f"desligar:{pid}"))
    promocoes = _sugerir_promocoes(cfg, tb, ate, pdi)
    ata = {"inicio": desde.isoformat(timespec="seconds"), "fim": ate.isoformat(timespec="seconds"), "andares": andares,
           "promocoes_sugeridas": promocoes, "pdi": pdi, "propostas_desligamento": propostas, "defeitos_de_codigo": defeitos, "aprovacoes": aprovacoes,
           "desempenho": sorted(desemp.values(), key=lambda d: (d["taxa"] is None, d["taxa"] or 0))}
    rid = f"REU-{ate:%Y%m%d-%H%M%S}"
    arq = _gravar_md(cfg, rid, ata, gente)
    with tb.tx() as c:
        c.execute("INSERT INTO reunioes (id, inicio, fim, data_hora, ata, arquivo) VALUES (?,?,?,?,?,?)",
                  (rid, ata["inicio"], ata["fim"], _agora(), json.dumps(ata, ensure_ascii=False, default=str), str(arq)))
    if publicar:
        _publicar(cfg, ata, acoes_todas, gente)
    for pid in pdi:
        memoria.experiencia(cfg, pid, "treinamento", "Entrou em plano de melhoria (PDI) na reunião semanal", "reuniao", rid, tb=tb)
    return {"id": rid, "arquivo": str(arq), **ata}


def _gravar_md(cfg, rid, ata, gente) -> Path:
    nome = lambda x: (gente.get(x) or {}).get("nome", x)  # noqa: E731
    md = [f"# Reunião semanal da liderança — {ata['fim'][:10]}", "",
          f"Período: {ata['inicio'][:10]} a {ata['fim'][:10]}. Gerada a partir dos dados registrados (nada escrito à mão).", ""]
    for a in ata["andares"]:
        md += [f"## {a['andar']}º andar — {a['nome']} (líder: {a['lider_nome']})", "", "**Deu certo**", ""]
        md += [f"- {x}" for x in a["deu_certo"]] + ["", "**Deu errado**", ""] + [f"- {x}" for x in a["deu_errado"]]
        md += ["", "**Plano de ação**", ""]
        md += [f"- {x['acao']} — responsável: {nome(x['responsavel'])}; prazo {x['prazo']}; como verificar: {x['verificacao']} "
               f"({x['handover']})" for x in a["plano_de_acao"]] or ["- Nada novo a corrigir nesta semana"]
        md.append("")
    md += ["## Desempenho", ""]
    if ata["pdi"]:
        md.append("Plano de melhoria (PDI): " + ", ".join(nome(x) for x in ata["pdi"]))
    if ata["propostas_desligamento"]:
        md.append("Desligamento PROPOSTO (decisão sua, na central de solicitações): "
                  + ", ".join(nome(x) for x in ata["propostas_desligamento"]))
    if ata["defeitos_de_codigo"]:
        md.append("Cargo fixo com desempenho ruim = defeito de código, enviado à TI: " + ", ".join(nome(x) for x in ata["defeitos_de_codigo"]))
    if not (ata["pdi"] or ata["propostas_desligamento"] or ata["defeitos_de_codigo"]):
        md.append("Ninguém com desempenho insuficiente na semana (mínimo de "
                  f"{memoria.MINIMO_EVENTOS} eventos e {memoria.TAXA_MINIMA:.0f}% de acerto).")
    pasta = Path(cfg.logs) / "reunioes"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"{rid}.md"
    arq.write_text("\n".join(md) + "\n", encoding="utf-8")
    return arq


def _publicar(cfg, ata, acoes, gente):
    try:
        from robo.canal import Canal
        canal = Canal(cfg)
        for a in ata["andares"]:
            texto = (f"Reunião semanal — {a['andar']}º andar. Deu certo: {'; '.join(a['deu_certo'][:3])}. "
                     f"Deu errado: {'; '.join(a['deu_errado'][:3])}. Ações: {len(a['plano_de_acao'])}.")
            canal.postar(a["lider"] if a["lider"] in gente else "canal_helena", texto, "lideranca", tipo="reuniao")
    except Exception:
        log.exception("Não consegui publicar a reunião no canal")
    try:
        from robo import estrategia
        tb = Trabalho(cfg)
        for x in acoes:
            with tb.tx() as c:
                ja = c.execute("SELECT backlog_id FROM handovers WHERE id=?", (x["handover"],)).fetchone()
            if ja and ja["backlog_id"]:
                continue
            item = estrategia.salvar_item(cfg, {"titulo": x["acao"][:200], "motivo": x["motivo"], "responsavel": x["responsavel"],
                                                "andar": x["andar"], "impacto": 4, "urgencia": 4, "esforco": 2})
            with tb.tx() as c:
                c.execute("UPDATE handovers SET backlog_id=?, estado=CASE WHEN estado='aberto' THEN 'em_aplicacao' ELSE estado END "
                          "WHERE id=?", (item["id"], x["handover"]))
    except Exception:
        log.exception("Não consegui levar o plano de ação para o backlog")


PROMOCAO_MIN_EVENTOS, PROMOCAO_MIN_TAXA = 20, 95.0


def _sugerir_promocoes(cfg, tb, ate, pdi) -> list[dict]:
    """Contratados com 20+ trabalhos em 30 dias, 95%+ de acerto e sem PDI: a liderança sugere, o dono decide."""
    from robo.rh import NIVEIS
    sugestoes = []
    for d in memoria.desempenho(cfg, 30, ate):
        if not d["pode_ser_desligado"] or d["id"] in pdi or d["eventos"] < PROMOCAO_MIN_EVENTOS or (d["taxa"] or 0) < PROMOCAO_MIN_TAXA:
            continue
        atual = organizacao.nivel_de(d["id"], organizacao.por_id(cfg).get(d["id"]))
        if atual not in NIVEIS or NIVEIS.index(atual) == len(NIVEIS) - 1:
            continue
        sugestoes.append({"id": d["id"], "nome": d["nome"], "de": atual, "para": NIVEIS[NIVEIS.index(atual) + 1],
                          "taxa": d["taxa"], "eventos": d["eventos"]})
    if sugestoes:
        sid = tb.criar_solicitacao("tarefa", "Promoções sugeridas na reunião semanal", "Critérios: 20+ trabalhos em 30 dias, "
                                   "95%+ de acerto, sem plano de melhoria", "automatica", "dir_pessoas", 4, "media", modelo="promocao")
        tb.mudar_estado(sid, "em_triagem", "dir_pessoas")
        tb.mudar_estado(sid, "planejada", "dir_pessoas", plano={"promover": sugestoes})
        tb.mudar_estado(sid, "aguardando_aprovacao", "dir_pessoas")
        for x in sugestoes:
            x["aprovacao"] = tb.pedir_aprovacao(sid, f"Promover {x['nome']} de {x['de']} para {x['para']}: {x['taxa']}% de acerto "
                                                     f"em {x['eventos']} trabalho(s) nos últimos 30 dias", "medio", "dir_pessoas",
                                                etapa_id=f"promover:{x['id']}:{x['para']}")
    return sugestoes


def decidir_promocao(cfg, aprovacao_id: str, aprovado: bool, motivo: str = "") -> dict:
    """Promoção aprovada pelo dono: o RH reaplica o processo seletivo no nível novo antes de efetivar."""
    tb = Trabalho(cfg)
    a = tb.decidir(aprovacao_id, aprovado, "dono", motivo)
    _, pid, novo = (str(a.get("etapa_id") or "") + "::").split(":")[:3]
    feito, recusa = False, ""
    if aprovado and pid:
        from robo.agentes import ErroAgente
        from robo.pipeline import obter_equipe
        equipe = obter_equipe(cfg)
        agente = next((x for x in equipe.personalizados if x["id"] == pid), None)
        if not agente:
            recusa = "funcionário não encontrado entre os contratados"
        else:
            try:
                equipe.salvar({**agente, "nivel": novo})
                feito = True
                memoria.experiencia(cfg, pid, "treinamento", f"Promovido(a) a {novo} (decisão do dono)", "rh", aprovacao_id, tb=tb)
            except ErroAgente as e:
                recusa = f"o processo seletivo no nível {novo} não aprovou: {e}"
                memoria.experiencia(cfg, pid, "aprendizado", f"Promoção a {novo} barrada pelo processo seletivo", "rh",
                                    aprovacao_id, recusa, tb)
    s = tb.solicitacao(a["solicitacao_id"])
    if s and not [x for x in s["aprovacoes"] if x["estado"] == "pendente"] and s["estado"] == "aguardando_aprovacao":
        tb.mudar_estado(s["id"], "na_fila", "dono")
        tb.mudar_estado(s["id"], "em_execucao", "dono")
        tb.mudar_estado(s["id"], "concluida", "dono", "Decisões de promoção registradas")
    return {**a, "promovido": feito, "motivo_recusa": recusa}


def decidir_desligamento(cfg, aprovacao_id: str, aprovado: bool, motivo: str = "") -> dict:
    """Decisão do dono sobre uma proposta de desligamento. Só contratados são desligados de verdade."""
    tb = Trabalho(cfg)
    a = tb.decidir(aprovacao_id, aprovado, "dono", motivo)
    pid = str(a.get("etapa_id") or "").removeprefix("desligar:")
    feito = False
    if aprovado and pid:
        from robo.pipeline import obter_equipe
        equipe = obter_equipe(cfg)
        if any(x["id"] == pid for x in equipe.personalizados):
            equipe.excluir(pid)
            feito = True
            memoria.experiencia(cfg, pid, "erro", "Desligado por desempenho (decisão do dono)", "reuniao", aprovacao_id, motivo, tb)
    s = tb.solicitacao(a["solicitacao_id"])
    if s and not [x for x in s["aprovacoes"] if x["estado"] == "pendente"] and s["estado"] == "aguardando_aprovacao":
        tb.mudar_estado(s["id"], "na_fila", "dono")
        tb.mudar_estado(s["id"], "em_execucao", "dono")
        tb.mudar_estado(s["id"], "concluida", "dono", "Decisões de desligamento registradas")
    return {**a, "desligado": feito}


def rotina(cfg) -> dict | None:
    """Uma reunião por semana (chamada pelas rotinas do robô)."""
    tb = Trabalho(cfg)
    u = _ultima(tb)
    if u and datetime.fromisoformat(u["data_hora"]) > datetime.now() - timedelta(days=DIAS):
        return None
    return gerar(cfg)


def ao_vivo(cfg, andar: int | None = None) -> dict:
    """Reunião em tempo real: a situação de agora, sem gravar nada. Com `andar`, só a daquele coordenador."""
    r = gerar(cfg, publicar=False, registrar=False)
    if andar:
        r["andares"] = [a for a in r["andares"] if a["andar"] == int(andar)]
        r["em_risco"] = [d for d in r["em_risco"] if d["andar"] == int(andar)]
    return r


def listar(cfg, limite: int = 20) -> list[dict]:
    with Trabalho(cfg).tx() as c:
        return [dict(r) | {"ata": json.loads(r["ata"])} for r in
                c.execute("SELECT * FROM reunioes ORDER BY data_hora DESC LIMIT ?", (limite,))]
