"""Liderança (diretores e heads), ciência de dados, RH, rotinas registradas, abertura do notebook e Raio-X."""

from datetime import datetime, timedelta

import pytest

from conftest import REGRA_NPS
from robo import atendimento, auditoria, ferramentas, lideranca, memoria, organizacao, raio_x, rotinas
from robo.pipeline import processar_arquivo


@pytest.fixture
def cfg(planilha_baguncada, cfg_factory):
    return cfg_factory(regras=[REGRA_NPS])


def teste_hierarquia_e_provas_da_lideranca(cfg):
    assert organizacao.gestor_de("ger_engenharia") == "head_engenharia"
    assert organizacao.gestor_de("head_engenharia") == "dir_dados" and organizacao.gestor_de("dir_dados") == "dono"
    for p in lideranca.EQUIPE:
        c = organizacao.contrato(p["id"], cfg)
        assert c["revisor"] != p["id"] and c["ferramentas"], p["id"]
        assert c["fontes_conhecimento"] and c["responsabilidades"]
    from robo import rh
    reprovados = [p["id"] for p in lideranca.EQUIPE if not rh.ficha({"id": p["id"], "habilidades": []})["provas"]["aprovado"]]
    assert reprovados == []
    andares = organizacao.lotacao()
    assert all("diretor" in andares[a] for a in (1, 2, 4, 5)) and all("head" in andares[a] for a in (1, 2, 3, 4, 5))


def teste_rotina_registrada_e_erro_vira_handover(cfg):
    rotinas.executar(cfg, "pdca", lambda: [])          # em dia: só verificação
    rotinas.executar(cfg, "estudo", lambda: {"funcionarios": 69})
    rotinas.executar(cfg, "backup", lambda: 1 / 0)    # erro registrado, não derruba
    estado = {r["nome"]: r for r in rotinas.estado(cfg)}
    assert estado["pdca"]["ultimo_status"] == "em_dia" and not estado["pdca"]["atrasada"]
    assert estado["estudo"]["ultimo_status"] == "fez" and "funcionarios: 69" in estado["estudo"]["detalhe"]
    assert estado["backup"]["ultimo_status"] == "erro" and "ZeroDivisionError" in estado["backup"]["detalhe"]
    assert any("Rotina backup" in h["erro"] for h in memoria.handovers(cfg))
    assert [e["nome"] for e in rotinas.execucoes(cfg)] == ["backup", "estudo"]


def teste_abertura_do_notebook_sabe_quanto_tempo_ficou_desligado(cfg):
    a1 = rotinas.abrir_sessao(cfg, fila=0)
    assert a1["desligado_horas"] is None and "Primeira abertura" in a1["briefing"]
    from robo.trabalho import Trabalho
    with Trabalho(cfg).tx() as c:  # simula notebook fechado há 30 horas
        c.execute("UPDATE sessoes SET ultimo_batimento=? WHERE id=?",
                  ((datetime.now() - timedelta(hours=30)).isoformat(timespec="seconds"), a1["sessao"]))
    a2 = rotinas.abrir_sessao(cfg, fila=2)
    assert 29.5 <= a2["desligado_horas"] <= 30.5 and "2 arquivo(s) esperando" in a2["briefing"]
    assert "estudo" in a2["atrasadas"]


def teste_raio_x_e_scorecards(planilha_baguncada, cfg):
    memoria.registrar_execucao(cfg, processar_arquivo(planilha_baguncada, cfg))
    r = raio_x.montar(cfg)
    assert r["pessoas"]["total"] == len(organizacao.lista(cfg)) and r["planilhas"]["semana"] == 1
    assert "Rotinas" in r["onde_fica"] and "funcionários" in raio_x.texto(r)
    for d in ("dir_dados", "dir_analytics", "dir_operacoes", "dir_pessoas", "dir_tecnologia"):
        sc = lideranca.scorecard(cfg, d)
        assert sc["indicadores"] and all(i["farol"] in ("verde", "amarelo", "vermelho", "cinza") for i in sc["indicadores"])
    painel = next(i for i in lideranca.scorecard(cfg, "dir_tecnologia")["indicadores"] if i["indicador"] == "Painel com senha")
    assert painel["farol"] == "vermelho"  # sem senha = vermelho, sem maquiagem


def teste_auditoria_dos_heads_confere_por_outro_caminho(planilha_baguncada, cfg):
    assert processar_arquivo(planilha_baguncada, cfg).status == "sucesso"
    r = auditoria.auditar(cfg, "head_engenharia")
    assert r["amostra"] == ["nps_outubro.xlsx"] and r["aprovada"], r["achados"]
    r = auditoria.auditar(cfg, "head_ciencia")
    assert r["amostra"] and r["aprovada"], r["achados"]
    # adultera a análise publicada: a auditoria percebe
    import pandas as pd
    from robo import historico
    exe = historico.ler_execucao(cfg.logs, historico.ler(cfg.logs, 1)[0]["id"])
    rel = exe["analise"]["relatorio"]
    abas = pd.read_excel(rel, sheet_name=None)
    abas["indicadores"].loc[abas["indicadores"]["segmento"] == "Total", "valor"] = 99.0
    with pd.ExcelWriter(rel) as w:
        for n, df in abas.items():
            df.to_excel(w, sheet_name=n, index=False)
    r = auditoria.auditar(cfg, "head_ciencia")
    assert not r["aprovada"] and "99.0" in r["achados"][0]
    assert any("Auditoria Ciência" in h["erro"] for h in memoria.handovers(cfg))
    assert len(auditoria.listar(cfg)) == 3


def teste_cientistas_no_chat(planilha_baguncada, cfg):
    processar_arquivo(planilha_baguncada, cfg)
    resp = atendimento.conversar(cfg, "cd_junior_anomalias", "tem valores estranhos?")["respostas"][-1]
    assert resp["autor"] == "cd_junior_anomalias" and resp["natureza"] == "calculo"
    # quem não tem a ferramenta encaminha para o cientista certo
    r = atendimento.conversar(cfg, "rh_rs", "o que mais influencia o nps?")["respostas"]
    assert r[0]["natureza"] == "limitacao" and r[-1]["autor"] == "cd_senior_drivers"


def teste_conversa_organizada_com_frase_natural(planilha_baguncada, cfg):
    processar_arquivo(planilha_baguncada, cfg)
    r = ferramentas.executar("calcular", cfg, pergunta="nps por curso")
    abertura, *secoes = r["texto"].split("\n\n## ")
    assert abertura.startswith("O NPS geral é **") and "Por curso, o maior é **" in abertura
    assert [s.split("\n")[0] for s in secoes][:1] == ["Resultado detalhado"]
    assert any(s.startswith("Faça você mesmo no Excel") for s in secoes)


def teste_raio_x_e_rh_respondem_no_chat(cfg):
    assert atendimento.conversar(cfg, "dir_operacoes", "como está a empresa?")["respostas"][-1]["autor"] == "dir_operacoes"
    resp = atendimento.conversar(cfg, "rh_people", "people analytics")["respostas"][-1]
    assert resp["autor"] == "rh_people" and "funcionários" in resp["texto"]
    resp = atendimento.conversar(cfg, "dir_pessoas", "qual o scorecard da área?")["respostas"][-1]
    assert resp["autor"] == "dir_pessoas" and "Marta" in resp["texto"]


def teste_promocao_sugerida_aprovada_pelo_dono_e_efetivada(cfg):
    from robo import orquestrador, reuniao
    from robo.pipeline import obter_equipe
    from robo.trabalho import Trabalho
    equipe = obter_equipe(cfg)
    equipe.salvar({"id": "contratado_bom", "nome": "Otávio", "papel": "Analista", "nivel": "junior", "andar": 2,
                   "posicao": "limpeza", "habilidades": [], "ativo": True})
    for _ in range(20):
        memoria.experiencia(cfg, "contratado_bom", "acerto", "conferência ok", "teste")
    ata = reuniao.gerar(cfg, publicar=False)
    sug = ata["promocoes_sugeridas"]
    assert [(x["id"], x["de"], x["para"]) for x in sug] == [("contratado_bom", "junior", "pleno")]
    pend = Trabalho(cfg).aprovacoes_pendentes()
    assert any("Promover Otávio" in a["pedido"] for a in pend)
    r = orquestrador.decidir(cfg, sug[0]["aprovacao"], True)
    assert r["promovido"] and next(a for a in obter_equipe(cfg).personalizados if a["id"] == "contratado_bom")["nivel"] == "pleno"


def teste_lideres_consultam_conhecimento_de_gestao(cfg):
    resp = atendimento.conversar(cfg, "head_rh", "como dar feedback para a equipe?")["respostas"][-1]
    assert resp["natureza"] == "conhecimento" and "Situação" in resp["texto"]
    assert any("lideranca_e_gestao" in f for f in organizacao.contrato("coord_analise", cfg)["fontes_conhecimento"])
