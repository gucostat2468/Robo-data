"""Identidade dos casos de treino (robo/treino.py): achado no log do turno da nuvem de 24/10/2026, três falhas
"UNIQUE constraint failed: treino_casos.id" na certificação. A semente do exame depende do segundo atual (repete a
cada 997 s e é igual para dois exames no mesmo segundo) e criar_caso APAGAVA o diretório já existente antes de
descobrir que o id estava em uso — perdia os arquivos do caso anterior e só depois quebrava.

Regras: id único mesmo em execução concorrente; nada preexistente é apagado; falha de geração fica registrada com a
causa (nunca vira aprovação); a semente continua guardada para reproduzir o caso.
"""

import sqlite3
import threading

import pytest

from robo import treino


@pytest.fixture
def cfg(cfg_factory):
    c = cfg_factory()
    c.criar_pastas()
    return c


def _linhas(cfg):
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT id, semente, estado, revisao FROM treino_casos ORDER BY criado_em, id")]


def teste_mesma_semente_duas_vezes_gera_dois_casos_e_preserva_o_primeiro(cfg):
    a = treino.criar_caso(cfg, "limpeza", 2, semente=4242)
    pasta_a = treino.pasta(cfg) / "casos" / a["id"]
    antes = sorted(p.name for p in pasta_a.rglob("*")) if pasta_a.exists() else None
    b = treino.criar_caso(cfg, "limpeza", 2, semente=4242)  # antes: IntegrityError, depois de apagar a pasta do 1º
    assert a["id"] != b["id"] and a["semente"] == b["semente"] == 4242
    if antes is not None:
        assert sorted(p.name for p in pasta_a.rglob("*")) == antes  # arquivos do caso anterior intactos
    ids = [r["id"] for r in _linhas(cfg)]
    assert len(ids) == len(set(ids)) == 2
    assert a["gabarito"] == b["gabarito"]  # mesma semente reproduz o mesmo caso


def teste_diretorio_ja_existente_nao_e_apagado(cfg):
    sobra = treino.pasta(cfg) / "casos" / "CASO-limpeza-n1-777"
    sobra.mkdir(parents=True)
    (sobra / "evidencia.txt").write_text("de outra execução")
    caso = treino.criar_caso(cfg, "limpeza", 1, semente=777)
    assert caso["id"] != "CASO-limpeza-n1-777"
    assert (sobra / "evidencia.txt").read_text() == "de outra execução"


def teste_criacoes_concorrentes_da_mesma_competencia_e_nivel(cfg):
    resultados, erros = [], []

    def criar():
        try:
            resultados.append(treino.criar_caso(cfg, "limpeza", 3, semente=31337))
        except Exception as e:  # noqa: BLE001 — o teste quer ver qualquer falha
            erros.append(repr(e))
    ts = [threading.Thread(target=criar) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not erros, erros
    ids = [r["id"] for r in resultados]
    assert len(set(ids)) == 4
    assert len([r for r in _linhas(cfg) if r["semente"] == 31337]) == 4  # nenhuma duplicação no banco


def teste_falha_na_geracao_fica_registrada_e_nao_aprova(cfg, monkeypatch):
    ok = treino.criar_caso(cfg, "limpeza", 1, semente=11)
    pasta_ok = treino.pasta(cfg) / "casos" / ok["id"]
    existia = pasta_ok.exists()

    def quebra(*a, **k):
        raise RuntimeError("disco cheio no meio da geração")
    monkeypatch.setattr(treino.CATALOGO["limpeza"], "gerar", quebra)
    with pytest.raises(treino.ErroGeracaoCaso, match="disco cheio"):
        treino.criar_caso(cfg, "limpeza", 1, semente=11)
    linhas = {r["id"]: r for r in _linhas(cfg)}
    falhou = [r for r in linhas.values() if r["estado"] == "falha_geracao"]
    assert len(falhou) == 1 and "disco cheio" in falhou[0]["revisao"] and falhou[0]["semente"] == 11
    assert linhas[ok["id"]]["estado"] == ok["estado"]  # o caso anterior segue como estava
    assert pasta_ok.exists() == existia


def teste_certificacao_com_falha_de_geracao_reprova_com_a_causa(cfg, monkeypatch):
    comp = treino.CATALOGO["limpeza"]

    def quebra(*a, **k):
        raise RuntimeError("gerador quebrou")
    monkeypatch.setattr(comp, "gerar", quebra)
    r = treino.certificar(cfg, comp.designer, "limpeza")
    assert r["ok"] is False and "gerador quebrou" in r["detalhe"]  # nunca uma falsa aprovação


def teste_exames_repetidos_no_mesmo_segundo_nao_colidem(cfg, monkeypatch):
    comp = treino.CATALOGO["limpeza"]
    monkeypatch.setattr(treino.time, "time", lambda: 1_761_300_000.0)  # mesmo segundo nos dois exames
    r1 = treino.certificar(cfg, comp.designer, "limpeza")
    r2 = treino.certificar(cfg, comp.designer, "limpeza")
    assert "UNIQUE" not in r1["detalhe"] + r2["detalhe"]
    ids = [r["id"] for r in _linhas(cfg)]
    assert len(ids) == len(set(ids)) == 10
