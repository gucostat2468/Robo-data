"""Cenários sintéticos com gabarito triplo (robo/cenarios.py) e os suspeitos da esteira (esteira_dados.suspeitos).

O que precisa ser verdade:
  - mesma semente = mesma planilha e mesmo gabarito; limite de 100 mil linhas;
  - cada erro plantado está no manifesto, com o id do cliente;
  - a esteira completa, rodada no cenário, bate o gabarito (números, correções, detecção e ML);
  - suspeitos não alarmam o que é legítimo: estorno em volume, vencimento no futuro, cauda natural de valores.
"""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from robo import cenarios, esteira_dados


def teste_mesma_semente_mesmo_cenario_e_limite():
    a, b = cenarios.gerar(800, 3), cenarios.gerar(800, 3)
    pd.testing.assert_frame_equal(a["sujo"], b["sujo"])
    assert a["gabarito"] == b["gabarito"]
    with pytest.raises(ValueError):
        cenarios.gerar(100_001, 1)


def teste_manifesto_e_gabarito_batem_com_a_planilha():
    c = cenarios.gerar(2000, 5)
    g = c["gabarito"]
    assert g["numeros"]["linhas_planilha"] == len(c["sujo"]) == 2000 + len(g["erros"]["duplicata"]) + \
        len(g["erros"]["quase_duplicata"])
    assert g["numeros"]["duplicatas_exatas"] == len(g["erros"]["duplicata"])
    sujo = c["sujo"].set_index("ID Cliente")
    for i in g["erros"]["idade_impossivel"]:
        v = sujo.loc[i, "Idade"]
        assert ((v < 0) | (v > 120)).all() if hasattr(v, "all") else (v < 0 or v > 120)
    # o erro muda a soma: a planilha "como está" não é a verdade (é por isso que a esteira aponta suspeitos)
    assert g["numeros"]["soma_valor_mensal_como_esta"] != g["numeros"]["soma_valor_mensal_verdadeira"]
    assert set(g["ml"]["drivers"]).isdisjoint(g["ml"]["ruido"])


def teste_placar_da_esteira_completa(cfg_factory, tmp_path):
    pytest.importorskip("sklearn")
    cfg = cfg_factory()
    cfg.criar_pastas()
    r = cenarios.placar(cfg, cenarios=1, linhas=2500, pasta=tmp_path, semente_inicial=2)
    falhas = [i for i in r["cenarios"][0]["itens"] if not i["ok"]]
    assert not falhas, falhas
    assert (tmp_path / r["pasta"].split("/")[-1] / "placar.json").exists()


def teste_suspeitos_nao_alarmam_o_legitimo():
    rng = np.random.default_rng(0)
    n = 2000
    df = pd.DataFrame({
        "id": range(n),
        "valor": np.where(rng.random(n) < 0.15, -1, 1) * rng.gamma(3, 50, n),   # 15% estornos: legítimo
        "horas": rng.gamma(2, 6, n),                                            # cauda natural
        "data_vencimento": pd.Timestamp("2030-01-01") + pd.to_timedelta(rng.integers(0, 30, n), "D"),
        "data_pedido": pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 300, n), "D"),
    })
    papeis = {"id": "id", "valor": "numero", "horas": "numero", "data_vencimento": "data", "data_pedido": "data"}
    assert esteira_dados.suspeitos(df, papeis, datetime(2026, 1, 1)).empty
    df.loc[5, "horas"] = 12_000.0
    df.loc[7, "data_pedido"] = pd.Timestamp("2031-01-01")
    df.loc[9, "id"] = 8
    s = esteira_dados.suspeitos(df, papeis, datetime(2026, 1, 1))
    assert set(s["regra"]) == {"valor muito acima do padrão (digitação?)", "data no futuro",
                               "identificador repetido (quase-duplicata)"}
    assert set(s["chave"]) == {5, 7, 8}
