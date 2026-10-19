"""Leitura de planilhas pela Bárbara: tema, cabeçalhos, regras conferidas, DAX e âncoras que batem — e o Heitor confere."""

import pandas as pd

from robo import leitura_bi as lb


def _marketing():
    return pd.DataFrame({"ID": [1, 2, 3, 4], "Canal": ["Google", "Meta", "Google", "Meta"],
                         "Investimento": [100.0, 200.0, 300.0, 400.0], "Cliques": [50, 80, -1, 100],
                         "Conversões": [5, 90, 1, 10]})


def teste_tema_papeis_regras_e_ancoras():
    le = lb.ler(_marketing(), "campanhas.xlsx", "real")
    assert le["tema"]["nome"] == "Marketing / mídia"
    papeis = {c["coluna"]: c["papel"] for c in le["colunas"]}
    assert papeis["canal"] == "categoria" and papeis["investimento"] == "numero"
    regras = {r["coluna"]: r["violacoes"] for r in le["regras"]}
    assert regras["cliques"] == 1 and regras["conversoes × cliques"] == 2   # 90 conv./80 cliques e 1 conv./-1 clique
    assert le["ancoras"]["Total Investimento"] == 1000.0 and le["ancoras"]["Linhas"] == 4
    assert le["ancoras"]["CPA (custo por conversão)"] == round(1000 / 106, 4)
    assert any("DIVIDE" in m["dax"] for m in le["medidas"]) and le["modelo"]["fato"] == "fato_campanhas"
    assert lb.reconciliar(_marketing(), le) == []


def teste_categoria_com_nome_de_valor_nao_vira_medida():
    df = pd.DataFrame({"Canal de Venda": ["Loja", "App"] * 15, "Valor da Venda": range(30)})
    le = lb.ler(df, "v.xlsx", "real")
    canal = next(c for c in le["colunas"] if c["coluna"] == "canal_de_venda")
    assert canal["papel"] == "categoria" and canal["agregacao"] is None
    assert le["modelo"]["metricas"] == ["valor_da_venda"]


def teste_nps_e_tema_desconhecido():
    df = pd.DataFrame({"Curso": ["A"] * 5 + ["B"] * 5, "Nota NPS": [10, 9, 9, 3, 7, 10, 10, 10, 10, 0]})
    le = lb.ler(df, "nps.xlsx", "real")
    assert le["ancoras"]["NPS"] == 50.0                                  # 7 promotores, 2 detratores em 10
    assert {r["segmento"]: r["NPS"] for r in le["por_segmento"]["linhas"]} == {"A": 40.0, "B": 60.0}
    estranho = lb.ler(pd.DataFrame({"xpto": [1, 2], "abc": ["u", "v"]}), "x.csv", "real")
    assert estranho["tema"]["certeza"] == 0                               # não inventa tema


def teste_heitor_pega_ancora_adulterada():
    le = lb.ler(_marketing(), "c.xlsx", "real")
    le["ancoras"]["Total Investimento"] = 999.0
    assert any("Total Investimento" in d for d in lb.reconciliar(_marketing(), le))


def teste_sinteticas_todas_as_areas_sem_divergencia():
    for nome, df in lb.planilhas_sinteticas():
        le = lb.ler(df, nome, "sintética")
        assert le["tema"]["certeza"] > 0, nome
        assert lb.reconciliar(df, le) == [], nome


def teste_rotina_registra_cada_planilha_uma_vez(cfg_factory):
    import sqlite3
    from robo import paineis
    cfg = cfg_factory()
    cfg.criar_pastas()
    paineis.rotina(cfg)
    paineis.rotina(cfg)
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    n = c.execute("SELECT COUNT(*), COUNT(DISTINCT nome) FROM paineis_planilhas").fetchone()
    c.close()
    assert n[0] == n[1] >= 6 and len(paineis.publicado(cfg)["planilhas"]) >= 6


def teste_amostra_do_relatorio_sem_identificador_e_registro_sem_linhas(cfg_factory):
    import json
    import sqlite3
    from robo import paineis
    le = lb.ler(_marketing(), "c.xlsx", "real")
    a = le["amostra"]
    assert "id" not in a["colunas"] and set(a["colunas"]) == {"canal", "investimento", "cliques", "conversoes"}
    assert a["linhas"] == a["total"] == 4 and sum(a["colunas"]["investimento"]) == le["ancoras"]["Total Investimento"]
    cfg = cfg_factory()
    cfg.criar_pastas()
    paineis.rotina(cfg)
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    registro = json.loads(c.execute("SELECT leitura FROM paineis_planilhas LIMIT 1").fetchone()[0])
    c.close()
    assert "amostra" not in registro                                       # as linhas não são duplicadas no banco
