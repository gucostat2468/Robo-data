"""Modo servidor: a empresa trabalhando dentro de um contêiner (Docker, Google Cloud Run, uma máquina Ubuntu).

    python -m robo servico            (é o que o Dockerfile roda)

O que faz:
  - turnos de trabalho um atrás do outro (os mesmos do GitHub Actions: robo/nuvem.py), salvando no PostgreSQL;
  - páginas de saúde, somente leitura, na porta da variável PORT (padrão 8080):
      GET /saude    estado do serviço e números do último turno (sempre 200, salvo erro);
      GET /healthz  checagem rápida do PostgreSQL (SELECT 1, até 3 s, resultado guardado por 15 s): 200 ou 503.
    Elas Não tem painel, não tem formulário, não aceita POST, não mostra
    segredo. O painel da empresa NUNCA é publicado por aqui;
  - trava de instância única: a memória da empresa é um instantâneo do SQLite salvo no PostgreSQL. Dois servidores
    trabalhando ao mesmo tempo gravariam dois futuros diferentes. Por isso, antes de trabalhar, o serviço pega uma
    trava no PostgreSQL (pg_try_advisory_lock). Quem não pega a trava fica em espera e só responde a saúde.
    (Mesmo assim, no Cloud Run use no máximo 1 instância: a trava é a rede de segurança, não o plano.)
  - encerramento gracioso: SIGTERM (o Cloud Run manda antes de desligar) ou SIGINT (Ctrl+C) param o laço do turno,
    a memória é SALVA, a trava é solta e o servidor de saúde fecha;
  - banco fora do ar: o serviço não morre; tenta de novo com espera crescente (1, 2, 4… até 10 min).
    Pool de conexões não é usado de propósito: há um trabalhador só e cada operação abre e fecha a sua conexão
    (com tempo limite), então uma conexão que caiu nunca é reaproveitada.

O banco vem das variáveis de ambiente (robo/nuvem.py, url_do_ambiente): ROBO_PG_URL ou DB_USER/DB_PASS/DB_NAME com
INSTANCE_CONNECTION_NAME (Unix socket do Cloud SQL). Nenhuma senha em arquivo.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("robo")

TRAVA = 7_316_2026  # número fixo da trava de instância única no PostgreSQL

ESTADO: dict = {"estado": "iniciando", "desde": datetime.now().isoformat(timespec="seconds"), "turnos": 0,
                "ultimo_turno": None, "ultimo_erro": None}
_lock = threading.Lock()
PARAR = threading.Event()  # ligado por SIGTERM/SIGINT
_BANCO: dict = {"cfg": None, "quando": 0.0, "ok": None, "erro": None}
CACHE_BANCO_S = 15


def _atualizar(**k) -> None:
    with _lock:
        ESTADO.update(k)


def checar_banco() -> dict:
    """SELECT 1 com tempo limite curto, guardado por 15 s (a saúde é chamada muitas vezes; o banco não sofre)."""
    agora = time.monotonic()
    with _lock:
        cfg, quando = _BANCO["cfg"], _BANCO["quando"]
        if cfg is None:
            return {"ok": None, "erro": "banco ainda não configurado"}
        if quando and agora - quando < CACHE_BANCO_S:
            return {"ok": _BANCO["ok"], "erro": _BANCO["erro"]}
    ok, erro = False, None
    try:
        import psycopg
        from robo.banco import Banco
        params = Banco(cfg.banco, cfg.base)._parametros(None, False)
        with psycopg.connect(**{**params, "connect_timeout": 3}) as conn:
            ok = conn.execute("SELECT 1").fetchone()[0] == 1
    except Exception as e:
        erro = type(e).__name__  # só o tipo: a mensagem pode conter o endereço do banco
    with _lock:
        _BANCO.update(quando=agora, ok=ok, erro=erro)
    return {"ok": ok, "erro": erro}


def foto() -> dict:
    with _lock:
        return json.loads(json.dumps(ESTADO, default=str))


class Saude(BaseHTTPRequestHandler):
    """Só GET /saude e GET /. Todo o resto: 404 ou 405."""
    server_version = "robo"
    sys_version = ""

    def _json(self, codigo: int, corpo: dict) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):  # noqa: N802
        rota = self.path.split("?")[0]
        if rota in ("/", "/saude", "/status"):
            f = foto()
            self._json(200 if f["estado"] != "erro" else 503, f)
        elif rota == "/healthz":
            b = checar_banco()
            self._json(200 if b["ok"] else 503, {"processo": "vivo", "estado": foto()["estado"], "banco": b})
        else:
            self._json(404, {"erro": "não existe"})

    def _recusar(self):
        self._json(405, {"erro": "somente leitura"})

    do_POST = do_PUT = do_DELETE = do_PATCH = _recusar  # noqa: N815

    def log_message(self, *_):  # sem log de cada acesso (ruído)
        pass


def iniciar_saude(porta: int | None = None) -> ThreadingHTTPServer:
    porta = int(porta if porta is not None else os.environ.get("PORT") or 8080)
    srv = ThreadingHTTPServer(("0.0.0.0", porta), Saude)
    threading.Thread(target=srv.serve_forever, name="saude", daemon=True).start()
    log.info("Serviço: saúde em http://0.0.0.0:%s/saude (somente leitura)", srv.server_address[1])
    return srv


def pegar_trava(cfg):
    """Conexão dedicada segurando a trava de instância única (ou None se outra instância já trabalha)."""
    from robo.banco import Banco
    conn = Banco(cfg.banco, cfg.base).conectar()
    conn.autocommit = True
    if conn.execute("SELECT pg_try_advisory_lock(%s)", (TRAVA,)).fetchone()[0]:
        return conn
    conn.close()
    return None


def instalar_sinais() -> None:
    """SIGTERM e SIGINT ligam PARAR: o turno em andamento sai do laço e salva (encerramento gracioso)."""
    import signal

    def _parar(sinal, _quadro):
        log.info("Serviço: sinal %s recebido; salvando e encerrando", sinal)
        _atualizar(estado="encerrando")
        PARAR.set()
    for s in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(s, _parar)
        except ValueError:  # fora da thread principal (testes): quem chama controla PARAR
            pass


def _soltar(trava) -> None:
    if trava is not None:
        try:
            trava.close()  # fechar a conexão solta a trava no PostgreSQL
        except Exception:
            pass


def _trava_viva(trava) -> bool:
    try:
        return trava is not None and not trava.closed and trava.execute("SELECT 1").fetchone()[0] == 1
    except Exception:
        return False


def principal(pasta: str, minutos: float = 20, verboso: bool = False, voltas: int | None = None,
              espera_s: float = 60, porta: int | None = None) -> int:
    from robo import nuvem
    from robo.comandos import configurar_log
    url = nuvem.url_do_ambiente()
    if not url:
        logging.basicConfig(level=logging.INFO)
        log.error("Serviço: faltam as variáveis do banco (ROBO_PG_URL ou DB_USER/DB_PASS/DB_NAME).")
        return 1
    cfg = nuvem.config_da_nuvem(Path(pasta), url, os.environ.get("ROBO_PG_SENHA_LEITURA", ""))
    configurar_log(cfg.logs, verboso)
    with _lock:
        _BANCO.update(cfg=cfg, quando=0.0)
    PARAR.clear()
    instalar_sinais()
    srv = iniciar_saude(porta)
    trava, feitas, falhas = None, 0, 0
    try:
        while not PARAR.is_set() and (voltas is None or feitas < voltas):
            feitas += 1
            try:
                if not _trava_viva(trava):  # conexão da trava caiu (rede, banco reiniciou): pega de novo
                    _soltar(trava)
                    trava = pegar_trava(cfg)
                if trava is None:
                    _atualizar(estado="em_espera", motivo="outra instância já está trabalhando (instância única)")
                    PARAR.wait(espera_s)
                    continue
                _atualizar(estado="trabalhando", motivo="")
                r = nuvem.turno(cfg, minutos, parar=PARAR)
                r["empresa"] = nuvem.resumo_do_turno(cfg)
                falhas = 0
                _atualizar(estado="entre_turnos", turnos=foto()["turnos"] + 1,
                           ultimo_turno={"fim": datetime.now().isoformat(timespec="seconds"), "minutos": r["minutos"],
                                         "planilhas": r["planilhas_processadas"], "banco_mb": r["banco_mb"],
                                         "alerta_espaco": r["alerta_espaco"], "empresa": r["empresa"]})
            except Exception as e:  # o serviço não morre: registra, espera cada vez mais e tenta de novo
                log.exception("Serviço: o turno falhou")
                falhas += 1
                espera = min(600.0, espera_s * 2 ** (falhas - 1)) if espera_s else 0
                _atualizar(estado="erro", ultimo_erro={"quando": datetime.now().isoformat(timespec="seconds"),
                                                       "tipo": type(e).__name__, "tentativa": falhas,
                                                       "proxima_em_s": espera})
                _soltar(trava)
                trava = None
                PARAR.wait(espera)
    finally:
        _soltar(trava)
        _atualizar(estado="encerrado")
        srv.shutdown()
        srv.server_close()
    return 0
