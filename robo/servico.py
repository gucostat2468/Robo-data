"""Modo servidor: a empresa trabalhando dentro de um contêiner (Docker, Google Cloud Run, uma máquina Ubuntu).

    python -m robo servico            (é o que o Dockerfile roda)

O que faz:
  - turnos de trabalho um atrás do outro (os mesmos do GitHub Actions: robo/nuvem.py), salvando no PostgreSQL;
  - UMA página de saúde, somente leitura, na porta da variável PORT (padrão 8080): GET /saude devolve JSON com o
    estado do serviço e números do último turno. Não tem painel, não tem formulário, não aceita POST, não mostra
    segredo. O painel da empresa NUNCA é publicado por aqui;
  - trava de instância única: a memória da empresa é um instantâneo do SQLite salvo no PostgreSQL. Dois servidores
    trabalhando ao mesmo tempo gravariam dois futuros diferentes. Por isso, antes de trabalhar, o serviço pega uma
    trava no PostgreSQL (pg_try_advisory_lock). Quem não pega a trava fica em espera e só responde a saúde.
    (Mesmo assim, no Cloud Run use no máximo 1 instância: a trava é a rede de segurança, não o plano.)

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


def _atualizar(**k) -> None:
    with _lock:
        ESTADO.update(k)


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
        if self.path.split("?")[0] in ("/", "/saude"):
            f = foto()
            self._json(200 if f["estado"] != "erro" else 503, f)
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


def principal(pasta: str, minutos: float = 20, verboso: bool = False, voltas: int | None = None,
              espera_s: float = 60) -> int:
    from robo import nuvem
    from robo.comandos import configurar_log
    url = nuvem.url_do_ambiente()
    if not url:
        logging.basicConfig(level=logging.INFO)
        log.error("Serviço: faltam as variáveis do banco (ROBO_PG_URL ou DB_USER/DB_PASS/DB_NAME).")
        return 1
    cfg = nuvem.config_da_nuvem(Path(pasta), url, os.environ.get("ROBO_PG_SENHA_LEITURA", ""))
    configurar_log(cfg.logs, verboso)
    iniciar_saude()
    trava, feitas = None, 0
    while voltas is None or feitas < voltas:
        feitas += 1
        try:
            if trava is None or trava.closed:
                trava = pegar_trava(cfg)
            if trava is None:
                _atualizar(estado="em_espera", motivo="outra instância já está trabalhando (instância única)")
                time.sleep(espera_s)
                continue
            _atualizar(estado="trabalhando", motivo="")
            r = nuvem.turno(cfg, minutos)
            r["empresa"] = nuvem.resumo_do_turno(cfg)
            _atualizar(estado="entre_turnos", turnos=foto()["turnos"] + 1,
                       ultimo_turno={"fim": datetime.now().isoformat(timespec="seconds"), "minutos": r["minutos"],
                                     "planilhas": r["planilhas_processadas"], "banco_mb": r["banco_mb"],
                                     "alerta_espaco": r["alerta_espaco"], "empresa": r["empresa"]})
        except Exception as e:  # o serviço não morre: registra, espera e tenta de novo
            log.exception("Serviço: o turno falhou")
            _atualizar(estado="erro", ultimo_erro={"quando": datetime.now().isoformat(timespec="seconds"),
                                                   "tipo": type(e).__name__})
            if trava is not None:
                try:
                    trava.close()
                except Exception:
                    pass
                trava = None
            time.sleep(espera_s)
    return 0
