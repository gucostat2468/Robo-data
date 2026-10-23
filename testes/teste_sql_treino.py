"""Treino de SQL sobre os dados que existem (lotes da fábrica) e disponibilidade da biblioteca de consultas.

O que precisa ser verdade sempre:
  - o exercício só aceita nome de arquivo da fábrica e nível conhecido (nada de texto livre dentro do SQL);
  - todo SQL gerado passa na validação de somente leitura da biblioteca;
  - no PostgreSQL de verdade, os 4 níveis batem com o gabarito de um lote processado pela esteira;
  - gabarito errado é pego (a conferência não é enfeite);
  - consulta que precisa de planilha REAL aparece como indisponível com o motivo, em vez de quebrar.
"""

import json
import os
import uuid

import pytest

from robo import consultas, fabrica, ferramentas, organizacao, sql_treino
from robo.pipeline import SUCESSO, processar_arquivo

DSN = os.environ.get("ROBO_TESTE_PG")
com_pg = pytest.mark.skipif(not DSN, reason="defina ROBO_TESTE_PG para testar com PostgreSQL")
ARQ = "TREINO_nps_20261023_100000_00001.xlsx"


# ----------------------------------------------------------------------------------------------- sem banco
@pytest.mark.parametrize("nivel", sql_treino.NIVEIS)
def teste_todo_sql_gerado_e_somente_leitura(nivel):
    ex = sql_treino.montar("nps", ARQ, nivel)
    consultas.validar_leitura(ex["sql"])  # levanta erro se não for um SELECT/WITH só
    assert ARQ in ex["sql"] and ex["pergunta"]


@pytest.mark.parametrize("arquivo", ["x'; DROP TABLE t; --", "planilha.xlsx", "", "TREINO_a b.xlsx"])
def teste_arquivo_fora_do_padrao_e_recusado(arquivo):
    with pytest.raises(ValueError):
        sql_treino.montar("nps", arquivo, "basico")


def teste_nivel_desconhecido_e_recusado():
    with pytest.raises(ValueError):
        sql_treino.montar("nps", ARQ, "facil")


def teste_conferencia_acha_diferenca():
    ex = sql_treino.montar("nps", ARQ, "basico")
    assert sql_treino.conferir(ex, ["linhas"], [[10]], {"linhas": 10}) == []
    assert sql_treino.conferir(ex, ["linhas"], [[9]], {"linhas": 10})
    assert sql_treino.conferir(ex, ["linhas"], [], {"linhas": 10}) == ["o SQL não devolveu nenhuma linha"]
    ex = sql_treino.montar("nps", ARQ, "dificil")
    linhas = [["Direito", 6, 60.0], ["Medicina", 4, 40.0]]
    assert sql_treino.conferir(ex, ["segmento", "linhas", "participacao_pct"], linhas,
                               {"por_segmento": {"Direito": 6, "Medicina": 4}}) == []
    assert sql_treino.conferir(ex, ["segmento", "linhas", "participacao_pct"], linhas,
                               {"por_segmento": {"Direito": 5, "Medicina": 5}})


def teste_so_areas_de_dados_ganham_o_treino_de_sql():
    com = [p["id"] for p in organizacao.lista() if "sql_treino" in organizacao.ferramentas_de(p["id"], p["andar"])]
    assert com, "ninguém ganhou o treino de SQL"
    assert all(organizacao.area_de(pid) in sql_treino.AREAS_DE_DADOS for pid in com)
    assert not any(organizacao.area_de(p["id"]) == "RH" for p in organizacao.lista() if p["id"] in com)


def teste_ferramenta_com_banco_desligado_nao_inventa(cfg_factory):
    cfg = cfg_factory()
    r = ferramentas.executar("sql_treino", cfg, regra="nps", arquivo=ARQ, nivel="basico")
    assert not r["ok"] and "desligado" in r["texto"]


# ----------------------------------------------------------------------------------------------- com PostgreSQL
@pytest.fixture
def banco_cfg():
    import psycopg
    d = dict(p.split("=", 1) for p in DSN.split())
    nome = f"robo_sqltreino_{uuid.uuid4().hex[:8]}"
    cfg = {"habilitado": True, "host": d.get("host", "localhost"), "porta": int(d.get("port", 5432)),
           "usuario": d.get("user", "postgres"), "senha": d.get("password", ""), "banco": nome}
    yield cfg
    with psycopg.connect(host=cfg["host"], port=cfg["porta"], user=cfg["usuario"], password=cfg["senha"],
                         dbname="postgres", autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)')


@pytest.fixture
def lote_no_banco(cfg_factory, banco_cfg):
    cfg = cfg_factory(banco=banco_cfg, fabrica={"linhas_min": 300, "linhas_max": 400})
    cfg.criar_pastas()
    lote = fabrica.produzir_lote(cfg, "nps", semente=11)
    arq = next((cfg.entrada / "sintetico").glob("TREINO_nps_*.xlsx"))
    assert processar_arquivo(arq, cfg).status == SUCESSO
    with fabrica._tb(cfg).tx() as c:
        gab = json.loads(c.execute("SELECT gabarito FROM fabrica_lotes WHERE id=?", (lote["lote"],)).fetchone()[0])
    return cfg, arq.name, gab


@com_pg
@pytest.mark.parametrize("nivel", sql_treino.NIVEIS)
def teste_os_quatro_niveis_batem_com_o_gabarito(lote_no_banco, nivel):
    cfg, arquivo, gab = lote_no_banco
    r = sql_treino.executar(cfg, "nps", arquivo, nivel, gab)
    assert r["confere"], r["diferencas"]
    assert r["linhas"]


@com_pg
def teste_gabarito_errado_nao_confere_e_ferramenta_registra(lote_no_banco):
    cfg, arquivo, gab = lote_no_banco
    errado = {**gab, "linhas": gab["linhas"] + 1}
    r = ferramentas.executar("sql_treino", cfg, regra="nps", arquivo=arquivo, nivel="basico", gabarito=errado)
    assert r["ok"] and r["dados"]["confere"] is False and "NÃO confere" in r["texto"]
    certo = ferramentas.executar("sql_treino", cfg, regra="nps", arquivo=arquivo, nivel="profissional", gabarito=gab)
    assert certo["dados"]["confere"] is True


@com_pg
def teste_lotes_no_banco_so_devolve_o_que_foi_carregado(lote_no_banco):
    cfg, arquivo, gab = lote_no_banco
    fantasmas = [{"regra": "nps", "arquivo": arquivo}, {"regra": "nps", "arquivo": "TREINO_nps_1_2_3.xlsx"},
                 {"regra": "churn", "arquivo": "TREINO_churn_1_2_3.xlsx"}]
    assert [l["arquivo"] for l in sql_treino.lotes_no_banco(cfg, fantasmas)] == [arquivo]


@com_pg
def teste_biblioteca_marca_o_que_tem_dado_e_o_que_precisa_de_planilha_real(lote_no_banco):
    from robo.banco import Banco
    cfg, _, _ = lote_no_banco
    itens = {c["id"]: c for c in consultas.disponibilidade(Banco(cfg.banco, cfg.base))}
    treino = [c for c in itens.values() if "treino.treino_nps" in (c.get("requer") or "")]
    assert treino and all(c["disponivel"] for c in treino)
    reais = [c for c in itens.values() if "tratado.fato_nps" in (c.get("requer") or "")]
    assert reais and all(not c["disponivel"] and "planilha REAL" in c["motivo"] for c in reais)
    # e as consultas de treino disponíveis rodam de verdade, sem erro
    for c in treino:
        r = consultas.executar(Banco(cfg.banco, cfg.base), c["id"])
        assert r["colunas"]


# ----------------------------------------------------------------------------------------------- biblioteca 07 e 08
@pytest.fixture(scope="module")
def empresa_com_um_lote_por_regra(tmp_path_factory):
    """Um lote de cada regra da fábrica processado pela esteira de verdade + o espelho da memória no PostgreSQL."""
    import psycopg
    from robo import memoria, regras_negocio
    from robo.config import carregar_config
    d = dict(p.split("=", 1) for p in DSN.split())
    nome = f"robo_biblioteca_{uuid.uuid4().hex[:8]}"
    banco = {"habilitado": True, "host": d.get("host", "localhost"), "porta": int(d.get("port", 5432)),
             "usuario": d.get("user", "postgres"), "senha": d.get("password", ""), "banco": nome}
    raiz = tmp_path_factory.mktemp("empresa")
    (raiz / "Bases-Limpeza").mkdir()
    cfg = carregar_config(raiz / "nao_existe.yaml", sobrescrever={
        "pastas": {"entrada": str(raiz / "Bases-Limpeza"), "logs": str(raiz / "logs"), "agentes": str(raiz / "agentes"),
                   "habilidades": str(raiz / "habilidades")},
        "banco": banco, "fabrica": {"linhas_min": 200, "linhas_max": 300}})
    cfg.criar_pastas()
    for i, regra in enumerate(regras_negocio.REGRAS):
        fabrica.produzir_lote(cfg, regra.id, semente=100 + i)
    for arq in sorted((cfg.entrada / "sintetico").glob("TREINO_*.xlsx")):
        processar_arquivo(arq, cfg)
    fabrica.conferir_pendentes(cfg)
    memoria.sincronizar_postgres(cfg)
    yield cfg
    with psycopg.connect(host=banco["host"], port=banco["porta"], user=banco["usuario"], password=banco["senha"],
                         dbname="postgres", autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)')


@com_pg
@pytest.mark.parametrize("id_consulta", [c["id"] for c in consultas.listar() if c["id"].startswith(("07 ", "08 "))])
def teste_consultas_da_empresa_rodam_ou_explicam_por_que_nao(empresa_com_um_lote_por_regra, id_consulta):
    from robo.banco import Banco
    cfg = empresa_com_um_lote_por_regra
    b = Banco(cfg.banco, cfg.base)
    disp = consultas.disponibilidade(b, [c for c in consultas.listar() if c["id"] == id_consulta])[0]
    if id_consulta.startswith("07 "):
        assert disp["disponivel"], disp["motivo"]  # todo lote da fábrica foi carregado: tem que ter dado
    if not disp["disponivel"]:
        assert disp["motivo"].startswith("ainda sem dados em robo.memoria_"), disp["motivo"]
        return
    r = consultas.executar(b, id_consulta)
    assert r["colunas"], id_consulta
    if id_consulta.startswith("07 "):
        assert r["linhas"], f"{id_consulta} sem linhas com um lote de cada regra carregado"


@com_pg
def teste_usuario_de_leitura_da_nuvem_alcanca_o_treino(lote_no_banco):
    """Bug achado pelo boletim do celular: na nuvem, robo_leitura só via o schema robo e TODO exercício de SQL falhava."""
    import psycopg
    from robo import nuvem
    cfg, arquivo, gab = lote_no_banco
    cfg.banco["senha_leitura"] = "leitura-" + uuid.uuid4().hex[:8]
    try:
        assert nuvem.garantir_leitura(cfg)
        cfg.banco["usuario_leitura"] = "robo_leitura"
        r = sql_treino.executar(cfg, "nps", arquivo, "profissional", gab)  # profissional lê laboratorio E treino
        assert r["confere"], r["diferencas"]
        with pytest.raises(psycopg.Error):  # e continua só de leitura
            from robo.banco import Banco
            with Banco(cfg.banco, cfg.base).conectar(leitura=True) as conn:
                conn.execute("CREATE TABLE treino.invasora (x int)")
    finally:
        cfg.banco.pop("usuario_leitura", None)
        b = cfg.banco
        with psycopg.connect(host=b["host"], port=b["porta"], user=b["usuario"], password=b["senha"], dbname=b["banco"],
                             autocommit=True) as c:
            c.execute("REASSIGN OWNED BY robo_leitura TO CURRENT_USER")
            c.execute("DROP OWNED BY robo_leitura")
