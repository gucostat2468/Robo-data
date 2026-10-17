"""Centro de treinamento: toda planilha difícil do catálogo precisa passar. Falha aqui = o robô ficou engessado."""

import pytest

from robo import treinamento


@pytest.mark.parametrize("caso", [c.id for c in treinamento.CASOS])
def teste_caso_dificil(caso):
    r = treinamento.rodar([caso])["casos"][0]
    assert r["ok"], r["falhas"]
