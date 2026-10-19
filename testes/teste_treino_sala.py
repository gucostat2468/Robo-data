"""Sala de Casos também treina: competência 'revisao_casos' (ferramenta revisar_caso) e revisores reforçados.

A Sala aprende revisando casos de verdade com defeito plantado (ou sem defeito: aprovar o certo também conta). A
varredura que criou esta competência achou revisores que NÃO pegavam gabarito adulterado (lgpd, anomalias,
segmentação, histórico, ronda de TI, resumo, desempenho, SQL e parte de limpeza e conhecimento) — os testes abaixo
garantem que cada um continua pegando.
"""

import copy
import json
from pathlib import Path

import pytest

from robo import ferramentas, treino
from robo.treino_casos import CATALOGO, _alterar, _folhas_gabarito, conteudo_hash, revisao_independente


def _caso_de(comp, nivel, semente, pasta, cfg=None):
    Path(pasta).mkdir(parents=True, exist_ok=True)
    caso = CATALOGO[comp].gerar(nivel, semente, Path(pasta), cfg)
    caso.update({"competencia": comp, "nivel": nivel, "semente": semente})
    return caso


def teste_gerador_reprodutivel_pela_semente(tmp_path):
    a = _caso_de("revisao_casos", 5, 123, tmp_path / "a")
    b = _caso_de("revisao_casos", 5, 123, tmp_path / "b")
    assert a["gabarito"] == b["gabarito"]
    assert conteudo_hash(a.get("arquivo"), a["gabarito"]) == conteudo_hash(b.get("arquivo"), b["gabarito"])
    assert json.dumps(a["parametros"]["caso"]["gabarito"], sort_keys=True) == json.dumps(b["parametros"]["caso"]["gabarito"],
                                                                                       sort_keys=True)


@pytest.mark.parametrize("nivel,semente,defeito", [
    (1, 10, "gabarito_grosseiro"), (2, 11, "gabarito_sutil"), (3, 12, "nenhum"), (3, 13, "gabarito_sutil"), (4, 14, "conteudo")])
def teste_cada_nivel_planta_o_defeito_prometido(tmp_path, nivel, semente, defeito):
    caso = _caso_de("revisao_casos", nivel, semente, tmp_path)
    assert caso["gabarito"]["defeito"] == defeito
    assert caso["gabarito"]["deve_aprovar"] == (defeito == "nenhum")
    assert CATALOGO["revisao_casos"].conferir(caso, None) == []           # o defeito existe de verdade (ou não existe)
    r = revisao_independente(caso["parametros"]["caso"], None, sha=caso["parametros"]["caso"]["sha"])
    assert r["aprovado"] == (defeito == "nenhum"), r["problemas"]
    if defeito == "conteudo":
        assert any("mudou depois de gravado" in p for p in r["problemas"])


def teste_corrige_pelo_veredito(tmp_path):
    caso = _caso_de("revisao_casos", 1, 10, tmp_path)
    c = CATALOGO["revisao_casos"]
    assert c.corrigir(caso, {"dados": {"aprovado": False, "problemas": ["x"]}})[0]
    errou = c.corrigir(caso, {"dados": {"aprovado": True, "problemas": []}})
    assert not errou[0] and errou[2] == "aprovou_caso_com_defeito"
    certo = _caso_de("revisao_casos", 3, 12, tmp_path / "c")
    errou = c.corrigir(certo, {"dados": {"aprovado": False, "problemas": ["alarme"]}})
    assert not errou[0] and errou[2] == "reprovou_caso_correto"


def teste_revisor_do_caso_de_revisao_pega_promessa_falsa(tmp_path):
    caso = _caso_de("revisao_casos", 2, 11, tmp_path)
    falso = copy.deepcopy(caso)
    falso["gabarito"].update({"defeito": "nenhum", "deve_aprovar": True})   # diz que está certo, mas o gabarito foi sabotado
    assert CATALOGO["revisao_casos"].conferir(falso, None)


def teste_sala_treina_so_revisao_e_os_outros_nao(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    ids = {p["id"] for p in treino.elegiveis(cfg)}
    assert treino.EQUIPE_SALA <= ids
    for pid in treino.EQUIPE_SALA:
        assert treino.competencias_de(pid, cfg) == ["revisao_casos"]
    assert all("revisao_casos" not in treino.competencias_de(pid, cfg) for pid in ids - treino.EQUIPE_SALA)


def teste_tentativa_real_da_sala_fica_registrada(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    caso = treino.criar_caso(cfg, "revisao_casos", 4, semente=14)
    assert caso["estado"] == "validado", caso.get("revisao")
    r = treino.tentar(cfg, "casos_revisor", "revisao_casos", caso, "T1")
    assert r["acertou"], r["detalhe"]
    assert treino.pessoa(cfg, "casos_revisor")["tentativas"]["revisao_casos"]["n"] == 1


def teste_ferramenta_exige_o_caso(cfg_factory):
    r = ferramentas.executar("revisar_caso", cfg_factory(), quem="casos_revisor")
    assert not r["ok"] and "precisa de: caso" in r["texto"]


# ------------------------------------------------------------------- revisores reforçados: gabarito adulterado é pego
def _sem_banco(comp):
    return comp not in ("conhecimento",)


@pytest.mark.parametrize("comp", [c for c in CATALOGO if _sem_banco(c) and c != "revisao_casos"])
@pytest.mark.parametrize("sutil", [False, True])
def teste_revisor_pega_gabarito_adulterado_em_cada_campo(cfg_factory, tmp_path, comp, sutil):
    cfg = cfg_factory()
    cfg.criar_pastas()
    for nivel in (1, 3, 5):
        caso = _caso_de(comp, nivel, 4000 + nivel, tmp_path / f"n{nivel}", cfg)
        assert CATALOGO[comp].conferir(caso, cfg) == [], (comp, nivel)   # caso correto passa
        for cam, v in _folhas_gabarito(caso["gabarito"]):
            if not cam:
                continue
            x = copy.deepcopy(caso)
            alvo = x["gabarito"]
            for k in cam[:-1]:
                alvo = alvo[k]
            alvo[cam[-1]] = _alterar(v, sutil)
            assert CATALOGO[comp].conferir(x, cfg), f"{comp} n{nivel}: não pegou {'/'.join(map(str, cam))}"
