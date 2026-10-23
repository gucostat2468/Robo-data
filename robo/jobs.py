"""Prova de trabalho: todo processamento de verdade abre um JOB, e cada etapa dele fica registrada com quem fez.

Por que existe: antes, o painel dizia "trabalhando" para quem tivesse QUALQUER registro nas últimas 2 horas — inclusive
o batimento automático de uma rotina. Parecia que todo mundo trabalhava sem estar. Agora a regra é:

  - só existe "trabalhando" se houver um job ABERTO com uma etapa em execução daquela pessoa (nos últimos 15 min);
  - rotina no prazo, sem job aberto, é "plantão" — e plantão NÃO é trabalho;
  - todo job fechado guarda a evidência (arquivo, linhas, hash da saída, caminho) e nunca mais pode ser alterado.

Tipos de job: "planilha" (esteira: real ou sintética), "treino" (rodada de treino), "laboratorio", "rotina".
Origem: "real" (planilha que chegou de fora), "sintetico" (fábrica/laboratório/treino) ou "rotina".
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from robo.trabalho import Trabalho, _agora

ESQUEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT, origem TEXT, arquivo TEXT, inicio TEXT, fim TEXT, estado TEXT,
  funcionario TEXT, evidencia TEXT, hash_saida TEXT);
CREATE INDEX IF NOT EXISTS ix_jobs_estado ON jobs(estado, inicio);
CREATE TABLE IF NOT EXISTS jobs_etapas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER, etapa TEXT, funcionario TEXT, inicio TEXT, fim TEXT, ok INTEGER,
  detalhe TEXT, evidencia TEXT);
CREATE INDEX IF NOT EXISTS ix_jobs_etapas_job ON jobs_etapas(job_id);
CREATE INDEX IF NOT EXISTS ix_jobs_etapas_pessoa ON jobs_etapas(funcionario, inicio);
CREATE TRIGGER IF NOT EXISTS jobs_fechado_nao_muda BEFORE UPDATE ON jobs WHEN OLD.fim IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'registro permanente: job fechado não pode ser alterado'); END;
CREATE TRIGGER IF NOT EXISTS jobs_etapas_fechada_nao_muda BEFORE UPDATE ON jobs_etapas WHEN OLD.fim IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'registro permanente: etapa fechada não pode ser alterada'); END;
"""
TRABALHANDO_MIN = 15          # etapa aberta há menos disso = trabalhando agora
ABANDONO_H = 6                # job aberto há mais disso (o programa caiu no meio) = abandonado

_prontos: set[str] = set()


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    chave = str(Path(cfg.logs).resolve())
    if chave not in _prontos:
        from robo.trabalho import proteger
        with tb.tx() as c:
            c.executescript(ESQUEMA)
            proteger(c)
        _prontos.add(chave)
    return tb


def _j(v) -> str:
    return json.dumps(v if v is not None else {}, ensure_ascii=False, default=str)


def hash_arquivo(caminho) -> str | None:
    try:
        h = hashlib.sha256()
        with open(caminho, "rb") as f:
            for bloco in iter(lambda: f.read(1 << 20), b""):
                h.update(bloco)
        return h.hexdigest()
    except OSError:
        return None


# ------------------------------------------------------------------------------------------------ escrever
def abrir(cfg, tipo: str, origem: str, arquivo: str | None = None, funcionario: str | None = None) -> int:
    with _tb(cfg).tx() as c:
        return c.execute("INSERT INTO jobs (tipo, origem, arquivo, inicio, estado, funcionario) VALUES (?,?,?,?,?,?)",
                         (tipo, origem, arquivo, _agora(), "aberto", funcionario)).lastrowid


def etapa(cfg, job_id: int, nome: str, funcionario: str | None) -> int:
    """Começa uma etapa. A etapa anterior ainda aberta do mesmo job é encerrada como feita (a esteira passou dela)."""
    agora = _agora()
    with _tb(cfg).tx() as c:
        c.execute("UPDATE jobs_etapas SET fim=?, ok=1 WHERE job_id=? AND fim IS NULL", (agora, job_id))
        return c.execute("INSERT INTO jobs_etapas (job_id, etapa, funcionario, inicio) VALUES (?,?,?,?)",
                         (job_id, nome, funcionario, agora)).lastrowid


def fechar_etapa(cfg, etapa_id: int, ok: bool, detalhe: str = "", evidencia: dict | None = None) -> None:
    with _tb(cfg).tx() as c:
        c.execute("UPDATE jobs_etapas SET fim=?, ok=?, detalhe=?, evidencia=? WHERE id=? AND fim IS NULL",
                  (_agora(), int(bool(ok)), detalhe, _j(evidencia), etapa_id))


def fechar(cfg, job_id: int, estado: str, evidencia: dict | None = None, hash_saida: str | None = None) -> None:
    """estado: concluido | falhou | abandonado. Fecha também as etapas que ficaram abertas."""
    agora = _agora()
    with _tb(cfg).tx() as c:
        c.execute("UPDATE jobs_etapas SET fim=?, ok=? WHERE job_id=? AND fim IS NULL", (agora, int(estado == "concluido"), job_id))
        c.execute("UPDATE jobs SET fim=?, estado=?, evidencia=?, hash_saida=? WHERE id=? AND fim IS NULL",
                  (agora, estado, _j(evidencia), hash_saida, job_id))


@contextmanager
def job(cfg, tipo: str, origem: str, arquivo: str | None = None, funcionario: str | None = None):
    """Uso: with jobs.job(cfg, "treino", "sintetico", funcionario="casos_planejamento") as j: j.etapa(...); j.evidencia[...]"""
    jid = abrir(cfg, tipo, origem, arquivo, funcionario)
    ctl = _Controle(cfg, jid)
    try:
        yield ctl
    except BaseException as e:
        fechar(cfg, jid, "falhou", {**ctl.evidencia, "erro": f"{type(e).__name__}: {e}"}, ctl.hash_saida)
        raise
    fechar(cfg, jid, ctl.estado or "concluido", ctl.evidencia, ctl.hash_saida)


class _Controle:
    def __init__(self, cfg, job_id: int):
        self.cfg, self.id = cfg, job_id
        self.evidencia: dict = {}
        self.hash_saida: str | None = None
        self.estado: str | None = None
        self._etapa: int | None = None

    def etapa(self, nome: str, funcionario: str | None) -> int:
        self._etapa = etapa(self.cfg, self.id, nome, funcionario)
        return self._etapa

    def fechar_etapa(self, ok: bool, detalhe: str = "", evidencia: dict | None = None) -> None:
        if self._etapa:
            fechar_etapa(self.cfg, self._etapa, ok, detalhe, evidencia)
            self._etapa = None


def registrar_concluido(cfg, tipo: str, origem: str, funcionario: str | None, inicio: str, etapas: list[dict],
                        estado: str = "concluido", arquivo: str | None = None, evidencia: dict | None = None) -> int:
    """Trabalho curto que já terminou (rotina, exercício do laboratório): grava o job JÁ FECHADO, com início e fim reais
    e cada etapa com quem fez. etapas: [{etapa, funcionario, ok, detalhe, evidencia, inicio?}]."""
    fim = _agora()
    with _tb(cfg).tx() as c:
        jid = c.execute("INSERT INTO jobs (tipo, origem, arquivo, inicio, fim, estado, funcionario, evidencia) VALUES (?,?,?,?,?,?,?,?)",
                        (tipo, origem, arquivo, inicio, fim, estado, funcionario, _j(evidencia))).lastrowid
        for e in etapas:
            c.execute("INSERT INTO jobs_etapas (job_id, etapa, funcionario, inicio, fim, ok, detalhe, evidencia) VALUES (?,?,?,?,?,?,?,?)",
                      (jid, e.get("etapa"), e.get("funcionario"), e.get("inicio") or inicio, fim, int(bool(e.get("ok"))),
                       str(e.get("detalhe") or ""), _j(e.get("evidencia"))))
    return jid


def marcar_abandonados(cfg, agora: datetime | None = None) -> int:
    """Job aberto há mais de 6 h é de um programa que caiu no meio: fica registrado como abandonado (não some)."""
    limite = ((agora or datetime.now()) - timedelta(hours=ABANDONO_H)).isoformat(timespec="seconds")
    with _tb(cfg).tx() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM jobs WHERE fim IS NULL AND inicio < ?", (limite,))]
    for i in ids:
        fechar(cfg, i, "abandonado", {"motivo": f"ficou aberto mais de {ABANDONO_H} h (o programa provavelmente caiu)"})
    return len(ids)


# ------------------------------------------------------------------------------------------------ ler
def trabalhando_agora(cfg, agora: datetime | None = None) -> dict[str, dict]:
    """pid → etapa aberta (job, etapa, arquivo, desde). Só conta etapa ABERTA iniciada há menos de 15 min."""
    desde = ((agora or datetime.now()) - timedelta(minutes=TRABALHANDO_MIN)).isoformat(timespec="seconds")
    with _tb(cfg).tx() as c:
        linhas = c.execute(
            "SELECT e.funcionario, e.etapa, e.inicio, j.id AS job, j.tipo, j.origem, j.arquivo FROM jobs_etapas e "
            "JOIN jobs j ON j.id = e.job_id WHERE e.fim IS NULL AND j.fim IS NULL AND e.inicio >= ? "
            "AND e.funcionario IS NOT NULL ORDER BY e.inicio", (desde,)).fetchall()
    return {r["funcionario"]: dict(r) for r in linhas}


def ultima_evidencia(cfg) -> dict[str, dict]:
    """pid → última etapa FECHADA com a evidência do job (arquivo, linhas, hash, caminho). É a prova auditável."""
    with _tb(cfg).tx() as c:
        linhas = c.execute(
            "SELECT * FROM (SELECT e.funcionario, e.etapa, e.fim, e.ok, e.detalhe, e.evidencia AS ev_etapa, j.id AS job, j.tipo, "
            "j.origem, j.arquivo, j.estado, j.evidencia AS ev_job, j.hash_saida, ROW_NUMBER() OVER (PARTITION BY e.funcionario "
            "ORDER BY e.fim DESC) rn FROM jobs_etapas e JOIN jobs j ON j.id = e.job_id WHERE e.fim IS NOT NULL "
            "AND e.funcionario IS NOT NULL) WHERE rn = 1").fetchall()
    saida = {}
    for r in linhas:
        d = dict(r)
        d.pop("rn", None)
        for k in ("ev_etapa", "ev_job"):
            try:
                d[k] = json.loads(d[k]) if d[k] else {}
            except ValueError:
                d[k] = {}
        saida[d["funcionario"]] = d
    return saida


def resumo(cfg, agora: datetime | None = None) -> dict:
    """Para o topo do escritório: quem trabalha AGORA e há quanto tempo a última planilha foi processada."""
    agora = agora or datetime.now()
    with _tb(cfg).tx() as c:
        ult = c.execute("SELECT fim, origem, arquivo, estado FROM jobs WHERE tipo='planilha' AND fim IS NOT NULL "
                        "ORDER BY fim DESC LIMIT 1").fetchone()
        ult_real = c.execute("SELECT fim, arquivo FROM jobs WHERE tipo='planilha' AND origem='real' AND fim IS NOT NULL "
                             "ORDER BY fim DESC LIMIT 1").fetchone()
        abertos = c.execute("SELECT COUNT(*) FROM jobs WHERE fim IS NULL").fetchone()[0]

    def minutos(r):
        return round((agora - datetime.fromisoformat(r["fim"])).total_seconds() / 60) if r else None
    return {"trabalhando_agora": len(trabalhando_agora(cfg, agora)), "jobs_abertos": abertos,
            "ultima_planilha_min": minutos(ult), "ultima_planilha": dict(ult) if ult else None,
            "ultima_planilha_real_min": minutos(ult_real), "ultima_planilha_real": dict(ult_real) if ult_real else None}
