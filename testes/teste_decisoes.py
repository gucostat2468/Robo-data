"""Reunião levada a sério: decisão tem dono, prazo e critério; é cobrada até ser cumprida; atrasada não passa em branco."""

import sqlite3
from datetime import date, timedelta

import pytest

from robo import decisoes, sala
from robo.trabalho import Trabalho


@pytest.fixture
def cfg(cfg_factory):
    c = cfg_factory()
    c.criar_pastas()
    return c


def _em(dias: int) -> str:
    return (date.today() + timedelta(days=dias)).isoformat()


@pytest.mark.parametrize("texto,dono,prazo,criterio,erro", [
    ("ver isso", "limpeza", 7, "duas cargas sem erro", "vaga"),
    ("padronizar as datas da base de vendas", "ninguem", 7, "duas cargas sem erro", "dono"),
    ("padronizar as datas da base de vendas", "limpeza", -1, "duas cargas sem erro", "passado"),
    ("padronizar as datas da base de vendas", "limpeza", 400, "duas cargas sem erro", "longo"),
    ("padronizar as datas da base de vendas", "limpeza", 7, "ok", "critério"),
])
def teste_decisao_vaga_ou_incompleta_e_recusada(cfg, texto, dono, prazo, criterio, erro):
    with pytest.raises(ValueError, match=erro):
        decisoes.registrar(cfg, texto, dono, _em(prazo), criterio, 1, "R1")


def teste_reuniao_cobra_atrasada_e_nao_encerra_sem_tratar(cfg):
    r1 = sala.abrir(cfg, 1)
    d = sala.decidir(cfg, r1["conversa_id"], "padronizar a coluna de data da base de vendas", "limpeza", _em(3),
                     "duas cargas seguidas sem aviso de data em texto")
    sala.encerrar(cfg, r1["conversa_id"])
    # o prazo passa sem a tarefa ser concluída: a situação é apurada pelos registros, não declarada
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    c.execute("UPDATE decisoes SET prazo=? WHERE id=?", (_em(-2), d["decisao"]))
    c.commit()
    c.close()
    r2 = sala.abrir(cfg, 1)
    cid = r2["conversa_id"]
    det = sala.detalhes(cfg, cid)
    assert any("Pendências das reuniões anteriores" in m["texto"] and d["decisao"] in m["texto"] for m in det["mensagens"])
    assert det["decisoes_pendentes"][0]["estado"] == "atrasada"
    coord = next(m for m in r2["maos"] if m["id"] == "coord_engenharia")
    assert "1 decisão(ões) atrasada(s)" in coord["motivo"]
    with pytest.raises(ValueError, match="atrasada"):
        sala.encerrar(cfg, cid)  # não fecha com pendência atrasada sem tratamento
    with pytest.raises(PermissionError):
        decisoes.repactuar(cfg, d["decisao"], _em(10), "a fonte atrasou o envio", cid, quem="limpeza")  # só você
    sala.repactuar(cfg, cid, d["decisao"], _em(10), "a fonte atrasou o envio dos arquivos")
    fim = sala.encerrar(cfg, cid)
    assert any(d["decisao"] in x and "repactuada" in x for x in fim["recap"]["pendencias_tratadas"])
    assert len(fim["recap"]["ata_sha256"]) == 64
    tipos = [e["tipo"] for e in decisoes.eventos(cfg, d["decisao"])]
    assert tipos == ["criada", "situacao", "cobrada", "repactuada"]


def teste_encerrar_com_pendencia_exige_justificativa_registrada(cfg):
    r = sala.abrir(cfg, 2)
    d = decisoes.registrar(cfg, "recalcular o NPS da pesquisa de professores", "analise_estatistica", _em(1),
                           "NPS conferido no PostgreSQL", 2, "R0")
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    c.execute("UPDATE decisoes SET prazo=? WHERE id=?", (_em(-1), d["id"]))
    c.commit()
    c.close()
    with pytest.raises(ValueError):
        sala.encerrar(cfg, r["conversa_id"], "curta")
    fim = sala.encerrar(cfg, r["conversa_id"], "dono ausente hoje; cobrar na próxima reunião sem falta")
    assert fim["recap"]["pendencias_sem_tratamento"] and "dono ausente" in fim["recap"]["justificativa"]
    assert [e["tipo"] for e in decisoes.eventos(cfg, d["id"])][-1] == "nao_tratada"


def teste_cumprida_so_com_a_tarefa_concluida_e_revisada(cfg, monkeypatch):
    r = sala.abrir(cfg, 1)
    d = sala.decidir(cfg, r["conversa_id"], "padronizar a coluna de data da base de vendas", "limpeza", _em(5),
                     "duas cargas seguidas sem aviso de data em texto")
    decisoes.atualizar(cfg)
    assert decisoes.listar(cfg, 1)[0]["estado"] == "em_andamento"
    tb = Trabalho(cfg)
    real = tb.solicitacao
    monkeypatch.setattr(Trabalho, "solicitacao", lambda self, sid: {**real(sid), "estado": "concluida", "estado_nome": "Concluída",
                                                                    "revisao": {"revisor": "coord_engenharia"}})
    decisoes.atualizar(cfg)
    x = decisoes.listar(cfg, 1)[0]
    assert x["estado"] == "cumprida" and "revisada por coord_engenharia" in x["evidencia"]
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("UPDATE decisoes_eventos SET detalhe='x'")
    c.execute("INSERT INTO decisoes_eventos (decisao_id, tipo) VALUES ('x', 'y')")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DELETE FROM decisoes_eventos")
    c.close()


def teste_plano_da_semanal_vira_decisao_ligada_ao_handover(cfg, planilha_baguncada):
    from conftest import REGRA_NPS
    from robo import memoria, reuniao
    from robo.pipeline import processar_arquivo
    c2 = type(cfg)({**cfg.dados, "regras": [{**REGRA_NPS, "valores_permitidos": {"uf": ["SP"]}}]}, cfg.base)
    memoria.registrar_execucao(c2, processar_arquivo(planilha_baguncada, c2))
    reuniao.gerar(c2)
    ds = [d for d in decisoes.listar(c2) if d["origem"] == "semanal"]
    assert ds and all(d["vinculo_tipo"] == "handover" and d["vinculo_id"].startswith("HO-") for d in ds)
    from datetime import datetime
    reuniao.gerar(c2, ate=datetime.now() + timedelta(days=7))  # a semanal seguinte não duplica a mesma pendência
    assert len([d for d in decisoes.listar(c2) if d["origem"] == "semanal"]) == len(ds)
