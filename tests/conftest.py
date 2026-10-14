from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from robo.config import carregar_config


@pytest.fixture
def pastas(tmp_path: Path):
    entrada = tmp_path / "OneDrive" / "Bases-Limpeza"
    entrada.mkdir(parents=True)
    (tmp_path / "OneDrive" / "Bases-Tratadas").mkdir()
    return tmp_path / "OneDrive"


@pytest.fixture
def cfg_factory(pastas, tmp_path):
    def _fazer(regras=None, **extra):
        sobrescrever = {"pastas": {"entrada": str(pastas / "Bases-Limpeza"), "logs": str(tmp_path / "logs"),
                                   "agentes": str(tmp_path / "agentes"), "skills": str(tmp_path / "skills")},
                        "regras": regras or [], **extra}
        return carregar_config(tmp_path / "nao_existe.yaml", sobrescrever=sobrescrever)
    return _fazer


@pytest.fixture
def planilha_baguncada(pastas) -> Path:
    """Planilha típica de vida real: título, linha vazia, cabeçalho sujo, números BR em texto, total no fim."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Relatório"
    ws.append(["Relatório de Pesquisa NPS - Outubro"])
    ws.append([])
    ws.append(["ID Resposta", " Data Resposta ", "Nota NPS", "Curso", "Modalidade", "UF", "Valor Mensalidade", "CEP", "Obs"])
    ws.append([1, datetime(2026, 10, 1), 10, "Direito", "EAD", "sp", "R$ 1.234,56", "01310-100", None])
    ws.append([2, "02/10/2026", "9", "  Direito ", "EAD", "rj", "999,90", "04567-000", None])
    ws.append([3, "03/10/2026", 6, "Medicina", "Presencial", "MG", "8.500,00", "30140-071", None])
    ws.append([3, "03/10/2026", 6, "Medicina", "Presencial", "MG", "8.500,00", "30140-071", None])  # duplicada
    ws.append([4, "04/10/2026", 0, "Direito", "EAD", "SP", "-", "01001-000", None])
    ws.append(["Total", None, None, None, None, None, "19.234,46", None, None])
    caminho = pastas / "Bases-Limpeza" / "nps_outubro.xlsx"
    wb.save(caminho)
    return caminho


REGRA_NPS = {
    "padrao": "nps_*",
    "colunas_obrigatorias": ["ID Resposta", "nota_nps"],
    "nao_nulos": ["id_resposta", "nota_nps"],
    "chave_unica": ["id_resposta"],
    "tipos": {"data_resposta": "data", "nota_nps": "inteiro"},
    "faixas": {"nota_nps": {"min": 0, "max": 10}},
    "texto": {"uf": "maiusculo"},
    "valores_permitidos": {"uf": ["SP", "RJ", "MG"]},
}
