"""Esteira genérica (robo/esteira_dados.py): qualidade, padronização, modelo estrela e ML honesto.

O que precisa ser verdade:
  - ML com sinal real: supera a linha de base e diz que vale;
  - ML com alvo aleatório: NÃO supera e diz para não usar (o teste mais importante: o robô não pode "achar" padrão
    em ruído);
  - coluna que é o resultado disfarçado (vazamento) é retirada e listada;
  - com data, a divisão é por tempo (teste = o período mais recente);
  - base pequena ou classe rara: recusa com motivo em vez de inventar;
  - 'sudeste ' e 'Sudeste' viram um valor só, registrado;
  - modelo estrela: fato com as mesmas linhas, chaves únicas, soma da métrica igual à da base;
  - a entrega completa grava modelo_powerbi.xlsx, medidas_dax.txt e a seção de ML no relatório.
"""

import numpy as np
import pandas as pd
import pytest

from robo import esteira_dados as e
from robo.analise import papel_coluna
from robo.relatorio import Relatorio

pytest.importorskip("sklearn")


def _base(n=800, semente=0):
    rng = np.random.default_rng(semente)
    df = pd.DataFrame({"id_cliente": range(n), "regiao": rng.choice(["Sul", "Norte", "Leste"], n),
                       "plano": rng.choice(["A", "B"], n), "uso_horas": rng.gamma(2, 10, n),
                       "chamados": rng.poisson(2, n), "data": pd.date_range("2025-01-01", periods=n, freq="12h")})
    z = -1 + 0.5 * df["chamados"] - 0.06 * df["uso_horas"] + (df["plano"] == "B") * 1.2
    df["cancelou"] = np.where(rng.random(n) < 1 / (1 + np.exp(-z)), "sim", "nao")
    df["ruido"] = rng.choice(["x", "y"], n)
    return df


def _papeis(df):
    return {c: papel_coluna(df[c], c, 30, ["id_*"]) for c in df.columns}


def teste_ml_com_sinal_supera_linha_de_base():
    df = _base()
    r = e.aprender(df, _papeis(df), "cancelou")
    assert r["ok"] and r["vale"], r.get("veredito")
    assert r["teste"]["acuracia_balanceada"] > r["teste_linha_base"]["acuracia_balanceada"]
    assert "id_cliente (identificador)" in r["fora"]
    assert {x["variavel"] for x in r["importancias"][:3]} & {"chamados", "uso_horas", "plano"}


def teste_ml_em_ruido_diz_para_nao_usar():
    df = _base()
    r = e.aprender(df, _papeis(df), "ruido")
    assert r["ok"] and not r["vale"] and "NÃO supera" in r["veredito"]


def teste_regressao_em_ruido_nao_vale():
    df = _base()
    df["valor"] = np.random.default_rng(5).normal(100, 10, len(df))
    r = e.aprender(df, _papeis(df), "valor")
    assert r["tipo"] == "regressao" and not r["vale"]


def teste_vazamento_e_retirado_e_divisao_por_tempo():
    df = _base()
    df["motivo_saida"] = np.where(df["cancelou"] == "sim", "preço", "(nenhum)")  # só existe depois do resultado
    r = e.aprender(df, _papeis(df), "cancelou")
    assert [v["coluna"] for v in r["vazamentos"]] == ["motivo_saida"]
    assert all(x["variavel"] != "motivo_saida" for x in r["importancias"])
    assert r["divisao"].startswith("por tempo (data)")
    prev = r["previsoes"]
    assert prev["linha"].min() >= int(len(df) * 0.8) - 1  # o teste é o pedaço mais recente


def teste_recusa_base_pequena_classe_rara_e_alvo_inexistente():
    df = _base(60)
    assert "mínimo" in e.aprender(df, _papeis(df), "cancelou")["motivo"]
    df = _base(400)
    df.loc[:, "raro"] = "comum"
    df.loc[:4, "raro"] = "raro"
    assert "só 5 casos" in e.aprender(df, _papeis(df), "raro")["motivo"]
    assert not e.aprender(df, _papeis(df), "nao_existe")["ok"]


def teste_mesma_planilha_mesmo_resultado():
    df = _base()
    a, b = e.aprender(df, _papeis(df), "cancelou"), e.aprender(df, _papeis(df), "cancelou")
    assert a["teste"] == b["teste"] and a["comparacao"] == b["comparacao"]


def teste_padroniza_grafias_e_registra():
    rel = Relatorio(arquivo="x")
    df = pd.DataFrame({"regiao": ["Sudeste", "Sudeste", "sudeste ", "SUDESTE", "Sul", "São Paulo", "sao paulo"],
                       "n": range(7)})
    out = e.padronizar_categorias(df, rel, "t")
    assert out["regiao"].tolist() == ["Sudeste"] * 4 + ["Sul", "São Paulo", "São Paulo"]
    assert any("unificadas" in o.mensagem and o.quantidade == 3 for o in rel.ocorrencias)
    assert df["regiao"].iloc[2] == "sudeste "  # o original não é alterado


def teste_qualidade_mede_dimensoes():
    df = pd.DataFrame({"id": [1, 2, 2, 4], "cat": ["a", "A", "b", None], "v": [1.0, None, 3.0, 4.0]})
    q = e.qualidade(df, {"id": "id", "cat": "categoria", "v": "numero"})
    c = q["colunas"].set_index("coluna")
    assert c.loc["id", "unicidade"] == 75.0 and c.loc["cat", "completude"] == 75.0
    assert c.loc["cat", "consistencia"] == 66.7  # "A" fora da grafia de referência "a" and c.loc["v", "completude"] == 75.0
    assert any("Exatidão" in x for x in q["notas"])


def teste_modelo_estrela_confere():
    df = _base(300)
    rel = Relatorio(arquivo="x")
    m = e.modelo_estrela(df, _papeis(df), "vendas", rel, [{"coluna": "uso_horas", "op": "soma"}])
    fato = m["tabelas"][m["fato"]]
    assert len(fato) == len(df) and all(c["ok"] for c in m["conferencias"])
    assert {"dim_regiao", "dim_plano", "dim_calendario"} <= set(m["tabelas"])
    assert fato["uso_horas"].sum() == pytest.approx(df["uso_horas"].sum())
    assert "Total Uso Horas = SUM('fato_vendas'[uso_horas])" in m["dax"]
    assert "SAMEPERIODLASTYEAR('dim_calendario'[data])" in m["dax"]


def teste_entrega_completa_com_ml(cfg_factory, tmp_path):
    from robo import entrega
    cfg = cfg_factory()
    arq = tmp_path / "clientes.xlsx"
    df = _base(600)
    df["regiao"] = df["regiao"].replace({"Sul": "sul "}).where(df.index % 2 == 0, df["regiao"])
    df.to_excel(arq, index=False)
    r = entrega.entregar(cfg, arq, tmp_path / "saida", alvo="cancelou")
    assert r["ok"] and {"modelo_powerbi.xlsx", "medidas_dax.txt"} <= set(r["arquivos"])
    assert r["ml"]["ok"] and r["ml"]["vale"]
    assert all(c["ok"] for c in r["conferencias"])
    pasta = tmp_path / "saida" / r["pasta"].split("/")[-1]
    html = (pasta / "relatorio.html").read_text(encoding="utf-8")
    assert "Machine Learning — prever" in html and "esquema estrela" in html and "dimensões DAMA" in html
    base = pd.read_excel(pasta / "base_tratada.xlsx")
    assert set(base["regiao"].dropna()) <= {"Sul", "Norte", "Leste", "sul"}
    assert base["regiao"].nunique() == 3  # 'sul ' e 'Sul' unificados
