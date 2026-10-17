"""Calculadora do canal: cálculos sobre a base publicada, pedidos em português."""

from conftest import REGRA_NPS
from robo.calculos import calcular
from robo.canal import responder
from robo.pipeline import processar_arquivo


def _cfg(planilha_baguncada, cfg_factory):
    cfg = cfg_factory([REGRA_NPS])
    processar_arquivo(planilha_baguncada, cfg)
    return cfg


def teste_nps_por_segmento_e_filtro(planilha_baguncada, cfg_factory):
    cfg = _cfg(planilha_baguncada, cfg_factory)
    r = calcular(cfg, "nps por curso")
    assert r and r["autor"] == "analise_indicadores" and "n=" in r["texto"]
    r = calcular(cfg, "contagem por curso onde nota_nps > 5")
    assert "filtro: nota_nps > 5" in r["texto"]


def teste_coluna_aproximada_e_coluna_inexistente(planilha_baguncada, cfg_factory):
    cfg = _cfg(planilha_baguncada, cfg_factory)
    assert "Média de nota_nps" in calcular(cfg, "média de nota nps")["texto"]
    r = calcular(cfg, "média de salário")
    assert "Não encontrei" in r["texto"] or "Nenhuma base" in r["texto"]


def teste_texto_nao_vira_soma(planilha_baguncada, cfg_factory):
    cfg = _cfg(planilha_baguncada, cfg_factory)
    assert "não é numérica" in calcular(cfg, "soma de curso")["texto"]


def teste_canal_usa_a_calculadora(planilha_baguncada, cfg_factory):
    cfg = _cfg(planilha_baguncada, cfg_factory)
    r = responder("quantas respostas por curso?", cfg)[0]
    assert r["intencao"] == "calculo" and "Contagem por curso" in r["texto"]
    assert responder("como faço um procx?", cfg)[0]["intencao"] == "conhecimento"


def teste_sem_base_publicada_responde_com_honestidade(cfg_factory):
    r = calcular(cfg_factory(), "nps por região")
    assert "Ainda não há" in r["texto"]
