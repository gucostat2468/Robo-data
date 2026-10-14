"""Registro de tudo o que aconteceu com um arquivo: etapas, avisos e erros.

- ERRO  -> bloqueia: o arquivo NÃO vai para Bases-Tratadas.
- AVISO -> não bloqueia, mas fica registrado (ex.: linhas duplicadas removidas).
- INFO  -> apenas documenta uma etapa de limpeza executada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

import pandas as pd

ERRO = "ERRO"
AVISO = "AVISO"
INFO = "INFO"

MAX_EXEMPLOS = 5


@dataclass
class Ocorrencia:
    nivel: str
    mensagem: str
    tabela: str = ""
    coluna: str = ""
    quantidade: int | None = None
    exemplos: list = field(default_factory=list)


@dataclass
class Relatorio:
    arquivo: str
    inicio: datetime = field(default_factory=datetime.now)
    ocorrencias: list[Ocorrencia] = field(default_factory=list)

    def _add(self, nivel, mensagem, tabela="", coluna="", quantidade=None, exemplos: Iterable = ()):
        exemplos = [str(e) for e in list(exemplos)[:MAX_EXEMPLOS]]
        self.ocorrencias.append(Ocorrencia(nivel, mensagem, tabela, coluna, quantidade, exemplos))

    def erro(self, mensagem, **kw):
        self._add(ERRO, mensagem, **kw)

    def aviso(self, mensagem, **kw):
        self._add(AVISO, mensagem, **kw)

    def info(self, mensagem, **kw):
        self._add(INFO, mensagem, **kw)

    @property
    def erros(self) -> list[Ocorrencia]:
        return [o for o in self.ocorrencias if o.nivel == ERRO]

    @property
    def avisos(self) -> list[Ocorrencia]:
        return [o for o in self.ocorrencias if o.nivel == AVISO]

    @property
    def tem_erros(self) -> bool:
        return bool(self.erros)

    def para_dataframe(self) -> pd.DataFrame:
        linhas = [
            {
                "nivel": o.nivel,
                "tabela": o.tabela,
                "coluna": o.coluna,
                "mensagem": o.mensagem,
                "quantidade": o.quantidade,
                "exemplos": "; ".join(o.exemplos),
            }
            for o in self.ocorrencias
        ]
        return pd.DataFrame(linhas, columns=["nivel", "tabela", "coluna", "mensagem", "quantidade", "exemplos"])

    def texto(self) -> str:
        """Relatório legível (usado no arquivo _ERROS.txt)."""
        linhas = [
            "RELATÓRIO DO ROBÔ DE PLANILHAS",
            "=" * 60,
            f"Arquivo:     {self.arquivo}",
            f"Processado:  {self.inicio:%d/%m/%Y %H:%M:%S}",
            f"Resultado:   {'REPROVADO' if self.tem_erros else 'APROVADO'}",
            f"Erros:       {len(self.erros)}",
            f"Avisos:      {len(self.avisos)}",
            "",
        ]
        for titulo, nivel in (("ERROS (impedem o envio para Bases-Tratadas)", ERRO), ("AVISOS", AVISO), ("ETAPAS EXECUTADAS", INFO)):
            itens = [o for o in self.ocorrencias if o.nivel == nivel]
            if not itens:
                continue
            linhas += [titulo, "-" * 60]
            for i, o in enumerate(itens, 1):
                local = " / ".join(p for p in (o.tabela, o.coluna) if p)
                cab = f"{i}. {o.mensagem}"
                if local:
                    cab += f"  [{local}]"
                if o.quantidade is not None:
                    cab += f"  (qtd: {o.quantidade})"
                linhas.append(cab)
                if o.exemplos:
                    linhas.append(f"   Exemplos: {'; '.join(o.exemplos)}")
            linhas.append("")
        if self.tem_erros:
            linhas += [
                "O QUE FAZER",
                "-" * 60,
                "1. Corrija os pontos acima na planilha original (está nesta mesma pasta).",
                "2. Salve e coloque o arquivo corrigido novamente em Bases-Limpeza.",
                "3. O robô vai processar de novo automaticamente.",
            ]
        return "\n".join(linhas)
