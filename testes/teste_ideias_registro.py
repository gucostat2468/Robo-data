"""Iara (ideias e expansão): ideias tiradas do treino, registradas no banco, sem repetir e sem inventar."""

import sqlite3

import pytest

from robo import ideias, treino


def teste_gargalo_do_treino_vira_ideia_registrada_uma_vez(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    treino._tb(cfg)
    with treino._tb(cfg).tx() as c:
        for i in range(12):  # 12 tentativas no nível 4 com 3 acertos (25%)
            c.execute("INSERT INTO treino_tentativas (data_hora, rodada, caso_id, funcionario, andar, cargo_nivel, competencia, "
                      "nivel, ferramenta, acertou, nota, tipo_erro, detalhe, resposta, segundos, versao_codigo) "
                      "VALUES (datetime('now','localtime'), 'R', 'C', 'dba', 1, 'pleno', 'conhecimento', 4, 'conhecimento', ?, 0, "
                      "'', '', '', 0.1, 'x')", (1 if i < 3 else 0,))
    r = ideias.rotina(cfg)
    assert r["registradas"] >= 1
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    titulos = [t for (t,) in c.execute("SELECT titulo FROM ideias_registro")]
    assert any("Gargalo de aprendizado" in t and "nível 4" in t for t in titulos)
    assert ideias.rotina(cfg) is None                 # mesma ideia não volta no mesmo dia
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("UPDATE ideias_registro SET titulo='x'")
    c.close()
