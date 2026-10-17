"""Memória por funcionário, handover de erros por área, desempenho e reunião semanal da liderança."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from conftest import REGRA_NPS
from robo import ferramentas, memoria, reuniao
from robo.pipeline import processar_arquivo
from robo.trabalho import Trabalho


@pytest.fixture
def cfg(planilha_baguncada, cfg_factory):
    return cfg_factory(regras=[{**REGRA_NPS, "valores_permitidos": {"uf": ["SP"]}}])  # RJ e MG viram erro


def teste_erro_do_pipeline_vira_handover_unico_com_recorrencia(planilha_baguncada, cfg):
    r = processar_arquivo(planilha_baguncada, cfg)
    assert r.status == "reprovado"
    memoria.registrar_execucao(cfg, r)
    hs = memoria.handovers(cfg)
    h = next(x for x in hs if "lista permitida" in x["erro"])
    assert h["responsavel"] == "validacao" and h["andar"] == 1 and h["regra"] and h["como_verificar"]
    memoria.registrar_execucao(cfg, r)  # mesmo erro de novo: não duplica, soma recorrência
    h2 = next(x for x in memoria.handovers(cfg) if x["id"] == h["id"])
    assert h2["recorrencias"] == 2 and len(memoria.handovers(cfg)) == len(hs)
    # Otto (validação) ganhou experiência de acerto por detectar o erro
    assert any(e["tipo"] == "acerto" for e in memoria.experiencias(cfg, "validacao"))


def teste_handover_aplicado_reabre_se_o_erro_voltar(planilha_baguncada, cfg):
    r = processar_arquivo(planilha_baguncada, cfg)
    memoria.registrar_execucao(cfg, r)
    h = memoria.handovers(cfg)[0]
    memoria.mudar_handover(cfg, h["id"], "aplicado")
    memoria.registrar_execucao(cfg, r)
    assert next(x for x in memoria.handovers(cfg) if x["id"] == h["id"])["estado"] == "reaberto"


def teste_handover_vira_conhecimento(planilha_baguncada, cfg):
    memoria.registrar_execucao(cfg, processar_arquivo(planilha_baguncada, cfg))
    k = ferramentas.executar("conhecimento", cfg, pergunta="valores fora da lista permitida na coluna uf, o que fazer?")
    assert k["ok"] and k["evidencia"].startswith("handover")


def teste_desempenho_e_dossie(cfg):
    for _ in range(4):
        memoria.experiencia(cfg, "analise_perfil", "erro", "x", "teste")
    memoria.experiencia(cfg, "analise_perfil", "acerto", "y", "teste")
    d = next(x for x in memoria.desempenho(cfg) if x["id"] == "analise_perfil")
    assert d["taxa"] == 20.0 and d["situacao"] == "insuficiente" and not d["pode_ser_desligado"]
    arq = memoria.exportar_dossie(cfg, "analise_perfil")
    texto = Path(arq).read_text(encoding="utf-8")
    assert "Onde pesquisa" in texto and "Onde registra" in texto and "Escopo" in texto


def teste_reuniao_semanal_com_plano_de_acao(planilha_baguncada, cfg):
    memoria.registrar_execucao(cfg, processar_arquivo(planilha_baguncada, cfg))
    ata = reuniao.gerar(cfg, publicar=True)
    a1 = ata["andares"][0]
    assert a1["andar"] == 1 and any("reprovada" in x for x in a1["deu_errado"])
    assert a1["plano_de_acao"] and all(x["responsavel"] and x["verificacao"] for x in a1["plano_de_acao"])
    assert Path(ata["arquivo"]).exists() and "Plano de ação" in Path(ata["arquivo"]).read_text(encoding="utf-8")
    from robo import estrategia
    assert any(i.get("motivo", "").startswith("HO-") for i in estrategia.ler_backlog(cfg))
    assert reuniao.rotina(cfg) is None  # uma por semana


def teste_cargo_fixo_ruim_vira_defeito_de_codigo_e_contratado_vai_a_pdi_e_proposta(cfg, monkeypatch):
    for _ in range(5):
        memoria.experiencia(cfg, "analise_perfil", "erro", "x", "teste")
    ata = reuniao.gerar(cfg, publicar=False)
    assert "analise_perfil" in ata["defeitos_de_codigo"] and not ata["propostas_desligamento"]
    assert any(h["responsavel"] == "dev_pleno" for h in memoria.handovers(cfg))
    # contratado: 1ª reunião = PDI; 2ª = proposta; só o dono decide
    from robo import organizacao
    orig = organizacao.lista
    monkeypatch.setattr(organizacao, "lista", lambda c=None, com_contratados=True: orig(c, com_contratados) + (
        [{"id": "contratado_teste", "nome": "Teste", "papel": "Analista", "andar": 2, "grupo": "contratado",
          "canal": "analise", "cor": None, "descricao": ""}] if com_contratados and c is not None else []))
    for _ in range(5):
        memoria.experiencia(cfg, "contratado_teste", "erro", "x", "teste")
    a1 = reuniao.gerar(cfg, ate=datetime.now() + timedelta(seconds=1), publicar=False)
    assert "contratado_teste" in a1["pdi"]
    a2 = reuniao.gerar(cfg, ate=datetime.now() + timedelta(seconds=2), publicar=False)
    assert a2["propostas_desligamento"] == ["contratado_teste"] and a2["aprovacoes"]
    pend = Trabalho(cfg).aprovacoes_pendentes()
    assert pend and pend[0]["aprovador"] == "dono"
    from robo import orquestrador
    r = orquestrador.decidir(cfg, a2["aprovacoes"][0], False, "dar mais uma chance")
    assert r["estado"] == "recusada" and not r["desligado"]


def teste_handover_explica_por_que_e_por_que_nao_foi_resolvido(planilha_baguncada, cfg):
    r = processar_arquivo(planilha_baguncada, cfg)
    for _ in range(3):
        memoria.registrar_execucao(cfg, r)
    h = next(x for x in memoria.handovers(cfg) if "lista permitida" in x["erro"])
    assert h["por_que_aconteceu"] and "ninguém começou" in h["por_que_nao_resolvido"]
    assert h["na_origem"] and "não muda dado da origem" in h["por_que_nao_resolvido"]
    assert h["escalado"] and h["escalado_para"] == "Carla"  # repetiu 3 vezes: sobe para a líder do 1º andar
    simples = memoria.explicar({"erro": "Agente Vera está com configuração inválida", "responsavel": "coord_engenharia",
                                "estado": "aberto", "causa": "x", "andar": 1, "recorrencias": 1})
    assert simples["simples"] and simples["quem_precisa_agir"].startswith("Você")


def teste_nps_mostra_a_conta_e_a_conclusao():
    import pandas as pd

    from robo import calculos
    df = pd.DataFrame({"nota_nps": [10, 9, 9, 8, 7, 6, 3, 10, 0, 9] * 10, "curso": ["A", "B"] * 50})
    _, texto = calculos._executar("nps", df, ["nota_nps"], ["curso"])
    assert "Total: NPS 20 = 50,0% promotores (50) − 30,0% detratores (30) = 20,0, arredondado para 20" in texto
    assert "neutros 20,0% (20)" in texto and "Conclusão: B (40) está de fato acima de A (0)" in texto
    assert "Como ler: NPS = % de promotores" in texto
