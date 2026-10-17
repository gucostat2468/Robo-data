"""Quadro de pessoal: todo andar lotado e toda conferência com efeito real no fluxo."""

from pathlib import Path

from conftest import REGRA_NPS
from robo import quadro, rh
from robo.pipeline import REPROVADO, SUCESSO, processar_arquivo

NIVEIS_OBRIGATORIOS = ["gerente", "coordenador", "pleno", "junior", "estagiario"]


def teste_todo_andar_tem_do_gerente_ao_estagiario():
    for andar, niveis in quadro.lotacao().items():
        for n in NIVEIS_OBRIGATORIOS:
            assert niveis.get(n), f"{andar}º andar sem {n}"
        assert niveis.get("senior") or niveis.get("especialista"), f"{andar}º andar sem sênior/especialista"


def teste_todo_cargo_do_quadro_passou_no_rh_com_escopo_definido():
    for p in quadro.QUADRO:
        f = rh.ficha({"id": p["id"], "habilidades": []})
        assert f["provas"]["aprovado"] and f["provas"]["total"] >= 2, (p["id"], f["provas"]["bloqueios"])
        assert f["responsabilidades"] and f["criterios"] and f["limites"] and f["gestor"], p["id"]


def teste_junior_do_primeiro_andar_bloqueia_publicacao(planilha_baguncada, cfg_factory, monkeypatch):
    monkeypatch.setitem(quadro.POR_ID["eng_junior_espacos"], "funcao", lambda c: ["texto com espaço sobrando (simulado)"])
    cfg = cfg_factory([REGRA_NPS])
    r = processar_arquivo(planilha_baguncada, cfg)
    assert r.status == REPROVADO
    assert any("Bruno" in o.mensagem for o in r.relatorio.erros)
    assert not list(cfg.tratadas.glob("*.xlsx"))


def teste_estagiario_so_observa(planilha_baguncada, cfg_factory, monkeypatch):
    monkeypatch.setitem(quadro.POR_ID["eng_estagiario"], "funcao", lambda c: ["chave não rastreada (simulado)"])
    r = processar_arquivo(planilha_baguncada, cfg_factory([REGRA_NPS]))
    assert r.status == SUCESSO
    assert any("Em observação" in o.mensagem and "Théo" in o.mensagem for o in r.relatorio.avisos)


def teste_releitura_divergente_desfaz_publicacao(planilha_baguncada, cfg_factory, monkeypatch):
    monkeypatch.setitem(quadro.POR_ID["eng_pleno_releitura"], "funcao", lambda c: ["arquivo gravado com 1 linha a menos (simulado)"])
    cfg = cfg_factory([REGRA_NPS])
    r = processar_arquivo(planilha_baguncada, cfg)
    assert r.status == REPROVADO
    assert not list(cfg.tratadas.glob("nps_outubro*.xlsx")), "arquivo divergente não pode ficar publicado"
    assert list(cfg.erros.glob("*nps_outubro*_ERROS.txt"))


def teste_conferencia_que_quebra_nao_vira_aprovacao(planilha_baguncada, cfg_factory, monkeypatch):
    def quebra(c):
        raise ValueError("bug")
    monkeypatch.setitem(quadro.POR_ID["eng_pleno_tipos"], "funcao", quebra)
    r = processar_arquivo(planilha_baguncada, cfg_factory([REGRA_NPS]))
    assert r.status == REPROVADO
    assert any("não consegui concluir" in o.mensagem for o in r.relatorio.erros)


def teste_catalogo_de_dados_atualizado(planilha_baguncada, cfg_factory):
    cfg = cfg_factory([REGRA_NPS])
    processar_arquivo(planilha_baguncada, cfg)
    import json
    catalogo = json.loads((Path(cfg.logs) / "catalogo_dados.json").read_text(encoding="utf-8"))
    assert any(v["ultimo_arquivo"] == "nps_outubro.xlsx" and v["linhas"] == 4 for v in catalogo.values()), catalogo.keys()
