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
    r = processar_arquivo(_planilha(cfg.entrada, "nps_b.xlsx", cab_nota="Nota NPS", uf="Sp."), cfg)
    aprendizado.propor(cfg, r)
    assert "erro de digitação" in aprendizado.listar(cfg, "pendente")[0]["alerta"]
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DELETE FROM propostas_regra")
    c.close()
