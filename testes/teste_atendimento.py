"""Conversa direta com funcionários, central de solicitações, orquestração com aprovação e revisão independente."""

import shutil
from pathlib import Path

import pytest

from conftest import REGRA_NPS
from robo import atendimento, ferramentas, orquestrador, organizacao
from robo.pipeline import processar_arquivo
from robo.trabalho import ErroTransicao, Trabalho


@pytest.fixture
def cfg(planilha_baguncada, cfg_factory):
    return cfg_factory(regras=[REGRA_NPS])


@pytest.fixture
def anexo(planilha_baguncada, tmp_path) -> str:
    """Cópia da planilha fora de Bases-Limpeza (arquivo anexado à conversa)."""
    destino = tmp_path / "anexos" / planilha_baguncada.name
    destino.parent.mkdir()
    shutil.copy2(planilha_baguncada, destino)
    planilha_baguncada.unlink()
    return str(destino)


# ----------------------------------------------------------------------------- registro único e contratos
def teste_registro_unico_bate_com_o_quadro_e_contrato_completo(cfg):
    from robo.canal import pessoas
    from robo.quadro import lotacao
    ids = {p["id"] for p in organizacao.lista()}
    assert ids == set(pessoas()) - {"dono"}
    assert {a: {n: sorted(v) for n, v in d.items()} for a, d in lotacao().items()} == \
        {a: {n: sorted(v) for n, v in d.items()} for a, d in organizacao.lotacao().items()}
    c = organizacao.contrato("analise_indicadores", cfg)
    for campo in ("cargo", "nivel", "andar", "gestor", "especialidade", "objetivo", "responsabilidades", "ferramentas",
                  "entradas", "saidas", "permissoes", "risco_maximo", "criterios_sucesso", "criterios_falha", "encaminha",
                  "pede_ajuda_quando", "revisor", "fontes_conhecimento"):
        assert campo in c, campo
    for p in organizacao.lista(cfg):  # ninguém revisa o próprio trabalho
        assert organizacao.revisor_de(p["id"], cfg) != p["id"]


def teste_estagiario_em_observacao_e_ninguem_se_promove(cfg):
    c = organizacao.contrato("ana_estagiario", cfg)
    assert not c["permissoes"]["altera_dados"] and not c["permissoes"]["aprova"]
    assert "publicar_planilha" not in c["ferramentas"] and "resumo_executivo" not in c["ferramentas"]
    assert not organizacao.pode_alterar_permissoes("coord_engenharia", "coord_engenharia")
    assert organizacao.pode_alterar_permissoes("dono", "ana_estagiario")


# ----------------------------------------------------------------------------- conversa com memória
def teste_conversa_calcula_lembra_e_continua(planilha_baguncada, cfg):
    processar_arquivo(planilha_baguncada, cfg)
    r = atendimento.conversar(cfg, "analise_estatistica", "nps por curso")
    cid = r["conversa_id"]
    assert r["respostas"][-1]["natureza"] == "calculo" and "Direito" in r["respostas"][-1]["texto"]
    r2 = atendimento.conversar(cfg, "analise_estatistica", "e por modalidade?", cid)
    assert "modalidade" in r2["respostas"][-1]["texto"] and "EAD" in r2["respostas"][-1]["texto"]
    # a memória sobrevive: outra instância lê o mesmo banco
    conv = Trabalho(cfg).conversa(cid)
    assert len(conv["mensagens"]) == 4 and conv["contexto"]["ultimo_calculo"].endswith("por modalidade")
    # toda pergunta entra na central
    assert len(Trabalho(cfg).listar(tipo="conversa")) == 2


def teste_correcao_do_dono_vale_na_conversa(planilha_baguncada, cfg):
    processar_arquivo(planilha_baguncada, cfg)
    r = atendimento.conversar(cfg, "analise_estatistica", "na verdade a coluna nota é nota_nps")
    assert r["respostas"][0]["natureza"] == "ferramenta"
    r2 = atendimento.conversar(cfg, "analise_estatistica", "média de nota por curso", r["conversa_id"])
    assert "nota_nps" in r2["respostas"][-1]["texto"]
    assert Trabalho(cfg).memorias("correcao")


def teste_correcao_do_dono_vira_regra_da_empresa_com_aprovacao(planilha_baguncada, cfg):
    from robo import aprendizado
    processar_arquivo(planilha_baguncada, cfg)
    r = atendimento.conversar(cfg, "analise_estatistica", "na verdade a coluna recomendacao é nota_nps")
    assert "esperando a sua aprovação" in r["respostas"][0]["texto"]
    [p] = [x for x in aprendizado.listar(cfg) if x["tipo"] == "apelido"]
    assert p["estado"] == "pendente" and p["valor"] == "recomendacao" and p["coluna"] == "nota_nps" and not p["alerta"]
    # antes da aprovação: OUTRA conversa, com OUTRO funcionário, não conhece a correção
    antes = atendimento.conversar(cfg, "dir_dados", "média de recomendacao por curso")["respostas"][-1]["texto"]
    assert "Usei a correção" not in antes
    with pytest.raises(PermissionError):
        aprendizado.decidir(cfg, p["id"], True, quem="analise_estatistica")  # quem propôs não aprova
    aprendizado.decidir(cfg, p["id"], True)
    # depois: vale para qualquer conversa e funcionário, avisa na resposta e o primeiro cálculo comprova
    depois = atendimento.conversar(cfg, "dir_dados", "média de recomendacao por curso")["respostas"][-1]["texto"]
    assert "nota_nps" in depois and "Usei a correção que você aprovou para a empresa" in depois
    assert depois.count("Usei a correção") == 1
    assert aprendizado.listar(cfg)[0]["estado"] == "comprovada"
    # e no canal da empresa também (mesma calculadora)
    from robo.calculos import calcular
    assert "Usei a correção" in calcular(cfg, "média de recomendacao por curso")["texto"]
    # o laboratório não usa correção de conversa
    assert "Usei a correção" not in (calcular(cfg, "média de recomendacao por curso", apelidos=False) or {}).get("texto", "")


def teste_apelido_novo_do_mesmo_termo_substitui_o_anterior(cfg):
    from robo import aprendizado
    cfg.criar_pastas()
    a = aprendizado.propor_apelido(cfg, "nota", "nota_nps", "analise_estatistica")
    aprendizado.decidir(cfg, a, True)
    b = aprendizado.propor_apelido(cfg, "nota", "nota_csat", "analise_estatistica")
    pend = aprendizado.listar(cfg, "pendente")[0]  # sem base publicada: avisa que não deu para conferir a coluna
    assert "nenhuma base publicada" in pend["evidencia"]
    aprendizado.decidir(cfg, b, True)
    assert aprendizado.apelidos_ativos(cfg) == {"nota": ("nota_csat", b)}
    antigo = next(x for x in aprendizado.listar(cfg) if x["id"] == a)
    assert antigo["ativa"] == 0 and b in antigo["motivo_desativacao"]
    assert aprendizado.aplicar_apelidos(cfg, "média de nota por região")[0] == "média de nota_csat por região"
    assert aprendizado.aplicar_apelidos(cfg, "média de nota_nps")[0] == "média de nota_nps"   # não mexe em outra coluna


def teste_fora_do_contrato_encaminha_para_o_colega(planilha_baguncada, cfg):
    processar_arquivo(planilha_baguncada, cfg)
    r = atendimento.conversar(cfg, "infra_pleno", "nps por curso")  # Rodrigo (TI) não calcula indicadores
    assert r["respostas"][0]["natureza"] == "limitacao" and r["respostas"][0]["encaminhado_para"]
    assert r["respostas"][1]["autor"] == r["respostas"][0]["encaminhado_para"] != "infra_pleno"
    assert r["respostas"][1]["natureza"] == "calculo"


def teste_sobre_mim_e_nao_inventa(cfg):
    r = atendimento.conversar(cfg, "dba", "o que você faz?")
    assert "Dora" in r["respostas"][0]["texto"] and r["respostas"][0]["natureza"] == "conhecimento"
    r = atendimento.conversar(cfg, "dba", "qual a capital da Mongólia segundo o relatório xyz")
    assert r["respostas"][-1]["natureza"] == "limitacao"


# ----------------------------------------------------------------------------- tarefas e orquestração
def teste_tarefa_verificar_planilha_com_plano_execucao_e_revisao(anexo, cfg):
    r = atendimento.conversar(cfg, "coord_engenharia", "Verifique esta planilha, por favor", arquivo=anexo)
    sid = r["solicitacao_id"]
    assert sid.startswith("TAR-")
    orquestrador.executar(cfg, sid)  # (já disparou em segundo plano; aqui garante o fim de forma síncrona)
    import time
    for _ in range(100):
        s = Trabalho(cfg).solicitacao(sid)
        if s["estado"] in ("concluida", "concluida_parcialmente", "falhou"):
            break
        time.sleep(0.1)
    assert s["estado"] == "concluida", s["eventos"]
    assert s["revisor"] not in {e["funcionario"] for e in s["etapas"]}
    assert [e["natureza"] for e in s["etapas"]] == ["execucao", "execucao", "execucao"]
    assert s["artefatos"] and Path(s["artefatos"][0]["caminho"]).read_text(encoding="utf-8").startswith("# ")
    estados = [e["para"] for e in s["eventos"] if e["tipo"] == "estado"]
    assert estados[:4] == ["em_triagem", "planejada", "na_fila", "em_execucao"] and "em_revisao" in estados


def teste_publicar_exige_aprovacao_do_dono(anexo, cfg):
    sid = orquestrador.criar(cfg, "publique esta planilha", "coord_engenharia", arquivo=anexo, iniciar=False)
    assert orquestrador.executar(cfg, sid) == "aguardando_aprovacao"
    tb = Trabalho(cfg)
    aprov = tb.aprovacoes_pendentes()
    assert len(aprov) == 1 and not list(Path(cfg.entrada).iterdir())  # nada foi copiado antes de aprovar
    with pytest.raises(ErroTransicao):
        tb.decidir(aprov[0]["id"], True, "recepcao")  # funcionário não aprova
    orquestrador.decidir(cfg, aprov[0]["id"], True, em_segundo_plano=False)
    s = tb.solicitacao(sid)
    assert s["estado"] == "concluida" and (Path(cfg.entrada) / Path(anexo).name).exists()


def teste_recusa_nao_executa(anexo, cfg):
    sid = orquestrador.criar(cfg, "publique esta planilha", "coord_engenharia", arquivo=anexo, iniciar=False)
    orquestrador.executar(cfg, sid)
    a = Trabalho(cfg).aprovacoes_pendentes()[0]
    orquestrador.decidir(cfg, a["id"], False, "ainda não", em_segundo_plano=False)
    s = Trabalho(cfg).solicitacao(sid)
    assert s["estado"] == "concluida_parcialmente" and not list(Path(cfg.entrada).iterdir())
    assert s["etapas"][1]["estado"] == "cancelada"


def teste_etapa_sem_ferramenta_fica_parcial_nunca_concluida(planilha_baguncada, cfg):
    processar_arquivo(planilha_baguncada, cfg)
    sid = orquestrador.criar(cfg, "monte uma apresentação para a diretoria", "ger_analise", iniciar=False)
    assert orquestrador.executar(cfg, sid) == "concluida_parcialmente"
    s = Trabalho(cfg).solicitacao(sid)
    ult = s["etapas"][-1]
    assert ult["estado"] == "bloqueada" and ult["natureza"] == "limitacao"
    assert s["resultado"]["nao_feitas"][0]["titulo"].startswith("Gerar arquivo de slides")


def teste_cancelar_durante_a_execucao_para_as_proximas_etapas(planilha_baguncada, cfg, monkeypatch):
    processar_arquivo(planilha_baguncada, cfg)
    sid = orquestrador.criar(cfg, "monte uma apresentação para a diretoria", "ger_analise", iniciar=False)
    feitas, original = [], ferramentas.executar

    def executar(nome, cfg_, **k):
        feitas.append(nome)
        if len(feitas) == 1:  # o dono cancela enquanto a 1ª etapa está rodando
            orquestrador.cancelar(cfg_, sid, "mudei de ideia")
        return original(nome, cfg_, **k)
    monkeypatch.setattr(ferramentas, "executar", executar)
    assert orquestrador.executar(cfg, sid) == "cancelada"
    s = Trabalho(cfg).solicitacao(sid)
    assert len(feitas) == 1 and s["estado"] == "cancelada"
    assert s["etapas"][0]["estado"] == "concluida"                     # a que estava rodando termina
    assert all(e["estado"] == "cancelada" for e in s["etapas"][1:])     # as próximas não começam


def teste_pedido_sem_arquivo_pede_esclarecimento(cfg):
    sid = orquestrador.criar(cfg, "verifique a planilha", "validacao", iniciar=False)
    assert Trabalho(cfg).solicitacao(sid)["estado"] == "aguardando_esclarecimento"


def teste_projeto_divide_em_tarefas(anexo, cfg):
    sid = orquestrador.criar(cfg, "projeto: verificar a planilha e depois publicar", "coord_engenharia", arquivo=anexo,
                             iniciar=False)
    p = Trabalho(cfg).solicitacao(sid)
    assert p["tipo"] == "projeto" and len(p["tarefas"]) == 2


def teste_transicao_invalida_e_filtros(cfg):
    tb = Trabalho(cfg)
    sid = tb.criar_solicitacao("tarefa", "x", "x", funcionario="dba", andar=1, prioridade="alta")
    with pytest.raises(ErroTransicao):
        tb.mudar_estado(sid, "concluida_parcialmente")
    assert [s["id"] for s in tb.listar(prioridade="alta", andar=1, dias=1)] == [sid]
    assert tb.listar(estado="concluida") == []


def teste_execucao_automatica_vira_solicitacao(planilha_baguncada, cfg):
    r = processar_arquivo(planilha_baguncada, cfg)
    sid = orquestrador.registrar_execucao_automatica(cfg, r)
    s = Trabalho(cfg).solicitacao(sid)
    assert s["origem"] == "automatica" and s["estado"] == "concluida" and s["artefatos"]


def teste_ferramenta_com_erro_vira_limitacao(cfg):
    r = ferramentas.executar("diagnosticar_planilha", cfg, arquivo="/nao/existe.xlsx")
    assert not r["ok"] and r["natureza"] == "limitacao"
    r = ferramentas.executar("consulta_sql", cfg, consulta="x.sql")
    assert not r["ok"] and "não está habilitado" in r["texto"]


def teste_ia_desligada_por_padrao_e_so_local(cfg):
    from robo import ia
    s = ia.status(cfg)
    assert not s["configurado"] and "Nenhum modelo" in s["motivo"]
    assert not ia.redigir(cfg, "resuma", "x")["ok"]
    cfg.dados["ia"] = {"provedor": "ollama", "url": "http://exemplo.com:11434", "modelo": "x"}
    assert "próprio computador" in ia.status(cfg)["motivo"]
