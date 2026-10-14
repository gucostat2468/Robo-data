"""Roda TODAS as consultas de consultas_sql/ contra um PostgreSQL real com dados de exemplo."""

import os
import uuid
from datetime import date, timedelta

import pytest

from robo import consultas
from robo.banco import Banco

DSN = os.environ.get("ROBO_TESTE_PG")
pytestmark = pytest.mark.skipif(not DSN, reason="defina ROBO_TESTE_PG para testar com PostgreSQL")

DADOS = """
CREATE SCHEMA IF NOT EXISTS tratado;
CREATE TABLE tratado.dim_curso (id_curso bigint, curso text, modalidade text);
INSERT INTO tratado.dim_curso VALUES (1, 'Direito', 'EAD'), (2, 'Medicina', 'Presencial');
CREATE TABLE tratado.fato_nps (id_resposta text, data_resposta date, nota_nps bigint, id_curso bigint, uf text,
    comentario text, _arquivo_origem text, _processado_em timestamp);
CREATE TABLE tratado.fato_csat (id_resposta text, data_resposta date, canal text, nota_csat bigint, nota_ces bigint, motivo text);
CREATE TABLE tratado.clientes (id_cliente text, data_entrada date, data_saida date, plano text);
CREATE TABLE tratado.vendas (id_venda text, data_venda date, id_cliente text, produto text, valor double precision);
CREATE TABLE tratado.funil (id_lead text, etapa text, data_etapa date, origem text);
"""


@pytest.fixture(scope="module")
def banco():
    import psycopg
    d = dict(p.split("=", 1) for p in DSN.split())
    nome = f"robo_consultas_{uuid.uuid4().hex[:8]}"
    cfg = {"host": d.get("host", "localhost"), "porta": int(d.get("port", 5432)), "usuario": d.get("user", "postgres"),
           "senha": d.get("password", ""), "banco": nome}
    b = Banco(cfg, consultas.RAIZ_PROJETO)
    b.criar_banco_se_preciso()
    with b.conectar() as conn:
        b.inicializar(conn)
        conn.execute(DADOS)
        # NPS: setembro (10,9,6,0,8) => NPS 0 ; outubro (10,10,9,7,7,3) => 3 promotores, 1 detrator, 6 => NPS 33,3
        nps = [("1", date(2026, 9, 1), 10, 1, "SP"), ("2", date(2026, 9, 2), 9, 1, "SP"), ("3", date(2026, 9, 3), 6, 2, "RJ"),
               ("4", date(2026, 9, 4), 0, 2, "RJ"), ("5", date(2026, 9, 5), 8, 1, "MG"), ("6", date(2026, 10, 1), 10, 1, "SP"),
               ("7", date(2026, 10, 2), 10, 2, "SP"), ("8", date(2026, 10, 3), 9, 1, "MG"), ("9", date(2026, 10, 4), 7, 2, "RJ"),
               ("9", date(2026, 10, 5), 7, 2, "RJ"),  # id 9 repetido de propósito
               ("10", date(2026, 10, 6), 3, 1, "SP")]
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO tratado.fato_nps VALUES (%s,%s,%s,%s,%s,'coment',%s,now())",
                            [(*n, f"nps_{n[1]:%m}.xlsx") for n in nps])
            cur.executemany("INSERT INTO tratado.fato_csat VALUES (%s,%s,%s,%s,%s,%s)",
                            [(str(i), date(2026, 9 + i % 2, 1 + i), ["chat", "telefone"][i % 2], 1 + i % 5, 1 + i % 7,
                              ["demora", "preço", None][i % 3]) for i in range(20)])
            cur.executemany("INSERT INTO tratado.clientes VALUES (%s,%s,%s,%s)",
                            [(str(i), date(2026, 1, 1) + timedelta(days=20 * i),
                              (date(2026, 1, 1) + timedelta(days=20 * i + 90)) if i % 3 == 0 else None,
                              ["Básico", "Premium"][i % 2]) for i in range(12)])
            cur.executemany("INSERT INTO tratado.vendas VALUES (%s,%s,%s,%s,%s)",
                            [(str(i), date(2026, 1 + i % 6, 1 + i % 25), str(i % 7), f"P{i % 5}",
                              100.0 + i * 3 if i != 13 else 99999.0) for i in range(40)])
            etapas = ["lead", "contato", "proposta", "matricula"]
            cur.executemany("INSERT INTO tratado.funil VALUES (%s,%s,%s,%s)",
                            [(str(l), etapas[e], date(2026, 3, 1) + timedelta(days=e), ["site", "indicação"][l % 2])
                             for l in range(10) for e in range(4 - l % 4)])
            cur.execute("INSERT INTO robo.lotes (lote_id, arquivo, status, linhas_entrada, linhas_saida, erros, avisos) "
                        "VALUES ('a', 'nps_09.xlsx', 'sucesso', 6, 5, 0, 1), ('b', 'nps_x.xlsx', 'reprovado', 3, 0, 2, 0)")
            cur.execute("INSERT INTO robo.ocorrencias (lote_id, arquivo, nivel, coluna, mensagem, quantidade) "
                        "VALUES ('b', 'nps_x.xlsx', 'ERRO', 'nota_nps', 'Valores fora da faixa', 2)")
        conn.commit()
    yield b
    with psycopg.connect(host=cfg["host"], port=cfg["porta"], user=cfg["usuario"], password=cfg["senha"],
                         dbname="postgres", autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)')


def _todas():
    return [c["id"] for c in consultas.listar()]


def test_biblioteca_tem_cabecalhos_completos():
    itens = consultas.listar()
    assert len(itens) >= 25
    for c in itens:
        assert c["titulo"] and c["pergunta"] and c["como_ler"] and c["requer"], c["id"]


@pytest.mark.parametrize("id_consulta", _todas())
def test_consulta_executa(banco, id_consulta):
    r = consultas.executar(banco, id_consulta)
    assert r["colunas"], id_consulta
    assert r["linhas"], f"{id_consulta} não retornou linhas com os dados de exemplo"


def test_numeros_do_nps_conferem(banco):
    r = consultas.executar(banco, "03 NPS/02_nps_mensal_com_variacao.sql")
    por_mes = {str(l[0]): float(l[2]) for l in r["linhas"]}
    assert por_mes["2026-09-01"] == 0.0
    assert por_mes["2026-10-01"] == 33.3
    teste = consultas.executar(banco, "03 NPS/05_teste_diferenca_ultimos_dois_meses.sql")
    assert float(teste["linhas"][0][4]) == 33.3
    dup = consultas.executar(banco, "02 Qualidade dos dados/02_duplicidades_por_chave.sql")
    assert dup["linhas"][0][0] == "9"
    outl = consultas.executar(banco, "02 Qualidade dos dados/04_outliers_iqr.sql")
    assert outl["linhas"][0][4] == 99999.0


def test_execucao_e_somente_leitura(banco, tmp_path):
    (tmp_path / "x.sql").write_text("CREATE TABLE tratado.invasora (a int);", encoding="utf-8")
    with pytest.raises(Exception) as erro:
        consultas.executar(banco, "x.sql", pasta=tmp_path)
    assert "read-only" in str(erro.value).lower() or "somente leitura" in str(erro.value).lower()


def test_nao_sai_da_pasta(tmp_path):
    with pytest.raises(ValueError):
        consultas.caminho_seguro("../config.yaml")
