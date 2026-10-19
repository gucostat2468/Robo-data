"""Jornada ponta a ponta: a esteira inteira com uma planilha sintética, num computador de teste, etapa por etapa."""

import sqlite3

import pytest

from robo import jornada


def teste_esteira_inteira_com_a_verdade_e_sem_tocar_a_producao(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    antes = {p: sorted(x.name for x in p.iterdir()) for p in (cfg.entrada, cfg.tratadas, cfg.originais, cfg.erros)}
    j = jornada.percorrer(cfg, "varejo", 123)
    assert j["ok"], j["etapas"]
    assert set(j["etapas"]) == set(jornada.ETAPAS) and all(e["ok"] for e in j["etapas"].values())
    assert j["linhas_saida"] == j["linhas_esperadas"]
    assert {"leitura", "limpeza", "publicacao"} <= set(j["tempos"])
    depois = {p: sorted(x.name for x in p.iterdir()) for p in antes}
    assert depois == antes                                                   # pastas de produção intactas
    assert not (cfg.logs / "trabalho.db").exists() or not sqlite3.connect(cfg.logs / "trabalho.db").execute(
        "SELECT name FROM sqlite_master WHERE name='historico'").fetchone()


def teste_falha_numa_etapa_e_apontada_e_vai_para_o_canal(cfg_factory, monkeypatch):
    from robo import pipeline
    cfg = cfg_factory()
    cfg.criar_pastas()
    original = pipeline.processar_arquivo

    def sem_analise(caminho, sb, gravar=True, ao_etapa=None):
        r = original(caminho, sb, gravar=gravar, ao_etapa=ao_etapa)
        (sb.logs / "analises" / f"{r.id}.json").unlink(missing_ok=True)     # simula o 2º andar sem gerar a análise
        return r
    monkeypatch.setattr(pipeline, "processar_arquivo", sem_analise)
    r = jornada.rotina(cfg)
    assert not r["ok"] and r["etapa_falhou"] == "analise"
    texto = (cfg.logs / "canal" / "mensagens.jsonl").read_text(encoding="utf-8")
    assert "Jornada ponta a ponta" in texto and "Análise" in texto
    ult = jornada.ultimas(cfg)[0]
    assert ult["etapas"]["validacao"]["ok"] and not ult["etapas"]["analise"]["ok"]


def teste_registro_permanente_e_ligado_ao_fluxo():
    from robo import orquestracao
    from robo.painel.servidor import ROTAS_POST
    from robo.rotinas import ROTINAS
    assert ROTINAS["jornada"][0] == "airflow_pleno"
    assert "jornada" in orquestracao.FLUXOS["robo_horario"]["rotinas"] and not orquestracao.validar_fluxos()
    assert "/api/jornada/rodar" in ROTAS_POST


def teste_execucoes_nao_mudam(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    jornada.rotina(cfg)
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    for sql in ("UPDATE jornada_execucoes SET ok=0", "DELETE FROM jornada_execucoes"):
        with pytest.raises(sqlite3.DatabaseError):
            c.execute(sql)
    c.close()
