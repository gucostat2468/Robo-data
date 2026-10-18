"""Teste DIRETO de cada ferramenta que só era testada por tabela (a visão de gestão apontou 15).
Cada uma roda de verdade sobre uma base publicada: não pode levantar exceção, tem que devolver texto, natureza
válida e evidência quando afirma algo — e o uso fica registrado em uso_ferramentas."""

import sqlite3

import pytest

from conftest import REGRA_NPS
from robo import ferramentas
from robo.pipeline import processar_arquivo

QUEM = {"historico": "analise_estatistica", "perfil_indicadores": "analise_indicadores", "dados_pessoais": "gov_estagiaria",
        "ronda_ti": "infra_pleno", "reuniao_andar": "ger_analise", "ideias": "canal_nina", "segmentacao": "cd_pleno_segmentos",
        "anomalias": "analise_estatistica", "scorecard": "ger_analise", "auditoria": "ger_analise",
        "recrutamento": "rh_td", "desenvolvimento": "rh_td", "people_analytics": "rh_td",
        "estrategia_python": "ger_analise", "organizacao": "ger_analise"}


# o que cada uma tem que dizer sobre a base de 4 linhas (honesto: segmentar 4 linhas é recusado, não inventado)
ESPERADO = {"historico": (True, "nps_outubro.xlsx: sucesso"), "perfil_indicadores": (True, "4 registros"),
            "dados_pessoais": (True, "Nenhuma coluna parece dado pessoal"), "ronda_ti": (True, "Ronda de TI:"),
            "reuniao_andar": (True, "2º andar"), "ideias": (True, "1."), "segmentacao": (False, "pelo menos 30"),
            "anomalias": (True, "coluna(s) numérica(s)"), "scorecard": (True, "## Indicadores"),
            "auditoria": (True, "conferi"), "recrutamento": (True, "contratações"), "desenvolvimento": (True, "70-20-10"),
            "people_analytics": (True, "funcionários"), "estrategia_python": (True, "laboratório"),
            "organizacao": (True, "1º andar")}


@pytest.fixture
def cfg(planilha_baguncada, cfg_factory):
    c = cfg_factory(regras=[REGRA_NPS])
    assert processar_arquivo(planilha_baguncada, c).status == "sucesso"
    return c


@pytest.mark.parametrize("ferramenta", sorted(QUEM))
def teste_ferramenta_roda_de_verdade_e_registra_o_uso(cfg, ferramenta):
    params = {"quem": QUEM[ferramenta], "base": "nps_outubro", "andar": 2}
    r = ferramentas.executar(ferramenta, cfg, **params)
    assert "excecao" not in r, r["texto"]
    assert r["natureza"] in ferramentas.NATUREZAS and r["texto"].strip()
    ok, trecho = ESPERADO[ferramenta]
    assert r["ok"] is ok and trecho in r["texto"], r["texto"][:300]
    if not ok:
        assert r["natureza"] == "limitacao"  # quando não faz, diz que não fez
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    usos = c.execute("SELECT ok, quem FROM uso_ferramentas WHERE ferramenta=?", (ferramenta,)).fetchall()
    c.close()
    assert usos == [(int(r["ok"]), QUEM[ferramenta])]
