"""Rotinas da empresa: o que roda sozinho, quando rodou, quem é o responsável e o que aconteceu.

A empresa só trabalha com o notebook aberto. Por isso:
  - cada rotina tem a última execução GRAVADA (logs/trabalho.db), e não só na memória do programa;
  - ao abrir o notebook, o robô vê quanto tempo ficou desligado, roda primeiro o que ficou atrasado e publica um
    resumo de abertura no canal (#geral), dito pela Renata (gerente de operações);
  - cada abertura e fechamento vira uma sessão (com "batimento" a cada 15 s, para saber quando o notebook fechou
    mesmo sem desligar o robô direito).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timedelta

from robo.trabalho import Trabalho, _agora

# nome → (responsável, o que faz, intervalo em horas para considerar "atrasada")
ROTINAS = {
    "ronda_ti": ("coord_devops", "Ronda de TI: disco, pastas, dependências, segurança e logs", 0.5),
    "estrategia": ("ger_operacoes", "Backlog da sprint, avaliação técnica e treinamento (a cada 15 dias)", 24 * 15),
    "backup": ("dba", "Backup do PostgreSQL (guarda os 7 últimos)", 24),
    "memoria_pg": ("dba", "Cópia da memória de todos os funcionários para o PostgreSQL", 1),
    "pdca": ("ger_operacoes", "Etapa C do PDCA: o que foi corrigido e não voltou vira boa prática", 1),
    "estudo": ("canal_helena", "Rodada de estudo de todos os funcionários (2x por semana)", 84),
    "reuniao": ("ger_operacoes", "Reunião semanal da liderança, andar por andar", 24 * 7),
    "auditoria": ("dir_dados", "Auditoria por amostragem dos heads (confiança nos resultados)", 24 * 7),
    "laboratorio": ("head_engenharia", "Laboratório: treino com planilhas sintéticas de várias áreas, no Excel e no PostgreSQL", 1 / 6),
    "canal": ("canal_nina", "Posta no canal o que aconteceu (aprovações, reprovações, entregas)", 1 / 60),
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS rotinas_execucoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, inicio TEXT, fim TEXT, segundos REAL, status TEXT, detalhe TEXT);
CREATE INDEX IF NOT EXISTS ix_rotina_nome ON rotinas_execucoes(nome, id);
CREATE TABLE IF NOT EXISTS rotinas_estado (
  nome TEXT PRIMARY KEY, ultima_verificacao TEXT, ultima_execucao TEXT, ultimo_status TEXT, detalhe TEXT);
CREATE TABLE IF NOT EXISTS sessoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, aberto_em TEXT, ultimo_batimento TEXT, desligado_antes_horas REAL, briefing TEXT);
"""


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
    return tb


@contextmanager
def _medir():
    t = time.perf_counter()
    yield lambda: round(time.perf_counter() - t, 2)


def executar(cfg, nome: str, funcao) -> object:
    """Roda a rotina e registra. Resultado vazio/None = 'em dia' (nada a fazer agora): só atualiza a verificação.
    Erro nunca derruba o robô: fica registrado com o motivo."""
    tb = _tb(cfg)
    inicio = _agora()
    status, detalhe, r = "fez", "", None
    with _medir() as seg:
        try:
            r = funcao()
            if not r:
                status = "em_dia"
            else:
                detalhe = _resumo(r)
        except Exception as e:
            status, detalhe = "erro", f"{type(e).__name__}: {e}"
        segundos = seg()
    with tb.tx() as c:
        if status != "em_dia":
            c.execute("INSERT INTO rotinas_execucoes (nome, inicio, fim, segundos, status, detalhe) VALUES (?,?,?,?,?,?)",
                      (nome, inicio, _agora(), segundos, status, detalhe[:1000]))
        anterior = c.execute("SELECT ultima_execucao FROM rotinas_estado WHERE nome=?", (nome,)).fetchone()
        ultima_exec = inicio if status == "fez" else (anterior["ultima_execucao"] if anterior else None)
        c.execute("INSERT INTO rotinas_estado (nome, ultima_verificacao, ultima_execucao, ultimo_status, detalhe) "
                  "VALUES (?,?,?,?,?) ON CONFLICT(nome) DO UPDATE SET ultima_verificacao=excluded.ultima_verificacao, "
                  "ultima_execucao=excluded.ultima_execucao, ultimo_status=excluded.ultimo_status, "
                  "detalhe=CASE WHEN excluded.detalhe <> '' THEN excluded.detalhe ELSE rotinas_estado.detalhe END",
                  (nome, inicio, ultima_exec, status, detalhe[:1000]))
    if status == "erro":
        try:
            from robo import memoria
            memoria.handover(cfg, f"Rotina {nome} não conseguiu concluir: {detalhe}", "rotinas", ROTINAS.get(nome, ("dev_pleno",))[0], tb=tb)
            memoria.experiencia(cfg, ROTINAS.get(nome, ("dev_pleno",))[0], "erro", f"Rotina {nome} falhou", "rotina", "", detalhe, tb)
        except Exception:
            pass
    return r


def _resumo(r) -> str:
    if isinstance(r, dict):
        partes = [f"{k}: {v}" for k, v in r.items() if isinstance(v, (int, float, str, bool)) and len(str(v)) < 80]
        return "; ".join(partes[:6])
    if isinstance(r, (list, tuple)):
        return f"{len(r)} item(ns)"
    return str(r)[:300]


def estado(cfg) -> list[dict]:
    """Situação de cada rotina: última execução, status e se está atrasada."""
    tb = _tb(cfg)
    with tb.tx() as c:
        linhas = {r["nome"]: dict(r) for r in c.execute("SELECT * FROM rotinas_estado")}
    agora = datetime.now()
    saida = []
    for nome, (resp, descricao, horas) in ROTINAS.items():
        r = linhas.get(nome, {})
        ultima = r.get("ultima_execucao")
        verif = r.get("ultima_verificacao")
        referencia = verif or ultima
        atrasada = not referencia or datetime.fromisoformat(referencia) < agora - timedelta(hours=horas * 1.5)
        saida.append({"nome": nome, "responsavel": resp, "descricao": descricao, "intervalo_horas": horas,
                      "ultima_execucao": ultima, "ultima_verificacao": verif, "ultimo_status": r.get("ultimo_status"),
                      "detalhe": r.get("detalhe") or "", "atrasada": atrasada})
    return saida


def execucoes(cfg, nome: str | None = None, limite: int = 100) -> list[dict]:
    tb = _tb(cfg)
    sql, args = "SELECT * FROM rotinas_execucoes", []
    if nome:
        sql += " WHERE nome=?"
        args.append(nome)
    with tb.tx() as c:
        return [dict(r) for r in c.execute(sql + " ORDER BY id DESC LIMIT ?", args + [limite])]


# --------------------------------------------------------------------------- sessões (notebook aberto/fechado)
def abrir_sessao(cfg, fila: int = 0) -> dict:
    """Chamado ao abrir o robô. Calcula quanto tempo ficou desligado e monta o resumo de abertura."""
    tb = _tb(cfg)
    with tb.tx() as c:
        anterior = c.execute("SELECT * FROM sessoes ORDER BY id DESC LIMIT 1").fetchone()
    agora = datetime.now()
    horas = None
    if anterior and anterior["ultimo_batimento"]:
        horas = round((agora - datetime.fromisoformat(anterior["ultimo_batimento"])).total_seconds() / 3600, 1)
    atrasadas = [r for r in estado(cfg) if r["atrasada"] and r["nome"] != "canal"]
    partes = []
    if horas is None:
        partes.append("Primeira abertura registrada do robô neste computador.")
    else:
        partes.append(f"O robô ficou desligado por {_duracao(horas)} (desde {anterior['ultimo_batimento'][:16].replace('T', ' ')}).")
    partes.append(f"{fila} arquivo(s) esperando em Bases-Limpeza — entram na fila agora." if fila
                  else "Nenhum arquivo esperando em Bases-Limpeza.")
    if atrasadas:
        partes.append("Rotinas que ficaram para trás e rodam agora: " + ", ".join(r["nome"] for r in atrasadas) + ".")
    else:
        partes.append("Todas as rotinas estão em dia.")
    briefing = " ".join(partes)
    with tb.tx() as c:
        cur = c.execute("INSERT INTO sessoes (aberto_em, ultimo_batimento, desligado_antes_horas, briefing) VALUES (?,?,?,?)",
                        (_agora(), _agora(), horas, briefing))
        sid = cur.lastrowid
    return {"sessao": sid, "desligado_horas": horas, "atrasadas": [r["nome"] for r in atrasadas], "fila": fila,
            "briefing": briefing}


def batimento(cfg, sessao: int) -> None:
    tb = _tb(cfg)
    with tb.tx() as c:
        c.execute("UPDATE sessoes SET ultimo_batimento=? WHERE id=?", (_agora(), sessao))


def sessoes(cfg, limite: int = 20) -> list[dict]:
    tb = _tb(cfg)
    with tb.tx() as c:
        linhas = [dict(r) for r in c.execute("SELECT * FROM sessoes ORDER BY id DESC LIMIT ?", (limite,))]
    for s in linhas:
        a, b = datetime.fromisoformat(s["aberto_em"]), datetime.fromisoformat(s["ultimo_batimento"])
        s["horas_ligado"] = round((b - a).total_seconds() / 3600, 2)
    return linhas


def _duracao(horas: float) -> str:
    if horas < 1:
        return f"{int(horas * 60)} minuto(s)"
    if horas < 48:
        return f"{horas:.1f} hora(s)".replace(".", ",")
    return f"{horas / 24:.1f} dia(s)".replace(".", ",")
