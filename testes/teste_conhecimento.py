"""Caderno de lições (conhecimento permanente com governança) e registro permanente de erros de sistema."""

import logging
import sqlite3

import pytest

from conftest import REGRA_NPS
from robo import erros, laboratorio, licoes, memoria
from robo.pipeline import processar_arquivo


@pytest.fixture
def cfg(planilha_baguncada, cfg_factory):
    return cfg_factory(regras=[REGRA_NPS])


def _banco(cfg):
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    c.row_factory = sqlite3.Row
    return c


def teste_colheita_vira_licao_para_o_andar(cfg):
    hid = memoria.handover(cfg, "Coluna de data com texto misturado", "limpeza", "limpeza", "teste")
    r = licoes.colher(cfg)
    assert r["handover"] >= 1 and r["manual"] >= 1  # conhecimento/*.md também vira lição
    assert licoes.colher(cfg)["handover"] == 0      # idempotente: não duplica
    lic = next(l for l in licoes.buscar(cfg, "coluna data texto misturado") if l["origem_ref"] == hid)
    cad = licoes.caderno(cfg, "limpeza")
    assert any(l["licao_id"] == lic["id"] for l in cad["licoes"])
    # o andar inteiro recebe (Engenharia de Dados), não só o responsável
    assert any(l["licao_id"] == lic["id"] for l in licoes.caderno(cfg, "leitura")["licoes"])


def teste_ciclo_estudada_avaliada_aplicada_sem_mentira(cfg):
    memoria.handover(cfg, "Coluna de data com texto misturado", "limpeza", "limpeza", "teste")
    r = licoes.rodada(cfg)
    assert r["estudada"] > 0 and r["integridade"]["integra"]
    cad = licoes.caderno(cfg, "limpeza")
    h = next(l for l in cad["licoes"] if l["origem_tipo"] == "handover")
    assert h["estado"] == "avaliada"  # o handover ainda não foi verificado: NÃO pode virar "aplicada"
    # manual também não vira "aplicada" só por existir: precisa ser USADO numa resposta por aquela pessoa
    assert not any(l["estado"] == "aplicada" for l in cad["licoes"] if l["origem_tipo"] == "manual")
    from robo import ferramentas
    usada = ferramentas.executar("conhecimento", cfg, pergunta="quais as boas práticas de ingestão na engenharia de dados?",
                                 quem="limpeza")
    assert usada["ok"] and "boas_praticas.md" in usada["evidencia"]
    licoes.rodada(cfg)
    cad = {l["licao_id"]: l for l in licoes.caderno(cfg, "limpeza")["licoes"]}
    lid = next(k for k, l in cad.items() if l["titulo"].startswith("Engenharia de dados: ingestão"))
    assert cad[lid]["estado"] == "aplicada" and "usada numa resposta" in cad[lid]["evidencia"]
    assert licoes.verificar_integridade(cfg)["integra"]


def teste_falha_do_laboratorio_so_vira_aplicada_quando_o_caso_passa(cfg, monkeypatch):
    from robo import ciencia
    original = ciencia.drivers
    monkeypatch.setattr(ciencia, "drivers", lambda df, alvo: {"ok": True, "drivers": [{"atributo": "ctr"}]})
    laboratorio.exercicio(cfg, "marketing", 3)
    licoes.rodada(cfg)
    lab = [l for l in licoes.caderno(cfg, "cd_senior_drivers")["licoes"] if l["origem_tipo"] == "laboratorio"]
    assert lab and all(l["estado"] != "aplicada" for l in lab)
    monkeypatch.setattr(ciencia, "drivers", original)  # "corrigiu" o código → o mesmo caso refeito passa
    licoes.rodada(cfg)
    lab = [l for l in licoes.caderno(cfg, "cd_senior_drivers")["licoes"] if l["origem_tipo"] == "laboratorio"]
    assert all(l["estado"] == "aplicada" and "passou" in l["evidencia"] for l in lab)


def teste_nada_e_apagado_e_adulteracao_e_detectada(cfg):
    licoes.colher(cfg)
    c = _banco(cfg)
    for sql in ["DELETE FROM licoes", "DELETE FROM licoes_funcionario", "DELETE FROM registro_conhecimento",
                "UPDATE licoes SET conteudo='x'", "UPDATE registro_conhecimento SET quem='x'"]:
        with pytest.raises(sqlite3.DatabaseError):
            c.execute(sql)
    c.rollback()
    assert licoes.verificar_integridade(cfg)["integra"]
    # alguém derruba o gatilho e mexe na cadeia por fora → a verificação acusa
    c.execute("DROP TRIGGER registro_sem_alterar")
    c.execute("UPDATE registro_conhecimento SET quem='intruso' WHERE id=2")
    c.commit()
    c.close()
    v = licoes.verificar_integridade(cfg)
    assert not v["integra"] and v["quebra_em"] == 2


def teste_so_o_dono_versiona_e_arquiva(cfg):
    licoes.colher(cfg)
    lid = licoes.painel(cfg)["recentes"][0]["id"]
    with pytest.raises(PermissionError):
        licoes.nova_versao(cfg, lid, "texto novo", "melhorar", quem="coord_engenharia")
    with pytest.raises(PermissionError):
        licoes.arquivar(cfg, lid, "não serve", quem="head_engenharia")
    nid = licoes.nova_versao(cfg, lid, "texto novo e corrigido", "estava incompleto")
    c = _banco(cfg)
    antiga, nova = (c.execute("SELECT * FROM licoes WHERE id=?", (i,)).fetchone() for i in (lid, nid))
    assert antiga["arquivada"] == 1 and antiga["conteudo"] != "texto novo e corrigido"  # a antiga continua guardada
    assert nova["versao"] == 2 and nova["substitui"] == lid
    assert licoes.exportar(cfg).read_text(encoding="utf-8").count(nid) >= 1


def teste_erro_de_sistema_fica_registrado_para_sempre(cfg):
    erros.instalar(cfg)
    log = logging.getLogger("robo.teste")
    for _ in range(3):
        try:
            1 / 0
        except ZeroDivisionError:
            log.exception("falha ao somar 12 linhas")
    lista = erros.listar(cfg)
    assert len(lista) == 1 and lista[0]["ocorrencias"] == 3 and "ZeroDivisionError" in lista[0]["traceback_ultimo"]
    assert any("Falha inesperada no código" in h["erro"] for h in memoria.handovers(cfg))
    c = _banco(cfg)
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DELETE FROM erros_sistema")
    c.close()
    erros.marcar_resolvido(cfg, lista[0]["id"])
    try:
        1 / 0
    except ZeroDivisionError:
        log.exception("falha ao somar 99 linhas")  # voltou → reabre
    assert erros.listar(cfg)[0]["estado"] == "reaberto"
    logging.getLogger("robo").removeHandler(erros._instalado.pop(str(cfg.logs)))


def teste_estudo_aplica_licoes(planilha_baguncada, cfg):
    from robo import desenvolvimento
    memoria.registrar_execucao(cfg, processar_arquivo(planilha_baguncada, cfg))
    r = desenvolvimento.estudar(cfg, anunciar=False)
    assert r["licoes"]["integridade"]["integra"] and r["licoes"]["estudada"] > 0


def teste_ancora_pega_fim_apagado_e_estado_forjado(cfg):
    licoes.rodada(cfg)
    licoes.exportar(cfg)  # grava a âncora fora do banco
    c = _banco(cfg)
    # forjar um estado sem passar pela cadeia
    c.execute("UPDATE licoes_funcionario SET estado='aplicada' WHERE rowid=(SELECT rowid FROM licoes_funcionario "
              "WHERE estado<>'aplicada' LIMIT 1)")
    c.commit()
    v = licoes.verificar_integridade(cfg)
    assert not v["integra"] and "sem registro na cadeia" in v["motivo"]
    # apagar o fim da cadeia (derrubando o gatilho): a âncora denuncia
    c.execute("DROP TRIGGER registro_sem_apagar")
    c.execute("DELETE FROM registro_conhecimento WHERE id=(SELECT MAX(id) FROM registro_conhecimento)")
    c.commit()
    c.close()
    v = licoes.verificar_integridade(cfg)
    assert not v["integra"] and "âncora" in v["motivo"]


def teste_reconferencia_do_laboratorio_nao_grava_nada(cfg):
    laboratorio.exercicio(cfg, "varejo", 5)  # cria as tabelas (e um treino normal, que grava)
    c = _banco(cfg)
    antes = lambda t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] if c.execute(
        "SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone() else 0
    n = {t: antes(t) for t in ("laboratorio_exercicios", "experiencias", "handovers")}
    r = laboratorio.exercicio(cfg, "varejo", 7, gravar=False, biblioteca="numpy")
    assert r["resultados"] and any("numpy" in x["etapa"] for x in r["resultados"])
    assert {t: antes(t) for t in n} == n
    c.close()


def teste_funcionario_novo_recebe_licoes_antigas(cfg):
    from robo import organizacao
    licoes.rodada(cfg)
    real = organizacao.lista

    def com_novato(c=None, com_contratados=True):
        return real(c, com_contratados) + [{"id": "novato_x", "nome": "Novato", "andar": 1, "papel": "Analista"}]
    import robo.organizacao as org
    org.lista = com_novato
    try:
        r = licoes.rodada(cfg)
    finally:
        org.lista = real
    assert r["novas"]["atribuicoes_novas"] > 0 and licoes.caderno(cfg, "novato_x")["total"] > 0
    assert licoes.verificar_integridade(cfg)["integra"]
