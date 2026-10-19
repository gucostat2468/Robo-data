"""RH de desempenho: promoção pela política (RH propõe, gestor valida), o que só o dono decide, PDI, afastamento da
ferramenta em produção (sem parar o treino) e reintegração — tudo dos registros, tudo imutável."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from robo import organizacao, rh_desempenho as rh, treino


def _cfg(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    treino._tb(cfg)
    rh._tb(cfg)
    return cfg


def _tentativas(cfg, pid, comp, resultados, nivel, quando):
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    for i, ok in enumerate(resultados):
        c.execute("INSERT INTO treino_tentativas (data_hora, funcionario, competencia, nivel, acertou) VALUES (?,?,?,?,?)",
                  ((quando + timedelta(seconds=i)).isoformat(timespec="seconds"), pid, comp, nivel, int(ok)))
    c.commit()
    c.close()


def _niveis(cfg, pid, mapa):
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    for comp, n in mapa.items():
        c.execute("INSERT OR REPLACE INTO treino_niveis (funcionario, competencia, nivel, desde) VALUES (?,?,?,?)",
                  (pid, comp, n, "2026-01-01T00:00:00"))
    c.commit()
    c.close()


def teste_promocao_pela_politica_com_validacao_do_gestor(cfg_factory):
    cfg = _cfg(cfg_factory)
    agora = datetime.now()
    assert organizacao.nivel_de("dev_junior", organizacao.por_id(cfg)["dev_junior"]) == "junior"
    _tentativas(cfg, "dev_junior", "ronda_ti", [True] * 30 + [False] * 2, 3, agora - timedelta(days=5))
    _niveis(cfg, "dev_junior", {"ronda_ti": 3, "conhecimento": 3, "historico": 3})
    r = rh.ciclo(cfg, agora)
    [p] = r["promocoes"]
    assert p["funcionario"] == "dev_junior" and (p["de"], p["para"]) == ("junior", "pleno")
    assert p["validado_por"] == "dev_pleno"                       # o gestor valida; o RH propôs
    m = rh.movimentos(cfg, "dev_junior")[0]
    assert m["proposto_por"] == "rh_desempenho" and m["validado_por"] == "dev_pleno" and m["situacao"] == "efetivada"
    gente = organizacao.por_id(cfg)
    assert organizacao.nivel_de("dev_junior", gente["dev_junior"]) == "pleno"
    assert organizacao.contrato("dev_junior", cfg)["permissoes"]["aprova"]   # a permissão segue o cargo
    assert rh.ciclo(cfg, agora)["promocoes"] == []               # idempotente: não promove de novo no mesmo mês
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("UPDATE rh_movimentos SET situacao='x'")       # movimento é imutável
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DELETE FROM rh_movimentos")
    c.close()


def teste_sem_numeros_nao_promove(cfg_factory):
    cfg = _cfg(cfg_factory)
    agora = datetime.now()
    _tentativas(cfg, "dev_junior", "ronda_ti", [True] * 10, 3, agora - timedelta(days=1))   # poucas tentativas
    _niveis(cfg, "dev_junior", {"ronda_ti": 3})
    assert rh.ciclo(cfg, agora)["promocoes"] == []
    ok, faltas = rh.elegivel(rh.numeros(_conn(cfg), "dev_junior", (agora - timedelta(days=30)).isoformat()), "pleno")
    assert not ok and any("tentativas" in f for f in faltas)


def _conn(cfg):
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    c.row_factory = sqlite3.Row
    return c


def teste_estagiario_e_quem_ganha_alterar_dados_so_o_dono_decide(cfg_factory):
    cfg = _cfg(cfg_factory)
    agora = datetime.now()
    for pid in ("eng_estagiario", "dev_pleno"):
        _tentativas(cfg, pid, "conhecimento", [True] * 40, 4, agora - timedelta(days=3))
        _niveis(cfg, pid, {"conhecimento": 4, "historico": 4})
    r = rh.ciclo(cfg, agora)
    assert r["promocoes"] == []
    pend = {x["funcionario"]: x for x in r["aguardando_dono"]}
    assert set(pend) == {"eng_estagiario", "dev_pleno"}
    assert (pend["eng_estagiario"]["de"], pend["eng_estagiario"]["para"]) == ("estagiario", "junior")
    assert (pend["dev_pleno"]["de"], pend["dev_pleno"]["para"]) == ("pleno", "senior")
    gente = organizacao.por_id(cfg)
    assert organizacao.nivel_de("eng_estagiario", gente["eng_estagiario"]) == "estagiario"   # nada mudou sozinho
    assert rh.ciclo(cfg, agora)["aguardando_dono"] == []                                     # não repete a proposta
    mid = pend["eng_estagiario"]["movimento"]
    with pytest.raises(PermissionError):
        rh.decidir_dono(cfg, mid, True, "boa evolução", quem="eng_pleno_releitura")
    with pytest.raises(PermissionError):                         # alçada nunca tira do estágio
        rh.aplicar_por_alcada(cfg, mid, "head_rh", "dir_pessoas", "teste")
    rh.decidir_dono(cfg, mid, True, "evolução comprovada")
    assert organizacao.nivel_de("eng_estagiario", organizacao.por_id(cfg)["eng_estagiario"]) == "junior"
    with pytest.raises(ValueError):
        rh.decidir_dono(cfg, mid, True, "de novo")


def teste_ninguem_propoe_a_propria_promocao(cfg_factory):
    assert rh.proponente_para("rh_desempenho") == "head_rh"
    gente = organizacao.por_id()
    assert rh.validador_gestor("dev_junior", "dev_pleno", gente) is None   # quem propôs não valida


def teste_pdi_afastamento_e_reintegracao(cfg_factory):
    cfg = _cfg(cfg_factory)
    inicio = datetime.now() - timedelta(days=20)
    _niveis(cfg, "dev_junior", {"ronda_ti": 2})
    _tentativas(cfg, "dev_junior", "ronda_ti", [True, False, False, True, False, False, True, False, False, False], 2, inicio)
    r = rh.ciclo(cfg, inicio + timedelta(minutes=5))
    [pdi] = r["pdi_abertos"]
    assert pdi["competencia"] == "ronda_ti" and pdi["acerto"] == 0.3
    assert rh.ciclo(cfg, inicio + timedelta(minutes=6))["pdi_abertos"] == []        # não abre dois
    assert organizacao.pode_usar("dev_junior", "ronda_ti", cfg, producao=True)        # ainda não afastado
    # 15 dias depois, sem melhorar → afastado da ferramenta EM PRODUÇÃO
    _tentativas(cfg, "dev_junior", "ronda_ti", [False, False, True], 2, inicio + timedelta(days=10))
    r = rh.ciclo(cfg, inicio + timedelta(days=15))
    [af] = r["afastamentos"]
    assert af["ferramenta"] == "ronda_ti" and af["validado_por"] not in ("dev_junior", "rh_desempenho")
    assert not organizacao.pode_usar("dev_junior", "ronda_ti", cfg, producao=True)
    assert organizacao.pode_usar("dev_junior", "ronda_ti", cfg)                      # treino continua
    assert "ronda_ti" in treino.competencias_de("dev_junior", cfg)
    assert organizacao.contrato("dev_junior", cfg)["afastado_de"] == ["ronda_ti"]
    assert organizacao.quem_usa("ronda_ti", cfg, preferido="dev_junior") != "dev_junior"
    # voltou a acertar 4 de 5 no nível dele → reintegrado e PDI fechado
    _tentativas(cfg, "dev_junior", "ronda_ti", [True, True, False, True, True], 2, inicio + timedelta(days=16))
    r = rh.ciclo(cfg, inicio + timedelta(days=17))
    assert [x["competencia"] for x in r["reintegracoes"]] == ["ronda_ti"] and len(r["pdi_fechados"]) == 1
    assert organizacao.pode_usar("dev_junior", "ronda_ti", cfg, producao=True)
    tipos = [m["tipo"] for m in rh.movimentos(cfg, "dev_junior")][::-1]
    assert tipos == ["pdi_aberto", "afastamento", "reintegracao", "pdi_fechado"]


def teste_reversao_so_pelo_dono(cfg_factory):
    cfg = _cfg(cfg_factory)
    agora = datetime.now()
    _tentativas(cfg, "dev_junior", "ronda_ti", [True] * 30, 3, agora - timedelta(days=2))
    _niveis(cfg, "dev_junior", {"ronda_ti": 3})
    [p] = rh.ciclo(cfg, agora)["promocoes"]
    with pytest.raises(PermissionError):
        rh.reverter_movimento(cfg, p["movimento"], "não concordo", quem="dev_pleno")
    rh.reverter_movimento(cfg, p["movimento"], "quero avaliar pessoalmente")
    assert organizacao.nivel_de("dev_junior", organizacao.por_id(cfg)["dev_junior"]) == "junior"
    with pytest.raises(ValueError):
        rh.reverter_movimento(cfg, p["movimento"], "de novo")
    assert rh.ciclo(cfg, agora + timedelta(hours=1))["promocoes"] == []   # reversão segura a próxima por um mês
