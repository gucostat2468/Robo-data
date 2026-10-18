"""Sala de reunião (estilo Teams): o dono conversa com a liderança de um andar, todos na tela ao mesmo tempo.

Ao abrir, cada participante fala a sua parte, com dados do momento:
  diretor(a) — o scorecard da área (farol e o que está vermelho);
  head       — a última auditoria por amostragem;
  gerente/coordenação — o que deu certo, o que deu errado e o plano de ação;
  laboratório — o que a equipe treinou e errou na semana.
Depois, cada mensagem do dono vai para quem ele escolher (clicando na tela da pessoa ou citando o nome) — ou para a
coordenação. A reunião é uma conversa com vários participantes: fica registrada e continua depois de reiniciar.

Recursos do Teams reproduzidos (engenharia reversa; ver documentacao/sala_teams.md):
  levantar a mão  — quem tem assunto real levanta (farol vermelho, auditoria reprovada, handover aberto, desempenho
                    abaixo da exigência); a fila é por ordem de chegada e você dá a palavra;
  reações         — curtir, amei, aplausos, risada, surpresa em cada fala;
  participantes   — convidar qualquer funcionário (ele se apresenta pelo contrato) e remover (menos quem conduz);
  compartilhar    — Raio-X, scorecard, PDCA, laboratório ou a última base processada vão para o palco;
  anotações, pauta, tarefas (viram solicitações de verdade na central) e o resumo ao encerrar (recap), salvo em
  logs/reunioes/sala_<id>.md e na tabela salas_encerradas (separada de reunioes, que é a reunião semanal da liderança).
Cada ação vira um registro em sala_eventos, que o banco não deixa apagar nem alterar.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from robo import lideranca, organizacao
from robo.trabalho import Trabalho, _agora

REACOES = {"curtir": "👍", "amei": "❤️", "aplausos": "👏", "risada": "😂", "surpresa": "😮"}
COMPARTILHAVEIS = {"raio_x": "Raio-X da empresa", "scorecard": "Scorecard da diretoria", "pdca": "PDCA da empresa",
                   "laboratorio": "Laboratório da semana", "base": "Última base processada"}
ESQUEMA = """CREATE TABLE IF NOT EXISTS sala_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, conversa_id TEXT, data_hora TEXT, quem TEXT, tipo TEXT, dados TEXT);
CREATE INDEX IF NOT EXISTS ix_sala_ev ON sala_eventos(conversa_id, id);
CREATE TRIGGER IF NOT EXISTS sala_eventos_sem_apagar BEFORE DELETE ON sala_eventos
BEGIN SELECT RAISE(ABORT, 'registro da reunião é permanente'); END;
CREATE TRIGGER IF NOT EXISTS sala_eventos_sem_alterar BEFORE UPDATE ON sala_eventos
BEGIN SELECT RAISE(ABORT, 'registro da reunião é permanente'); END;
CREATE TABLE IF NOT EXISTS salas_encerradas (
  id TEXT PRIMARY KEY, andar INTEGER, inicio TEXT, fim TEXT, recap TEXT, arquivo TEXT);
CREATE TRIGGER IF NOT EXISTS salas_encerradas_sem_apagar BEFORE DELETE ON salas_encerradas
BEGIN SELECT RAISE(ABORT, 'ata de reunião é permanente'); END;"""


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        from robo.trabalho import proteger
        proteger(c)
    return tb


def _evento(tb: Trabalho, cid: str, quem: str, tipo: str, dados: dict | None = None) -> None:
    with tb.tx() as c:
        c.execute("INSERT INTO sala_eventos (conversa_id, data_hora, quem, tipo, dados) VALUES (?,?,?,?,?)",
                  (cid, _agora(), quem, tipo, json.dumps(dados or {}, ensure_ascii=False, default=str)))


def eventos(cfg, cid: str) -> list[dict]:
    with _tb(cfg).tx() as c:
        return [dict(r) | {"dados": json.loads(r["dados"] or "{}")} for r in
                c.execute("SELECT * FROM sala_eventos WHERE conversa_id=? ORDER BY id", (cid,))]


def _sala(cfg, cid: str, aberta: bool = True) -> tuple[Trabalho, dict]:
    tb = _tb(cfg)
    conv = tb.conversa(cid)
    if not conv or not conv["contexto"].get("sala"):
        raise ValueError("Reunião não encontrada.")
    if aberta and conv["contexto"].get("encerrada"):
        raise ValueError("Esta reunião já foi encerrada. Abra uma nova.")
    return tb, conv


def participantes(andar: int) -> list[str]:
    from robo.contratacao import LIDER_DO_ANDAR
    from robo import quadro
    gerentes = [p["id"] for p in quadro.QUADRO if p["andar"] == andar and p["nivel"] == "gerente"]
    if andar == 3:
        gerentes = ["excel_supervisor"]
    ids = [lideranca.DIRETOR_DO_ANDAR.get(andar), lideranca.HEAD_DO_ANDAR.get(andar)] + gerentes + [LIDER_DO_ANDAR.get(andar)]
    if andar == 4:
        ids += ["dir_pessoas", "head_rh"]
    if andar == 5:
        ids += ["head_python"]
    vistos = []
    for i in ids:
        if i and i not in vistos:
            vistos.append(i)
    return vistos


def abrir(cfg, andar: int) -> dict:
    from robo import auditoria, ferramentas, interacoes, reuniao
    andar = int(andar)
    gente = organizacao.por_id(cfg)
    ps = [p for p in participantes(andar) if p in gente]
    lider = next((p for p in reversed(ps) if organizacao.nivel_de(p, gente[p]) == "coordenador"), ps[-1])
    tb = Trabalho(cfg)
    cid = tb.criar_conversa(lider, f"Reunião do {andar}º andar — {organizacao.NOME_ANDAR.get(andar, '')}", "reuniao",
                            {"participantes": ps, "andar": andar, "sala": True})
    tb.mensagem(cid, "dono", f"Abri a reunião do {andar}º andar. Quero saber de tudo o que está acontecendo.")

    def fala(autor, r):
        tb.mensagem(cid, autor, r["texto"], r["natureza"], r)
        interacoes.balao(autor, r["texto"].split("\n")[0].replace("**", "")[:120], rotulo="reunião")

    diretor = lideranca.DIRETOR_DO_ANDAR.get(andar)
    if diretor in ps:
        fala(diretor, ferramentas.executar("scorecard", cfg, quem=diretor, andar=andar))
    if andar == 4 and "dir_pessoas" in ps:
        fala("dir_pessoas", ferramentas.executar("scorecard", cfg, quem="dir_pessoas"))
    head = lideranca.HEAD_DO_ANDAR.get(andar)
    if head in ps:
        ult = next((a for a in auditoria.listar(cfg, 50) if a["head"] == head), None)
        texto = (auditoria.texto({**ult, "sem_amostra": not ult["amostra"]}) if ult else
                 "Ainda não fiz a auditoria por amostragem desta área. Ela roda uma vez por semana; se quiser, "
                 "peça agora: “faça a auditoria”.")
        fala(head, ferramentas.resultado(True, "ferramenta", texto, evidencia="última auditoria registrada"))
    v = reuniao.ao_vivo(cfg, andar)["andares"]
    if v:
        a = v[0]
        plano = "; ".join(f"{x['acao'][:90]} ({x.get('quem_precisa_agir') or x['responsavel']})" for x in a["plano_de_acao"][:3])
        texto = (f"Deu certo: {'; '.join(a['deu_certo'][:3])}.\n\n## Deu errado\n" + "\n".join(f"• {x}" for x in a["deu_errado"][:5])
                 + f"\n\n## Plano de ação\n{plano or 'Nada novo a corrigir.'}\n\n## Em andamento agora\n"
                 + ("\n".join(a["agora"]) or "Nada em andamento."))
        fala(lider, ferramentas.resultado(True, "ferramenta", texto, evidencia="histórico, memória, handovers e central (agora)"))
    lab = ferramentas.executar("laboratorio", cfg, quem=lideranca.HEAD_DO_ANDAR.get(andar) or lider)
    if lab["ok"]:
        fala(head if head in ps else lider, lab)
    # cobrança: a reunião começa pelo que foi decidido antes e ainda não está cumprido (situação apurada pelos registros)
    from robo import decisoes
    decisoes.atualizar(cfg)
    pend = decisoes.listar(cfg, andar, abertas=True)
    if pend:
        icone = {"atrasada": "🔴", "em_andamento": "🟡"}
        texto = (f"Pendências das reuniões anteriores ({len(pend)}). As atrasadas precisam ser tratadas hoje: novo prazo "
                 f"com motivo ou cancelamento com motivo.\n" + "\n".join(
                     f"{icone[d['estado']]} {d['id']} — {d['texto'][:140]} · dono {d['dono_nome']} · prazo "
                     f"{date.fromisoformat(d['prazo']):%d/%m/%Y} ({'atrasada há ' + str(-d['dias_para_o_prazo']) + ' dia(s)' if d['dias_para_o_prazo'] < 0 else 'faltam ' + str(d['dias_para_o_prazo']) + ' dia(s)'})"
                     f" · pronto quando: {d['criterio'][:120]}" + (f" · repactuada {d['repactuacoes']}x" if d["repactuacoes"] else "")
                     for d in pend))
        fala(lider, ferramentas.resultado(True, "ferramenta", texto, evidencia="decisões registradas e situação apurada agora"))
        for d in pend:
            decisoes.cobrar(cfg, d["id"], cid, lider, d["estado"])
    _tb(cfg)
    _evento(tb, cid, "dono", "abrir", {"andar": andar, "participantes": ps, "pendencias": [d["id"] for d in pend]})
    filas = levantar_maos(cfg, cid)
    return {"conversa_id": cid, "participantes": ps, "lider": lider, "maos": filas}


# ------------------------------------------------------------------ mão levantada (com motivo real)
def _motivo(cfg, pid: str, andar: int, evolucao: dict | None = None) -> tuple[str, str] | None:
    """Por que esta pessoa tem algo a dizer agora (só dado gravado). Devolve (motivo curto, fala completa)."""
    from robo import auditoria, memoria
    if pid in lideranca.EQUIPE and pid.startswith("dir_"):
        sc = lideranca.scorecard(cfg, pid)
        vermelhos = [i for i in sc["indicadores"] if i["farol"] == "vermelho"]
        if vermelhos:
            return (f"{len(vermelhos)} indicador(es) no vermelho",
                    "Pedi a palavra porque tenho indicador fora da meta:\n" +
                    "\n".join(f"• {i['indicador']}: {i['valor_texto']} (meta {i['meta']}; fonte: {i['fonte']})" for i in vermelhos))
    if pid in auditoria.HEADS:
        ult = next((a for a in auditoria.listar(cfg, 50) if a["head"] == pid), None)
        if ult and not ult["aprovada"]:
            return ("auditoria com achado", "Pedi a palavra porque a minha última auditoria achou problema:\n" +
                    "\n".join(f"• {x}" for x in ult["achados"][:5]))
    if organizacao.nivel_de(pid, organizacao.por_id(cfg).get(pid, {})) == "coordenador":
        abertos = memoria.handovers(cfg, andar, abertos=True, limite=50)
        # alerta de regressão da equipe: quem não está na reunião tem a queda levada pela coordenação
        piorando = sorted((e for e in (evolucao or {}).values() if e["andar"] == andar and e["tendencia"] == "piorando"
                           and e["id"] != pid), key=lambda e: e["delta_pp"])
        motivos, falas = [], []
        if abertos:
            motivos.append(f"{len(abertos)} handover(s) aberto(s) no andar")
            falas.append("O andar tem erro ainda não resolvido:\n" + "\n".join(
                f"• {h['id']} ({h['recorrencias']}x): {h['erro'][:140]} → {h['regra'][:140]} "
                f"(responsável: {h['responsavel']})" for h in abertos[:5]))
        from robo import decisoes
        atrasadas = [d for d in decisoes.listar(cfg, andar, abertas=True) if d["estado"] == "atrasada"]
        if atrasadas:
            motivos.append(f"{len(atrasadas)} decisão(ões) atrasada(s)")
            falas.append("Decisões de reunião que passaram do prazo sem estarem cumpridas:\n" + "\n".join(
                f"• {d['id']} — {d['texto'][:120]} (dono {d['dono_nome']}, prazo {d['prazo']})" for d in atrasadas[:5]))
        if piorando:
            motivos.append(f"{len(piorando)} pessoa(s) do andar com acerto em queda")
            falas.append("Gente da equipe com a taxa de acerto caindo 5 pontos ou mais (2 últimas semanas × anteriores):\n" +
                         "\n".join(f"• {e['nome']} ({e['papel']}): {e['delta_pp']:+.1f} pontos".replace(".", ",")
                                    for e in piorando[:5]) +
                         "\nVou revisar os erros recentes de cada um no caderno de lições e montar o plano de estudo.")
        if motivos:
            return " · ".join(motivos), "Pedi a palavra. " + "\n\n".join(falas)
    ev = (evolucao or {}).get(pid)
    if ev and ev["tendencia"] == "piorando":  # alerta de regressão: caiu 5 pontos ou mais (com base mínima de eventos)
        taxas = [t for t in ev["taxas_semana"] if t is not None]
        return (f"acerto caiu {abs(ev['delta_pp']):.1f} pontos".replace(".", ","),
                f"Pedi a palavra para avisar que piorei: minha taxa de acerto nas 2 últimas semanas está "
                f"{abs(ev['delta_pp']):.1f} pontos abaixo das semanas anteriores".replace(".", ",") +
                (f" (semanas: {' → '.join(f'{t:.0f}%' for t in taxas[-4:])})" if taxas else "") +
                ". Vou revisar meus erros recentes no caderno de lições e peço ajuda da coordenação.")
    d = next((x for x in memoria.desempenho(cfg) if x["id"] == pid), None)
    if d and d.get("situacao") == "insuficiente":
        return ("desempenho abaixo da exigência", f"Pedi a palavra para ser transparente: minha taxa de acerto está em "
                f"{d['taxa']}% ({d['acertos']} acertos, {d['erros']} erros), abaixo da exigência do cargo. Estou no plano de estudo.")
    return None


def levantar_maos(cfg, cid: str) -> list[dict]:
    tb, conv = _sala(cfg, cid)
    ctx = conv["contexto"]
    fila = list(ctx.get("maos") or [])
    ja = {m["id"] for m in fila} | set(ctx.get("maos_atendidas") or [])
    try:  # uma vez por rodada (é a mesma série da Gestão → Evolução por funcionário)
        from robo import gestao
        evol = {e["id"]: e for e in gestao.evolucao(cfg)}
    except Exception:
        evol = {}
    for pid in ctx["participantes"]:
        if pid in ja:
            continue
        m = _motivo(cfg, pid, int(ctx.get("andar") or 0), evol)
        if m:
            fila.append({"id": pid, "motivo": m[0], "fala": m[1], "desde": _agora()})
            _evento(tb, cid, pid, "mao_levantada", {"motivo": m[0]})
    tb.atualizar_contexto(cid, maos=fila)
    return fila


def dar_palavra(cfg, cid: str, pid: str) -> dict:
    """O dono dá a palavra: a pessoa fala o motivo (com os dados) e abaixa a mão."""
    from robo import ferramentas, interacoes
    tb, conv = _sala(cfg, cid)
    ctx = conv["contexto"]
    m = next((x for x in ctx.get("maos") or [] if x["id"] == pid), None)
    if not m:
        raise ValueError("Essa pessoa não está com a mão levantada.")
    r = ferramentas.resultado(True, "ferramenta", m["fala"], evidencia="dados gravados (scorecard, auditoria, handovers, memória)")
    tb.mensagem(cid, pid, r["texto"], r["natureza"], r)
    interacoes.balao(pid, r["texto"].split("\n")[0][:120], rotulo="reunião")
    tb.atualizar_contexto(cid, maos=[x for x in ctx["maos"] if x["id"] != pid],
                          maos_atendidas=list(ctx.get("maos_atendidas") or []) + [pid])
    _evento(tb, cid, "dono", "palavra", {"para": pid, "motivo": m["motivo"]})
    return {"ok": True}


# ------------------------------------------------------------------ reações, participantes, palco, notas, pauta, tarefas
def reagir(cfg, cid: str, mensagem_id: int, reacao: str, quem: str = "dono") -> dict:
    tb, _ = _sala(cfg, cid)
    if reacao not in REACOES:
        raise ValueError("Reação inválida.")
    with tb.tx() as c:
        if not c.execute("SELECT 1 FROM mensagens WHERE id=? AND conversa_id=?", (int(mensagem_id), cid)).fetchone():
            raise ValueError("Mensagem não é desta reunião.")
    _evento(tb, cid, quem, "reacao", {"mensagem": int(mensagem_id), "reacao": reacao})
    return {"ok": True}


def convidar(cfg, cid: str, pid: str) -> dict:
    tb, conv = _sala(cfg, cid)
    gente = organizacao.por_id(cfg)
    if pid not in gente:
        raise ValueError("Funcionário não existe.")
    ps = conv["contexto"]["participantes"]
    if pid in ps:
        raise ValueError(f"{gente[pid]['nome']} já está na reunião.")
    tb.atualizar_contexto(cid, participantes=ps + [pid])
    c = organizacao.contrato(pid, cfg) or {}
    escopo = "; ".join((c.get("responsabilidades") or [])[:2])
    texto = (f"Oi, entrei na reunião. Sou {gente[pid]['nome']}, {c.get('cargo') or gente[pid]['papel']} "
             f"({c.get('andar', gente[pid]['andar'])}º andar).\n\n## O que eu faço\n{escopo or 'ver meu contrato'}")
    tb.mensagem(cid, pid, texto, "conhecimento", {"evidencia": "contrato do funcionário"})
    _evento(tb, cid, "dono", "convite", {"pid": pid})
    levantar_maos(cfg, cid)
    return {"ok": True}


def remover(cfg, cid: str, pid: str) -> dict:
    tb, conv = _sala(cfg, cid)
    if pid == conv["funcionario"]:
        raise ValueError("Quem conduz a reunião não pode ser removido.")
    ps = conv["contexto"]["participantes"]
    if pid not in ps:
        raise ValueError("Essa pessoa não está na reunião.")
    tb.atualizar_contexto(cid, participantes=[p for p in ps if p != pid],
                          maos=[m for m in conv["contexto"].get("maos") or [] if m["id"] != pid])
    _evento(tb, cid, "dono", "remocao", {"pid": pid})
    return {"ok": True}


def _conteudo(cfg, tipo: str, ref: str | None, andar: int) -> tuple[str, str]:
    from robo import historico, laboratorio, memoria, raio_x
    if tipo == "raio_x":
        return COMPARTILHAVEIS[tipo], raio_x.texto(raio_x.montar(cfg))
    if tipo == "scorecard":
        d = ref if ref in lideranca.EQUIPE and str(ref).startswith("dir_") else lideranca.DIRETOR_DO_ANDAR.get(andar, "dir_dados")
        sc = lideranca.scorecard(cfg, d)
        return f"Scorecard — {sc['nome']}", sc["parecer"] + "\n" + "\n".join(
            f"{i['farol']}: {i['indicador']} = {i['valor_texto']} (meta {i['meta']})" for i in sc["indicadores"])
    if tipo == "pdca":
        r = memoria.resumo_pdca(cfg)
        return COMPARTILHAVEIS[tipo], (f"Planejar: {r['planejar']} · Fazer: {r['fazer']} · Checar: {r['checar']} · "
                                       f"Agir (virou boa prática): {r['agir']}")
    if tipo == "laboratorio":
        lab = laboratorio.resumo(cfg)
        return COMPARTILHAVEIS[tipo], (f"{lab['rodadas']} exercício(s) em {len(lab['por_area'])} área(s).\n" + "\n".join(
            f"{a}: {v}" for a, v in lab["por_area"].items()))
    if tipo == "base":
        h = historico.ler(cfg.logs, 1)
        if not h:
            return COMPARTILHAVEIS[tipo], "Nenhuma base processada ainda."
        x = h[0]
        return f"Base: {x.get('arquivo')}", "\n".join(f"{k}: {v}" for k, v in x.items() if not isinstance(v, (list, dict)))
    raise ValueError("Conteúdo não pode ser compartilhado.")


def compartilhar(cfg, cid: str, tipo: str, ref: str | None = None) -> dict:
    tb, conv = _sala(cfg, cid)
    if tipo == "parar":
        tb.atualizar_contexto(cid, palco=None)
        _evento(tb, cid, "dono", "parar_compartilhar")
        return {"palco": None}
    titulo, texto = _conteudo(cfg, tipo, ref, int(conv["contexto"].get("andar") or 0))
    palco = {"tipo": tipo, "titulo": titulo, "texto": texto, "desde": _agora()}
    tb.atualizar_contexto(cid, palco=palco)
    tb.mensagem(cid, "dono", f"📺 Compartilhei na tela: {titulo}", "", {"palco": tipo})
    _evento(tb, cid, "dono", "compartilhar", {"tipo": tipo, "titulo": titulo})
    return {"palco": palco}


def anotar(cfg, cid: str, texto: str) -> dict:
    import hashlib
    tb, _ = _sala(cfg, cid)
    tb.atualizar_contexto(cid, notas=texto[:20000])
    _evento(tb, cid, "dono", "notas", {"tamanho": len(texto), "sha256": hashlib.sha256(texto.encode()).hexdigest(), "texto": texto[:20000]})
    return {"ok": True}


def pauta(cfg, cid: str, itens: list[str] | None = None, marcar: int | None = None) -> dict:
    tb, conv = _sala(cfg, cid)
    atual = list(conv["contexto"].get("pauta") or [])
    if itens is not None:
        atual = [{"texto": str(t)[:200], "feito": False} for t in itens if str(t).strip()][:30]
        _evento(tb, cid, "dono", "pauta", {"itens": [a["texto"] for a in atual]})
    if marcar is not None and 0 <= int(marcar) < len(atual):
        atual[int(marcar)]["feito"] = not atual[int(marcar)]["feito"]
        _evento(tb, cid, "dono", "pauta_item", {"item": atual[int(marcar)]["texto"], "feito": atual[int(marcar)]["feito"]})
    tb.atualizar_contexto(cid, pauta=atual)
    return {"pauta": atual}


def decidir(cfg, cid: str, texto: str, responsavel: str, prazo, criterio: str) -> dict:
    """Decisão da reunião: dono + prazo + critério de pronto. Vira tarefa na central e é cobrada nas próximas reuniões."""
    from robo import decisoes
    tb, conv = _sala(cfg, cid)
    r = decisoes.registrar(cfg, texto, responsavel, prazo, criterio, conv["contexto"].get("andar"), cid, "sala", "dono")
    sid = r["vinculo"][1]
    tarefas = list(conv["contexto"].get("tarefas") or []) + [{"id": sid, "decisao": r["id"], "texto": texto[:300],
                                                             "responsavel": responsavel, "prazo": r["prazo"],
                                                             "criterio": criterio[:300]}]
    tb.atualizar_contexto(cid, tarefas=tarefas)
    tb.mensagem(cid, "dono", f"📌 Decisão {r['id']} — {texto} · dono {organizacao.por_id(cfg)[responsavel]['nome']} · prazo "
                             f"{date.fromisoformat(r['prazo']):%d/%m/%Y} · pronto quando: {criterio} (tarefa {sid})", "", {}, sid)
    _evento(tb, cid, "dono", "decisao", {"id": r["id"], "tarefa": sid, "responsavel": responsavel, "prazo": r["prazo"],
                                         "criterio": criterio[:300]})
    return {"id": sid, "decisao": r["id"], "prazo": r["prazo"]}


def criar_tarefa(cfg, cid: str, texto: str, responsavel: str, prazo=None, criterio: str = "") -> dict:
    """Tarefa de reunião é uma decisão: sem prazo e critério de pronto ela não é registrada (nada vago)."""
    if not prazo or not (criterio or "").strip():
        raise ValueError("Toda tarefa de reunião precisa de prazo e de critério de pronto (como vamos verificar que foi feita).")
    return decidir(cfg, cid, texto, responsavel, prazo, criterio)


def repactuar(cfg, cid: str, decisao_id: str, novo_prazo, motivo: str) -> dict:
    from robo import decisoes
    tb, conv = _sala(cfg, cid)
    r = decisoes.repactuar(cfg, decisao_id, novo_prazo, motivo, cid, "dono")
    tb.mensagem(cid, "dono", f"🗓️ {decisao_id}: novo prazo {date.fromisoformat(r['prazo']):%d/%m/%Y}. Motivo: {motivo}", "", {})
    _evento(tb, cid, "dono", "repactuar", {"id": decisao_id, "prazo": r["prazo"], "motivo": motivo[:500]})
    return r


def cancelar_decisao(cfg, cid: str, decisao_id: str, motivo: str) -> dict:
    from robo import decisoes
    tb, conv = _sala(cfg, cid)
    r = decisoes.cancelar(cfg, decisao_id, motivo, cid, "dono")
    tb.mensagem(cid, "dono", f"✖️ {decisao_id} cancelada. Motivo: {motivo}", "", {})
    _evento(tb, cid, "dono", "cancelar_decisao", {"id": decisao_id, "motivo": motivo[:500]})
    return r


# ------------------------------------------------------------------ encerrar e resumo (recap)
def encerrar(cfg, cid: str, justificativa: str = "") -> dict:
    from robo import decisoes
    import hashlib
    tb, conv = _sala(cfg, cid)
    ctx = conv["contexto"]
    pendentes = decisoes.nao_tratadas(cfg, int(ctx.get("andar") or 0), cid)
    if pendentes and len((justificativa or "").strip()) < 15:
        raise ValueError(f"Há {len(pendentes)} decisão(ões) atrasada(s) sem tratamento nesta reunião: "
                         + "; ".join(f"{d['id']} ({d['texto'][:60]})" for d in pendentes)
                         + ". Dê novo prazo com motivo, cancele com motivo, ou escreva a justificativa para encerrar assim.")
    for d in pendentes:
        with decisoes._tb(cfg).tx() as c:
            decisoes._evento(c, d["id"], "nao_tratada", d["estado"], d["estado"], "dono", cid, justificativa.strip())
    gente = organizacao.por_id(cfg)
    nome = lambda p: "Você" if p == "dono" else (gente.get(p) or {}).get("nome", p)
    msgs = conv["mensagens"]
    evs = eventos(cfg, cid)
    inicio, fim = conv["criada_em"], _agora()
    minutos = round((datetime.fromisoformat(fim) - datetime.fromisoformat(inicio)).total_seconds() / 60, 1)
    falas: dict[str, int] = {}
    for m in msgs:
        falas[m["autor"]] = falas.get(m["autor"], 0) + 1
    reacoes: dict[str, int] = {}
    for e in evs:
        if e["tipo"] == "reacao":
            reacoes[e["dados"]["reacao"]] = reacoes.get(e["dados"]["reacao"], 0) + 1
    tarefas = ctx.get("tarefas") or []
    recap = {
        "titulo": conv["titulo"], "inicio": inicio, "fim": fim, "minutos": minutos,
        "participantes": [nome(p) for p in ctx["participantes"]],
        "falas": {nome(k): v for k, v in sorted(falas.items(), key=lambda x: -x[1])},
        "maos_atendidas": [nome(p) for p in ctx.get("maos_atendidas") or []],
        "maos_sem_palavra": [f"{nome(m['id'])} ({m['motivo']})" for m in ctx.get("maos") or []],
        "tarefas": [f"{t['id']} — {nome(t['responsavel'])}: {t['texto']}" for t in tarefas],
        "pauta": [f"[{'x' if p['feito'] else ' '}] {p['texto']}" for p in ctx.get("pauta") or []],
        "compartilhado": [e["dados"]["titulo"] for e in evs if e["tipo"] == "compartilhar"],
        "reacoes": {REACOES[k]: v for k, v in reacoes.items()},
        "notas": ctx.get("notas") or "",
        "decisoes": [f"{d['id']} — {d['texto']} · dono {d['dono_nome']} · prazo {d['prazo']} · pronto quando: {d['criterio']}"
                     for d in decisoes.listar(cfg) if d["reuniao_id"] == cid],
        "pendencias_tratadas": [f"{e['decisao_id']}: {e['tipo']} ({e['detalhe'][:120]})" for e in _eventos_decisao(cfg, cid)],
        "pendencias_sem_tratamento": [f"{d['id']} — {d['texto'][:120]}" for d in pendentes],
        "justificativa": justificativa.strip(),
    }
    md = [f"# {recap['titulo']}", "", f"{inicio.replace('T', ' ')} → {fim.replace('T', ' ')} ({minutos} min)", "",
          "## Participantes", ""] + [f"- {p}" for p in recap["participantes"]]
    md += ["", "## Quem falou", ""] + [f"- {k}: {v} fala(s)" for k, v in recap["falas"].items()]
    md += ["", "## Pauta", ""] + (recap["pauta"] or ["- (sem pauta)"])
    md += ["", "## Decisões (dono, prazo e critério de pronto — cobradas nas próximas reuniões)", ""] + \
        ([f"- {d}" for d in recap["decisoes"]] or ["- nenhuma"])
    md += ["", "## Pendências anteriores tratadas", ""] + ([f"- {d}" for d in recap["pendencias_tratadas"]] or ["- nenhuma"])
    if recap["pendencias_sem_tratamento"]:
        md += ["", "## Pendências atrasadas NÃO tratadas", "", f"Justificativa registrada: {recap['justificativa']}", ""] + \
            [f"- {d}" for d in recap["pendencias_sem_tratamento"]]
    md += ["", "## Tarefas (na central de solicitações)", ""] + ([f"- {t}" for t in recap["tarefas"]] or ["- nenhuma"])
    md += ["", "## Mãos levantadas", ""] + [f"- atendida: {p}" for p in recap["maos_atendidas"]] + \
          [f"- sem palavra: {p}" for p in recap["maos_sem_palavra"]]
    md += ["", "## Compartilhado na tela", ""] + ([f"- {x}" for x in recap["compartilhado"]] or ["- nada"])
    md += ["", "## Anotações", "", recap["notas"] or "(sem anotações)", "", "## Transcrição", ""]
    md += [f"**{nome(m['autor'])}** ({m['criada_em'][11:16]}): {m['texto']}" + "\n" for m in msgs]
    pasta = Path(cfg.logs) / "reunioes"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"sala_{cid}.md"
    texto_ata = "\n".join(md) + "\n"
    arq.write_text(texto_ata, encoding="utf-8")
    recap["ata_sha256"] = hashlib.sha256(texto_ata.encode("utf-8")).hexdigest()  # prova de que a ata não foi mexida depois
    with tb.tx() as c:
        c.execute("INSERT INTO salas_encerradas (id, andar, inicio, fim, recap, arquivo) VALUES (?,?,?,?,?,?)",
                  (cid, ctx.get("andar"), inicio, fim, json.dumps(recap, ensure_ascii=False), str(arq)))
    tb.atualizar_contexto(cid, encerrada=True, recap=recap, arquivo=str(arq))
    _evento(tb, cid, "dono", "encerrar", {"minutos": minutos, "arquivo": str(arq), "ata_sha256": recap["ata_sha256"],
                                          "pendencias_sem_tratamento": [d["id"] for d in pendentes]})
    return {"recap": recap, "arquivo": str(arq)}


def _eventos_decisao(cfg, cid: str) -> list[dict]:
    from robo import decisoes
    with decisoes._tb(cfg).tx() as c:
        return [dict(r) for r in c.execute("SELECT * FROM decisoes_eventos WHERE reuniao_id=? AND tipo IN "
                                           "('repactuada','cancelada') ORDER BY id", (cid,))]


def falar(cfg, conversa_id: str, texto: str, para: str | None = None) -> dict:
    from robo import atendimento
    tb, conv = _sala(cfg, conversa_id)
    ps = conv["contexto"]["participantes"]
    gente = organizacao.por_id(cfg)
    alvo = para if para in ps else None
    if not alvo:  # citou alguém pelo nome? ("Beatriz, …", "@Eduardo …")
        t = texto.lower()
        alvo = next((p for p in ps if re.search(rf"(^|[@\s]){re.escape(gente[p]['nome'].lower())}([\s,:?!.]|$)", t)), None)
    return atendimento.conversar(cfg, alvo or conv["funcionario"], texto, conversa_id, origem="reuniao")


def detalhes(cfg, conversa_id: str) -> dict | None:
    from robo import rh
    conv = Trabalho(cfg).conversa(conversa_id)
    if not conv or not conv["contexto"].get("sala"):
        return None
    gente = organizacao.por_id(cfg)
    conv["pessoas"] = [{"id": p, "nome": gente[p]["nome"], "cargo": gente[p]["papel"], "cor": gente[p].get("cor"),
                        "nivel": rh.NOME_NIVEL.get(organizacao.nivel_de(p, gente[p]), "")}
                       for p in conv["contexto"]["participantes"] if p in gente]
    evs = eventos(cfg, conversa_id)
    reacoes: dict[int, dict[str, int]] = {}
    for e in evs:
        if e["tipo"] == "reacao":
            r = reacoes.setdefault(e["dados"]["mensagem"], {})
            r[REACOES[e["dados"]["reacao"]]] = r.get(REACOES[e["dados"]["reacao"]], 0) + 1
    for m in conv["mensagens"]:
        m["reacoes"] = reacoes.get(m["id"], {})
    from robo.trabalho import Trabalho as _T
    tb = _T(cfg)
    for t in conv["contexto"].get("tarefas") or []:
        sol = tb.solicitacao(t["id"]) if hasattr(tb, "solicitacao") else None
        t["estado"] = (sol or {}).get("estado", "")
    from robo import decisoes
    conv["decisoes_pendentes"] = decisoes.listar(cfg, conv["contexto"].get("andar"), abertas=True)
    conv["eventos"] = evs[-200:]
    conv["reacoes_disponiveis"] = REACOES
    conv["compartilhaveis"] = COMPARTILHAVEIS
    return conv
