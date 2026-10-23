"""Prova de trabalho: job aberto para todo processamento real, etapas com quem fez, evidência e nada alterável depois."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from robo import jobs


def teste_job_fechado_nao_pode_ser_alterado_nem_apagado(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    with jobs.job(cfg, "treino", "sintetico", "TR-1", "casos_planejamento") as j:
        j.etapa("treino:sql:n2", "dba")
        j.fechar_etapa(True, "caso 1")
        j.evidencia["tentativas"] = 1
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    for sql in ("UPDATE jobs SET estado='x'", "UPDATE jobs_etapas SET ok=0", "DELETE FROM jobs", "DELETE FROM jobs_etapas"):
        with pytest.raises(sqlite3.DatabaseError):
            c.execute(sql)
    assert c.execute("SELECT estado, evidencia FROM jobs").fetchone() == ("concluido", '{"tentativas": 1}')
    c.close()


def teste_erro_fecha_o_job_como_falhou(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    with pytest.raises(ValueError):
        with jobs.job(cfg, "rotina", "rotina", funcionario="dba") as j:
            j.etapa("backup", "dba")
            raise ValueError("disco cheio")
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    assert c.execute("SELECT estado FROM jobs").fetchone()[0] == "falhou"
    assert c.execute("SELECT ok FROM jobs_etapas").fetchone()[0] == 0
    c.close()
    assert jobs.trabalhando_agora(cfg) == {}


def teste_job_esquecido_aberto_vira_abandonado(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    jobs.abrir(cfg, "planilha", "real", "x.xlsx")
    assert jobs.marcar_abandonados(cfg, datetime.now() + timedelta(hours=7)) == 1
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    assert c.execute("SELECT estado FROM jobs").fetchone()[0] == "abandonado"
    c.close()


def teste_esteira_real_abre_job_com_etapas_e_evidencia(cfg_factory):
    import pandas as pd
    from robo.pipeline import processar_arquivo
    cfg = cfg_factory()
    cfg.criar_pastas()
    arq = cfg.entrada / "vendas.xlsx"
    pd.DataFrame({"id": range(1, 31), "regiao": ["Sul", "Norte"] * 15, "valor": range(30)}).to_excel(arq, index=False)
    r = processar_arquivo(arq, cfg)
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    c.row_factory = sqlite3.Row
    j = c.execute("SELECT * FROM jobs WHERE tipo='planilha'").fetchone()
    etapas = [x["etapa"] for x in c.execute("SELECT etapa FROM jobs_etapas WHERE job_id=? ORDER BY id", (j["id"],))]
    abertas = c.execute("SELECT COUNT(*) FROM jobs_etapas WHERE fim IS NULL").fetchone()[0]
    c.close()
    assert j["origem"] == "real" and j["arquivo"] == "vendas.xlsx" and j["fim"]
    assert j["estado"] == ("concluido" if r.status == "sucesso" else "falhou")
    assert "leitura" in etapas and "limpeza" in etapas and abertas == 0
    if r.status == "sucesso":
        assert j["hash_saida"] and len(j["hash_saida"]) == 64
    assert jobs.ultima_evidencia(cfg)["limpeza"]["arquivo"] == "vendas.xlsx"


def teste_rotina_em_dia_nao_vira_job_e_rotina_que_fez_vira(cfg_factory):
    from robo import rotinas
    cfg = cfg_factory()
    cfg.criar_pastas()
    rotinas.executar(cfg, "backup", lambda: None)
    rotinas.executar(cfg, "backup", lambda: {"copiado": 1})
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    linhas = c.execute("SELECT tipo, funcionario, estado FROM jobs").fetchall()
    c.close()
    assert linhas == [("rotina", "dba", "concluido")]
