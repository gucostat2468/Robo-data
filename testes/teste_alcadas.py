"""Alçadas: com o dono fora, a liderança decide só o que a matriz permite — duas pessoas, prova, registro imutável e
reversão pelo dono. Com o dono presente, nada é decidido por ninguém além dele."""

import sqlite3
from datetime import date, datetime, timedelta

import pytest
from openpyxl import Workbook

from robo import alcadas, aprendizado, decisoes, organizacao, rh_desempenho as rh
from robo.pipeline import processar_arquivo

REGRA = {"padrao": "nps_*", "colunas_obrigatorias": ["id_resposta", "nota_nps"], "valores_permitidos": {"uf": ["SP", "RJ", "MG"]}}


@pytest.fixture
def cfg(cfg_factory):
    c = cfg_factory(regras=[REGRA], autonomia={"horas_pendente": 0})
    c.criar_pastas()
    return c


def _fora(cfg, horas=13):
    alcadas.marcar_presenca(cfg, "painel", datetime.now() - timedelta(hours=horas))


def _planilha(pasta, nome, cab_nota="Nota NPS Aluno", uf="SP"):
    wb = Workbook()
    ws = wb.active
    ws.append(["ID Resposta", cab_nota, "UF"])
    for i in range(1, 11):
        ws.append([i, i % 11, uf if i == 3 else "SP"])
    wb.save(pasta / nome)
    return pasta / nome


def _decisao_atrasada(cfg, dono="dev_junior"):
    d = decisoes.registrar(cfg, "Revisar a ronda de logs", dono, date.today() + timedelta(days=3), "ronda verde 3 dias",
                           5, "REU-T", vinculo=("handover", "H-T"))
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    c.execute("UPDATE decisoes SET prazo=? WHERE id=?", ((date.today() - timedelta(days=2)).isoformat(), d["id"]))
    c.commit()
    c.close()
    decisoes.atualizar(cfg)
    return d["id"]


def teste_presenca_do_dono(cfg):
    assert not alcadas.dono_offline(cfg)["offline"]              # sem registro nenhum não presume ausência
    _fora(cfg, 13)
    assert alcadas.dono_offline(cfg)["offline"]
    alcadas.marcar_presenca(cfg, "painel")
    off = alcadas.dono_offline(cfg)
    assert not off["offline"] and off["horas"] < 1
    assert alcadas.rodada(cfg)["decididas"] == []                # dono presente: ninguém decide no lugar dele


def teste_regra_de_baixo_risco_com_prova_e_duas_pessoas(cfg):
    r = processar_arquivo(_planilha(cfg.entrada, "nps_outubro.xlsx"), cfg)
    [pid] = aprendizado.propor(cfg, r)
    autor = aprendizado.listar(cfg)[0]["autor"]
    _fora(cfg)
    decisor, validador = alcadas.par_para(cfg, "proposta_regra", aprendizado.listar(cfg)[0])
    assert decisor and validador and len({decisor, validador, autor}) == 3
    # ninguém aprova a própria proposta, nem valida a própria decisão, nem usa um estagiário
    assert not alcadas.autoriza(cfg, "proposta_regra", pid, autor, validador)[0]
    assert not alcadas.autoriza(cfg, "proposta_regra", pid, decisor, decisor)[0]
    assert not alcadas.autoriza(cfg, "proposta_regra", pid, decisor, "eng_estagiario")[0]
    with pytest.raises(PermissionError):
        aprendizado.decidir(cfg, pid, True, quem=decisor)       # sem validador: recusado
    r = alcadas.rodada(cfg)
    [d] = r["decididas"]
    assert (d["decisor"], d["validador"]) == (decisor, validador)
    p = aprendizado.listar(cfg)[0]
    assert p["estado"] == "aprovada" and p["decidido_por"] == decisor
    assert processar_arquivo(cfg.entrada / "nps_outubro.xlsx", cfg).status == "sucesso"   # o comportamento mudou
    assert alcadas.rodada(cfg)["decididas"] == []                # idempotente
    reg = alcadas.listar(cfg)[0]
    assert reg["decisao"] == "aprovada_por_alcada" and reg["reversivel_ate"]
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("UPDATE alcadas_decisoes SET decisao='x'")
    c.close()
    # o dono reverte: a regra sai de vigor, a decisão original continua registrada
    with pytest.raises(PermissionError):
        alcadas.reverter(cfg, reg["id"], "não concordo", quem=decisor)
    alcadas.reverter(cfg, reg["id"], "prefiro decidir eu")
    assert aprendizado.regras_ativas(cfg, "nps_*") == {}
    assert [x["decisao"] for x in alcadas.listar(cfg)] == ["revertida_pelo_dono", "aprovada_por_alcada"]
    with pytest.raises(ValueError):
        alcadas.reverter(cfg, reg["id"], "de novo")


def teste_risco_medio_fica_para_o_dono(cfg):
    r = processar_arquivo(_planilha(cfg.entrada, "nps_a.xlsx", cab_nota="Nota NPS", uf="BA"), cfg)
    [pid] = aprendizado.propor(cfg, r)
    _fora(cfg)
    r = alcadas.rodada(cfg)
    assert r["decididas"] == [] and r["para_o_dono"][0]["item_id"] == pid
    assert aprendizado.listar(cfg)[0]["estado"] == "pendente"    # continua esperando o dono
    assert alcadas.rodada(cfg)["para_o_dono"] == []              # registra uma vez só
    aprendizado.decidir(cfg, pid, False, motivo="BA não é atendida")   # o dono decide depois, normalmente


def teste_decisao_atrasada_repactuada_uma_vez_pelo_gestor(cfg):
    did = _decisao_atrasada(cfg, "dev_junior")
    with pytest.raises(PermissionError):
        decisoes.repactuar(cfg, did, date.today() + timedelta(days=5), "motivo bem escrito", "R", quem="dev_pleno",
                           validador="coord_devops")             # dono presente? não há registro → não está fora
    _fora(cfg)
    with pytest.raises(PermissionError):                         # o próprio responsável não se dá mais prazo
        decisoes.repactuar(cfg, did, date.today() + timedelta(days=5), "motivo bem escrito", "R", quem="dev_junior",
                           validador="coord_devops")
    [d] = alcadas.rodada(cfg)["decididas"]
    assert d["decisor"] == organizacao.gestor_de("dev_junior") and d["validador"] not in ("dev_junior", d["decisor"])
    dec = decisoes.listar(cfg)[0]
    assert dec["estado"] == "em_andamento" and dec["prazo"] == (date.today() + timedelta(days=7)).isoformat()
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    c.execute("UPDATE decisoes SET prazo=? WHERE id=?", ((date.today() - timedelta(days=1)).isoformat(), did))
    c.commit()
    c.close()
    decisoes.atualizar(cfg)
    assert alcadas.rodada(cfg)["decididas"] == []                # só uma vez por decisão
    alc = next(x for x in alcadas.listar(cfg) if x["decisao"] == "aprovada_por_alcada")
    alcadas.reverter(cfg, alc["id"], "o prazo era esse mesmo")
    assert any(e["tipo"] == "repactuacao_revertida" for e in decisoes.eventos(cfg, did))


def teste_promocao_que_esperava_o_dono(cfg):
    rh._tb(cfg)
    velho = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    for pid, de, para in (("dev_junior", "junior", "pleno"), ("eng_estagiario", "estagiario", "junior")):
        c.execute("INSERT INTO rh_movimentos (data_hora, funcionario, tipo, de_nivel, para_nivel, motivo, evidencia, "
                  "proposto_por, situacao) VALUES (?,?,?,?,?,?,?,?,?)",
                  (velho, pid, "promocao", de, para, "teste", "{}", "rh_desempenho", "aguardando_dono"))
    c.commit()
    c.close()
    _fora(cfg)
    r = alcadas.rodada(cfg)
    [d] = r["decididas"]
    assert d["item_tipo"] == "rh_promocao" and d["decisor"] == "head_rh" and d["validador"] not in ("head_rh", "dev_junior")
    assert organizacao.nivel_de("dev_junior", organizacao.por_id(cfg)["dev_junior"]) == "pleno"
    [fica] = r["para_o_dono"]                                    # estagiário → júnior nunca por alçada
    assert fica["item_tipo"] == "rh_promocao_do_dono"
    assert organizacao.nivel_de("eng_estagiario", organizacao.por_id(cfg)["eng_estagiario"]) == "estagiario"
    alcadas.reverter(cfg, d["alcada"], "quero conversar antes")
    assert organizacao.nivel_de("dev_junior", organizacao.por_id(cfg)["dev_junior"]) == "junior"


def teste_fora_da_matriz_e_desligada(cfg_factory):
    cfg = cfg_factory(autonomia={"habilitada": False})
    cfg.criar_pastas()
    _fora(cfg)
    assert alcadas.autoriza(cfg, "aprovacoes", "A1", "head_rh", "dir_pessoas")[0] is False
    assert alcadas.rodada(cfg)["decididas"] == []
    assert not alcadas.MATRIZ["permissoes_seguranca_configuracao"][1] and not alcadas.MATRIZ["rh_desligamento"][1]
