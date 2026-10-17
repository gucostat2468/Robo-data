"""Raio-X da empresa: como ela está AGORA e onde cada coisa fica registrada. Só conta o que está gravado."""

from __future__ import annotations

from datetime import datetime, timedelta

from robo import memoria, organizacao, rotinas
from robo.trabalho import Trabalho

ONDE = {
    "Planilhas processadas": "logs/historico_execucoes.csv + logs/execucoes/<id>.json (uma ficha por arquivo)",
    "Memória de cada funcionário": "logs/trabalho.db → experiencias (cópia no PostgreSQL: robo.memoria_experiencias)",
    "Erros e handovers": "logs/trabalho.db → handovers (cópia no PostgreSQL: robo.memoria_handovers)",
    "Boas práticas": "logs/trabalho.db → boas_praticas",
    "Planos de ação": "backlog da Estratégia (logs/estrategia/backlog.json), ligados ao handover de origem",
    "Pedidos, tarefas e aprovações": "logs/trabalho.db → solicitacoes, etapas, aprovacoes, eventos",
    "Conversas": "logs/trabalho.db → conversas e mensagens",
    "Rotinas": "logs/trabalho.db → rotinas_estado e rotinas_execucoes",
    "Sessões (notebook aberto/fechado)": "logs/trabalho.db → sessoes",
    "Reuniões": "logs/trabalho.db → reunioes + logs/reunioes/<id>.md",
    "Auditorias dos heads": "logs/trabalho.db → auditorias",
    "Canal da equipe": "logs/canal/mensagens.jsonl",
}


def montar(cfg) -> dict:
    tb = Trabalho(cfg)
    semana = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    with tb.tx() as c:
        exp_total = {r["tipo"]: r["n"] for r in c.execute("SELECT tipo, COUNT(*) n FROM experiencias GROUP BY tipo")}
        exp_semana = {r["tipo"]: r["n"] for r in c.execute(
            "SELECT tipo, COUNT(*) n FROM experiencias WHERE data_hora>=? GROUP BY tipo", (semana,))}
        com_memoria = c.execute("SELECT COUNT(DISTINCT funcionario) FROM experiencias").fetchone()[0]
        conversas = c.execute("SELECT COUNT(*) FROM conversas").fetchone()[0]
        mensagens = c.execute("SELECT COUNT(*) FROM mensagens").fetchone()[0]
        reunioes = c.execute("SELECT COUNT(*) FROM reunioes").fetchone()[0]
    conferencias: dict[str, int] = {}
    for m in tb.memorias("conferencia_calculo", limite=100_000):
        conferencias[m["chave"]] = conferencias.get(m["chave"], 0) + 1
    from robo import historico
    hist = historico.ler(cfg.logs, 5000)
    h7 = [h for h in hist if str(h.get("data_hora", "")).replace(" ", "T") >= semana]
    try:
        from robo import auditoria
        auds = auditoria.listar(cfg, 20)
    except Exception:
        auds = []
    gente = organizacao.lista(cfg)
    estado_rotinas = rotinas.estado(cfg)
    ses = rotinas.sessoes(cfg, 10)
    return {
        "agora": datetime.now().isoformat(timespec="seconds"),
        "pessoas": {"total": len(gente), "por_andar": {a: sum(1 for p in gente if p["andar"] == a) for a in organizacao.NOME_ANDAR},
                    "com_memoria_registrada": com_memoria},
        "planilhas": {"total": len(hist), "semana": len(h7), "aprovadas_semana": sum(h.get("status") == "sucesso" for h in h7),
                      "reprovadas_semana": sum(h.get("status") == "reprovado" for h in h7)},
        "memoria": {"total": exp_total, "semana": exp_semana},
        "pdca": memoria.resumo_pdca(cfg),
        "solicitacoes": tb.contagem(),
        "conversas": {"conversas": conversas, "mensagens": mensagens},
        "reunioes": reunioes,
        "conferencias_calculo": conferencias,
        "auditorias": auds,
        "rotinas": estado_rotinas,
        "sessoes": ses,
        "onde_fica": ONDE,
    }


def texto(r: dict) -> str:
    """Resumo em linguagem natural (para o chat)."""
    p, m, s = r["planilhas"], r["memoria"], r["solicitacoes"]
    atrasadas = [x["nome"] for x in r["rotinas"] if x["atrasada"] and x["nome"] != "canal"]
    conf = r["conferencias_calculo"]
    total_conf = sum(conf.values())
    linhas = [
        f"Temos {r['pessoas']['total']} funcionários em {len(r['pessoas']['por_andar'])} andares; "
        f"{r['pessoas']['com_memoria_registrada']} já têm memória registrada.",
        f"Nesta semana chegaram {p['semana']} planilha(s): {p['aprovadas_semana']} aprovada(s) e {p['reprovadas_semana']} reprovada(s).",
        f"Memória da semana: {m['semana'].get('acerto', 0)} acertos, {m['semana'].get('erro', 0)} erros, "
        f"{m['semana'].get('aprendizado', 0)} aprendizados e {m['semana'].get('treinamento', 0)} treinamentos registrados.",
        f"PDCA: {r['pdca']['planejar']} problema(s) em planejamento, {r['pdca']['fazer']} em correção, {r['pdca']['checar']} "
        f"sendo checados e {r['pdca']['agir']} já viraram boa prática.",
        f"Central: {s['total']} solicitação(ões) no total, {s['aprovacoes_pendentes']} aprovação(ões) esperando você.",
    ]
    if total_conf:
        linhas.append(f"Confiabilidade: {conf.get('conferido', 0)} de {total_conf} cálculos foram conferidos no banco; "
                      f"{conf.get('divergente', 0)} divergência(s).")
    if r["auditorias"]:
        ok = sum(1 for a in r["auditorias"] if a["aprovada"])
        linhas.append(f"Auditorias dos heads: {ok} de {len(r['auditorias'])} recentes aprovadas.")
    linhas.append("Rotinas atrasadas: " + ", ".join(atrasadas) + "." if atrasadas else "Todas as rotinas estão em dia.")
    return "\n".join(linhas)
