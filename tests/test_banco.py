"""Testes contra um PostgreSQL REAL. Rodam só se a variável ROBO_TESTE_PG estiver definida, ex.:
    set ROBO_TESTE_PG=host=localhost port=5432 user=postgres password=suasenha
"""

import os
import uuid

import pandas as pd
import pytest
from openpyxl import Workbook

from conftest import REGRA_NPS
from robo.pipeline import ADIADO, REPROVADO, SUCESSO, processar_arquivo

DSN = os.environ.get("ROBO_TESTE_PG")
pytestmark = pytest.mark.skipif(not DSN, reason="defina ROBO_TESTE_PG para testar com PostgreSQL")


def _dsn_dict():
    return dict(p.split("=", 1) for p in DSN.split())


@pytest.fixture
def banco_cfg():
    import psycopg
    d = _dsn_dict()
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


def _planilha(pasta, nome, linhas, cabecalho=("ID Resposta", "Data Resposta", "Nota NPS", "Curso", "Modalidade", "UF")):
    wb = Workbook()
    ws = wb.active
    ws.append(list(cabecalho))
    for l in linhas:
        ws.append(list(l))
    caminho = pasta / "Bases-Limpeza" / nome
    wb.save(caminho)
    return caminho


def test_elt_completo_bruto_tratado_analitico(planilha_baguncada, cfg_factory, banco_cfg, tmp_path):
    modelos = tmp_path / "modelos"
    modelos.mkdir()
    (modelos / "01_nps_por_curso.sql").write_text("""
        CREATE OR REPLACE VIEW analitico.vw_nps_por_curso AS
        SELECT c.curso, count(*) AS respostas,
               round(100.0 * (count(*) FILTER (WHERE f.nota_nps >= 9) - count(*) FILTER (WHERE f.nota_nps <= 6)) / count(*), 1) AS nps
        FROM tratado.fato_nps f JOIN tratado.dim_curso c USING (id_curso) GROUP BY c.curso;""", encoding="utf-8")
    (modelos / "_rascunho.sql").write_text("ISSO NAO E SQL", encoding="utf-8")  # ignorado (começa com _)

    regra = dict(REGRA_NPS, modelo={"fato": "fato_nps", "calendario": "data_resposta",
                                    "dimensoes": {"dim_curso": {"colunas": ["curso", "modalidade"], "chave": "id_curso"}}})
    cfg = cfg_factory([regra], banco={**banco_cfg, "pasta_modelos": str(modelos)})
    r = processar_arquivo(planilha_baguncada, cfg)
    assert r.status == SUCESSO, r.relatorio.texto()

    # bruto: exatamente o que veio (6 linhas de dados incluindo duplicada e Total), tudo texto, com linha de origem
    bruto = _q(banco_cfg, "SELECT _linha_origem, valor_mensalidade FROM bruto.nps_outubro ORDER BY 1")
    assert len(bruto) == 6
    assert bruto[0] == (4, "R$ 1.234,56")
    # tratado: tipado e limpo
    fato = _q(banco_cfg, "SELECT id_resposta, nota_nps, valor_mensalidade, data_resposta FROM tratado.fato_nps ORDER BY 1")
    assert len(fato) == 4
    assert fato[0][1] == 10 and fato[0][2] == 1234.56
    tipos = dict(_q(banco_cfg, "SELECT column_name, data_type FROM information_schema.columns "
                               "WHERE table_schema='tratado' AND table_name='fato_nps'"))
    assert tipos["nota_nps"] == "bigint" and tipos["data_resposta"] == "date"
    # analítico: view criada pelo modelo SQL
    nps = dict(_q(banco_cfg, "SELECT curso, nps FROM analitico.vw_nps_por_curso"))
    assert float(nps["Direito"]) == pytest.approx(33.3)
    # controle
    lotes = _q(banco_cfg, "SELECT status, linhas_saida FROM robo.lotes")
    assert lotes == [("sucesso", 4)]
    assert _q(banco_cfg, "SELECT count(*) FROM tratado.dim_calendario")[0][0] == 365


def test_reprocessar_mesmo_arquivo_nao_duplica(pastas, cfg_factory, banco_cfg):
    cfg = cfg_factory([], banco=banco_cfg)
    for _ in range(2):
        c = _planilha(pastas, "vendas.xlsx", [(1, "01/10/2026", 9, "Direito", "EAD", "SP")])
        assert processar_arquivo(c, cfg).status == SUCESSO
    assert _q(banco_cfg, "SELECT count(*) FROM tratado.vendas")[0][0] == 1
    assert _q(banco_cfg, "SELECT count(*) FROM bruto.vendas")[0][0] == 1
    assert _q(banco_cfg, "SELECT count(*) FROM robo.lotes")[0][0] == 2


def test_dimensao_mantem_chaves_entre_arquivos(pastas, cfg_factory, banco_cfg):
    regra = {"padrao": "nps_*", "destino": {"tabela": "nps"},
             "modelo": {"fato": "fato_nps", "dimensoes": {"dim_curso": {"colunas": ["curso"], "chave": "id_curso"}}}}
    cfg = cfg_factory([regra], banco=banco_cfg)
    c1 = _planilha(pastas, "nps_set.xlsx", [(1, "01/09/2026", 9, "Medicina", "EAD", "SP"),
                                            (2, "02/09/2026", 5, "Direito", "EAD", "SP")])
    assert processar_arquivo(c1, cfg).status == SUCESSO
    c2 = _planilha(pastas, "nps_out.xlsx", [(3, "01/10/2026", 10, "Direito", "EAD", "SP"),
                                            (4, "02/10/2026", 8, "Psicologia", "EAD", "SP")])
    assert processar_arquivo(c2, cfg).status == SUCESSO
    dim = dict(_q(banco_cfg, "SELECT curso, id_curso FROM tratado.dim_curso"))
    assert len(dim) == 3
    juntos = _q(banco_cfg, "SELECT f.id_resposta, d.curso FROM tratado.fato_nps f JOIN tratado.dim_curso d "
                           "USING (id_curso) ORDER BY 1")
    assert [c for _, c in juntos] == ["Medicina", "Direito", "Direito", "Psicologia"]


def test_mesclar_por_chave(pastas, cfg_factory, banco_cfg):
    regra = {"padrao": "clientes*", "destino": {"tabela": "clientes", "modo": "mesclar", "chave": ["id_cliente"]}}
    cfg = cfg_factory([regra], banco=banco_cfg)
    cab = ("ID Cliente", "Nome", "Plano")
    assert processar_arquivo(_planilha(pastas, "clientes_1.xlsx", [(1, "Ana", "A"), (2, "Bia", "B")], cab), cfg).status == SUCESSO
    assert processar_arquivo(_planilha(pastas, "clientes_2.xlsx", [(2, "Bia", "C"), (3, "Caio", "A")], cab), cfg).status == SUCESSO
    assert _q(banco_cfg, "SELECT id_cliente, plano FROM tratado.clientes ORDER BY 1") == [("1", "A"), ("2", "C"), ("3", "A")]


def test_conflito_de_tipo_reprova_e_nao_publica(pastas, cfg_factory, banco_cfg):
    cfg = cfg_factory([{"padrao": "metas*", "destino": {"tabela": "metas"}}], banco=banco_cfg)
    cab = ("Mes", "Meta")
    assert processar_arquivo(_planilha(pastas, "metas_1.xlsx", [("jan", 10), ("fev", 20)], cab), cfg).status == SUCESSO
    r = processar_arquivo(_planilha(pastas, "metas_2.xlsx", [("mar", "alta"), ("abr", "baixa")], cab), cfg)
    assert r.status == REPROVADO
    assert "Conflito de tipo" in r.relatorio.texto()
    assert not (cfg.tratadas / "metas_2.xlsx").exists()
    assert _q(banco_cfg, "SELECT count(*) FROM tratado.metas")[0][0] == 2
    # bruto guarda tudo o que chegou (auditoria), inclusive o reprovado; tratado não
    assert _q(banco_cfg, "SELECT count(*) FROM bruto.metas WHERE _arquivo_origem = 'metas_2.xlsx'")[0][0] == 2
    assert ("reprovado",) in _q(banco_cfg, "SELECT status FROM robo.lotes")
    erros = _q(banco_cfg, "SELECT arquivo, nivel, mensagem FROM robo.ocorrencias WHERE nivel = 'ERRO'")
    assert erros and erros[0][0] == "metas_2.xlsx" and "Conflito de tipo" in erros[0][2]


def test_alargamento_de_tipo_e_coluna_nova(pastas, cfg_factory, banco_cfg):
    cfg = cfg_factory([{"padrao": "m*", "destino": {"tabela": "m"}}], banco=banco_cfg)
    assert processar_arquivo(_planilha(pastas, "m1.xlsx", [("a", 10)], ("Item", "Valor")), cfg).status == SUCESSO
    assert processar_arquivo(_planilha(pastas, "m2.xlsx", [("b", 2.5, "x")], ("Item", "Valor", "Extra")), cfg).status == SUCESSO
    tipos = dict(_q(banco_cfg, "SELECT column_name, data_type FROM information_schema.columns "
                               "WHERE table_schema='tratado' AND table_name='m'"))
    assert tipos["valor"] == "double precision" and tipos["extra"] == "text"


def test_modelo_sql_com_erro_reprova(planilha_baguncada, cfg_factory, banco_cfg, tmp_path):
    (tmp_path / "ruim.sql").write_text("SELECT * FROM tabela_que_nao_existe;", encoding="utf-8")
    cfg = cfg_factory([REGRA_NPS], banco={**banco_cfg, "pasta_modelos": str(tmp_path)})
    r = processar_arquivo(planilha_baguncada, cfg)
    assert r.status == REPROVADO
    assert "ruim.sql" in r.relatorio.texto()


def test_banco_fora_do_ar_adia_sem_mexer_no_arquivo(planilha_baguncada, cfg_factory, banco_cfg):
    cfg = cfg_factory([REGRA_NPS], banco={**banco_cfg, "porta": 1, "tempo_limite_conexao": 2})
    r = processar_arquivo(planilha_baguncada, cfg)
    assert r.status == ADIADO
    assert planilha_baguncada.exists()
    assert not (cfg.tratadas / "nps_outubro.xlsx").exists()
