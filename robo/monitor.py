"""Monitoramento da pasta Bases-Limpeza.

Usa "polling" (olha a pasta a cada N segundos) em vez de eventos do sistema, porque é o método
mais confiável com o OneDrive: ele cria/renomeia arquivos temporários durante a sincronização e
eventos podem se perder. Um arquivo só é processado quando:
  1. o tamanho e a data de modificação ficam iguais por X segundos (sincronização terminou) e
  2. ele pode ser aberto (não está aberto no Excel).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date
from pathlib import Path

from robo.config import Config
from robo.manutencao import executar_manutencao
from robo.pipeline import ADIADO, processar_arquivo

log = logging.getLogger("robo")

IGNORAR_NOMES = {"desktop.ini", "thumbs.db", ".ds_store"}


def eh_candidato(caminho: Path) -> bool:
    nome = caminho.name.lower()
    return (
        caminho.is_file()
        and nome not in IGNORAR_NOMES
        and not nome.startswith(("~$", "~robo_tmp_", ".", "~"))
        and not nome.endswith((".tmp", ".crdownload", ".part", ".partial", ".lnk"))
    )


def pode_abrir(caminho: Path) -> bool:
    """No Windows, abrir para escrita falha se o Excel estiver com o arquivo aberto."""
    try:
        with open(caminho, "rb+"):
            return True
    except (PermissionError, OSError):
        return False


class Monitor:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.intervalo = float(cfg.monitoramento["intervalo_segundos"])
        self.espera = float(cfg.monitoramento["espera_estabilidade_segundos"])
        # caminho -> (tamanho, modificação, momento em que essa assinatura foi vista pela 1ª vez)
        self._vistos: dict[Path, tuple[int, float, float]] = {}
        self._ultima_manutencao: date | None = None

    def ciclo(self, agora: float | None = None) -> list:
        """Uma passada na pasta. Devolve os resultados dos arquivos processados."""
        agora = time.monotonic() if agora is None else agora
        resultados = []
        try:
            arquivos = sorted(p for p in self.cfg.entrada.iterdir() if eh_candidato(p))
        except FileNotFoundError:
            log.error("Pasta de entrada não encontrada: %s", self.cfg.entrada)
            return resultados

        for arq in arquivos:
            try:
                st = arq.stat()
            except OSError:
                continue
            assinatura = (st.st_size, st.st_mtime)
            anterior = self._vistos.get(arq)
            if anterior is None or anterior[:2] != assinatura:
                self._vistos[arq] = (*assinatura, agora)
                if anterior is None:
                    log.info("Novo arquivo detectado: %s (aguardando sincronização terminar)", arq.name)
                continue
            if agora - anterior[2] < self.espera or not pode_abrir(arq):
                continue
            try:
                r = processar_arquivo(arq, self.cfg)
            except Exception:
                log.exception("Erro ao processar %s; nova tentativa no próximo ciclo", arq.name)
                self._vistos[arq] = (*assinatura, agora)
                continue
            resultados.append(r)
            if r.status == ADIADO:
                self._vistos[arq] = (*assinatura, agora + 50)  # espera ~1 min antes de tentar de novo
            else:
                self._vistos.pop(arq, None)

        for antigo in [p for p in self._vistos if not p.exists()]:
            self._vistos.pop(antigo, None)
        self._manutencao_diaria()
        return resultados

    def _manutencao_diaria(self):
        hoje = date.today()
        if self._ultima_manutencao != hoje:
            self._ultima_manutencao = hoje
            try:
                executar_manutencao(self.cfg)
            except Exception:
                log.exception("Falha na manutenção diária")

    def rodar(self, parar: threading.Event | None = None):
        parar = parar or threading.Event()
        log.info("Robô iniciado. Monitorando: %s", self.cfg.entrada)
        log.info("Saída: %s | Erros: %s", self.cfg.tratadas, self.cfg.erros)
        log.info("Para encerrar, feche esta janela ou pressione Ctrl+C.")
        while not parar.is_set():
            self.ciclo()
            parar.wait(self.intervalo)


class TravaInstancia:
    """Impede dois robôs rodando ao mesmo tempo (ex.: um na inicialização do Windows e outro manual)."""

    def __init__(self, pasta: Path):
        pasta.mkdir(parents=True, exist_ok=True)
        self.caminho = pasta / "robo.lock"
        self._arquivo = None

    def __enter__(self):
        self._arquivo = open(self.caminho, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                self._arquivo.seek(0)
                msvcrt.locking(self._arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._arquivo.close()
            raise RuntimeError("Já existe um robô rodando neste computador. Feche-o antes de abrir outro.")
        return self

    def __exit__(self, *exc):
        if self._arquivo:
            self._arquivo.close()
