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
        self._trava_eventos = threading.Lock()
        self.ligado_desde: float | None = None
        self.memoria_log = MemoriaLog()
        self.eventos = collections.deque(maxlen=400)   # etapas do pipeline, para o escritório 3D
        self._seq_eventos = 0
        log.addHandler(self.memoria_log)
        self.carregar()

    # ------------------------------------------------------------ configuração
    def carregar(self):
        try:
            self.cfg = carregar_config(self.caminho_config)
            self.cfg.criar_pastas()
            self.monitor = Monitor(self.cfg, ao_processar=self._apos_processar, ao_etapa=self._registrar_etapa)
            self.erro_config = None
            from robo import erros, orquestrador
            orquestrador.AO_EVENTO = self._registrar_etapa  # tarefas da central aparecem no escritório 3D
            erros.instalar(self.cfg)                        # todo ERRO de log vira registro permanente + handover
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
            if not getattr(self, "_rotinas_independentes", False):
                self._rotinas()
            parar.wait(monitor.intervalo)

    def iniciar_rotinas(self):
        """Rotinas da empresa num laço próprio: continuam rodando mesmo com o monitoramento pausado."""
        if getattr(self, "_rotinas_independentes", False):
            return
        self._rotinas_independentes = True
        if self.cfg:
            try:
                from robo import orquestrador
                retomadas = orquestrador.retomar_pendentes(self.cfg)  # tarefas interrompidas por reinício
                if retomadas:
                    log.info("Tarefas retomadas depois de reiniciar: %s", ", ".join(retomadas))
            except Exception:
                log.exception("Não consegui retomar as tarefas pendentes")

        sessao = None
        if self.cfg:
            try:  # resumo de abertura: quanto tempo ficou desligado, fila e rotinas atrasadas
                from robo import rotinas
                fila = len(self.monitor.estado_fila()) if self.monitor else 0
                abertura = rotinas.abrir_sessao(self.cfg, fila)
                sessao = abertura["sessao"]
                from robo.canal import Canal
                Canal(self.cfg).postar("ger_operacoes", "Abertura do dia — " + abertura["briefing"], "geral", tipo="boletim")
            except Exception:
                log.exception("Não consegui registrar a abertura da sessão")

        def _laco_rotinas():
            while True:
                try:
                    self._rotinas()
                    if sessao:
                        from robo import rotinas
                        rotinas.batimento(self.cfg, sessao)
                except Exception:
                    log.exception("Erro nas rotinas da empresa")
                time.sleep(15)
        threading.Thread(target=_laco_rotinas, name="robo-rotinas", daemon=True).start()

    def _rotinas(self):
        """Rotinas da empresa que não dependem de arquivo novo. Cada execução fica registrada (robo/rotinas.py)."""
        if not self.cfg:
            return
        from robo import rotinas
        cfg = self.cfg
        agora = time.time()
        if agora - getattr(self, "_ultimo_canal", 0) >= 60:
            self._ultimo_canal = agora
            from robo.canal import Canal
            rotinas.executar(cfg, "canal", lambda: Canal(cfg).sincronizar())
        # rotinas pesadas em segundo plano (avaliação, backup, estudo, reunião…): cada uma decide se está na hora
        if agora - getattr(self, "_ultima_estrategia", 0) >= 3600 and not getattr(self, "_estrategia_rodando", False):
            self._ultima_estrategia, self._estrategia_rodando = agora, True

            def _rodar():
                from robo import auditoria, backup, desenvolvimento, estrategia, licoes, memoria, reuniao
                try:
                    rotinas.executar(cfg, "estrategia", lambda: estrategia.rotina(cfg))
                    rotinas.executar(cfg, "backup", lambda: backup.rotina(cfg))
                    rotinas.executar(cfg, "memoria_pg", lambda: (memoria.sincronizar_postgres(cfg)
                                                                 if cfg.banco.get("habilitado") else None))
                    rotinas.executar(cfg, "pdca", lambda: memoria.checar_pdca(cfg)["verificados"])
                    rotinas.executar(cfg, "licoes", lambda: licoes.rotina(cfg))
                    rotinas.executar(cfg, "estudo", lambda: desenvolvimento.rotina(cfg))
                    rotinas.executar(cfg, "auditoria", lambda: auditoria.rotina(cfg))
                    rotinas.executar(cfg, "reuniao", lambda: reuniao.rotina(cfg))
                finally:
                    self._estrategia_rodando = False
            threading.Thread(target=_rodar, name="robo-estrategia", daemon=True).start()
        # laboratório: treino contínuo (a própria rotina decide se já passou o intervalo); em linha própria
        if agora - getattr(self, "_ultimo_lab", 0) >= 60 and not getattr(self, "_lab_rodando", False):
            self._ultimo_lab, self._lab_rodando = agora, True

            def _lab():
                from robo import laboratorio
                try:
                    rotinas.executar(cfg, "laboratorio", lambda: laboratorio.rotina(cfg))
                finally:
                    self._lab_rodando = False
            threading.Thread(target=_lab, name="robo-laboratorio", daemon=True).start()
        from robo.ti import _c as cfg_ti
        if agora - getattr(self, "_ultima_ronda_ti", 0) >= 60 * float(cfg_ti(cfg)["intervalo_minutos"]):
            self._ultima_ronda_ti = agora
            from robo.ti import ronda
            rotinas.executar(cfg, "ronda_ti", lambda: ronda(cfg))

    def processar_agora(self) -> bool:
        if not self.monitor:
            return False
        threading.Thread(target=lambda: self.monitor.ciclo(forcar=True), name="robo-agora", daemon=True).start()
        return True

    # ------------------------------------------------------------ eventos do escritório
    def _registrar_etapa(self, etapa: str, arquivo: str, **extra):
        with self._trava_eventos:
            self._seq_eventos += 1
            self.eventos.append({"seq": self._seq_eventos, "ts": time.time(), "etapa": etapa, "arquivo": arquivo, **extra})

    def eventos_desde(self, seq: int) -> list[dict]:
        with self._trava_eventos:
            return [e for e in self.eventos if e["seq"] > seq]

    # ------------------------------------------------------------ notificações
    def _apos_processar(self, r):
        if not self.cfg:
            return
        try:
            from robo import memoria, orquestrador
            orquestrador.registrar_execucao_automatica(self.cfg, r)  # central de solicitações (pedido automático)
            memoria.registrar_execucao(self.cfg, r)                  # experiências e handovers de cada área
            if self.cfg.banco.get("habilitado"):
                memoria.sincronizar_postgres(self.cfg)               # e a mesma memória no PostgreSQL (schema robo)
        except Exception:
            log.exception("Não consegui registrar a execução na central/memória")
        try:  # aprendizado operacional: reprovou → proposta de regra; regra aprovada → prova de que mudou
            from robo import aprendizado
            aprendizado.comprovar(self.cfg, r)
            aprendizado.propor(self.cfg, r)
        except Exception:
            log.exception("Não consegui registrar o aprendizado da execução")
        if not self.cfg.painel.get("notificacoes", True):
            return
        if r.status == SUCESSO:
            sistema.notificar("Planilha tratada", f"{r.arquivo.name}: {r.linhas_saida:,} linhas prontas".replace(",", "."))
        elif r.status == REPROVADO:
            sistema.notificar("Planilha reprovada", f"{r.arquivo.name}: {len(r.relatorio.erros)} erro(s). Abra o painel para corrigir.")
        elif r.status == ADIADO:
            pass  # adiamentos se resolvem sozinhos; aparecem na fila do painel
