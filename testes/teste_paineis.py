"""Estúdio de Painéis: a Bárbara monta do banco real, o Heitor confere por outro caminho, e só então publica."""

import json
import sqlite3

import pytest

from robo import paineis
from robo.trabalho import Trabalho, _agora


def _semear(cfg, tentativas):
    from robo import treino
    treino._tb(cfg)
    with Trabalho(cfg).tx() as c:
        for pid, ok, nivel, erro in tentativas:
            c.execute("INSERT INTO treino_tentativas (data_hora, funcionario, competencia, nivel, acertou, tipo_erro) "
                      "VALUES (?,?,?,?,?,?)", (_agora(), pid, "sql", nivel, ok, erro))


def teste_numeros_batem_com_o_banco_e_tem_consulta_de_origem(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    _semear(cfg, [("recepcao", 1, 1, ""), ("recepcao", 0, 4, "achou outra coisa"), ("dba", 1, 2, ""), ("dba", 0, 4, "")])
    painel = paineis.construir(cfg)
    pag = {p["id"]: p for p in painel["paginas"]}
    ex = pag["executiva"]
    assert ex["indicadores"]["tentativas"]["valor"] == 4
    assert ex["indicadores"]["taxa_acerto"]["valor"] == pytest.approx(0.5)
    assert {r["nivel"]: r["tentativas"] for r in ex["graficos"]["por_nivel"]["linhas"]} == {1: 1, 2: 1, 4: 2}
    assert [r["n"] for r in pag["treino"]["graficos"]["erros"]["linhas"]] == [1]   # erro sem tipo não vira categoria
    assert all(i["sql"] for p in painel["paginas"] for i in p["indicadores"].values())
    assert paineis.reconciliar(cfg, painel) == []
    assert "50,0% de acerto em 4 tentativas" in ex["achados"][0]                 # pt-BR, vírgula decimal


def teste_conferencia_barra_numero_adulterado_e_mantem_o_anterior(cfg_factory, monkeypatch):
    cfg = cfg_factory()
    cfg.criar_pastas()
    _semear(cfg, [("recepcao", 1, 1, "")])
    r1 = paineis.rotina(cfg)
    assert r1["situacao"] == "publicado" and not r1["divergencias"]
    assert paineis.rotina(cfg)["situacao"] == "sem_mudanca"                       # o próprio registro não "muda" o painel
    original = paineis.construir

    def adulterado(cfg_, agora=None):
        p = original(cfg_, agora)
        p["paginas"][0]["indicadores"]["tentativas"]["valor"] += 1
        return p
    monkeypatch.setattr(paineis, "construir", adulterado)
    r3 = paineis.rotina(cfg)
    assert r3["situacao"] == "reprovado" and any("Tentativas" in d for d in r3["divergencias"])
    assert paineis.publicado(cfg)["versao"] == r1["versao"]                       # o painel bom continua no ar
    assert [v["situacao"] for v in paineis.versoes(cfg)] == ["reprovado", "sem_mudanca", "publicado"]


def teste_versoes_sao_permanentes(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    paineis.rotina(cfg)
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    for sql in ("UPDATE paineis_versoes SET situacao='x'", "DELETE FROM paineis_versoes"):
        with pytest.raises(sqlite3.DatabaseError):
            c.execute(sql)
    c.close()


def teste_banco_vazio_nao_inventa_numero(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    painel = paineis.construir(cfg)
    ex = painel["paginas"][0]
    assert "tentativas" not in ex["indicadores"] and "Ainda não há tentativas" in ex["achados"][0]
    assert paineis.reconciliar(cfg, painel) == []


def teste_equipe_no_organograma_rotina_e_fluxo():
    from robo import organizacao, orquestracao, rh
    from robo.rotinas import ROTINAS
    assert organizacao.gestor_de("bi_powerbi") == "head_bi" and organizacao.gestor_de("bi_reconciliacao") == "bi_powerbi"
    ids = {p["id"] for p in organizacao.lista()}
    assert {"bi_powerbi", "bi_reconciliacao"} <= ids
    assert ROTINAS["paineis"][0] == "bi_powerbi"
    assert "paineis" in orquestracao.FLUXOS["robo_horario"]["rotinas"] and not orquestracao.validar_fluxos()
    provas = rh._provas_nativas_cache()
    assert all(x["aprovado"] for pid in ("bi_powerbi", "bi_reconciliacao") for x in provas[pid])


def teste_api_do_painel(cfg_factory):
    from robo.painel.servidor import ROTAS_GET, ROTAS_POST
    assert "/api/paineis" in ROTAS_GET and "/api/paineis/atualizar" in ROTAS_POST
    cfg = cfg_factory()
    cfg.criar_pastas()
    paineis.rotina(cfg)
    salvo = json.loads((cfg.logs / "paineis" / "painel.json").read_text(encoding="utf-8"))
    assert salvo["conferencia"]["conferente"] == "bi_reconciliacao" and salvo["autor"] == "bi_powerbi"
