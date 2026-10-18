"""Registro permanente de todo erro de sistema: nenhum erro some no log.

Todo log de nível ERRO (ou exceção) do robô é gravado em logs/trabalho.db → erros_sistema:
  - agrupado por "impressão digital" (módulo + função + tipo do erro + mensagem sem números), contando as repetições;
  - com o traceback completo da primeira e da última ocorrência;
  - o primeiro de cada tipo vira handover para a TI (Diego), com a regra de corrigir e criar teste automatizado;
  - se voltar depois de marcado como resolvido, reabre (o handover também reabre).
O registro nunca é apagado: resolvido muda de estado, não de lugar.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import traceback

from robo.trabalho import Trabalho, _agora

ESQUEMA = """CREATE TABLE IF NOT EXISTS erros_sistema (
  id INTEGER PRIMARY KEY AUTOINCREMENT, impressao TEXT UNIQUE, primeira TEXT, ultima TEXT, ocorrencias INTEGER DEFAULT 1,
  modulo TEXT, funcao TEXT, tipo TEXT, mensagem TEXT, traceback_primeiro TEXT, traceback_ultimo TEXT,
  handover_id TEXT, estado TEXT DEFAULT 'aberto');
CREATE TRIGGER IF NOT EXISTS erros_sistema_sem_apagar BEFORE DELETE ON erros_sistema
BEGIN SELECT RAISE(ABORT, 'registro de erros é permanente: marque como resolvido, não apague'); END;"""

_local = threading.local()


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        from robo.trabalho import proteger
        proteger(c)
    return tb


def impressao(modulo: str, funcao: str, tipo: str, mensagem: str) -> str:
    base = re.sub(r"\d+([.,]\d+)?", "#", mensagem.lower())
    base = re.sub(r"(/|\\\\)[^\s:]+", "<caminho>", base)[:200]
    return hashlib.sha1(f"{modulo}|{funcao}|{tipo}|{base}".encode()).hexdigest()[:16]


def registrar(cfg, modulo: str, funcao: str, tipo: str, mensagem: str, tb_texto: str = "") -> dict:
    from robo import memoria
    tb = _tb(cfg)
    imp = impressao(modulo, funcao, tipo, mensagem)
    with tb.tx() as c:
        r = c.execute("SELECT id, estado, handover_id FROM erros_sistema WHERE impressao=?", (imp,)).fetchone()
        if r:
            c.execute("UPDATE erros_sistema SET ocorrencias=ocorrencias+1, ultima=?, traceback_ultimo=?, "
                      "estado=CASE WHEN estado='resolvido' THEN 'reaberto' ELSE estado END WHERE id=?",
                      (_agora(), tb_texto[-6000:], r["id"]))
            novo, hid = False, r["handover_id"]
        else:
            c.execute("INSERT INTO erros_sistema (impressao, primeira, ultima, modulo, funcao, tipo, mensagem, traceback_primeiro, "
                      "traceback_ultimo) VALUES (?,?,?,?,?,?,?,?,?)",
                      (imp, _agora(), _agora(), modulo, funcao, tipo, mensagem[:1000], tb_texto[-6000:], tb_texto[-6000:]))
            novo, hid = True, None
    # handover (e recorrência) — a regra de categoria "falha inesperada" já manda para o Diego com teste automatizado
    hid = memoria.handover(cfg, f"Falha inesperada no código ({modulo}.{funcao}): {tipo}: {mensagem[:200]}", "sistema",
                           "dev_junior", f"impressão {imp}", tb)
    if novo:
        with tb.tx() as c:
            c.execute("UPDATE erros_sistema SET handover_id=? WHERE impressao=?", (hid, imp))
    return {"impressao": imp, "novo": novo, "handover": hid}


class RegistroErros(logging.Handler):
    """Handler de logging: todo ERRO do robô vira registro permanente."""

    def __init__(self, cfg):
        super().__init__(level=logging.ERROR)
        self.cfg = cfg

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(_local, "dentro", False):  # erro ao registrar erro: não entra em laço
            return
        _local.dentro = True
        try:
            tipo, tb_texto = "Erro", ""
            if record.exc_info and record.exc_info[0]:
                tipo = record.exc_info[0].__name__
                tb_texto = "".join(traceback.format_exception(*record.exc_info))
            registrar(self.cfg, record.module, record.funcName, tipo, record.getMessage(), tb_texto)
        except Exception:
            pass
        finally:
            _local.dentro = False


_instalado: dict[str, RegistroErros] = {}


def instalar(cfg) -> None:
    """Liga o registro no logger do robô (uma vez por pasta de logs)."""
    chave = str(cfg.logs)
    log = logging.getLogger("robo")
    for h in list(log.handlers):
        if isinstance(h, RegistroErros) and str(h.cfg.logs) != chave:
            log.removeHandler(h)
    if chave not in _instalado or _instalado[chave] not in log.handlers:
        _instalado[chave] = RegistroErros(cfg)
        log.addHandler(_instalado[chave])


def listar(cfg, limite: int = 200) -> list[dict]:
    with _tb(cfg).tx() as c:
        return [dict(r) for r in c.execute("SELECT * FROM erros_sistema ORDER BY ultima DESC LIMIT ?", (limite,))]


def marcar_resolvido(cfg, id_erro: int, quem: str = "dono") -> None:
    tb = _tb(cfg)
    with tb.tx() as c:
        c.execute("UPDATE erros_sistema SET estado='resolvido' WHERE id=?", (int(id_erro),))
    tb.lembrar("erro_resolvido", str(id_erro), f"{quem} marcou o erro {id_erro} como resolvido", quem)
