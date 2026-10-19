"""Caixa do dono: toda ideia da equipe e toda pendência do dono chegam a ele; só ele decide; tudo fica registrado."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from robo import caixa_dono, ideias
from robo.trabalho import Trabalho, _agora


def _ideia(cfg, titulo="Gargalo de aprendizado: SQL no nível 4", motivo="20 tentativas com só 40% de acerto", quando=None):
    tb = ideias._tb_registro(cfg)
    with tb.tx() as c:
        c.execute("INSERT INTO ideias_registro (data_hora, titulo, motivo, primeiro_passo, dono, impacto, chave) "
                  "VALUES (?,?,?,?,?,?,?)", (quando or _agora(), titulo, motivo, "Revisar os casos", "head_casos", 4,
                                             caixa_dono._chave(titulo)))


def _erros_de_treino(cfg, pid="recepcao", n=3):
    from robo import treino
    treino._tb(cfg)
    with Trabalho(cfg).tx() as c:
        for _ in range(n):
            c.execute("INSERT INTO treino_tentativas (data_hora, funcionario, competencia, nivel, acertou, tipo_erro) "
                      "VALUES (?,?,?,?,?,?)", (_agora(), pid, "sql", 3, 0, "achou outra coisa"))


def teste_ideia_chega_e_aprovada_vira_backlog_de_quem_sugeriu(cfg_factory):
    from robo import estrategia
    cfg = cfg_factory()
    cfg.criar_pastas()
    _ideia(cfg)
    itens = caixa_dono.itens(cfg)
    assert len(itens) == 1 and itens[0]["situacao"] == "nova" and itens[0]["sugerido_por"]["nome"] == "Iara"
    assert caixa_dono.resumo(cfg) == {"novas": 1, "ideias_novas": 1, "pendencias_novas": 0}
    r = caixa_dono.decidir(cfg, itens[0]["id"], True, "Pode seguir")
    assert r["decisao"] == "aprovada"
    item = next(i for i in estrategia.ler_backlog(cfg) if i["id"] == r["detalhe"]["backlog"])
    assert item["responsavel"] == "head_casos" and "Pode seguir" in item["motivo"]
    assert caixa_dono.itens(cfg)[0]["situacao"] == "aprovada"
    with pytest.raises(ValueError):
        caixa_dono.decidir(cfg, itens[0]["id"], False)                     # não decide duas vezes


def teste_so_o_dono_decide(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    _ideia(cfg)
    iid = caixa_dono.itens(cfg)[0]["id"]
    with pytest.raises(PermissionError):
        caixa_dono.decidir(cfg, iid, True, quem="canal_iara")
    with pytest.raises(PermissionError):
        caixa_dono.decidir(cfg, iid, True, quem="dir_operacoes")


def teste_recusada_so_volta_se_o_numero_mudar_muito(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    _ideia(cfg, motivo="20 tentativas com só 40% de acerto")
    iid = caixa_dono.itens(cfg)[0]["id"]
    caixa_dono.decidir(cfg, iid, False, "agora não")
    _ideia(cfg, motivo="21 tentativas com só 41% de acerto")               # quase igual: continua recusada
    assert caixa_dono.itens(cfg)[0]["situacao"] == "recusada" and caixa_dono.resumo(cfg)["novas"] == 0
    _ideia(cfg, motivo="60 tentativas com só 20% de acerto")               # piorou muito: volta para o dono
    assert caixa_dono.itens(cfg)[0]["situacao"] == "nova"


def teste_sugestao_do_gestor_pelos_fatos_e_sem_repetir(cfg_factory):
    from robo import organizacao
    cfg = cfg_factory()
    cfg.criar_pastas()
    _erros_de_treino(cfg, "recepcao", 2)
    assert caixa_dono.gerar_sugestoes(cfg) == []                          # 2 erros: ainda não é padrão
    _erros_de_treino(cfg, "recepcao", 1)
    novas = caixa_dono.gerar_sugestoes(cfg)
    assert len(novas) == 1 and novas[0]["autor"] == organizacao.gestor_de("recepcao") and "3 erros" in novas[0]["motivo"]
    assert caixa_dono.gerar_sugestoes(cfg) == []                          # mesma sugestão não repete na semana
    it = next(i for i in caixa_dono.itens(cfg) if i["tipo"] == "sugestao")
    assert it["sugerido_por"]["id"] == organizacao.gestor_de("recepcao")


def teste_pendencia_de_rh_do_dono_aparece_e_decisao_vai_para_o_rh(cfg_factory):
    from robo import rh_desempenho
    cfg = cfg_factory()
    cfg.criar_pastas()
    rh_desempenho._tb(cfg)
    with Trabalho(cfg).tx() as c:
        mid = c.execute("INSERT INTO rh_movimentos (data_hora, funcionario, tipo, de_nivel, para_nivel, motivo, evidencia, "
                        "proposto_por, situacao) VALUES (?,?,?,?,?,?,?,?,?)",
                        (_agora(), "eng_estagiario", "promocao", "estagiario", "junior", "95% de acerto em 40 tentativas", "{}",
                         "rh_desempenho", "aguardando_dono")).lastrowid
    it = next(i for i in caixa_dono.itens(cfg) if i["tipo"] == "rh")
    assert it["id"] == f"rh:{mid}" and "estagiario → junior" in it["titulo"]
    caixa_dono.decidir(cfg, it["id"], False, "Ainda não: quero ver mais uma semana")
    with Trabalho(cfg).tx() as c:
        assert c.execute("SELECT situacao FROM rh_movimentos WHERE ref=? AND tipo='decisao_dono'", (mid,)).fetchone()[0] == "recusada"
    assert not [i for i in caixa_dono.itens(cfg) if i["tipo"] == "rh"]   # decidida: sai das pendências do RH


def teste_eventos_sao_permanentes(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    _ideia(cfg)
    caixa_dono.decidir(cfg, caixa_dono.itens(cfg)[0]["id"], False)
    _erros_de_treino(cfg, "dba", 3)
    assert caixa_dono.gerar_sugestoes(cfg)                                 # (gatilho só dispara com linha para apagar)
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    for sql in ("UPDATE caixa_dono_eventos SET decisao='aprovada'", "DELETE FROM caixa_dono_eventos",
                "DELETE FROM caixa_dono_sugestoes"):
        with pytest.raises(sqlite3.DatabaseError):
            c.execute(sql)
    c.close()


def teste_ideia_antiga_sai_da_janela(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    _ideia(cfg, quando=(datetime.now() - timedelta(days=40)).isoformat(timespec="seconds"))
    assert caixa_dono.itens(cfg) == []


def teste_api_e_rotina(cfg_factory):
    from robo import orquestracao
    from robo.painel.servidor import ROTAS_GET, ROTAS_POST
    from robo.rotinas import ROTINAS
    assert "/api/caixa-dono" in ROTAS_GET and "/api/caixa-dono/decidir" in ROTAS_POST
    assert "caixa_dono" in ROTINAS and "caixa_dono" in orquestracao.FLUXOS["robo_horario"]["rotinas"]
    cfg = cfg_factory()
    cfg.criar_pastas()
    _erros_de_treino(cfg, "dba", 4)
    r = caixa_dono.rotina(cfg)
    assert r["sugestoes_novas"] == 1 and r["novas"] == 1
