"""Histórico de processamentos.

- logs/historico_processamentos.csv : uma linha por arquivo processado (fácil de abrir no Excel/Power BI)
- logs/execucoes/<id>.json          : detalhe completo de cada processamento (usado pelo painel)

O <id> é o mesmo nome (sem extensão) que o arquivo original recebe em Bases-Originais/Bases-Erros,
por exemplo "20261014_093012_nps_outubro". Assim o painel liga o arquivo ao seu relatório.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

CABECALHO = ["data_hora", "arquivo", "status", "linhas_entrada", "linhas_saida", "erros", "avisos",
             "duracao_seg", "saidas", "id"]


def arquivo_historico(pasta_logs: Path) -> Path:
    return pasta_logs / "historico_processamentos.csv"


def pasta_execucoes(pasta_logs: Path) -> Path:
    return pasta_logs / "execucoes"


def registrar(pasta_logs: Path, linha: dict) -> None:
    pasta_logs.mkdir(parents=True, exist_ok=True)
    arquivo = arquivo_historico(pasta_logs)
    if arquivo.exists():
        with open(arquivo, encoding="utf-8-sig") as f:
            cabecalho_atual = f.readline().strip().split(";")
        if cabecalho_atual != CABECALHO:  # versão antiga do histórico: guarda e começa um novo
            arquivo.rename(arquivo.with_name(f"historico_antigo_{datetime.now():%Y%m%d_%H%M%S}.csv"))
    novo = not arquivo.exists()
    with open(arquivo, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(CABECALHO)
        w.writerow([linha.get(c, "") for c in CABECALHO])


def ler(pasta_logs: Path, limite: int | None = None) -> list[dict]:
    """Mais recentes primeiro."""
    arquivo = arquivo_historico(pasta_logs)
    if not arquivo.exists():
        return []
    with open(arquivo, encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    linhas.reverse()
    return linhas[:limite] if limite else linhas


def salvar_execucao(pasta_logs: Path, id_execucao: str, dados: dict) -> Path:
    pasta = pasta_execucoes(pasta_logs)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{id_execucao}.json"
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return destino


def ler_execucao(pasta_logs: Path, id_execucao: str) -> dict | None:
    if not id_execucao or any(c in id_execucao for c in "/\\") or id_execucao.startswith("."):
        return None
    arquivo = pasta_execucoes(pasta_logs) / f"{id_execucao}.json"
    if not arquivo.exists():
        return None
    return json.loads(arquivo.read_text(encoding="utf-8"))


CABECALHO_OCORRENCIAS = ["data_hora", "arquivo", "status", "nivel", "tabela", "coluna", "mensagem", "quantidade",
                         "exemplos", "id"]
ARQUIVO_OCORRENCIAS = "resumo_ocorrencias.csv"


def registrar_ocorrencias(pasta: Path, data_hora: str, arquivo: str, status: str, id_execucao: str,
                          ocorrencias: list) -> None:
    """Resumo consolidado de TODOS os erros e avisos de todas as planilhas (um por linha).

    Fica em Bases-Relatorios/resumo_ocorrencias.csv: abra no Excel (filtro por arquivo/mensagem)
    ou no Power BI para descobrir quais problemas mais se repetem e em quais planilhas.
    """
    linhas = [o for o in ocorrencias if o.nivel in ("ERRO", "AVISO")]
    if not linhas:
        return
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / ARQUIVO_OCORRENCIAS
    novo = not destino.exists()
    try:
        with open(destino, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            if novo:
                w.writerow(CABECALHO_OCORRENCIAS)
            for o in linhas:
                w.writerow([data_hora, arquivo, status, o.nivel, o.tabela, o.coluna, o.mensagem,
                            "" if o.quantidade is None else o.quantidade, " | ".join(o.exemplos), id_execucao])
    except PermissionError:
        import logging
        logging.getLogger("robo").warning("resumo_ocorrencias.csv está aberto no Excel; o resumo desta execução "
                                          "ficou só no histórico do painel.")
