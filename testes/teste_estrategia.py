"""Central de dados e estratégia: números reais, backlog que nasce e morre com os dados, avaliações e trilhas."""

from conftest import REGRA_NPS
from robo import central, estrategia
from robo.pipeline import processar_arquivo


def teste_central_conta_acertos_e_erradas(planilha_baguncada, cfg_factory, pastas):
    cfg = cfg_factory([REGRA_NPS])
    processar_arquivo(planilha_baguncada, cfg)
    (pastas / "Bases-Limpeza" / "nps_quebrado.xlsx").write_bytes(b"corrompido" * 20)
    processar_arquivo(pastas / "Bases-Limpeza" / "nps_quebrado.xlsx", cfg)
    c = central.montar(cfg, 1)
    assert c["totais"]["recebidos"] == 2 and c["totais"]["aprovados"] == 1 and c["totais"]["reprovados"] == 1
    assert c["erradas"][0]["arquivo"] == "nps_quebrado.xlsx" and c["erradas"][0]["quem_barrou"] == "Leitura"
    assert c["serie"][-1] == {"dia": c["serie"][-1]["dia"], "aprovados": 1, "reprovados": 1}


def teste_backlog_nasce_dos_dados_e_fecha_sozinho(pastas, cfg_factory):
    cfg = cfg_factory()
    for i in range(2):
        (pastas / "Bases-Limpeza" / f"quebrado_{i}.xlsx").write_bytes(b"x" * 100)
        processar_arquivo(pastas / "Bases-Limpeza" / f"quebrado_{i}.xlsx", cfg)
    estrategia.sincronizar(cfg)
    erro = [i for i in estrategia.ler_backlog(cfg) if i["chave"].startswith("erro:")]
    assert erro and erro[0]["status"] == "a_fazer" and erro[0]["prioridade"] > 0
    # sem as reprovações (histórico limpo), o item se fecha sozinho com a observação
    from robo import historico
    historico.arquivo_historico(cfg.logs).unlink()
    estrategia.sincronizar(cfg)
    item = next(i for i in estrategia.ler_backlog(cfg) if i["id"] == erro[0]["id"])
    assert item["status"] == "feito" and item["resolvido_sozinho"]


def teste_prioridade_do_dono_e_alinhamento(cfg_factory):
    cfg = cfg_factory()
    item = estrategia.salvar_item(cfg, {"titulo": "Padronizar nomes", "andar": 2, "impacto": 5, "urgencia": 4, "esforco": 2,
                                        "responsavel": "ger_analise"})
    assert item["prioridade"] == 10.0
    estrategia.salvar_item(cfg, {"id": item["id"], "status": "fazendo"})
    andar2 = next(a for a in estrategia.alinhamento(cfg) if a["andar"] == 2)
    assert andar2["gerente"] == "Patrícia" and andar2["prioridades"][0]["status"] == "Fazendo"


def teste_avaliacao_tecnica_de_todo_o_quadro(cfg_factory):
    cfg = cfg_factory()
    r = estrategia.avaliar_todos(cfg)
    assert r["total"] >= 50 and r["aprovados"] == r["total"]
    assert estrategia.ler_avaliacoes(cfg)[-1]["total"] == r["total"]


def teste_trilhas_por_pessoa(cfg_factory):
    cfg = cfg_factory()
    estrategia.treinar_todos(cfg)
    leo = next(t for t in estrategia.trilhas(cfg) if t["id"] == "leitura")
    assert leo["total"] >= 5 and leo["dominados"] == leo["total"]
