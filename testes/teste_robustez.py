"""Robustez de operação: nada se perde e nada trava, mesmo com arquivos abertos ou configuração errada."""

import shutil
from unittest import mock

from conftest import REGRA_NPS
from robo import historico, quadro
from robo.pipeline import REPROVADO, SUCESSO, processar_arquivo


def teste_historico_aberto_no_excel_vai_para_fila_e_volta(tmp_path):
    historico.registrar(tmp_path, {"arquivo": "a.xlsx", "status": "sucesso", "id": "1"})
    real_open = open

    def bloqueia(arquivo, modo="r", *a, **k):
        if str(arquivo).endswith("historico_processamentos.csv") and "a" in modo:
            raise PermissionError("aberto no Excel")
        return real_open(arquivo, modo, *a, **k)
    with mock.patch("builtins.open", bloqueia):
        historico.registrar(tmp_path, {"arquivo": "b.xlsx", "status": "sucesso", "id": "2"})
    assert [l["arquivo"] for l in historico.ler(tmp_path)] == ["b.xlsx", "a.xlsx"], "pendente aparece no painel"
    historico.registrar(tmp_path, {"arquivo": "c.xlsx", "status": "sucesso", "id": "3"})
    assert not (tmp_path / "historico_pendente.jsonl").exists()
    assert [l["arquivo"] for l in historico.ler(tmp_path)] == ["c.xlsx", "b.xlsx", "a.xlsx"]


def teste_republicacao_reprovada_mantem_a_versao_anterior(planilha_baguncada, cfg_factory, monkeypatch, pastas):
    cfg = cfg_factory([REGRA_NPS])
    copia = pastas / "copia.xlsx"
    shutil.copy(planilha_baguncada, copia)
    assert processar_arquivo(planilha_baguncada, cfg).status == SUCESSO
    publicado = cfg.tratadas / "nps_outubro.xlsx"
    conteudo_bom = publicado.read_bytes()
    monkeypatch.setitem(quadro.POR_ID["eng_pleno_releitura"], "funcao", lambda c: ["linha a menos (simulado)"])
    shutil.copy(copia, pastas / "Bases-Limpeza" / "nps_outubro.xlsx")
    assert processar_arquivo(pastas / "Bases-Limpeza" / "nps_outubro.xlsx", cfg).status == REPROVADO
    assert publicado.exists() and publicado.read_bytes() == conteudo_bom, "a versão boa anterior precisa continuar lá"


def teste_formato_de_saida_invalido_reprova_sem_travar(planilha_baguncada, cfg_factory):
    r = processar_arquivo(planilha_baguncada, cfg_factory([REGRA_NPS], saida={"formato": "xls"}))
    assert r.status == REPROVADO
    assert any("Formato de saída inválido" in o.mensagem for o in r.relatorio.erros)
    assert not planilha_baguncada.exists(), "o arquivo sai da entrada (não fica em laço)"
