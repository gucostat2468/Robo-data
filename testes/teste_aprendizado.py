"""Aprendizado operacional: o erro vira proposta, o dono aprova, a regra muda o comportamento e há prova."""

import sqlite3

import pytest
from openpyxl import Workbook

from robo import aprendizado, licoes
from robo.pipeline import processar_arquivo

REGRA = {"padrao": "nps_*", "colunas_obrigatorias": ["id_resposta", "nota_nps"], "valores_permitidos": {"uf": ["SP", "RJ", "MG"]}}


def _planilha(pasta, nome, cab_nota="Nota NPS Aluno", uf="SP"):
    wb = Workbook()
    ws = wb.active
    ws.append(["ID Resposta", cab_nota, "UF"])
    for i in range(1, 11):
        ws.append([i, i % 11, uf if i == 3 else "SP"])
    caminho = pasta / nome
    wb.save(caminho)
    return caminho


@pytest.fixture
def cfg(cfg_factory):
    c = cfg_factory(regras=[REGRA])
    c.criar_pastas()
    return c


def teste_coluna_com_outro_nome_vira_regra_aprovada_e_comprovada(cfg):
    r = processar_arquivo(_planilha(cfg.entrada, "nps_outubro.xlsx"), cfg)
    assert r.status == "reprovado"
    [pid] = aprendizado.propor(cfg, r)
    p = aprendizado.listar(cfg)[0]
    assert p["tipo"] == "sinonimo" and p["coluna"] == "nota_nps" and p["valor"] == "nota_nps_aluno" and p["estado"] == "pendente"
    assert aprendizado.propor(cfg, r) == []                   # não duplica
    with pytest.raises(PermissionError):
        aprendizado.decidir(cfg, pid, True, quem=p["autor"])  # ninguém aprova a própria proposta
    d = aprendizado.decidir(cfg, pid, True)
    assert d["reenviado"] == "nps_outubro.xlsx" and (cfg.entrada / "nps_outubro.xlsx").exists()
    # o comportamento mudou: o MESMO arquivo agora passa, e isso é a prova
    r2 = processar_arquivo(cfg.entrada / "nps_outubro.xlsx", cfg)
    assert r2.status == "sucesso"
    assert aprendizado.comprovar(cfg, r2) == [pid]
    assert aprendizado.listar(cfg)[0]["estado"] == "comprovada"
    # e um arquivo NOVO do mês seguinte, com o mesmo nome de coluna, já passa direto
    assert processar_arquivo(_planilha(cfg.entrada, "nps_novembro.xlsx"), cfg).status == "sucesso"
    # a lição da regra só vira 'aplicada' com essa prova
    licoes.rodada(cfg)
    lic = next(l for l in licoes.caderno(cfg, p["autor"])["licoes"] if l["origem_tipo"] == "regra")
    assert lic["estado"] == "aplicada" and "aprovada depois da regra" in lic["evidencia"]


def teste_valor_novo_exige_decisao_e_aviso_de_digitacao(cfg):
    r = processar_arquivo(_planilha(cfg.entrada, "nps_a.xlsx", cab_nota="Nota NPS", uf="BA"), cfg)
    [pid] = aprendizado.propor(cfg, r)
    assert aprendizado.listar(cfg)[0]["valor"] == "BA" and not aprendizado.listar(cfg)[0]["alerta"]
    with pytest.raises(ValueError):
        aprendizado.decidir(cfg, pid, False)                  # recusar exige motivo
    aprendizado.decidir(cfg, pid, False, motivo="BA não é atendida")
    assert aprendizado.regras_ativas(cfg, "nps_*") == {}      # recusada não muda nada
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DELETE FROM propostas_regra")
    c.close()


def teste_valor_parecido_vira_correcao_de_valor_e_o_arquivo_passa(cfg):
    r = processar_arquivo(_planilha(cfg.entrada, "nps_b.xlsx", cab_nota="Nota NPS", uf="Sp."), cfg)
    assert r.status == "reprovado"
    [pid] = aprendizado.propor(cfg, r)
    p = aprendizado.listar(cfg, "pendente")[0]
    # parecido com um permitido → CORRIGIR (não ampliar a lista com um erro de digitação)
    assert p["tipo"] == "mapeamento" and p["valor"] == "Sp." and p["para"] == "SP" and "recuse" in p["alerta"]
    aprendizado.decidir(cfg, pid, True)
    assert aprendizado.regras_ativas(cfg, "nps_*") == {"mapear_valores": {"uf": {"Sp.": "SP"}}}
    r2 = processar_arquivo(cfg.entrada / "nps_b.xlsx", cfg)
    assert r2.status == "sucesso"
    corr = [o for o in r2.relatorio.ocorrencias if o.mensagem == "Valores corrigidos pela regra (mapear_valores)"]
    assert corr and corr[0].quantidade == 1 and "'Sp.' → 'SP'" in corr[0].exemplos[0]
    assert aprendizado.comprovar(cfg, r2) == [pid] and aprendizado.listar(cfg)[0]["estado"] == "comprovada"


def teste_valor_sem_parecido_continua_sendo_valor_permitido():
    assert aprendizado._parecido("BA", ["SP", "RJ", "MG"]) is None
    assert aprendizado._parecido("Sao Paolo", ["São Paulo", "Rio"]) == "São Paulo"
    assert aprendizado._parecido("s.p", ["SP"]) == "SP"


def teste_regra_que_nao_resolveu_e_desativada_sozinha(cfg):
    r = processar_arquivo(_planilha(cfg.entrada, "nps_c.xlsx", cab_nota="Nota NPS", uf="Sp."), cfg)
    [pid] = aprendizado.propor(cfg, r)
    aprendizado.decidir(cfg, pid, True)
    # o arquivo voltou a reprovar PELO MESMO MOTIVO → não resolveu → a regra sai de vigor, com o registro
    assert aprendizado.comprovar(cfg, r) == [pid]
    p = aprendizado.listar(cfg)[0]
    assert p["estado"] == "nao_resolveu" and p["ativa"] == 0 and p["desativada_por"] == "sistema"
    assert aprendizado.regras_ativas(cfg, "nps_*") == {}
    with pytest.raises(ValueError):
        aprendizado.desativar(cfg, pid, "dono", "de novo")   # já desativada


def teste_so_o_dono_desativa_e_com_motivo(cfg):
    r = processar_arquivo(_planilha(cfg.entrada, "nps_d.xlsx"), cfg)
    [pid] = aprendizado.propor(cfg, r)
    aprendizado.decidir(cfg, pid, True)
    p = aprendizado.listar(cfg)[0]
    with pytest.raises(PermissionError):
        aprendizado.desativar(cfg, pid, p["autor"], "eu mesmo")
    with pytest.raises(ValueError):
        aprendizado.desativar(cfg, pid, "dono", " ")
    aprendizado.desativar(cfg, pid, "dono", "a pesquisa mudou de layout")
    assert aprendizado.regras_ativas(cfg, "nps_*") == {} and aprendizado.listar(cfg)[0]["motivo_desativacao"]
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DELETE FROM regras_aprendidas")             # desativa, nunca apaga
    c.close()


def teste_config_prevalece_sobre_correcao_aprendida():
    nova = aprendizado.aplicar_overlay({"mapear_valores": {"uf": {"Sp.": "SP"}}},
                                       {"mapear_valores": {"uf": {"Sp.": "RJ", "S.P": "SP"}}})
    assert nova["mapear_valores"]["uf"] == {"Sp.": "SP", "S.P": "SP"}
