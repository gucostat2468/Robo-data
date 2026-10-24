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
    assert demandas.nivel_para("gerente", [])[0] == "dificil"  # 1ª demanda no início do cargo
    assert demandas.nivel_para("junior", [])[0] == "basico" and demandas.nivel_para("senior", [])[0] == "medio"
    # recalibração: head com histórico todo no básico (de antes da regra) vai ao início do cargo; quem caiu por falha não
    assert demandas.nivel_para("head", [c("concluida", "basico")])[0] == "dificil"
    assert demandas.nivel_para("head", [c("falhou", "dificil")])[0] == "medio"
    assert demandas.nivel_para("head", [c("concluida", "medio"), c("falhou", "dificil")])[0] == "medio"
    assert demandas.nivel_para("gerente", [c("concluida", "basico")] * 2)[0] == "dificil"  # recalibrado
    assert demandas.nivel_para("senior", [c("concluida", "medio")] * 2)[0] == "dificil"  # sobe com prova
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
    # justificativa é sempre registrada: estagiário em observação ou equipe cujo trabalho é a própria rotina
    assert all("observação" in m or "rotina" in m for a in cob["andares"].values() for m in a["justificados"].values())
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


# ----------------------------------------------------------------------------------------------- SQL e 5º andar
def teste_cada_um_faz_o_trabalho_do_papel_em_rodizio(cfg_factory):
    """Pedido do dono: cada funcionário faz o SEU papel, sem repetir sempre a mesma coisa."""
    cfg = _cfg(cfg_factory)
    gente = organizacao.por_id()
    # o RH faz RH (antes o 4º andar inteiro conferia LGPD), a Sala de Casos revisa casos, o 5º andar opera a TI
    rh = demandas.candidatas(cfg, gente["rh_rs"])
    assert rh[0] == "recrutamento" and {"desempenho", "people_analytics"} <= set(rh) and "dados_pessoais" not in rh
    assert demandas.candidatas(cfg, gente["casos_engenharia"]) == ["revisar_caso"]
    assert demandas.candidatas(cfg, gente["head_aws"])[0] == "prontidao_nuvem"
    assert demandas.candidatas(cfg, gente["aws_senior"])[0] == "restauracao_backup"
    assert "dados_pessoais" in demandas.candidatas(cfg, gente["gov_pleno_lgpd"])
    # rodízio: em 4 demandas seguidas, 4 trabalhos diferentes para quem tem 4 ou mais no papel
    pessoa, usadas = gente["cd_senior_drivers"], []
    for _ in range(4):
        usadas.insert(0, demandas.escolher_ferramenta(cfg, pessoa, usadas=usadas))
    assert len(set(usadas)) == 4 and "sql_treino" in usadas and usadas[-1] == "drivers"  # especialidade primeiro


def teste_equipes_com_rotina_propria_nao_recebem_trabalho_de_outra_area(cfg_factory, ferramentas_rapidas):
    cfg = _cfg(cfg_factory, por_ciclo=200)
    demandas.rotina(cfg)
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        receberam = {r[0] for r in c.execute("SELECT funcionario FROM solicitacoes WHERE origem='demanda_sintetica'")}
        motivos = dict(c.execute("SELECT funcionario, motivo FROM demandas_registro WHERE evento='pulada'").fetchall())
    for pid in organizacao.ROTINA_PROPRIA:
        assert pid not in receberam and "rotina" in motivos[pid]


def teste_quinto_andar_e_aws_trabalham_mais_vezes(cfg_factory):
    c = dict(demandas.PADRAO)
    gente = organizacao.por_id()
    assert demandas.intervalo_da_pessoa(c, gente["aws_senior"]) == 1   # AWS: a cada hora
    assert demandas.intervalo_da_pessoa(c, gente["head_aws"]) == 1
    quinto = next(p for p in gente.values() if p["andar"] == 5 and p["id"] not in c["horas_por_pessoa"])
    assert demandas.intervalo_da_pessoa(c, quinto) == 3                # 5º andar: a cada 3 h
    outro = next(p for p in gente.values() if p["andar"] == 2)
    assert demandas.intervalo_da_pessoa(c, outro) == 6                 # todos: a cada 6 h (antes 24 h)
    # só aperta: um intervalo geral menor vale para todos
    assert demandas.intervalo_da_pessoa({**c, "por_pessoa_horas": 1}, gente["aws_senior"]) == 1


def teste_sql_profissional_tem_conferencia_cruzada_de_sql_por_colega(cfg_factory, monkeypatch):
    cfg = _cfg(cfg_factory)
    gab = {"linhas": 10}
    monkeypatch.setattr(demandas.CATALOGO["sql_treino"], "preparar",
                        lambda cfg, p: ({"regra": "nps", "arquivo": "TREINO_nps_1_2_3.xlsx", "gabarito": gab},
                                        [{"tipo": "verdadeiro", "chave": "confere"}]))
    pessoa = organizacao.por_id()["head_engenharia"]
    plano = demandas.montar(cfg, pessoa, "sql_treino", "profissional")
    cruz = next(e for e in plano["etapas"] if e["titulo"].startswith("Conferência cruzada"))
    assert cruz["ferramenta"] == "sql_treino" and cruz["funcionario"] != "head_engenharia"
    assert cruz["parametros"]["nivel"] == "medio" and cruz["parametros"]["arquivo"] == "TREINO_nps_1_2_3.xlsx"
    n = str(plano["etapas"].index(cruz) + 1)
    assert {"tipo": "verdadeiro", "chave": "confere"} in plano["criterios_por_etapa"][n]


def teste_estagiario_observa_e_registra_sem_executar(cfg_factory, ferramentas_rapidas):
    cfg = _cfg(cfg_factory, por_ciclo=200)
    demandas.rotina(cfg)
    estagiarios = {p["id"] for p in organizacao.lista() if organizacao.nivel_de(p["id"], p) == "estagiario"}
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        executaram = {r[0] for r in c.execute("SELECT funcionario FROM solicitacoes WHERE origem='demanda_sintetica'")}
        observaram = {r[0] for r in c.execute("SELECT funcionario FROM demandas_registro WHERE evento='observou'")}
        memoria = {r[0] for r in c.execute("SELECT funcionario FROM experiencias WHERE origem='observacao'")}
    assert not (estagiarios & executaram)          # regra do dono: estagiário não executa
    assert observaram and observaram <= estagiarios and observaram == memoria  # mas observa e fica registrado


def teste_sala_de_casos_revisa_mesmo_em_maquina_nova(cfg_factory):
    """Na nuvem cada turno começa numa máquina nova: os casos antigos não têm arquivo aqui. A Sala produz um caso novo
    e a pessoa revisa (antes a revisão ficava bloqueada e virava estudo)."""
    cfg = _cfg(cfg_factory)
    pessoa = organizacao.por_id()["casos_revisor"]
    r = demandas._caso_para_revisar(cfg, pessoa)
    assert not isinstance(r, str), r
    caso = r[0]["caso"]
    from robo.treino_casos import CATALOGO as COMP
    assert COMP[caso["competencia"]].designer != pessoa["id"] and caso["sha"]
    res = ferramentas.executar("revisar_caso", cfg, caso=caso)
    assert res["ok"] and res["dados"]["aprovado"], res["texto"]


def teste_trabalho_bloqueado_vai_para_o_proximo_do_papel_e_nao_para_estudo(cfg_factory, ferramentas_rapidas, monkeypatch):
    """Achado na nuvem: o rodízio caía no exercício de SQL (bloqueado) e a pessoa ia estudar, com 3 trabalhos livres."""
    cfg = _cfg(cfg_factory, por_ciclo=1)
    _base(cfg)
    ordem = ["drivers", "calcular"]  # drivers bloqueia (a base não tem NPS/CSAT); calcular tem base
    monkeypatch.setattr(demandas, "escolher_ferramenta",
                        lambda cfg, p, ultima=None, usadas=None: next((f for f in ordem if f not in (usadas or [])), None))
    r = demandas.rotina(cfg)
    assert r["atribuidas"] == 1 and r["bloqueadas"] == 1
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        modelo, plano = c.execute("SELECT modelo, plano FROM solicitacoes WHERE origem='demanda_sintetica'").fetchone()
        eventos = [r[0] for r in c.execute("SELECT evento FROM demandas_registro WHERE evento IN ('bloqueada','atribuida',"
                                           "'treinamento') ORDER BY id")]
    assert modelo == "demanda:calcular" and json.loads(plano)["tipo_demanda"] == "trabalho"  # trabalho do papel, não estudo
    assert eventos == ["bloqueada", "atribuida"]  # o bloqueio do drivers fica registrado com o motivo


def _ultimo_ciclo(cfg) -> dict:
    with Trabalho(cfg).tx() as c:
        return json.loads(c.execute("SELECT detalhe FROM demandas_ciclos ORDER BY id DESC LIMIT 1").fetchone()[0])


def teste_estudo_por_bloqueio_nao_ocupa_a_vez_da_pessoa(cfg_factory, ferramentas_rapidas, monkeypatch):
    """Quem recebeu estudo porque o trabalho estava bloqueado volta a ser candidato no ciclo seguinte (antes: 6 h preso)."""
    cfg = _cfg(cfg_factory, por_ciclo=1, por_pessoa_horas=6)
    monkeypatch.setattr(demandas, "escolher_ferramenta", lambda cfg, p, ultima=None, usadas=None: "drivers")  # sem base
    r1 = demandas.rotina(cfg)
    alvo = _ultimo_ciclo(cfg)["atribuidas"][0]
    assert r1["atribuidas"] == 1 and alvo["tipo"] == "treinamento"
    _base(cfg)  # a base chegou: agora há trabalho de verdade
    monkeypatch.setattr(demandas, "escolher_ferramenta", lambda cfg, p, ultima=None, usadas=None: "calcular")
    demandas.rotina(cfg)
    puladas = {x["funcionario"]: x["motivo"] for x in _ultimo_ciclo(cfg)["puladas"]}
    assert "menos de 6 h" not in puladas.get(alvo["funcionario"], "")  # não ficou preso por causa do estudo
