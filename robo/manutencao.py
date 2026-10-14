"""Manutenção: apaga backups, relatórios e logs antigos conforme a retenção do config.yaml.

A pasta Bases-Erros NUNCA é limpa automaticamente — ali estão arquivos que precisam da sua ação.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from robo.config import Config

log = logging.getLogger("robo")


def _limpar(pasta: Path, dias: int, padrao: str = "*") -> int:
    if not dias or dias <= 0 or not pasta.exists():
        return 0
    limite = time.time() - dias * 86400
    removidos = 0
    for arq in pasta.rglob(padrao):
        try:
            if arq.is_file() and arq.stat().st_mtime < limite:
                arq.unlink()
                removidos += 1
        except OSError:
            continue
    for sub in sorted((p for p in pasta.rglob("*") if p.is_dir()), reverse=True):
        try:
            sub.rmdir()  # só remove se estiver vazia
        except OSError:
            pass
    return removidos


def executar_manutencao(cfg: Config) -> dict[str, int]:
    m = cfg.manutencao
    resumo = {
        "originais": _limpar(cfg.originais, int(m.get("dias_retencao_originais", 0))),
        "relatorios": _limpar(cfg.relatorios, int(m.get("dias_retencao_relatorios", 0))),
        "logs": _limpar(cfg.logs, int(m.get("dias_retencao_logs", 0)), "robo.log.*"),
    }
    if any(resumo.values()):
        log.info("Manutenção: arquivos antigos removidos %s", resumo)
    return resumo
