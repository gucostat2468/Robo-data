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


PASTA_SINTETICO = "sintetico"   # Bases-Limpeza/sintetico: planilhas TREINO_ da Fábrica de Planilhas (robo/fabrica.py)


def eh_candidato(caminho: Path) -> bool:
    nome = caminho.name.lower()
    return (
        caminho.is_file()
        and nome not in IGNORAR_NOMES
        and not nome.startswith(("~$", "~robo_tmp_", ".", "~"))
        and not nome.endswith((".tmp", ".crdownload", ".part", ".partial", ".lnk", ".gabarito.json"))
    )


def pode_abrir(caminho: Path) -> bool:
    """No Windows, abrir para escrita falha se o Excel estiver com o arquivo aberto.
    Arquivo marcado como "somente leitura" não pode ser aberto para escrita nunca: nele, basta conseguir ler."""
    import os
    try:
        with open(caminho, "rb" if not os.access(caminho, os.W_OK) else "rb+"):
            return True
    except (PermissionError, OSError):
        return False


# Uma trava por PASTA de entrada, compartilhada por todos os monitores do processo: depois de recarregar a configuração
# nasce um Monitor novo, e um "Processar agora" ainda rodando no antigo não pode processar a mesma pasta ao mesmo tempo.
_TRAVAS_POR_PASTA: dict[str, threading.Lock] = {}
_TRAVA_DAS_TRAVAS = threading.Lock()


def _trava_da_pasta(pasta: Path) -> threading.Lock:
    chave = os.path.normcase(str(Path(pasta).resolve()))
    with _TRAVA_DAS_TRAVAS:
        return _TRAVAS_POR_PASTA.setdefault(chave, threading.Lock())


class Monitor:
    def __init__(self, cfg: Config, ao_processar=None, ao_etapa=None):
        self.cfg = cfg
        self.intervalo = float(cfg.monitoramento["intervalo_segundos"])
        self.espera = float(cfg.monitoramento["espera_estabilidade_segundos"])
        # caminho -> (tamanho, modificação, momento em que essa assinatura foi vista pela 1ª vez)
        self._vistos: dict[Path, tuple[int, float, float]] = {}
        self._ultima_manutencao: date | None = None
        self._trava = _trava_da_pasta(cfg.entrada)
        self.ao_processar = ao_processar      # função chamada com cada Resultado (painel/notificações)
        self.ao_etapa = ao_etapa              # função chamada a cada etapa (escritório 3D)
        self.processando: str | None = None
        self.em_uso: set[str] = set()
        self.adiados: dict[str, str] = {}     # nome -> motivo
        self.ultimo_ciclo: float | None = None

    def ciclo(self, agora: float | None = None, forcar: bool = False) -> list:
        """Uma passada na pasta. Devolve os resultados dos arquivos processados.
        forcar=True: processa já, sem esperar a estabilidade (botão "Processar agora")."""
        with self._trava:
            return self._ciclo(time.monotonic() if agora is None else agora, forcar)

    def _ciclo(self, agora: float, forcar: bool) -> list:
        resultados = []
        try:
            arquivos = sorted(p for p in self.cfg.entrada.iterdir() if eh_candidato(p))
        except FileNotFoundError:
            log.error("Pasta de entrada não encontrada: %s", self.cfg.entrada)
            return resultados
        if not arquivos:  # produção real vem primeiro: a subpasta da fábrica só é lida com a raiz vazia
            sint = self.cfg.entrada / PASTA_SINTETICO
            if sint.is_dir():
                arquivos = sorted(p for p in sint.iterdir() if eh_candidato(p))

        from robo.pipeline import ja_publicado
        for arq in arquivos:
            if ja_publicado(self.cfg, arq):  # processado, mas o original estava travado: não processa de novo
                continue
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
                    if self.ao_etapa:
                        self.ao_etapa("recepcao", arq.name)
                if not forcar:
                    continue
                anterior = self._vistos[arq]
            if not forcar and agora - anterior[2] < self.espera:
                continue
            if not pode_abrir(arq):
                if arq.name not in self.em_uso:
                    log.info("%s está aberto em outro programa (Excel?). Aguardando ser fechado.", arq.name)
                self.em_uso.add(arq.name)
                continue
            self.em_uso.discard(arq.name)
            self.processando = arq.name
            try:
                r = processar_arquivo(arq, self.cfg, ao_etapa=self.ao_etapa)
            except Exception:
                log.exception("Erro ao processar %s; nova tentativa no próximo ciclo", arq.name)
                self._vistos[arq] = (*assinatura, agora)
                continue
            finally:
                self.processando = None
            resultados.append(r)
            if r.status == ADIADO:
                self.adiados[arq.name] = r.motivo_adiamento
                self._vistos[arq] = (*assinatura, agora + 50)  # espera ~1 min antes de tentar de novo
            else:
                self.adiados.pop(arq.name, None)
                self._vistos.pop(arq, None)
            if self.ao_processar:
                try:
                    self.ao_processar(r)
                except Exception:
                    log.exception("Falha no aviso pós-processamento")

        nomes = {a.name for a in arquivos}
        for antigo in [p for p in self._vistos if not p.exists()]:
            self._vistos.pop(antigo, None)
        self.em_uso &= nomes
        self.adiados = {k: v for k, v in self.adiados.items() if k in nomes}
        self.ultimo_ciclo = time.time()
        self._manutencao_diaria()
        return resultados

    def estado_fila(self) -> list[dict]:
        """Situação de cada arquivo em Bases-Limpeza, para o painel."""
        agora = time.monotonic()
        fila = []
        try:
            arquivos = sorted(p for p in self.cfg.entrada.iterdir() if eh_candidato(p))
        except OSError:
            return fila
        for arq in arquivos:
            try:
                tamanho = arq.stat().st_size
            except OSError:
                continue
            item = {"nome": arq.name, "tamanho": tamanho, "estado": "detectado", "segundos": None, "motivo": ""}
            visto = self._vistos.get(arq)
            if arq.name == self.processando:
                item["estado"] = "processando"
            elif arq.name in self.adiados:
                item.update(estado="adiado", motivo=self.adiados[arq.name])
            elif arq.name in self.em_uso:
                item["estado"] = "em_uso"
            elif visto is not None:
                restante = self.espera - (agora - visto[2])
                item.update(estado="aguardando", segundos=max(0, round(restante)))
            fila.append(item)
        return fila

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
