"""Histórico de processamentos.

- logs/historico_processamentos.csv : uma linha por arquivo processado (fácil de abrir no Excel/Power BI)
- logs/execucoes/<id>.json          : detalhe completo de cada processamento (usado pelo painel)

O <id> é o mesmo nome (sem extensão) que o arquivo original recebe em Bases-Originais/Bases-Erros,
por exemplo "20261014_093012_nps_outubro". Assim o painel liga o arquivo ao seu relatório.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

CABECALHO = ["data_hora", "arquivo", "status", "linhas_entrada", "linhas_saida", "erros", "avisos",
             "duracao_seg", "saidas", "id"]


def arquivo_historico(pasta_logs: Path) -> Path:
    return pasta_logs / "historico_processamentos.csv"


def pasta_execucoes(pasta_logs: Path) -> Path:
    return pasta_logs / "execucoes"


def registrar(pasta_logs: Path, linha: dict) -> None:
    """Acrescenta uma linha ao histórico. Se o CSV estiver aberto no Excel, a linha vai para uma fila
    (historico_pendente.jsonl) e entra no CSV na próxima gravação — nada se perde e o robô não trava."""
    pasta_logs.mkdir(parents=True, exist_ok=True)
    pendente = pasta_logs / "historico_pendente.jsonl"
    linhas = []
    if pendente.exists():
        linhas = [json.loads(l) for l in pendente.read_text(encoding="utf-8").splitlines() if l.strip()]
    linhas.append(linha)
    try:
        _gravar_linhas(pasta_logs, linhas)
        pendente.unlink(missing_ok=True)
    except PermissionError:
        with open(pendente, "a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False, default=str) + "\n")


def _gravar_linhas(pasta_logs: Path, linhas: list[dict]) -> None:
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
        for linha in linhas:
            w.writerow([linha.get(c, "") for c in CABECALHO])


PREFIXO_SINTETICO = "TREINO_"
_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}")


def eh_sintetico(nome_arquivo) -> bool:
    """Planilha da Fábrica de Planilhas (dados inventados para treino): nunca entra em número real."""
    return str(nome_arquivo or "").upper().startswith(PREFIXO_SINTETICO)


def ler(pasta_logs: Path, limite: int | None = None, incluir_sinteticos: bool = False) -> list[dict]:
    """Mais recentes primeiro. Por padrão SEM as planilhas sintéticas da fábrica (TREINO_*): nenhum painel, BI ou
    número real mistura dado inventado. Quem precisa delas (a tela da fábrica) pede incluir_sinteticos=True."""
    arquivo = arquivo_historico(pasta_logs)
    if not arquivo.exists():
        return []
    with open(arquivo, encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    pendente = pasta_logs / "historico_pendente.jsonl"
    if pendente.exists():  # linhas que esperam o CSV ser fechado no Excel também aparecem no painel
        linhas += [{k: str(v) for k, v in json.loads(l).items()} for l in pendente.read_text(encoding="utf-8").splitlines() if l.strip()]
    linhas.reverse()
    # linha com outra coisa no lugar da data é linha cortada (defeito antigo da restauração entre turnos da nuvem, já corrigido em
    # registro_total): com as colunas deslocadas, uma planilha de treino passava por real. Não entra em conta nenhuma;
    # o registro original continua guardado no banco.
    linhas = [x for x in linhas if not x.get("data_hora") or _RE_DATA.match(str(x["data_hora"]))]
    if not incluir_sinteticos:
        linhas = [x for x in linhas if not eh_sintetico(x.get("arquivo"))]
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
