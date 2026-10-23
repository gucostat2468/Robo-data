"""Etapa 4 — equipe de demandas (Aurora, Vicente, Isadora, Renan, Bento): níveis de verdade, distribuição por andar,
abandono, treinamento no lugar, avaliação independente e cobertura por andar e área.

O que precisa ser verdade sempre:
  - nível começa no básico, sobe com acertos, desce com falha e nunca passa do teto do cargo;
  - o nível muda o TRABALHO: médio entrega arquivo; difícil consulta o conhecimento; profissional tem um colega de
    outra área conferindo; quem não tem a ferramenta da etapa a repassa (encaminhamento registrado);
  - a fila alterna os andares; demanda abandonada é encerrada pelo Renan (nunca em nome do dono) e a pessoa volta;
  - o Bento nunca avalia o que executou ou revisou, e acha a divergência quando a conta refeita do arquivo não bate;
  - cobertura 'completa' só é verdade quando todo elegível foi atendido ou tem motivo registrado.
"""

import json
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import pytest

from robo import demandas, ferramentas, organizacao, orquestrador
from robo.trabalho import Trabalho

REAL = ferramentas.executar


def _cfg(cfg_factory, **dem):
    cfg = cfg_factory(demandas={"intervalo_minutos": 0, "por_ciclo": 6, "por_dia": 1000, "por_pessoa_horas": 0, **dem})
    cfg.criar_pastas()
    return cfg


def _base(cfg, nome="TREINO_vendas_20261023_100000_1.xlsx"):
    pasta = cfg.tratadas / "_treino"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / nome
    pd.DataFrame({"pedido": [1001, 1002, 1003, 1004], "quantidade": [3, 5, 8, 10],
                  "email": ["a@x.com", "b@x.com", "", "d@x.com"]}).to_excel(arq, index=False)
    return arq


@pytest.fixture
def ferramentas_rapidas(monkeypatch):
    """As ferramentas de leitura respondem na hora; o resumo executivo é o DE VERDADE (precisa gerar o .md)."""
    def executar(fid, cfg, **params):
        if fid == "resumo_executivo":
            return REAL(fid, cfg, **params)
        return ferramentas.resultado(True, "ferramenta", f"{fid}: resultado conferido com evidência suficiente.",
                                     {"fonte": "teste", "calculo": {"valores": {"(total)": 6.5}}}, evidencia="teste")
    monkeypatch.setattr(ferramentas, "executar", executar)


# ----------------------------------------------------------------------------------------------- a equipe
def teste_os_cinco_estao_no_quadro_com_gestao_independente():
    gente = organizacao.por_id()
    for pid in demandas.POR_ID:
        assert pid in gente and gente[pid]["andar"] == 4
    assert organizacao.gestor_de("dem_avaliador") == "head_casos"  # quem avalia não responde a quem distribui
    assert organizacao.gestor_de("dem_gerador") == "dem_coordenador"
    # nenhum nome repetido no quadro inteiro (as 3 repetições antigas foram resolvidas com autorização do dono,
    # trocando só o nome exibido: id, histórico e permissões continuam os mesmos)
    nomes = [p["nome"] for p in organizacao.lista()]
    assert len(set(nomes)) == len(nomes)


def teste_provas_tecnicas_da_equipe():
    assert all(ok for casos in demandas.provas().values() for _, ok in casos)


# ----------------------------------------------------------------------------------------------- níveis
def teste_nivel_sobe_desce_e_respeita_o_teto():
    c = lambda e, n, t="trabalho": {"estado": e, "nivel": n, "tipo_demanda": t}
    assert demandas.nivel_para("gerente", [])[0] == "basico"
    assert demandas.nivel_para("gerente", [c("concluida", "basico")] * 2)[0] == "medio"
    assert demandas.nivel_para("gerente", [c("concluida", "dificil")] * 2)[0] == "profissional"
    assert demandas.nivel_para("pleno", [c("concluida", "medio")] * 2)[0] == "medio"  # teto do pleno
    assert demandas.nivel_para("junior", [c("concluida", "basico")] * 5)[0] == "basico"  # teto do júnior
    assert demandas.nivel_para("senior", [c("falhou", "dificil"), c("concluida", "dificil")])[0] == "medio"
    assert demandas.nivel_para("senior", [c("concluida_parcialmente", "dificil"), c("concluida", "dificil")])[0] == "dificil"
    # treinamento e demanda abandonada (cancelada) não mexem no nível
    assert demandas.nivel_para("senior", [c("falhou", "medio", "treinamento"), c("concluida", "medio"),
                                          c("concluida", "medio")])[0] == "dificil"
    assert demandas.nivel_para("senior", [c("cancelada", "medio"), c("concluida", "medio"),
                                          c("concluida", "medio")])[0] == "dificil"


def teste_cada_nivel_muda_o_trabalho(cfg_factory):
    cfg = _cfg(cfg_factory)
    arq = _base(cfg)
    pessoa = organizacao.por_id(cfg)["analise_estatistica"]
    etapas = {n: demandas.montar(cfg, pessoa, "perfil_indicadores", n)["etapas"] for n in demandas.NIVEIS}
    assert [len(etapas[n]) for n in demandas.NIVEIS] == [1, 2, 3, 4]
    assert etapas["medio"][-1]["ferramenta"] == "resumo_executivo" and etapas["medio"][-1]["depende"] == [1]
    estudo = [e for e in etapas["dificil"] if e["ferramenta"] == "conhecimento"][0]
    assert estudo["parametros"]["pergunta"].startswith("Perfil e indicadores")  # sobre o trabalho, não genérica
    cruzada = [e for e in etapas["profissional"] if e["ferramenta"] == "dados_pessoais"][0]
    assert cruzada["funcionario"] != pessoa["id"] and cruzada["parametros"]["arquivo"] == str(arq)


def teste_abertura_generica_de_manual_nao_vale_como_conhecimento():
    genericas = demandas.secoes_genericas()
    assert "Manual de boas práticas da empresa" in genericas
    crit = [{"tipo": "fonte_especifica", "genericas": sorted(genericas)}]
    generica = {"ok": True, "evidencia": "manual boas_praticas.md, seção “Manual de boas práticas da empresa”"}
    especifica = {"ok": True, "evidencia": "manual boas_praticas.md, seção “Segurança e LGPD”"}
    assert demandas.conferir_criterios(generica, crit) and not demandas.conferir_criterios(especifica, crit)


def teste_nivel_medio_entrega_arquivo_e_registra_o_repasse(cfg_factory, ferramentas_rapidas):
    cfg = _cfg(cfg_factory)
    _base(cfg)
    pessoa = organizacao.por_id(cfg)["dba"]  # a DBA não tem o resumo executivo no contrato: repassa a quem tem
    assert not organizacao.pode_usar("dba", "resumo_executivo", cfg, producao=True)
    sid, motivo = demandas.criar_demanda(cfg, pessoa, "ronda_ti" if False else "historico", "medio")
    assert sid, motivo
    assert orquestrador.executar(cfg, sid) == "concluida"
    s = Trabalho(cfg).solicitacao(sid)
    assert len(s["artefatos"]) == 1 and s["artefatos"][0]["caminho"].endswith(".md")
    assert any(e["tipo"] == "encaminhada" for e in s["eventos"])  # o repasse ficou registrado
    resumo = s["etapas"][-1]
    assert resumo["funcionario"] != "dba" and resumo["estado"] == "concluida"


# ----------------------------------------------------------------------------------------------- distribuição
def teste_fila_alterna_os_andares(cfg_factory, ferramentas_rapidas, monkeypatch):
    cfg = _cfg(cfg_factory, por_ciclo=5)
    monkeypatch.setattr(demandas, "escolher_ferramenta", lambda cfg, p: "historico")
    demandas.rotina(cfg)
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        andares = [r[0] for r in c.execute("SELECT andar FROM demandas_registro WHERE evento='atribuida' ORDER BY id")]
    assert sorted(andares) == [1, 2, 3, 4, 5]  # 5 vagas, 5 andares: um de cada


def teste_abandonada_e_encerrada_pelo_renan_e_a_pessoa_volta(cfg_factory, ferramentas_rapidas, monkeypatch):
    cfg = _cfg(cfg_factory, por_ciclo=1, horas_abandono=6)
    monkeypatch.setattr(demandas, "escolher_ferramenta", lambda cfg, p: "historico")
    monkeypatch.setattr(orquestrador, "executar", lambda cfg, sid: "na_fila")  # o robô "caiu" no meio
    antes = datetime.now() - timedelta(hours=8)
    demandas.rotina(cfg, agora=antes)
    with Trabalho(cfg).tx() as c:
        c.execute("UPDATE solicitacoes SET criada_em=?", (antes.isoformat(timespec="seconds"),))  # aberta há 8 h
    r = demandas.rotina(cfg)
    assert r["reatribuidas"] == 1
    tb = Trabalho(cfg)
    with tb.tx() as c:
        sid, pid = c.execute("SELECT id, funcionario FROM solicitacoes WHERE estado='cancelada'").fetchone()
        reg = c.execute("SELECT responsavel, motivo FROM demandas_registro WHERE evento='reatribuida'").fetchone()
    ev = [e for e in tb.solicitacao(sid)["eventos"] if e["para"] == "cancelada"][0]
    assert ev["quem"] == "dem_cobertura" and "mais de 6 h" in ev["texto"]  # nunca em nome do dono
    assert reg[0] == "dem_cobertura"


# ----------------------------------------------------------------------------------------------- avaliação
def teste_bento_confirma_e_acha_divergencia_na_conta_refeita_do_arquivo(cfg_factory):
    cfg = _cfg(cfg_factory)
    arq = _base(cfg)
    pessoa = organizacao.por_id(cfg)["canal_nina"]
    sid, _ = demandas.criar_demanda(cfg, pessoa, "calcular")
    assert orquestrador.executar(cfg, sid) == "concluida"
    assert demandas.avaliar(cfg)[0]["veredito"] == "confirmada"
    sid2, _ = demandas.criar_demanda(cfg, pessoa, "calcular")
    assert orquestrador.executar(cfg, sid2) == "concluida"
    pd.DataFrame({"pedido": [1], "quantidade": [100]}).to_excel(arq, index=False)  # o arquivo mudou depois da entrega
    av = demandas.avaliar(cfg)
    assert av[0]["solicitacao"] == sid2 and av[0]["veredito"] == "divergente"
    assert any("conta refeita do arquivo" in a for a in av[0]["achados"])
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        assert c.execute("SELECT COUNT(*) FROM aprendizados WHERE evidencia_id=?", (sid2,)).fetchone()[0] == 1
        assert c.execute("SELECT estado FROM solicitacoes WHERE id=?", (sid2,)).fetchone()[0] == "concluida"  # nada apagado
    assert demandas.avaliar(cfg) == []  # cada demanda é avaliada uma vez só


def teste_bento_nunca_avalia_o_que_executou(cfg_factory, ferramentas_rapidas):
    cfg = _cfg(cfg_factory)
    sid, _ = demandas.criar_demanda(cfg, organizacao.por_id(cfg)["dem_avaliador"], "historico")
    assert orquestrador.executar(cfg, sid) == "concluida"
    assert demandas.avaliar(cfg) == []


# ----------------------------------------------------------------------------------------------- cobertura e prova
def teste_cobertura_por_andar_e_area_so_completa_com_todos(cfg_factory, ferramentas_rapidas, monkeypatch):
    cfg = _cfg(cfg_factory, por_ciclo=3)
    monkeypatch.setattr(demandas, "escolher_ferramenta", lambda cfg, p: "historico")
    r = demandas.rotina(cfg)
    assert r["cobertura_completa"] is False
    cob = demandas.cobertura(cfg)
    assert set(cob["andares"]) == {1, 2, 3, 4, 5} and cob["areas"]
    assert sum(len(a["sem_demanda"]) for a in cob["andares"].values()) > 0
    assert all("observação" in m for a in cob["andares"].values() for m in a["justificados"].values())
    cfg.dados["demandas"]["por_ciclo"] = 1000
    assert demandas.rotina(cfg)["cobertura_completa"] is True
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:  # prova de trabalho dos cinco: uma etapa de cada no ciclo
        quem = {r[0] for r in c.execute("SELECT e.funcionario FROM jobs_etapas e JOIN jobs j ON j.id=e.job_id "
                                        "WHERE j.tipo='ciclo_demandas'")}
        dono_do_job = {r[0] for r in c.execute("SELECT funcionario FROM jobs WHERE tipo='ciclo_demandas'")}
    assert quem == {"dem_cobertura", "dem_distribuidor", "dem_gerador", "dem_avaliador"}
    assert dono_do_job == {"dem_coordenador"}


def teste_estudo_especifico_pula_a_abertura_e_o_canal_continua_igual(cfg_factory):
    cfg = _cfg(cfg_factory)
    generico = ferramentas.f_conhecimento(cfg, "boas práticas da empresa", registrar_uso=False)
    assert "Manual de boas práticas da empresa" in generico["evidencia"]  # pergunta do dono no canal: como sempre
    especifico = ferramentas.f_conhecimento(cfg, "boas práticas da empresa", registrar_uso=False, especifico=True)
    assert "Manual de boas práticas da empresa" not in especifico["evidencia"]


def teste_treinamento_estuda_o_assunto_da_demanda_bloqueada(cfg_factory, monkeypatch):
    cfg = _cfg(cfg_factory, por_ciclo=1)  # sem base sintética: drivers fica bloqueado
    monkeypatch.setattr(demandas, "escolher_ferramenta", lambda cfg, p: "drivers")
    demandas.rotina(cfg)
    with Trabalho(cfg).tx() as c:
        sid = c.execute("SELECT id FROM solicitacoes WHERE origem=?", (demandas.ORIGEM,)).fetchone()[0]
    s = Trabalho(cfg).solicitacao(sid)
    assert s["plano"]["tipo_demanda"] == "treinamento"
    params = s["etapas"][0]["parametros"]
    assert params["pergunta"].startswith("Drivers do indicador") and params["especifico"] is True
