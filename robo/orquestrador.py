"""Orquestrador: transforma um objetivo em plano, executa etapa por etapa com ferramentas reais e manda revisar.

Fluxo de uma tarefa:
  recebida → em triagem → planejada → (aguardando aprovação) → na fila → em execução → em revisão
  → concluída | concluída parcialmente | reprovada na revisão → em correção → … | falhou | bloqueada | cancelada

Regras:
  - cada etapa tem responsável, ferramenta, dependências e risco; o responsável precisa ter a ferramenta no contrato
    (robo/organizacao.py). Se não tiver, a etapa vai para quem tem; se ninguém tiver, a etapa fica BLOQUEADA;
  - etapa que altera dados só roda depois da aprovação do dono (ninguém aprova o próprio pedido);
  - etapa sem ferramenta no robô (ex.: gerar .pptx) fica bloqueada com a explicação e a tarefa termina
    "concluída parcialmente" — nunca "concluída" de mentira;
  - no fim, um REVISOR INDEPENDENTE (nunca quem executou) confere: toda etapa concluída tem evidência, artefatos
    existem e cálculos são refeitos por outra pessoa e comparados.
Os planos são modelos determinísticos (sem IA): o mesmo pedido gera sempre o mesmo plano.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime
from pathlib import Path

from robo import ferramentas, organizacao
from robo.trabalho import FINAIS, Trabalho

log = logging.getLogger("robo")

# --------------------------------------------------------------------------- modelos de plano
# etapa: (titulo, ferramenta|None, responsável preferido, índices das dependências, parâmetros)
MODELOS = {
    "verificar_planilha": {
        "titulo": "Verificar planilha", "precisa": ["arquivo"], "revisor": "coord_engenharia",
        "etapas": [("Diagnóstico da planilha (pipeline sem gravar + conferências do 1º andar)", "diagnosticar_planilha", "validacao", [], {}),
                   ("Verificação de dados pessoais (LGPD)", "dados_pessoais", "gov_pleno_lgpd", [], {}),
                   ("Resumo executivo do resultado", "resumo_executivo", "analise_relator", [1, 2], {})]},
    "analise_completa": {
        "titulo": "Análise completa", "precisa": [], "revisor": "coord_analise",
        "etapas": [("Diagnóstico da planilha", "diagnosticar_planilha", "validacao", [], {"_se": "arquivo"}),
                   ("Perfil, indicadores (NPS/CSAT/CES) e testes estatísticos", "perfil_indicadores", "analise_indicadores", [1], {}),
                   ("Verificação de dados pessoais (LGPD)", "dados_pessoais", "gov_pleno_lgpd", [], {}),
                   ("Resumo executivo", "resumo_executivo", "analise_relator", [2, 3], {})]},
    "apresentacao": {
        "titulo": "Apresentação executiva", "precisa": [], "revisor": "ger_analise",
        "etapas": [("Perfil, indicadores e testes estatísticos", "perfil_indicadores", "analise_indicadores", [], {}),
                   ("Resumo executivo (.md)", "resumo_executivo", "analise_relator", [1], {}),
                   ("Gerar arquivo de slides (.pptx)", None, "excel_dinamicas", [2], {})]},
    "publicar_planilha": {
        "titulo": "Publicar planilha", "precisa": ["arquivo"], "revisor": "coord_engenharia",
        "etapas": [("Diagnóstico antes de publicar", "diagnosticar_planilha", "validacao", [], {}),
                   ("Enviar para o pipeline de produção", "publicar_planilha", "recepcao", [1], {"_exige_aprovacao": True})]},
    "calculo": {
        "titulo": "Cálculo", "precisa": ["pergunta"], "revisor": "ana_pleno_recalculo",
        "etapas": [("Cálculo pedido", "calcular", "analise_estatistica", [], {})]},
    "consulta_sql": {
        "titulo": "Consulta SQL", "precisa": [], "revisor": "coord_engenharia",
        "etapas": [("Consulta no PostgreSQL (somente leitura)", "consulta_sql", "dba", [], {})]},
    "saude_sistema": {
        "titulo": "Saúde do sistema", "precisa": [], "revisor": "ger_ti",
        "etapas": [("Ronda de TI (disco, pastas, dependências, segurança, logs)", "ronda_ti", "infra_pleno", [], {}),
                   ("Resumo executivo", "resumo_executivo", "analise_relator", [1], {})]},
}

RECONHECER = [  # ordem importa: o mais específico primeiro
    ("apresentacao", r"apresenta|slides?\b|pptx|power ?point"),
    ("publicar_planilha", r"\bpubli(ca|car|que|cacao)\b|mand(a|ar|e) (para|pra) produc|sub(a|ir) (para|pra) produc"),
    ("analise_completa", r"anali[sz](e|ar|a|ise)\b.*\b(complet|planilha|arquivo|base)|analise complet|relatorio complet"),
    ("verificar_planilha", r"verifi[cq]|confer|che[cq]|diagnost|valid(a|e|ar)\b|tem (algum )?erro|esta (certa|correta|ok)"),
    ("saude_sistema", r"saude do (sistema|robo|computador)|ronda (de )?ti|o sistema esta|computador esta"),
    ("consulta_sql", r"consulta sql|rod(a|e|ar) (a )?consulta|\bsql\b"),
]
VERBO_ACAO = r"^(por favor )?(faca|faz|fazer|monte|montar|prepare|preparar|gere|gerar|crie|criar|rode|rodar|execute|" \
             r"verifique|verificar|confira|conferir|analise|analisar|publique|publicar|mande|quero|preciso|pode)\b"


def _norm(t: str) -> str:
    from robo.canal import normalizar
    return normalizar(t)


def reconhecer(texto: str) -> list[str]:
    """Modelos de plano que o pedido aciona (vários = projeto)."""
    t = _norm(texto)
    achados = []
    for modelo, rx in RECONHECER:
        if re.search(rx, t) and modelo not in achados:
            achados.append(modelo)
    if "apresentacao" in achados and "analise_completa" in achados:
        achados.remove("analise_completa")  # a apresentação já inclui a análise
    return achados


def classificar(texto: str) -> str:
    """conversa (pergunta), tarefa (um objetivo com plano) ou projeto (vários objetivos ou 'projeto')."""
    t = _norm(texto)
    modelos = reconhecer(texto)
    if re.search(r"\bprojeto\b", t) and len(modelos) >= 1 or len(modelos) >= 2 and re.search(VERBO_ACAO, t):
        return "projeto"
    if modelos and (re.search(VERBO_ACAO, t) or not t.endswith("?")):
        return "tarefa"
    return "conversa"


# --------------------------------------------------------------------------- criação
def _responsavel(ferramenta: str | None, preferido: str, cfg) -> str:
    if not ferramenta:
        return preferido
    if organizacao.pode_usar(preferido, ferramenta, cfg, producao=True):
        return preferido
    return organizacao.quem_usa(ferramenta, cfg) or preferido


def planejar(modelo: str, cfg, params: dict) -> list[dict]:
    m = MODELOS[modelo]
    etapas = []
    mapa = {}  # índice do modelo → índice real (etapas condicionais podem sair)
    for i, (titulo, ferr, pref, deps, extra) in enumerate(m["etapas"], 1):
        if extra.get("_se") and not params.get(extra["_se"]):
            continue
        mapa[i] = len(etapas) + 1
        f = ferramentas.REGISTRO.get(ferr) if ferr else None
        etapas.append({"titulo": titulo, "ferramenta": ferr, "funcionario": _responsavel(ferr, pref, cfg),
                       "depende": [mapa[d] for d in deps if d in mapa], "risco": f.risco if f else "baixo",
                       "precisa_aprovacao": bool(extra.get("_exige_aprovacao") or (f and f.altera_dados)),
                       "parametros": {k: v for k, v in params.items() if k in ("arquivo", "base", "pergunta", "consulta")}})
    return etapas


def criar(cfg, pedido: str, funcionario: str | None = None, conversa_id: str | None = None, origem: str = "manual",
          arquivo: str | None = None, base: str | None = None, prioridade: str = "media", modelo: str | None = None,
          projeto_id: str | None = None, iniciar: bool = True) -> str:
    """Registra o pedido, monta o plano e (se não precisar de esclarecimento nem aprovação) põe na fila."""
    tb = Trabalho(cfg)
    modelos = [modelo] if modelo else reconhecer(pedido)
    tipo = "projeto" if len(modelos) > 1 and not projeto_id else "tarefa"
    titulo = pedido.strip().split("\n")[0][:120]
    andar = (organizacao.por_id(cfg).get(funcionario) or {}).get("andar") if funcionario else None
    sid = tb.criar_solicitacao(tipo, titulo, pedido, origem, funcionario, andar, prioridade, conversa_id, projeto_id,
                               modelos[0] if len(modelos) == 1 else None)
    if arquivo:
        tb.anexar(conversa_id, arquivo, sid)
    tb.mudar_estado(sid, "em_triagem", funcionario or "canal_nina")
    if tipo == "projeto":
        filhas = [criar(cfg, f"{MODELOS[m]['titulo']} — {titulo}", funcionario, conversa_id, origem, arquivo, base, prioridade,
                        m, sid, iniciar) for m in modelos]
        tb.mudar_estado(sid, "planejada", "canal_nina", f"Projeto dividido em {len(filhas)} tarefa(s): " + ", ".join(filhas),
                        plano={"tarefas": filhas})
        tb.mudar_estado(sid, "na_fila", "canal_nina")
        tb.mudar_estado(sid, "em_execucao", "canal_nina", "Projeto em andamento (acompanha as tarefas)")
        atualizar_projeto(cfg, sid)
        return sid
    if not modelos:
        tb.mudar_estado(sid, "aguardando_esclarecimento", funcionario or "canal_nina",
                        "Não reconheci um objetivo com plano. Diga o que quer como resultado (ex.: verificar a planilha, "
                        "análise completa, publicar, apresentação).")
        return sid
    m = MODELOS[modelos[0]]
    params = {"arquivo": arquivo, "base": base, "pergunta": pedido}
    faltando = [p for p in m["precisa"] if not params.get(p)]
    if faltando:
        tb.mudar_estado(sid, "aguardando_esclarecimento", funcionario or "canal_nina",
                        f"Para “{m['titulo']}” preciso de: {', '.join('uma planilha anexada' if f == 'arquivo' else f for f in faltando)}.")
        return sid
    etapas = planejar(modelos[0], cfg, params)
    executores = {e["funcionario"] for e in etapas}
    revisor = m["revisor"] if m["revisor"] not in executores else organizacao.revisor_de(next(iter(executores)), cfg)
    if revisor in executores:
        revisor = "dono"
    tb.criar_etapas(sid, etapas)
    plano = {"modelo": modelos[0], "etapas": len(etapas), "revisor": revisor,
             "riscos": sorted({e["risco"] for e in etapas}), "aprovacoes": sum(e["precisa_aprovacao"] for e in etapas)}
    tb.mudar_estado(sid, "planejada", funcionario or "canal_nina",
                    f"Plano “{m['titulo']}”: {len(etapas)} etapa(s), revisão independente de {revisor}", plano=plano, revisor=revisor)
    tb.mudar_estado(sid, "na_fila", "canal_nina")
    if iniciar:
        executar_em_segundo_plano(cfg, sid)
    return sid


def criar_demanda(cfg, titulo: str, pedido: str, funcionario: str, etapas: list[dict], revisor: str,
                  plano_extra: dict | None = None, origem: str = "demanda_sintetica") -> str:
    """Tarefa montada por robo/demandas.py: etapas com responsável, ferramenta, parâmetros e dependências (índices
    1..n). Passa pela mesma máquina de estados, execução, encaminhamento e revisão independente das tarefas pedidas
    pelo dono. Não executa (quem chama decide)."""
    tb = Trabalho(cfg)
    pessoa = organizacao.por_id(cfg).get(funcionario) or {}
    sid = tb.criar_solicitacao("tarefa", titulo, pedido, origem, funcionario, pessoa.get("andar"), "media",
                               modelo=f"demanda:{etapas[0]['ferramenta']}")
    tb.mudar_estado(sid, "em_triagem", "dem_gerador", f"Demanda para {pessoa.get('nome', funcionario)}")
    completas = []
    for e in etapas:
        f = ferramentas.REGISTRO.get(e["ferramenta"])
        completas.append({**e, "risco": f.risco if f else "baixo", "precisa_aprovacao": bool(f and f.altera_dados),
                          "depende": e.get("depende") or []})
    tb.criar_etapas(sid, completas)
    executores = {e["funcionario"] for e in etapas}
    if revisor in executores or revisor == organizacao.DONO:
        # quem executa não revisa; e a conferência automática não pode sair no nome do dono, que não a fez:
        # vai para a Revisora Independente de Casos (Sala de Casos), que existe para isso
        revisor = "casos_revisor" if "casos_revisor" not in executores else organizacao.revisor_de("head_casos", cfg)
    plano = {"modelo": f"demanda:{etapas[0]['ferramenta']}", "etapas": len(etapas), "revisor": revisor, **(plano_extra or {})}
    tb.mudar_estado(sid, "planejada", "dem_gerador", f"Demanda com {len(etapas)} etapa(s); revisão independente de {revisor}",
                    plano=plano, revisor=revisor)
    tb.mudar_estado(sid, "na_fila", "dem_distribuidor")
    return sid


# --------------------------------------------------------------------------- execução
_executando: set[str] = set()
_trava_exec = threading.Lock()
AO_EVENTO = None  # callback(etapa, arquivo, **extra) para o escritório 3D (definido pelo painel)


def _sinal(etapa: str, rotulo: str, **extra):
    if AO_EVENTO:
        try:
            AO_EVENTO(etapa, rotulo, **extra)
        except Exception:
            pass


def executar_em_segundo_plano(cfg, sid: str) -> None:
    threading.Thread(target=executar, args=(cfg, sid), name=f"tarefa-{sid}", daemon=True).start()


def executar(cfg, sid: str) -> str:
    """Executa as etapas pendentes. Devolve o estado final (ou o estado em que parou para aprovação)."""
    with _trava_exec:
        if sid in _executando:
            return "em_execucao"
        _executando.add(sid)
    try:
        return _executar(cfg, sid)
    except Exception as e:  # erro de programa: a tarefa falha com o motivo, nunca fica "em execução" para sempre
        log.exception("Tarefa %s falhou", sid)
        tb = Trabalho(cfg)
        try:
            tb.mudar_estado(sid, "falhou", "robo", f"Erro inesperado: {type(e).__name__}: {e}")
        except Exception:
            pass
        return "falhou"
    finally:
        with _trava_exec:
            _executando.discard(sid)


def _executar(cfg, sid: str) -> str:
    tb = Trabalho(cfg)
    s = tb.solicitacao(sid)
    if not s or s["estado"] in FINAIS:
        return s["estado"] if s else "falhou"
    if s["estado"] in ("na_fila", "aguardando_aprovacao", "aguardando_dependencia", "em_correcao"):
        tb.mudar_estado(sid, "em_execucao", "robo")
    elif s["estado"] != "em_execucao" or s["tipo"] != "tarefa":  # esclarecimento, planejada, projeto: nada a executar
        return s["estado"]
    rotulo = f"{sid} · {s['titulo'][:40]}"
    por_ordem = {e["ordem"]: e for e in s["etapas"]}
    for e in s["etapas"]:
        if _cancelada(tb, sid):  # o dono cancelou enquanto rodava: a etapa em curso termina, as próximas não começam
            return "cancelada"
        if e["estado"] in ("concluida", "falhou", "bloqueada", "pulada", "cancelada"):
            continue
        deps = [por_ordem[d] for d in e["depende"] if d in por_ordem]
        ruins = [d for d in deps if d["estado"] != "concluida"]
        if ruins:
            tb.atualizar_etapa(e["id"], estado="bloqueada", natureza="limitacao",
                               resultado=ferramentas.resultado(False, "limitacao", "Não rodou: depende de “" + "”, “".join(
                                   d["titulo"] for d in ruins) + "”, que não foi concluída."))
            por_ordem[e["ordem"]]["estado"] = "bloqueada"
            continue
        if e["precisa_aprovacao"]:
            aprov = [a for a in s["aprovacoes"] if a["etapa_id"] == e["id"]]
            if not aprov:
                tb.pedir_aprovacao(sid, f"{e['titulo']} (risco {e['risco']}; altera dados)", e["risco"], e["funcionario"], e["id"])
                tb.atualizar_etapa(e["id"], estado="aguardando_aprovacao")
                tb.mudar_estado(sid, "aguardando_aprovacao", e["funcionario"], f"Aguardando sua aprovação: {e['titulo']}")
                return "aguardando_aprovacao"
            if aprov[-1]["estado"] == "pendente":
                tb.mudar_estado(sid, "aguardando_aprovacao", e["funcionario"])
                return "aguardando_aprovacao"
            if aprov[-1]["estado"] == "recusada":
                tb.atualizar_etapa(e["id"], estado="cancelada", natureza="limitacao",
                                   resultado=ferramentas.resultado(False, "limitacao", "Você recusou esta etapa; ela não foi executada."))
                por_ordem[e["ordem"]]["estado"] = "cancelada"
                continue
        if not e["ferramenta"]:
            tb.atualizar_etapa(e["id"], estado="bloqueada", natureza="limitacao", resultado=ferramentas.resultado(
                False, "limitacao", "O robô não tem ferramenta para esta etapa (ainda). Ela não foi feita — "
                                    "o que existe de verdade está nas outras etapas."))
            por_ordem[e["ordem"]]["estado"] = "bloqueada"
            continue
        quem = e["funcionario"]
        if not organizacao.pode_usar(quem, e["ferramenta"], cfg, producao=True):
            outro = organizacao.quem_usa(e["ferramenta"], cfg)
            if not outro:
                tb.atualizar_etapa(e["id"], estado="bloqueada", natureza="limitacao", resultado=ferramentas.resultado(
                    False, "limitacao", f"Ninguém no quadro tem a ferramenta '{e['ferramenta']}' no contrato."))
                por_ordem[e["ordem"]]["estado"] = "bloqueada"
                continue
            tb.evento(sid, "encaminhada", f"{quem} não tem '{e['ferramenta']}' no contrato; etapa encaminhada para {outro}", quem)
            quem = outro
        tb.atualizar_etapa(e["id"], quem, estado="em_execucao", funcionario=quem, inicio=datetime.now().isoformat(timespec="seconds"),
                           tentativas=int(e["tentativas"] or 0) + 1)
        _sinal(quem, rotulo, tarefa=sid, fala=f"Fazendo: {e['titulo'][:90]}")
        params = dict(e["parametros"])
        if e["ferramenta"] == "resumo_executivo":
            params.update(titulo=s["titulo"], ref=sid, partes=[
                {"titulo": d["titulo"], **(d["resultado"] or {})} for d in s["etapas"] if d["ordem"] < e["ordem"]
                and por_ordem[d["ordem"]]["estado"] == "concluida"])
        r = ferramentas.executar(e["ferramenta"], cfg, **{"quem": quem, **params})
        estado = "concluida" if r["ok"] else "falhou"
        tb.atualizar_etapa(e["id"], quem, estado=estado, natureza=r["natureza"], resultado=r,
                           fim=datetime.now().isoformat(timespec="seconds"))
        for a in r["artefatos"]:
            tb.artefato(sid, a, Path(a).suffix.lstrip(".") or "arquivo", e["titulo"], e["id"])
        por_ordem[e["ordem"]].update(estado=estado, resultado=r)
    if _cancelada(tb, sid):
        return "cancelada"
    return _revisar(cfg, sid)


def _cancelada(tb: Trabalho, sid: str) -> bool:
    """Relê do banco (a lista de etapas em memória é de antes do cancelamento)."""
    atual = tb.solicitacao(sid)
    return bool(atual and atual["estado"] == "cancelada")


def _revisar(cfg, sid: str) -> str:
    """Revisão independente: outra pessoa confere evidências, artefatos e refaz os cálculos."""
    tb = Trabalho(cfg)
    s = tb.solicitacao(sid)
    revisor = s["revisor"] or "dono"
    executores = {e["funcionario"] for e in s["etapas"]}
    if revisor in executores:  # salvaguarda: quem executou não revisa
        revisor = "dono"
    tb.mudar_estado(sid, "em_revisao", revisor, f"Revisão independente com {revisor}")
    _sinal(revisor, f"{sid} · revisão", tarefa=sid, fala=f"Revisando {sid} de forma independente")
    achados = []
    concluidas = [e for e in s["etapas"] if e["estado"] == "concluida"]
    for e in concluidas:
        r = e["resultado"] or {}
        if not r.get("texto") or not r.get("evidencia"):
            achados.append(f"Etapa “{e['titulo']}” concluída sem texto ou evidência")
        for a in r.get("artefatos") or []:
            if not Path(a).exists() or Path(a).stat().st_size == 0:
                achados.append(f"Artefato {Path(a).name} não existe ou está vazio")
        if e["ferramenta"] == "calcular":  # recálculo independente
            de_novo = ferramentas.executar("calcular", cfg, **e["parametros"])
            if de_novo["texto"] != r.get("texto"):
                achados.append("O recálculo independente deu resultado diferente")
    criterios = (s.get("plano") or {}).get("criterios_por_etapa") or {}
    if criterios:  # critérios de aceitação de cada etapa da demanda (robo/demandas.py), conferidos sem IA
        from robo.demandas import conferir_criterios
        for e in concluidas:
            achados += [f"Critério não atendido em “{e['titulo']}”: {x}"
                        for x in conferir_criterios(e["resultado"], criterios.get(str(e["ordem"])))]
    revisao = {"revisor": revisor, "achados": achados, "data_hora": datetime.now().isoformat(timespec="seconds"),
               "conferido": [e["titulo"] for e in concluidas], "criterios": criterios or []}
    if achados:
        tb.mudar_estado(sid, "reprovada_revisao", revisor, "Reprovada na revisão: " + "; ".join(achados), revisao=revisao)
        tentativas = int(s["tentativas"] or 0)
        if tentativas < 1:  # uma correção automática: refaz as etapas reprovadas
            tb.mudar_estado(sid, "em_correcao", "robo", "Refazendo as etapas apontadas", tentativas=tentativas + 1)
            for e in concluidas:
                tb.atualizar_etapa(e["id"], estado="pendente")
            return _executar(cfg, sid)
        tb.mudar_estado(sid, "falhou", revisor, "Continua reprovada depois da correção")
        _fim(sid, "falhou", cfg)
        _projeto_pai(cfg, s)
        return "falhou"
    todas = s["etapas"]
    ok = len(concluidas)
    if not todas:  # tarefa sem etapa nenhuma não pode sair "concluída" (0 de 0)
        final = "falhou"
    elif ok == len(todas):
        final = "concluida"
    elif ok:
        final = "concluida_parcialmente"
    else:
        final = "falhou"
    resumo = {"etapas_concluidas": ok, "etapas": len(todas),
              "nao_feitas": [{"titulo": e["titulo"], "motivo": (e["resultado"] or {}).get("texto", "")}
                             for e in todas if e["estado"] != "concluida"]}
    if final == "falhou":
        tb.mudar_estado(sid, "reprovada_revisao", revisor, "Nenhuma etapa foi concluída", revisao=revisao)
        tb.mudar_estado(sid, "falhou", revisor, "Nenhuma etapa foi concluída", resultado=resumo)
    else:
        tb.mudar_estado(sid, final, revisor, f"Revisão aprovada por {revisor}: {ok}/{len(todas)} etapa(s) concluída(s)",
                        revisao=revisao, resultado=resumo)
        if final == "concluida" and s["modelo"]:
            tb.lembrar("solucao_aprovada", s["modelo"], f"{s['titulo']}: {ok} etapa(s) aprovadas por {revisor}", revisor, sid)
    _fim(sid, final, cfg)
    _projeto_pai(cfg, s)
    return final


def _fim(sid: str, estado: str, cfg=None):
    if cfg is not None:
        try:
            from robo import memoria
            memoria.registrar_tarefa(cfg, sid)  # acertos, erros e handovers de quem trabalhou
        except Exception:
            log.exception("Não consegui registrar a memória da tarefa %s", sid)
    _sinal("tarefa_fim", sid, status=estado)


def _projeto_pai(cfg, s: dict):
    if s.get("projeto_id"):
        atualizar_projeto(cfg, s["projeto_id"])


def atualizar_projeto(cfg, pid: str) -> None:
    """O projeto termina quando todas as tarefas terminam: concluído só se todas foram concluídas."""
    tb = Trabalho(cfg)
    p = tb.solicitacao(pid)
    if not p or p["estado"] in FINAIS or not p["tarefas"]:
        return
    estados = [t["estado"] for t in p["tarefas"]]
    if not all(e in FINAIS for e in estados):
        return
    if all(e == "concluida" for e in estados):
        final = "concluida"
    elif any(e in ("concluida", "concluida_parcialmente") for e in estados):
        final = "concluida_parcialmente"
    else:
        final = "falhou"
    tb.mudar_estado(pid, final, "canal_nina", f"Projeto encerrado: {estados.count('concluida')}/{len(estados)} tarefa(s) concluída(s)",
                    resultado={"tarefas": {t["id"]: t["estado"] for t in p["tarefas"]}})


# --------------------------------------------------------------------------- decisões do dono
def decidir(cfg, aprovacao_id: str, aprovado: bool, motivo: str = "", em_segundo_plano: bool = True) -> dict:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        alvo = c.execute("SELECT s.modelo FROM aprovacoes a JOIN solicitacoes s ON s.id=a.solicitacao_id WHERE a.id=?",
                         (aprovacao_id,)).fetchone()
    if alvo and alvo["modelo"] == "desligamento":
        from robo import reuniao
        return reuniao.decidir_desligamento(cfg, aprovacao_id, aprovado, motivo)
    if alvo and alvo["modelo"] == "promocao":
        from robo import reuniao
        return reuniao.decidir_promocao(cfg, aprovacao_id, aprovado, motivo)
    a = tb.decidir(aprovacao_id, aprovado, "dono", motivo)
    s = tb.solicitacao(a["solicitacao_id"])
    if s and s["estado"] == "aguardando_aprovacao":
        tb.mudar_estado(s["id"], "na_fila", "dono", "Aprovado: volta para a fila" if aprovado else "Recusado: segue sem a etapa")
        if em_segundo_plano:
            executar_em_segundo_plano(cfg, s["id"])
        else:
            executar(cfg, s["id"])
    return a


def cancelar(cfg, sid: str, motivo: str = "") -> None:
    tb = Trabalho(cfg)
    s = tb.solicitacao(sid)
    tb.mudar_estado(sid, "cancelada", "dono", "Cancelada por você" + (f": {motivo}" if motivo else ""))
    for e in s["etapas"]:
        if e["estado"] in ("pendente", "aguardando_aprovacao", "aguardando_dependencia"):
            tb.atualizar_etapa(e["id"], "dono", estado="cancelada")
    for a in s["aprovacoes"]:
        if a["estado"] == "pendente":
            tb.decidir(a["id"], False, "dono", "tarefa cancelada")


CAMINHO_ATE_FALHA = {"na_fila": ["em_execucao"], "em_correcao": ["em_execucao"], "aguardando_dependencia": ["em_execucao"],
                     "em_revisao": ["reprovada_revisao"], "reprovada_revisao": [], "em_execucao": []}


def _encerrar_como_falha(tb: Trabalho, sid: str, estado: str, motivo: str) -> None:
    """Leva a tarefa até 'falhou' pelos estados permitidos (a máquina de estados não deixa pular)."""
    try:
        for passo in CAMINHO_ATE_FALHA.get(estado, []):
            tb.mudar_estado(sid, passo, "robo", motivo)
        tb.mudar_estado(sid, "falhou", "robo", motivo)
    except Exception:
        log.exception("Não consegui encerrar %s depois do reinício", sid)


def _revisar_seguro(cfg, sid: str) -> None:
    try:
        _revisar(cfg, sid)
    except Exception:
        log.exception("Revisão retomada de %s falhou", sid)


def retomar_pendentes(cfg) -> list[str]:
    """Depois de reiniciar: tarefas que estavam na fila ou em execução voltam a rodar (nada se perde)."""
    tb = Trabalho(cfg)
    retomadas = []
    # registro automático do pipeline: não se "refaz" — a planilha já foi processada; se ficou no meio, é falha registrada
    for estado in ("na_fila", "em_execucao", "em_correcao", "em_revisao", "reprovada_revisao", "aguardando_dependencia"):
        for s in tb.listar(estado=estado, tipo="tarefa"):
            if s.get("modelo") == "pipeline":
                _encerrar_como_falha(tb, s["id"], estado,
                                     "Registro automático interrompido por reinício (a planilha está no histórico)")
                continue
            if estado == "em_revisao":  # a execução terminou; falta a revisão independente
                retomadas.append(s["id"])
                threading.Thread(target=_revisar_seguro, args=(cfg, s["id"]), daemon=True, name=f"revisao-{s['id']}").start()
                continue
            if estado == "reprovada_revisao":
                tb.mudar_estado(s["id"], "em_correcao", "robo", "Retomada depois de reiniciar: refazer o que a revisão apontou")
            if estado == "em_execucao":
                for e in tb.solicitacao(s["id"])["etapas"]:
                    if e["estado"] == "em_execucao":  # interrompida no meio: roda de novo
                        tb.atualizar_etapa(e["id"], estado="pendente")
                tb.evento(s["id"], "retomada", "Retomada depois de reiniciar o robô")
            retomadas.append(s["id"])
            executar_em_segundo_plano(cfg, s["id"])
    return retomadas


def registrar_execucao_automatica(cfg, r, origem: str = "automatica") -> str | None:
    """Toda planilha processada pelo monitor vira uma solicitação automática (com evidência do histórico).
    origem='sintetica' para as planilhas da fábrica (TREINO_*), para nunca se misturarem com as reais."""
    try:
        from robo.pipeline import REPROVADO, SUCESSO
        if r.status not in (SUCESSO, REPROVADO):
            return None
        tb = Trabalho(cfg)
        sid = tb.criar_solicitacao("tarefa", f"Processar {r.arquivo.name}", f"Arquivo recebido em Bases-Limpeza: {r.arquivo.name}",
                                   origem, "recepcao", 1, "media", modelo="pipeline")
        tb.mudar_estado(sid, "em_triagem", "recepcao")
        tb.mudar_estado(sid, "planejada", "recepcao", "Pipeline completo de produção")
        tb.mudar_estado(sid, "na_fila", "recepcao")
        tb.mudar_estado(sid, "em_execucao", "recepcao")
        erros = [getattr(e, "mensagem", str(e)) for e in r.relatorio.erros]
        resultado = {"status": r.status, "id_execucao": r.id, "linhas_entrada": r.linhas_entrada, "linhas_saida": r.linhas_saida,
                     "erros": erros[:20], "saidas": [str(s) for s in r.saidas]}
        tb.mudar_estado(sid, "em_revisao", "coord_engenharia", "Portão de produção (supervisor, quadro, checklist)")
        if r.status == SUCESSO:
            tb.mudar_estado(sid, "concluida", "coord_engenharia", f"Publicada: {r.linhas_saida} linha(s)", resultado=resultado)
            for s in r.saidas:
                tb.artefato(sid, s, Path(s).suffix.lstrip("."), "Base publicada")
        else:
            tb.mudar_estado(sid, "reprovada_revisao", "coord_engenharia", f"Reprovada: {len(erros)} erro(s)", resultado=resultado)
            tb.mudar_estado(sid, "falhou", "coord_engenharia", "Arquivo foi para Bases-Erros com o relatório do que corrigir")
        return sid
    except Exception:
        log.exception("Não consegui registrar a execução automática na central de solicitações")
        return None
