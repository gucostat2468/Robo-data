"""Edição do config.yaml pelo painel, PRESERVANDO comentários e organização do arquivo.

Só altera a linha "  chave: valor" dentro da seção indicada; se não existir, acrescenta.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

from robo.config import RAIZ_PROJETO

# o que o painel pode alterar (seção -> chaves). Qualquer outra coisa é recusada.
EDITAVEIS = {
    "pastas": {"entrada"},
    "saida": {"formato", "versionar"},
    "monitoramento": {"espera_estabilidade_segundos"},
    "banco": {"habilitado", "host", "porta", "banco", "usuario", "senha", "carregar_bruto", "modo_carga_padrao"},
    "painel": {"ligar_robo_ao_abrir", "notificacoes"},
}


def garantir_arquivo(caminho: Path | None) -> Path:
    caminho = caminho or RAIZ_PROJETO / "config.yaml"
    if not caminho.exists():
        shutil.copy(RAIZ_PROJETO / "config.exemplo.yaml", caminho)
    return caminho


def _escalar(valor) -> str:
    texto = yaml.safe_dump(valor, allow_unicode=True, default_flow_style=True).strip()
    if texto.endswith("\n..."):
        texto = texto[:-4].strip()
    return texto.removesuffix("...").strip()


def definir(caminho: Path, secao: str, chave: str, valor) -> None:
    if chave not in EDITAVEIS.get(secao, set()):
        raise ValueError(f"Configuração '{secao}.{chave}' não pode ser alterada pelo painel.")
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    novo = f"  {chave}: {_escalar(valor)}"
    inicio = next((i for i, l in enumerate(linhas) if re.match(rf"^{re.escape(secao)}:\s*(#.*)?$", l)), None)
    if inicio is None:
        linhas += ["", f"{secao}:", novo]
    else:
        fim = next((i for i in range(inicio + 1, len(linhas)) if linhas[i] and not linhas[i][0].isspace()
                    and not linhas[i].startswith("#")), len(linhas))
        padrao = re.compile(rf"^(\s+){re.escape(chave)}:(\s*)([^#]*?)(\s*#.*)?$")
        for i in range(inicio + 1, fim):
            m = padrao.match(linhas[i])
            if m:
                linhas[i] = f"{m.group(1)}{chave}: {_escalar(valor)}{m.group(4) or ''}"
                break
        else:
            ultimo = max((i for i in range(inicio + 1, fim) if linhas[i].strip() and not linhas[i].lstrip().startswith("#")),
                         default=inicio)
            linhas.insert(ultimo + 1, novo)
    texto = "\n".join(linhas) + "\n"
    yaml.safe_load(texto)  # garante que o arquivo continua válido antes de gravar
    caminho.write_text(texto, encoding="utf-8")
