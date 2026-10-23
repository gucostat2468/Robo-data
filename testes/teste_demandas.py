"""Demandas: trabalho real distribuído com justiça, critérios de aceitação conferidos sem IA e revisão independente.

O que precisa ser verdade sempre:
  - estagiário não recebe demanda (modo de observação) e o motivo fica registrado no ciclo;
  - ninguém tem duas demandas abertas, nem recebe outra antes de `por_pessoa_horas`;
  - quem nunca recebeu vem primeiro;
  - demanda sem condição de rodar não vira tarefa: fica no ciclo como bloqueada, com o motivo;
  - o revisor nunca é quem executou, e a conferência automática nunca sai no nome do dono;
  - critério não atendido reprova (com uma nova tentativa controlada) e a tarefa termina 'falhou', não 'concluída';
  - planilha sintética processada vira solicitação 'sintetica' e não gera proposta de regra para o dono.
"""

import json
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from robo import demandas, ferramentas, organizacao, orquestrador
from robo.trabalho import Trabalho


def _cfg(cfg_factory, **dem):
    cfg = cfg_factory(demandas={"intervalo_minutos": 0, "por_ciclo": 4, "por_dia": 500, **dem})
    cfg.criar_pastas()
    return cfg


def _ok(texto="Resultado conferido com evidência e texto suficiente.", **dados):
    return ferramentas.resultado(True, "ferramenta", texto, dados, evidencia="teste")


@pytest.fixture
def ferramenta_ok(monkeypatch):
    """Ferramenta sempre bem-sucedida: testa o fluxo (distribuição, estados, revisão) sem depender de cada ferramenta."""
    chamadas = []

    def falsa(fid, cfg, **params):
        chamadas.append((fid, params.get("quem")))
        return _ok()
    monkeypatch.setattr(ferramentas, "executar", falsa)
    monkeypatch.setattr(demandas, "escolher_ferramenta", lambda cfg, p: "ronda_ti")  # sem preparar: nunca bloqueia
    return chamadas


def _ultimo_ciclo(cfg) -> dict:
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        return json.loads(c.execute("SELECT detalhe FROM demandas_ciclos ORDER BY id DESC LIMIT 1").fetchone()[0])


# ----------------------------------------------------------------------------------------------- critérios
def teste_criterios_aceitam_e_reprovam_sem_ia():
    bom = _ok(calculo={"valores": {"(total)": 19.786}}, fonte="manual.md", linhas=[[1], [2]])
    crits = demandas.BASICOS + [{"tipo": "valor_unico", "esperado": 19.786, "coluna": "x"},
                                {"tipo": "dados", "chave": "fonte"}, {"tipo": "linhas_min", "n": 2}]
    assert demandas.conferir_criterios(bom, crits) == []
    ruim = ferramentas.resultado(False, "limitacao", "curto", {"calculo": {"valores": {"a": 1.0, "b": 2.0}}})
    falhas = demandas.conferir_criterios(ruim, crits)
    assert any("sucesso" in f for f in falhas) and any("evidência" in f for f in falhas)
    assert any("limitacao" in f for f in falhas) and any("único valor" in f for f in falhas)
    assert any("fonte" in f for f in falhas) and any("linha" in f for f in falhas)
    errado = _ok(calculo={"valores": {"(total)": 20.0}})
    assert any("conta independente" in f for f in demandas.conferir_criterios(errado, [{"tipo": "valor_unico", "esperado": 19.786}]))


# ----------------------------------------------------------------------------------------------- distribuição
def teste_estagiario_fica_em_observacao_e_o_motivo_fica_registrado(cfg_factory, ferramenta_ok):
    cfg = _cfg(cfg_factory)
    demandas.rotina(cfg)
    estagiarios = {p["id"] for p in organizacao.lista(cfg) if organizacao.nivel_de(p["id"], p) == "estagiario"}
    assert estagiarios
    assert not {quem for _, quem in ferramenta_ok} & estagiarios
    puladas = {x["funcionario"]: x["motivo"] for x in _ultimo_ciclo(cfg)["puladas"]}
    assert all("observação" in puladas[e] for e in estagiarios)


def teste_quem_nunca_recebeu_vem_primeiro_e_ninguem_recebe_duas(cfg_factory, ferramenta_ok):
    cfg = _cfg(cfg_factory, por_ciclo=5)
    r1 = demandas.rotina(cfg)
    r2 = demandas.rotina(cfg)
    assert r1["atribuidas"] == r2["atribuidas"] == 5
    primeiros = {a["funcionario"] for a in _ultimo_ciclo(cfg)["atribuidas"]}
    with Trabalho(cfg).tx() as c:
        por = [r[0] for r in c.execute("SELECT funcionario FROM solicitacoes WHERE origem=?", (demandas.ORIGEM,))]
    assert len(por) == len(set(por)) == 10  # 10 pessoas diferentes: o 2º ciclo foi para quem ainda não tinha recebido
    assert len(primeiros) == 5
    # todos os elegíveis recebem antes de alguém repetir; depois, ninguém repete antes de por_pessoa_horas
    cfg.dados["demandas"]["por_ciclo"] = 500
    demandas.rotina(cfg)
    cob = demandas.cobertura(cfg)
    assert all(not a["sem_demanda"] for a in cob["andares"].values())
    assert demandas.rotina(cfg)["atribuidas"] == 0
    assert any("menos de 24" in x["motivo"] for x in _ultimo_ciclo(cfg)["puladas"])


def teste_demanda_aberta_bloqueia_outra(cfg_factory, monkeypatch):
    cfg = _cfg(cfg_factory, por_ciclo=1)
    monkeypatch.setattr(demandas, "escolher_ferramenta", lambda cfg, p: "ronda_ti")
    monkeypatch.setattr(orquestrador, "executar", lambda cfg, sid: "na_fila")  # simula execução que ainda não terminou
    demandas.rotina(cfg)
    dono = _ultimo_ciclo(cfg)["atribuidas"][0]["funcionario"]
    cfg.dados["demandas"]["por_pessoa_horas"] = 0
    demandas.rotina(cfg)
    puladas = {x["funcionario"]: x["motivo"] for x in _ultimo_ciclo(cfg)["puladas"]}
    assert puladas[dono] == "já tem uma demanda aberta"


def teste_demanda_sem_condicao_nao_vira_tarefa(cfg_factory, monkeypatch):
    cfg = _cfg(cfg_factory, por_ciclo=3)  # sem planilha sintética: as demandas de dados ficam bloqueadas
    monkeypatch.setattr(demandas, "escolher_ferramenta", lambda cfg, p: "perfil_indicadores")
    r = demandas.rotina(cfg)
    assert r["atribuidas"] == 0 and r["bloqueadas"] > 0
    assert all("Bases-Tratadas/_treino" in b["motivo"] for b in _ultimo_ciclo(cfg)["bloqueadas"])
    with Trabalho(cfg).tx() as c:
        assert c.execute("SELECT COUNT(*) FROM solicitacoes").fetchone()[0] == 0  # nada de tarefa de mentira


def teste_intervalo_entre_ciclos(cfg_factory, ferramenta_ok):
    cfg = _cfg(cfg_factory, intervalo_minutos=30)
    assert demandas.rotina(cfg) is not None
    assert demandas.rotina(cfg) is None  # dentro do intervalo: não roda e não conta como trabalho


# ----------------------------------------------------------------------------------------------- execução e revisão
def teste_revisor_independente_e_nunca_o_dono(cfg_factory, ferramenta_ok):
    cfg = _cfg(cfg_factory, por_ciclo=500)
    demandas.rotina(cfg)
    tb = Trabalho(cfg)
    with tb.tx() as c:
        linhas = [dict(r) for r in c.execute("SELECT funcionario, revisor, estado FROM solicitacoes WHERE origem=?",
                                             (demandas.ORIGEM,))]
    assert linhas and all(l["revisor"] not in (l["funcionario"], "dono") for l in linhas)
    assert all(l["estado"] == "concluida" for l in linhas)
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:  # prova de trabalho: um job fechado por demanda, com a pessoa
        jobs = c.execute("SELECT funcionario, estado, fim FROM jobs WHERE tipo='demanda'").fetchall()
    assert sorted(j[0] for j in jobs) == sorted(l["funcionario"] for l in linhas)
    assert all(j[1] == "concluido" and j[2] for j in jobs)


def teste_criterio_nao_atendido_reprova_tenta_de_novo_e_falha(cfg_factory, monkeypatch):
    cfg = _cfg(cfg_factory)
    tentativas = []

    def errada(fid, cfg, **params):
        tentativas.append("execucao" if params.get("quem") else "recalculo_do_revisor")
        return _ok(calculo={"valores": {"(total)": 1.0}})  # o "cálculo" não bate com a conta independente
    monkeypatch.setattr(ferramentas, "executar", errada)
    pessoa = organizacao.por_id(cfg)["canal_nina"]
    monkeypatch.setitem(demandas.CATALOGO, "calcular", demandas.Modelo(
        "calcular", "Calcular", "objetivo", "evidência", demandas.BASICOS,
        lambda cfg, p: ({"pergunta": "média de x"}, [{"tipo": "valor_unico", "esperado": 19.786, "coluna": "x"}])))
    sid, _ = demandas.criar_demanda(cfg, pessoa, "calcular")
    assert orquestrador.executar(cfg, sid) == "falhou"
    s = Trabalho(cfg).solicitacao(sid)
    # 2 execuções (a original e UMA nova tentativa controlada) e, depois de cada uma, o recálculo do revisor
    assert tentativas.count("execucao") == 2 and tentativas.count("recalculo_do_revisor") == 2
    assert int(s["tentativas"]) == 1
    assert any("conta independente" in a for a in s["revisao"]["achados"])
    caminho = [e["para"] for e in s["eventos"] if e["tipo"] == "estado"]
    assert caminho[-3:] == ["em_correcao", "em_execucao", "em_revisao"] or "reprovada_revisao" in caminho
    assert caminho[-1] == "falhou"


def teste_calculo_real_bate_com_a_conta_independente(cfg_factory):
    cfg = _cfg(cfg_factory)
    pasta = cfg.tratadas / "_treino"
    pasta.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"pedido": [1001, 1002, 1003, 1004], "quantidade": [3, 5, 8, 10]}).to_excel(
        pasta / "TREINO_vendas_20261023_100000_1.xlsx", index=False)
    pessoa = organizacao.por_id(cfg)["canal_nina"]
    sid, motivo = demandas.criar_demanda(cfg, pessoa, "calcular")
    assert sid, motivo
    s = Trabalho(cfg).solicitacao(sid)
    assert s["etapas"][0]["parametros"]["pergunta"] == "média de quantidade"  # 'pedido' é identificador: fica de fora
    assert orquestrador.executar(cfg, sid) == "concluida"
    s = Trabalho(cfg).solicitacao(sid)
    assert s["etapas"][0]["resultado"]["dados"]["calculo"]["valores"] == {"(total)": 6.5}
    assert s["origem"] == demandas.ORIGEM and s["plano"]["dados"] == "sintetico"


# ----------------------------------------------------------------------------------------------- pós-processamento
def _resultado(arquivo, status):
    rel = SimpleNamespace(erros=[])
    return SimpleNamespace(arquivo=arquivo, status=status, relatorio=rel, id="exec1", linhas_entrada=3, linhas_saida=3,
                           saidas=[])


def teste_planilha_sintetica_vira_solicitacao_marcada_sem_proposta_de_regra(cfg_factory, monkeypatch, tmp_path):
    from robo import aprendizado, pos_processamento
    from robo.pipeline import SUCESSO
    cfg = _cfg(cfg_factory)
    propostas = []
    monkeypatch.setattr(aprendizado, "propor", lambda cfg, r: propostas.append(r))
    monkeypatch.setattr(aprendizado, "comprovar", lambda cfg, r: None)
    sid = pos_processamento.registrar(cfg, _resultado(tmp_path / "TREINO_nps_20261023_100000_1.xlsx", SUCESSO))
    assert Trabalho(cfg).solicitacao(sid)["origem"] == "sintetica" and propostas == []
    sid2 = pos_processamento.registrar(cfg, _resultado(tmp_path / "pesquisa_real.xlsx", SUCESSO))
    assert Trabalho(cfg).solicitacao(sid2)["origem"] == "automatica" and len(propostas) == 1
