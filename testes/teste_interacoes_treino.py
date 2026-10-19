"""Conversas que nascem de fatos registrados: mentoria do erro de treino (com a lição real), fechamento ajudou/não
ajudou, troca ao subir de nível e conversas entre áreas (SLA, acerto baixo) — sem repetir o mesmo fato."""

import sqlite3

import pytest

from robo import interacoes, licoes, orquestracao, treino
from robo.trabalho import _agora


def _tentativa(cfg, pid, comp, nivel, acertou, tipo="contagem_errada", detalhe="contou 10, eram 12", andar=None):
    """Grava uma tentativa como o treino grava (mesma tabela, mesmas colunas)."""
    from robo import organizacao
    andar = andar or (organizacao.por_id(cfg).get(pid) or {}).get("andar")
    with treino._tb(cfg).tx() as c:
        cur = c.execute("INSERT INTO treino_tentativas (data_hora, rodada, caso_id, funcionario, andar, cargo_nivel, competencia, "
                        "nivel, ferramenta, acertou, nota, tipo_erro, detalhe, resposta, segundos, versao_codigo) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (_agora(), "T", f"CASO-{comp}-n{nivel}-1", pid, andar, "pleno", comp, nivel, "x", int(acertou),
                         1.0 if acertou else 0.0, None if acertou else tipo, detalhe if not acertou else "acertou tudo",
                         "{}", 0.1, "teste"))
        tid = cur.lastrowid
    return {"tentativa": tid, "funcionario": pid, "competencia": comp, "nivel": nivel, "acertou": acertou,
            "tipo_erro": None if acertou else tipo, "detalhe": detalhe, "mudanca_nivel": None}


def _licao(cfg, pid, comp, nivel, tipo="contagem_errada"):
    return licoes.criar(cfg, "treino", f"{comp}:{nivel}:{tipo}", f"Treino — {comp} nível {nivel}", "conteúdo", "pergunta",
                        "como aplicar", 1, pid, "pessoa", "casos_planejamento")


@pytest.fixture
def cfg(cfg_factory):
    c = cfg_factory()
    c.criar_pastas()
    treino._tb(c)
    interacoes._tb(c)
    return c


def teste_mentor_prefere_mesmo_andar_e_nunca_a_propria_pessoa(cfg):
    _tentativa(cfg, "analise_perfil", "limpeza", 4, True)   # 2º andar, mais recente
    _tentativa(cfg, "leitura", "limpeza", 3, True)          # 1º andar, nível abaixo do erro: não serve
    _tentativa(cfg, "validacao", "limpeza", 5, True)        # 1º andar, nível acima: serve
    _tentativa(cfg, "limpeza", "limpeza", 5, True)          # a própria pessoa
    assert interacoes.escolher_mentor(cfg, "limpeza", "limpeza", 4) == "validacao"
    assert interacoes.escolher_mentor(cfg, "limpeza", "limpeza", 4, {"validacao"}) == "analise_perfil"
    assert interacoes.escolher_mentor(cfg, "limpeza", "limpeza", 4, {"validacao", "analise_perfil"}) == "casos_engenharia"


def teste_erro_abre_mentoria_com_a_licao_real_e_proxima_tentativa_fecha(cfg):
    certo = _tentativa(cfg, "validacao", "limpeza", 4, True)
    lid = _licao(cfg, "limpeza", "limpeza", 4)
    erro = _tentativa(cfg, "limpeza", "limpeza", 4, False)
    r = interacoes.apos_tentativa(cfg, erro)
    assert r["aberta"]["mentor"] == "validacao" and r["aberta"]["licao"] == lid
    assert r["aberta"]["tentativa_mentor"] == certo["tentativa"]
    falas = interacoes.recentes(cfg, 10)
    resposta = next(f for f in falas if f["tipo"] == "mentoria")
    assert lid in resposta["texto"] and f"T{certo['tentativa']}" in resposta["texto"] and resposta["para"] == "limpeza"
    assert any(f["tipo"] == "pedido" and f["de"] == "limpeza" and f["para"] == "validacao" for f in falas)
    assert interacoes.apos_tentativa(cfg, _tentativa(cfg, "limpeza", "limpeza", 3, True))["fechada"] is None  # nível abaixo
    fechou = interacoes.apos_tentativa(cfg, _tentativa(cfg, "limpeza", "limpeza", 4, True))["fechada"]
    assert fechou["situacao"] == "ajudou"
    res = interacoes.resumo(cfg)
    assert res["melhores_mentores"][0]["mentor"] == "validacao" and res["melhores_mentores"][0]["taxa"] == 1.0
    assert res["mentorias_abertas"] == 0 and res["por_tipo_24h"]["agradecimento"] == 1


def teste_nao_ajudou_troca_de_mentor_na_vez_seguinte(cfg):
    _tentativa(cfg, "validacao", "limpeza", 4, True)
    _tentativa(cfg, "modelagem", "limpeza", 4, True)
    interacoes.apos_tentativa(cfg, _tentativa(cfg, "limpeza", "limpeza", 4, False))
    r = interacoes.apos_tentativa(cfg, _tentativa(cfg, "limpeza", "limpeza", 4, False))
    assert r["fechada"]["situacao"] == "nao_ajudou"
    assert r["aberta"]["mentor"] == "validacao"  # 1º mentor era modelagem (acerto mais recente); agora outro


def teste_sem_mentor_avisa_o_head_do_andar(cfg):
    r = interacoes.apos_tentativa(cfg, _tentativa(cfg, "analise_perfil", "orquestracao_inexistente", 5, False))
    assert r["aberta"] == {"mentor": None, "head": "head_ciencia"}
    f = interacoes.recentes(cfg, 1)[0]
    assert f["tipo"] == "sem_mentor" and f["para"] == "head_ciencia"


def teste_subida_de_nivel_vira_troca_com_colega_abaixo(cfg):
    with treino._tb(cfg).tx() as c:
        for pid, nivel, desde in (("leitura", 2, "2026-01-01T00:00:00"), ("validacao", 3, "2026-02-01T00:00:00"),
                                  ("analise_perfil", 1, "2025-01-01T00:00:00")):
            c.execute("INSERT INTO treino_niveis (funcionario, competencia, nivel, desde) VALUES (?,?,?,?)", (pid, "limpeza", nivel, desde))
    _tentativa(cfg, "limpeza", "limpeza", 3, False, tipo="nao_barrou")
    for _ in range(4):
        _tentativa(cfg, "limpeza", "limpeza", 3, True)
    t = _tentativa(cfg, "limpeza", "limpeza", 3, True)
    t["mudanca_nivel"] = {"de": 3, "para": 4}
    r = interacoes.apos_tentativa(cfg, t)
    assert r["troca"]["para"] == "leitura"  # mesmo andar, nível abaixo, há mais tempo (analise_perfil é de outro andar)
    f = next(x for x in interacoes.recentes(cfg, 5) if x["tipo"] == "troca")
    assert "nivel 4" not in f["texto"] and "nível 4" in f["texto"] and "nao barrou" in f["texto"]
    assert interacoes.compartilhar_subida(cfg, "limpeza", "limpeza", 3, 4) is None  # mesmo fato não repete


def teste_conversas_por_fatos_sla_e_acerto_baixo_sem_repetir(cfg):
    cen = {"sessao_min_atras": 600, "execucoes": [{"nome": "backup", "fim_min_atras": 2, "segundos": 3, "status": "erro"}],
           "estado": [{"nome": n, "verif_min_atras": 0.1, "ultimo_status": "fez"} for n in orquestracao.ROTINAS]}
    orquestracao.gravar_cenario(cfg, cen)
    for i in range(20):
        _tentativa(cfg, "analise_perfil", "calculo", 3, i % 2 == 0)  # 50% no 2º andar
    feitas = interacoes.conversas_por_fatos(cfg)
    tipos = {(f["de"], f["para"], f["tipo"]) for f in feitas}
    assert ("airflow_pleno", "dba", "cobranca") in tipos
    assert ("head_ciencia", "casos_analytics", "revisao") in tipos
    assert interacoes.conversas_por_fatos(cfg) == []  # nada novo: não fala de novo


def teste_mentorias_nao_se_apagam_nem_mudam_a_evidencia(cfg):
    _tentativa(cfg, "validacao", "limpeza", 4, True)
    interacoes.apos_tentativa(cfg, _tentativa(cfg, "limpeza", "limpeza", 4, False))
    con = sqlite3.connect(cfg.logs / "trabalho.db")
    try:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("DELETE FROM mentorias")
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("UPDATE mentorias SET mentor='outro'")
        con.execute("UPDATE mentorias SET situacao='ajudou'")  # a situação pode mudar
    finally:
        con.close()


def teste_treino_real_gera_conversa(cfg):
    """Tentativa REAL (caso, ferramenta e correção de verdade): errar abre mentoria pelo próprio treino.tentar."""
    caso = treino.criar_caso(cfg, "historico", 1, semente=3)
    _tentativa(cfg, "validacao", "historico", 1, True)
    caso_ruim = {**caso, "gabarito": {"ultimos": [["nao-existe.xlsx", "sucesso"]]}}  # gabarito impossível: a pessoa erra
    r = treino.tentar(cfg, "limpeza", "historico", caso_ruim, "TX")
    assert not r["acertou"]
    with interacoes._tb(cfg).tx() as c:
        m = c.execute("SELECT * FROM mentorias WHERE tentativa_erro_id=?", (r["tentativa"],)).fetchone()
    assert m and m["mentor"] == "validacao" and m["licao_id"]
