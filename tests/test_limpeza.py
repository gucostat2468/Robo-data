import pandas as pd
import pytest

from robo.limpeza import limpar_tabela, normalizar_nome_coluna, numero_de
from robo.config import PADROES
from robo.relatorio import Relatorio


@pytest.mark.parametrize("entrada,esperado", [
    ("  Data de Admissão (R$) ", "data_de_admissao_r"),
    ("Nota NPS", "nota_nps"),
    ("2024", "c_2024"),
    ("", "coluna"),
    ("Ação/Reação", "acao_reacao"),
])
def test_normalizar_nome_coluna(entrada, esperado):
    assert normalizar_nome_coluna(entrada) == esperado


@pytest.mark.parametrize("valor,decimal,esperado", [
    ("1.234,56", ",", 1234.56),
    ("R$ 1.234,56", ",", 1234.56),
    ("-R$ 10,00", ",", -10.0),
    ("(1.000)", ",", -1000.0),
    ("45%", ",", 0.45),
    ("12,5%", ",", 0.125),
    ("1,234.56", ".", 1234.56),
    ("1.5", ",", None),
    ("abc", ",", None),
    (7, ",", 7.0),
])
def test_numero_de(valor, decimal, esperado):
    resultado = numero_de(valor, decimal)
    assert resultado == pytest.approx(esperado) if esperado is not None else resultado is None


def _limpar(df, regra=None):
    rel = Relatorio("teste.xlsx")
    df.index = range(2, len(df) + 2)
    return limpar_tabela(df, "dados", PADROES["limpeza"], regra or {}, rel), rel


def test_inferencia_de_tipos_e_zeros_a_esquerda():
    df = pd.DataFrame({
        "Valor": ["1.000,50", "2,5", "300"],
        "Data": ["01/02/2026", "15/03/2026", "31/12/2025"],
        "Matricula": ["00123", "00456", "00789"],
        "Codigo Postal": ["01001", "02002", "03003"],
        "Nome": ["Ana", "Bruno", "Carla"],
    }, dtype=object)
    out, rel = _limpar(df)
    assert out["valor"].tolist() == [1000.5, 2.5, 300.0]
    assert pd.api.types.is_datetime64_any_dtype(out["data"])
    assert out["matricula"].tolist() == ["00123", "00456", "00789"]
    assert out["codigo_postal"].tolist() == ["01001", "02002", "03003"]
    assert not rel.tem_erros


def test_inteiros_viram_int64():
    out, _ = _limpar(pd.DataFrame({"qtd": [1, 2.0, "3"]}, dtype=object))
    assert str(out["qtd"].dtype) == "Int64"


def test_erro_excel_reprova():
    out, rel = _limpar(pd.DataFrame({"a": [1, "#REF!", 3], "b": ["x", "y", "#N/D"]}, dtype=object))
    assert rel.tem_erros
    assert len(rel.erros) == 2


def test_nulos_textuais_e_espacos():
    out, _ = _limpar(pd.DataFrame({"nome": ["  Ana   Maria ", "N/A", "-"], "x": [1, 2, 3]}, dtype=object))
    assert out["nome"].iloc[0] == "Ana Maria"
    assert out["nome"].isna().sum() == 2


def test_tipo_forcado_invalido_gera_erro():
    out, rel = _limpar(pd.DataFrame({"nota": ["10", "nove", "8"]}, dtype=object), {"tipos": {"nota": "inteiro"}})
    assert rel.tem_erros
    assert "nove" in rel.erros[0].exemplos[0]
    assert "linha 3" in rel.erros[0].exemplos[0]


def test_inteiro_com_decimais_gera_erro():
    _, rel = _limpar(pd.DataFrame({"nota": ["10", "9,5"]}, dtype=object), {"tipos": {"nota": "inteiro"}})
    assert rel.tem_erros


def test_coluna_quase_numerica_esvazia_invalidos_com_aviso():
    valores = [str(i) for i in range(40)] + ["sem nota"]
    out, rel = _limpar(pd.DataFrame({"nota": valores}, dtype=object))
    assert out["nota"].isna().sum() == 1
    assert any("esvaziados" in a.mensagem for a in rel.avisos)
