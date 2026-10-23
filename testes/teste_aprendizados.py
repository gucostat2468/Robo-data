"""Memória de acertos e erros: todo arquivo barrado ensina, a semente não conta como acerto real, replay mede reincidência."""

import sqlite3

import pandas as pd

from robo import aprendizados
from robo.pipeline import processar_arquivo


def _ruim(cfg, nome="ruim.txt"):
    arq = cfg.entrada / nome
    arq.write_text("isso não é planilha", encoding="utf-8")
    return arq


def teste_arquivo_barrado_gera_aprendizado_com_causa_e_correcao(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    r = processar_arquivo(cfg.entrada / _ruim(cfg).name, cfg)
    assert r.status != "sucesso"
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    linhas = c.execute("SELECT funcionario, resultado, causa, correcao, origem FROM aprendizados").fetchall()
    c.close()
    assert linhas and all(x[1] == "erro" and x[2] and x[3] and x[4] == "pipeline" for x in linhas)


def teste_aprovado_vira_acerto_e_sintetico_fica_marcado(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    df = pd.DataFrame({"id": range(1, 31), "regiao": ["Sul", "Norte"] * 15, "valor": range(30)})
    df.to_excel(cfg.entrada / "ok.xlsx", index=False)
    processar_arquivo(cfg.entrada / "ok.xlsx", cfg)
    (cfg.entrada / "sintetico").mkdir(exist_ok=True)
    df.to_excel(cfg.entrada / "sintetico" / "TREINO_x.xlsx", index=False)
    processar_arquivo(cfg.entrada / "sintetico" / "TREINO_x.xlsx", cfg)
    origens = aprendizados.por_origem(cfg)
    assert origens.get("pipeline", 0) >= 1 and origens.get("laboratorio", 0) >= 1


def teste_semente_e_idempotente_e_nao_conta_como_real(cfg_factory, tmp_path):
    cfg = cfg_factory()
    cfg.criar_pastas()
    arq = tmp_path / "semente.json"
    n = aprendizados.gerar_semente(arq)
    assert n >= 180
    assert aprendizados.semear(cfg, arq) == n and aprendizados.semear(cfg, arq) == 0
    assert aprendizados.por_origem(cfg) == {"semente": n}
    assert aprendizados.reincidencia(cfg) == []                       # semente nunca entra em indicador real
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    assert c.execute("SELECT COUNT(*) FROM aprendizados WHERE origem='semente' AND resultado='acerto'").fetchone()[0] == 0
    c.close()


def teste_consultar_traz_o_erro_parecido_e_registra_o_uso(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    aprendizados.registrar(cfg, "dba", "treino:sql", "erro", causa="soma sem filtro", correcao="aplicar o WHERE do pedido",
                           contexto={"tipo_erro": "numero_diferente"}, origem="treino")
    aprendizados.registrar(cfg, "dba", "treino:sql", "acerto", origem="treino")
    achados = aprendizados.consultar(cfg, "treino:sql", {"tipo_erro": "numero_diferente"}, onde="teste", quem="dba")
    assert [x["correcao"] for x in achados] == ["aplicar o WHERE do pedido"]
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    assert c.execute("SELECT COUNT(*) FROM aprendizados_uso").fetchone()[0] == 1
    c.close()


def teste_replay_mede_reincidencia(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    processar_arquivo(cfg.entrada / _ruim(cfg).name, cfg)
    r = aprendizados.replay(cfg)
    assert r["testados"] == 1 and r["reincidiram"] == 1 and r["taxa_reincidencia"] == 1.0
