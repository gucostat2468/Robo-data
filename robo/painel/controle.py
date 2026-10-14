"""Controle do robô usado pelo painel: liga/pausa o monitor, guarda o log recente e envia notificações."""

from __future__ import annotations

import collections
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from robo.config import ErroConfig, carregar_config
from robo.monitor import Monitor
from robo.painel import sistema
from robo.pipeline import ADIADO, REPROVADO, SUCESSO

log = logging.getLogger("robo")


class MemoriaLog(logging.Handler):
    """Guarda as últimas mensagens do log para a tela "Atividade" do painel."""

    def __init__(self, capacidade: int = 1000):
        super().__init__()
        self.registros = collections.deque(maxlen=capacidade)
        self.sequencia = 0
        self._trava = threading.Lock()

    def emit(self, record):
        with self._trava:
            self.sequencia += 1
            self.registros.append({
                "seq": self.sequencia,
                "hora": datetime.fromtimestamp(record.created).strftime("%d/%m %H:%M:%S"),
                "nivel": record.levelname,
                "mensagem": record.getMessage(),
            })

    def desde(self, seq: int) -> list[dict]:
        with self._trava:
            return [r for r in self.registros if r["seq"] > seq]


class ControleRobo:
    def __init__(self, caminho_config: Path | None = None):
        self.caminho_config = caminho_config
        self.cfg = None
        self.erro_config: str | None = None
        self.monitor: Monitor | None = None
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()
        self._trava = threading.Lock()
        self.ligado_desde: float | None = None
        self.memoria_log = MemoriaLog()
        log.addHandler(self.memoria_log)
        self.carregar()

    # ------------------------------------------------------------ configuração
    def carregar(self):
        try:
            self.cfg = carregar_config(self.caminho_config)
            self.cfg.criar_pastas()
            self.monitor = Monitor(self.cfg, ao_processar=self._apos_processar)
            self.erro_config = None
        except ErroConfig as e:
            self.cfg, self.monitor, self.erro_config = None, None, str(e)
            log.error("Configuração: %s", e)
        except OSError as e:
            self.cfg, self.monitor, self.erro_config = None, None, f"Não consegui acessar as pastas: {e}"
            log.error(self.erro_config)

    def recarregar(self):
        estava_ligado = self.ligado
        self.pausar()
        self.carregar()
        if estava_ligado and self.cfg:
            self.ligar()

    # ------------------------------------------------------------ liga / pausa
    @property
    def ligado(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def ligar(self) -> bool:
        with self._trava:
            if self.ligado or not self.monitor:
                return self.ligado
            self._parar = threading.Event()
            self._thread = threading.Thread(target=self._laco, args=(self.monitor, self._parar),
                                            name="robo-monitor", daemon=True)
            self._thread.start()
            self.ligado_desde = time.time()
            log.info("Robô ligado. Monitorando %s", self.cfg.entrada)
            return True

    def pausar(self):
        with self._trava:
            if not self.ligado:
                return
            self._parar.set()
            self._thread.join(timeout=120)
            self.ligado_desde = None
            log.info("Robô pausado. Arquivos novos ficarão aguardando em Bases-Limpeza.")

    def _laco(self, monitor: Monitor, parar: threading.Event):
        while not parar.is_set():
            try:
                monitor.ciclo()
            except Exception:
                log.exception("Erro no ciclo do monitor")
            parar.wait(monitor.intervalo)

    def processar_agora(self) -> bool:
        if not self.monitor:
            return False
        threading.Thread(target=lambda: self.monitor.ciclo(forcar=True), name="robo-agora", daemon=True).start()
        return True

    # ------------------------------------------------------------ notificações
    def _apos_processar(self, r):
        if not self.cfg or not self.cfg.painel.get("notificacoes", True):
            return
        if r.status == SUCESSO:
            sistema.notificar("Planilha tratada", f"{r.arquivo.name}: {r.linhas_saida:,} linhas prontas".replace(",", "."))
        elif r.status == REPROVADO:
            sistema.notificar("Planilha reprovada", f"{r.arquivo.name}: {len(r.relatorio.erros)} erro(s). Abra o painel para corrigir.")
        elif r.status == ADIADO:
            pass  # adiamentos se resolvem sozinhos; aparecem na fila do painel
