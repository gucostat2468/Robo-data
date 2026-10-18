"""Visão de gestão: inventário real e evolução medida (sem afirmar tendência sem amostra)."""

from datetime import datetime, timedelta

from robo import gestao
from robo.trabalho import Trabalho


def _exp(tb, pid, tipo, quando):
    with tb.tx() as c:
        c.execute("INSERT INTO experiencias (funcionario, data_hora, tipo, resumo, origem, andar) VALUES (?,?,?,?,?,?)",
                  (pid, quando.isoformat(timespec="seconds"), tipo, "teste", "teste", 1))


def teste_evolucao_so_com_amostra_e_diferenca_real(cfg_factory):
    cfg = cfg_factory()
    tb = Trabalho(cfg)
    agora = datetime(2026, 10, 18, 12, 0)
    # leitura: antes 50% (5 acertos/5 erros, há 3–5 semanas), agora 90% (9/1, nas 2 últimas) → evoluindo
    for i in range(5):
        _exp(tb, "leitura", "acerto", agora - timedelta(weeks=4, hours=i))
        _exp(tb, "leitura", "erro", agora - timedelta(weeks=4, hours=10 + i))
    for i in range(9):
        _exp(tb, "leitura", "acerto", agora - timedelta(days=3, hours=i))
    _exp(tb, "leitura", "erro", agora - timedelta(days=2))
    # limpeza: só 3 eventos → não dá para afirmar nada
    for i in range(3):
        _exp(tb, "limpeza", "acerto", agora - timedelta(days=1, hours=i))
    ev = {e["id"]: e for e in gestao.evolucao(cfg, agora=agora)}
    assert ev["leitura"]["tendencia"] == "evoluindo" and ev["leitura"]["delta_pp"] == 40.0
    assert ev["leitura"]["taxas_semana"][-1] == 90.0 and len(ev["leitura"]["taxas_semana"]) == 8
    assert ev["limpeza"]["tendencia"] == "dados_insuficientes"


def teste_visao_tem_todas_as_paginas_andares_e_funcoes(cfg_factory):
    from robo import ferramentas
    cfg = cfg_factory()
    ferramentas.executar("laboratorio", cfg, quem="head_engenharia")
    v = gestao.visao(cfg)
    assert len(v["paginas"]) == 23 and [a["andar"] for a in v["andares"]] == [1, 2, 3, 4, 5]
    assert {f["id"] for f in v["funcoes"]} == set(ferramentas.REGISTRO)
    lab = next(f for f in v["funcoes"] if f["id"] == "laboratorio")
    assert lab["usos"] == 1 and lab["pct_ok"] == 100  # o uso de cada ferramenta é registrado
    assert any(m["modulo"] == "robo.gestao" for m in v["modulos"])
