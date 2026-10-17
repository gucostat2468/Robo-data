"""Laboratório contínuo, guilda Python, interação entre funcionários, balões no 3D e sala de reunião."""

import pytest

from conftest import REGRA_NPS
from robo import bibliotecas, interacoes, laboratorio, lideranca, memoria, orquestrador, organizacao, sala
from robo.pipeline import processar_arquivo


@pytest.fixture
def cfg(planilha_baguncada, cfg_factory):
    return cfg_factory(regras=[REGRA_NPS])


@pytest.fixture
def baloes():
    capturados = []
    anterior = orquestrador.AO_EVENTO
    orquestrador.AO_EVENTO = lambda etapa, rotulo, **extra: capturados.append({"etapa": etapa, **extra})
    yield capturados
    orquestrador.AO_EVENTO = anterior


@pytest.mark.parametrize("area", laboratorio.AREAS)
def teste_laboratorio_cada_area_com_resposta_conhecida(cfg, area):
    r = laboratorio.exercicio(cfg, area, 11)
    assert r["falhas"] == [] and r["acertos"] >= 4, r
    # nada vai para a produção: nem histórico, nem Bases-Tratadas
    from robo import historico
    assert historico.ler(cfg.logs, 10) == [] and not list((cfg.entrada.parent / "Bases-Tratadas").glob("lab_*"))
    assert any(e["origem"] == "laboratorio" for e in memoria.experiencias(cfg, "limpeza"))


def teste_laboratorio_pega_erro_plantado_e_pede_ajuda(cfg, baloes, monkeypatch):
    from robo import ciencia
    monkeypatch.setattr(ciencia, "drivers", lambda df, alvo: {"ok": True, "drivers": [{"atributo": "ctr"}]})
    r = laboratorio.exercicio(cfg, "marketing", 3)
    assert any("driver" in f for f in r["falhas"])
    assert any("Laboratório: Achar o driver plantado" in h["erro"] for h in memoria.handovers(cfg))
    conversa = interacoes.recentes(cfg)
    assert [c["tipo"] for c in conversa[:2]] == ["resposta", "pedido"] and conversa[1]["de"] == "cd_senior_drivers"
    assert any(b.get("fala") and b["etapa"] == "cd_senior_drivers" for b in baloes)


def teste_rotina_do_laboratorio_respeita_intervalo(cfg):
    assert laboratorio.rotina(cfg)["etapas"] >= 4
    assert laboratorio.rotina(cfg) is None


def teste_guilda_python_e_a_mais_cobrada(cfg):
    for pid in lideranca.GUILDA_PYTHON:
        c = organizacao.contrato(pid, cfg)
        assert "revisao_biblioteca" in c["ferramentas"] and lideranca.EXIGENCIA[pid] == 90.0
    for _ in range(4):
        memoria.experiencia(cfg, "esp_pandas", "acerto", "ok", "teste")
        memoria.experiencia(cfg, "analise_perfil", "acerto", "ok", "teste")
    memoria.experiencia(cfg, "esp_pandas", "erro", "x", "teste")
    memoria.experiencia(cfg, "analise_perfil", "erro", "x", "teste")
    d = {x["id"]: x for x in memoria.desempenho(cfg)}
    assert d["esp_pandas"]["situacao"] == "insuficiente"  # 80% < 90% exigido da guilda
    assert d["analise_perfil"]["situacao"] == "atencao"   # 80% é atenção para o resto da empresa
    for nome in bibliotecas.BIBLIOTECAS:
        assert bibliotecas.revisar(nome)["ok"], nome


def teste_troca_de_experiencias_entre_colegas(cfg, baloes):
    memoria.experiencia(cfg, "leitura", "acerto", "Laboratório (varejo): Achar o cabeçalho", "laboratorio")
    memoria.experiencia(cfg, "limpeza", "erro", "Laboratório (varejo): Limpar o Total", "laboratorio")
    trocas = interacoes.trocar_experiencias(cfg)
    assert trocas and trocas[0]["aprendiz"] == "limpeza" and organizacao.por_id(cfg)[trocas[0]["mentor"]]["andar"] == 1
    assert any(e["tipo"] == "aprendizado" for e in memoria.experiencias(cfg, "limpeza"))


def teste_pedido_do_dono_vira_balao(cfg, baloes):
    from robo import atendimento
    atendimento.conversar(cfg, "dba", "o que você faz?")
    assert baloes[0]["etapa"] == "dba" and "Pedido do dono" in baloes[0]["fala"]
    assert baloes[-1]["etapa"] == "dba" and baloes[-1]["fala"].startswith("Sou Dora")


def teste_sala_de_reuniao_com_varias_pessoas(planilha_baguncada, cfg):
    memoria.registrar_execucao(cfg, processar_arquivo(planilha_baguncada, cfg))
    r = sala.abrir(cfg, 1)
    assert r["participantes"] == ["dir_dados", "head_engenharia", "ger_engenharia", "coord_engenharia"]
    d = sala.detalhes(cfg, r["conversa_id"])
    autores = {m["autor"] for m in d["mensagens"]}
    assert {"dono", "dir_dados", "head_engenharia", "coord_engenharia"} <= autores
    # citou o nome → quem responde é a pessoa citada; sem nome → a coordenação
    x = sala.falar(cfg, r["conversa_id"], "Beatriz, qual o scorecard da área?")
    assert x["respostas"][-1]["autor"] == "dir_dados"
    x = sala.falar(cfg, r["conversa_id"], "o que você faz?")
    assert x["respostas"][-1]["autor"] == "coord_engenharia"
    x = sala.falar(cfg, r["conversa_id"], "o que você faz?", para="head_engenharia")
    assert x["respostas"][-1]["autor"] == "head_engenharia"


def teste_nps_numa_formula_so():
    from robo import conferencia
    passos = conferencia.montar_excel("nps", "nota", [], [], None)
    formulas = [l for l in passos.split("\n") if l.startswith("=")]
    assert len(formulas) == 1 and formulas[0].count("CONT.SES") == 3 and formulas[0].startswith("=ARRED((")
