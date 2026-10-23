"""Cobertura do banco: o levantamento conta de verdade, explica cada tabela vazia e nunca inventa dado; a planilha da
fábrica chega ao PostgreSQL só nos schemas laboratorio e treino (nunca nos de produção), com teto de espaço.

Os testes com PostgreSQL rodam só com ROBO_TESTE_PG definido (como em teste_banco.py).
"""

import os
import sqlite3
import uuid
from pathlib import Path

import pytest

from robo import cobertura_banco as cb
from robo import fabrica
from robo.pipeline import SUCESSO, base_sintetica, processar_arquivo

DSN = os.environ.get("ROBO_TESTE_PG")
com_pg = pytest.mark.skipif(not DSN, reason="defina ROBO_TESTE_PG para testar com PostgreSQL")


def teste_uma_tabela_por_regra_e_nao_por_lote():
    assert base_sintetica(Path("TREINO_nps_20261023_042837_17916.xlsx")) == "treino_nps"
    assert base_sintetica(Path("TREINO_csat_ces_20261023_042837_1.xlsx")) == "treino_csat_ces"
    assert base_sintetica(Path("TREINO_pesquisa_mercado_20261024_101010_9.csv")) == "treino_pesquisa_mercado"


def teste_levantamento_explica_cada_vazia_e_nao_inventa(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    from robo.trabalho import Trabalho
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.execute("CREATE TABLE tabela_misteriosa (x INTEGER)")
    r = cb.levantar(cfg)
    por = {i["tabela"]: i for i in r["itens"] if i["onde"] == "sqlite"}
    assert por["solicitacoes"]["situacao"] == cb.NAO_ACIONADA and "pedido" in por["solicitacoes"]["gatilho"]
    assert por["aprendizados_replay"]["situacao"] == cb.DESCONECTADA
    assert por["tabela_misteriosa"]["situacao"] == cb.SEM_CAUSA  # sem causa conhecida não ganha desculpa inventada
    assert por["tabela_misteriosa"]["linhas"] == 0
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        assert c.execute("SELECT COUNT(*) FROM tabela_misteriosa").fetchone()[0] == 0  # só contou, não encheu nada
        gravados = c.execute("SELECT COUNT(*) FROM cobertura_persistencia WHERE levantamento=?",
                             (r["levantamento"],)).fetchone()[0]
        assert gravados == len(r["itens"])
        with pytest.raises(sqlite3.DatabaseError):
            c.execute("UPDATE cobertura_persistencia SET linhas = 999")
    assert r["erro_postgres"] is None and not any(i["onde"] == "postgres" for i in r["itens"])  # banco desligado
    md = cb.relatorio_md(r)
    assert "Vazias e por quê" in md and "tabela_misteriosa" in md


def teste_tabela_com_linhas_conta_certo(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    from robo import jobs
    jobs.registrar_concluido(cfg, "rotina", "rotina", "dba", "2026-10-23T10:00:00", [{"etapa": "x", "funcionario": "dba",
                                                                                      "ok": True}])
    por = {i["tabela"]: i for i in cb.levantar(cfg, gravar=False)["itens"]}
    assert por["jobs"]["linhas"] == 1 and por["jobs"]["situacao"] == cb.COM_DADOS
    assert por["jobs_etapas"]["linhas"] == 1


# ----------------------------------------------------------------------------------------------- com PostgreSQL
@pytest.fixture
def banco_cfg():
    import psycopg
    d = dict(p.split("=", 1) for p in DSN.split())
    nome = f"robo_teste_{uuid.uuid4().hex[:8]}"
    cfg = {"habilitado": True, "host": d.get("host", "localhost"), "porta": int(d.get("port", 5432)),
           "usuario": d.get("user", "postgres"), "senha": d.get("password", ""), "banco": nome}
    yield cfg
    with psycopg.connect(host=cfg["host"], port=cfg["porta"], user=cfg["usuario"], password=cfg["senha"],
                         dbname="postgres", autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)')


def _q(cfg, sql, params=()):
    import psycopg
    with psycopg.connect(host=cfg["host"], port=cfg["porta"], user=cfg["usuario"], password=cfg["senha"],
                         dbname=cfg["banco"]) as c:
        return c.execute(sql, params).fetchall()


def _lote(cfg_factory, banco_cfg, **fab):
    cfg = cfg_factory(banco=banco_cfg, fabrica={"linhas_min": 300, "linhas_max": 400, **fab})
    cfg.criar_pastas()
    lote = fabrica.produzir_lote(cfg, "nps", semente=7)
    arq = next((cfg.entrada / "sintetico").glob("TREINO_nps_*.xlsx"))
    return cfg, lote, arq


@com_pg
def teste_fabrica_enche_laboratorio_e_treino_e_nunca_a_producao(cfg_factory, banco_cfg):
    cfg, lote, arq = _lote(cfg_factory, banco_cfg)
    r = processar_arquivo(arq, cfg)
    assert r.status == SUCESSO
    bruto = _q(banco_cfg, "SELECT COUNT(*), COUNT(DISTINCT _arquivo_origem) FROM laboratorio.treino_nps")[0]
    tratado = _q(banco_cfg, "SELECT COUNT(*) FROM treino.treino_nps")[0][0]
    assert bruto == (r.linhas_entrada, 1) and tratado == r.linhas_saida > 0
    assert _q(banco_cfg, "SELECT arquivo, status FROM treino.lotes") == [(arq.name, "sucesso")]
    assert _q(banco_cfg, "SELECT COUNT(*) FROM treino.resumo")[0][0] > 0  # análise do 2º andar, também separada
    # nenhuma tabela de produção recebeu a planilha sintética
    producao = _q(banco_cfg, "SELECT table_schema, table_name FROM information_schema.tables "
                             "WHERE table_schema IN ('bruto','tratado','analitico','analise')")
    assert producao == []
    assert _q(banco_cfg, "SELECT to_regclass('robo.lotes')")[0][0] is None
    # o levantamento enxerga o que foi gravado, schema por schema
    pg = {(i["schema"], i["tabela"]): i for i in cb.levantar(cfg, gravar=False)["itens"] if i["onde"] == "postgres"}
    assert pg[("laboratorio", "treino_nps")]["natureza"] == "sintetico" and pg[("laboratorio", "treino_nps")]["linhas"] > 0
    assert pg[("treino", "lotes")]["situacao"] == cb.COM_DADOS


@com_pg
def teste_segundo_lote_da_mesma_regra_usa_a_mesma_tabela(cfg_factory, banco_cfg):
    cfg, _, arq = _lote(cfg_factory, banco_cfg)
    processar_arquivo(arq, cfg)
    fabrica.produzir_lote(cfg, "nps", semente=8)
    arq2 = next(p for p in (cfg.entrada / "sintetico").glob("TREINO_nps_*.xlsx"))
    processar_arquivo(arq2, cfg)
    tabelas = _q(banco_cfg, "SELECT table_name FROM information_schema.tables WHERE table_schema='laboratorio'")
    assert tabelas == [("treino_nps",)]
    assert _q(banco_cfg, "SELECT COUNT(DISTINCT _arquivo_origem) FROM laboratorio.treino_nps")[0][0] == 2


@com_pg
def teste_teto_de_espaco_para_de_carregar_sem_apagar(cfg_factory, banco_cfg):
    cfg, _, arq = _lote(cfg_factory, banco_cfg, pg_treino_mb_max=0)  # teto zero: já começa cheio
    r = processar_arquivo(arq, cfg)
    assert r.status == SUCESSO and r.tabelas_banco == []  # a planilha foi tratada; só não subiu ao banco
    assert any("NÃO carregada no PostgreSQL" in o.mensagem for o in r.relatorio.ocorrencias)
    assert _q(banco_cfg, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('laboratorio','treino')")[0][0] == 0
