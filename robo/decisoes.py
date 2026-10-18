"""Decisões de reunião: o que foi decidido tem dono, prazo e critério de pronto — e é cobrado até ser cumprido.

Regras (para a reunião não ser só troca de ideias):
  - decisão só é registrada com DONO (alguém da empresa), PRAZO (de hoje a 180 dias) e CRITÉRIO DE PRONTO (como se
    verifica que foi feito). Sem isso, o registro é recusado com o motivo;
  - decisão de reunião de andar vira tarefa na central (com plano, revisão independente e aprovação quando altera dado);
    o plano de ação da reunião semanal vira decisão ligada ao handover de origem;
  - a situação é apurada pelos REGISTROS, nunca declarada: cumprida = a tarefa foi concluída e revisada (ou o handover
    foi verificado pelo PDCA); atrasada = passou do prazo sem isso;
  - toda reunião de andar abre cobrando as decisões abertas do andar; decisão atrasada precisa ser TRATADA na reunião
    (repactuar com novo prazo e motivo, ou cancelar com motivo — só você decide) ou a reunião não encerra sem uma
    justificativa registrada;
  - nada é apagado: decisoes (protegida) e decisoes_eventos (imutável: criada, situação, cobrada, repactuada, cancelada).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from robo import organizacao
from robo.trabalho import Trabalho, _agora, novo_id, proteger

ESQUEMA = """
CREATE TABLE IF NOT EXISTS decisoes (
  id TEXT PRIMARY KEY, criada_em TEXT, origem TEXT, reuniao_id TEXT, andar INTEGER, texto TEXT, dono TEXT, prazo TEXT,
  criterio TEXT, vinculo_tipo TEXT, vinculo_id TEXT, registrada_por TEXT, estado TEXT DEFAULT 'em_andamento',
  estado_em TEXT, evidencia TEXT, repactuacoes INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_dec_andar ON decisoes(andar, estado);
CREATE TABLE IF NOT EXISTS decisoes_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, decisao_id TEXT, data_hora TEXT, tipo TEXT, de TEXT, para TEXT, quem TEXT,
  reuniao_id TEXT, detalhe TEXT);
CREATE TRIGGER IF NOT EXISTS decisoes_eventos_imutavel BEFORE UPDATE ON decisoes_eventos
BEGIN SELECT RAISE(ABORT, 'histórico de decisão não muda'); END;
"""
ESTADOS = {"em_andamento": "Em andamento", "atrasada": "Atrasada", "cumprida": "Cumprida", "cancelada": "Cancelada"}
ABERTOS = ("em_andamento", "atrasada")
PRAZO_MAXIMO_DIAS = 180
_prontos: set[str] = set()


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    if str(tb.arquivo) not in _prontos or not tb.arquivo.exists():
        with tb.tx() as c:
            c.executescript(ESQUEMA)
            proteger(c)
        _prontos.add(str(tb.arquivo))
    return tb


def _evento(c, did: str, tipo: str, de, para, quem: str, reuniao_id: str = "", detalhe: str = "") -> None:
    c.execute("INSERT INTO decisoes_eventos (decisao_id, data_hora, tipo, de, para, quem, reuniao_id, detalhe) "
              "VALUES (?,?,?,?,?,?,?,?)", (did, _agora(), tipo, de, para, quem, reuniao_id or "", (detalhe or "")[:1000]))


def ler_prazo(prazo) -> date:
    texto = str(prazo or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    raise ValueError("Prazo inválido: use dd/mm/aaaa.")


def validar(cfg, texto: str, dono: str, prazo, criterio: str, hoje: date | None = None) -> date:
    hoje = hoje or date.today()
    if len((texto or "").strip()) < 15:
        raise ValueError("Decisão vaga: escreva o que será feito (pelo menos 15 caracteres).")
    if dono not in organizacao.por_id(cfg):
        raise ValueError("Toda decisão precisa de um dono da empresa (quem vai fazer).")
    p = ler_prazo(prazo)
    if p < hoje:
        raise ValueError("O prazo não pode estar no passado.")
    if p > hoje + timedelta(days=PRAZO_MAXIMO_DIAS):
        raise ValueError(f"Prazo longo demais (mais de {PRAZO_MAXIMO_DIAS} dias): quebre em entregas menores.")
    if len((criterio or "").strip()) < 10 or criterio.strip().lower() == texto.strip().lower():
        raise ValueError("Diga como vamos verificar que ficou pronto (critério de pronto), diferente do texto da decisão.")
    return p


def registrar(cfg, texto: str, dono: str, prazo, criterio: str, andar: int | None, reuniao_id: str, origem: str = "sala",
              registrada_por: str = "dono", vinculo: tuple[str, str] | None = None) -> dict:
    p = validar(cfg, texto, dono, prazo, criterio)
    tb = _tb(cfg)
    if vinculo is None:  # decisão de reunião de andar: vira tarefa de verdade na central
        from robo import orquestrador
        sid = orquestrador.criar(cfg, f"{texto.strip()} — prazo {p:%d/%m/%Y}; pronto quando: {criterio.strip()}", dono,
                                 origem="reuniao")
        vinculo = ("solicitacao", sid)
    did = novo_id("DEC")
    with tb.tx() as c:
        c.execute("INSERT INTO decisoes (id, criada_em, origem, reuniao_id, andar, texto, dono, prazo, criterio, vinculo_tipo, "
                  "vinculo_id, registrada_por, estado, estado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (did, _agora(), origem, reuniao_id, andar, texto.strip()[:600], dono, p.isoformat(), criterio.strip()[:400],
                   vinculo[0], vinculo[1], registrada_por, "em_andamento", _agora()))
        _evento(c, did, "criada", None, "em_andamento", registrada_por, reuniao_id,
                json.dumps({"dono": dono, "prazo": p.isoformat(), "criterio": criterio.strip()[:400],
                            "vinculo": list(vinculo)}, ensure_ascii=False))
    return {"id": did, "prazo": p.isoformat(), "vinculo": list(vinculo)}


def _apurar(cfg, d: dict, hoje: date) -> tuple[str, str]:
    """Situação pelos registros: tarefa concluída e revisada, ou handover verificado = cumprida."""
    if d["estado"] == "cancelada":
        return "cancelada", d.get("evidencia") or ""
    if d["vinculo_tipo"] == "solicitacao":
        s = Trabalho(cfg).solicitacao(d["vinculo_id"])
        if s and s["estado"] in ("concluida", "concluida_parcialmente"):
            rev = (s.get("revisao") or {}).get("revisor")
            return "cumprida", f"tarefa {s['id']} {s['estado_nome'].lower()}" + (f", revisada por {rev}" if rev else "")
        if s and s["estado"] == "cancelada":
            return "cancelada", f"tarefa {s['id']} cancelada na central"
    elif d["vinculo_tipo"] == "handover":
        with Trabalho(cfg).tx() as c:
            h = c.execute("SELECT estado FROM handovers WHERE id=?", (d["vinculo_id"],)).fetchone()
        if h and h["estado"] == "verificado":
            return "cumprida", f"handover {d['vinculo_id']} verificado pelo PDCA (o erro não voltou)"
    return ("atrasada" if hoje > date.fromisoformat(d["prazo"]) else "em_andamento"), ""


def atualizar(cfg, hoje: date | None = None) -> list[dict]:
    """Recalcula a situação das decisões abertas e registra cada mudança. Devolve as que mudaram."""
    hoje = hoje or date.today()
    tb = _tb(cfg)
    with tb.tx() as c:
        abertas = [dict(r) for r in c.execute("SELECT * FROM decisoes WHERE estado IN ('em_andamento','atrasada')")]
    mudou = []
    for d in abertas:
        novo, evid = _apurar(cfg, d, hoje)
        if novo != d["estado"]:
            with tb.tx() as c:
                c.execute("UPDATE decisoes SET estado=?, estado_em=?, evidencia=? WHERE id=?", (novo, _agora(), evid, d["id"]))
                _evento(c, d["id"], "situacao", d["estado"], novo, "robo", "", evid or f"prazo {d['prazo']}")
            mudou.append({**d, "estado": novo, "evidencia": evid})
    return mudou


def listar(cfg, andar: int | None = None, abertas: bool = False, limite: int = 200) -> list[dict]:
    sql, args = "SELECT * FROM decisoes WHERE 1=1", []
    if andar:
        sql += " AND andar=?"
        args.append(int(andar))
    if abertas:
        sql += " AND estado IN ('em_andamento','atrasada')"
    with _tb(cfg).tx() as c:
        linhas = [dict(r) for r in c.execute(sql + " ORDER BY prazo, criada_em LIMIT ?", args + [limite])]
    gente = organizacao.por_id(cfg)
    hoje = date.today()
    for d in linhas:
        d["dono_nome"] = (gente.get(d["dono"]) or {}).get("nome", d["dono"])
        d["estado_nome"] = ESTADOS.get(d["estado"], d["estado"])
        d["dias_para_o_prazo"] = (date.fromisoformat(d["prazo"]) - hoje).days
    return linhas


def eventos(cfg, did: str) -> list[dict]:
    with _tb(cfg).tx() as c:
        return [dict(r) for r in c.execute("SELECT * FROM decisoes_eventos WHERE decisao_id=? ORDER BY id", (did,))]


def _aberta(c, did: str) -> dict:
    d = c.execute("SELECT * FROM decisoes WHERE id=?", (did,)).fetchone()
    if not d:
        raise ValueError("Decisão não existe.")
    if d["estado"] not in ABERTOS:
        raise ValueError(f"Esta decisão já está {ESTADOS.get(d['estado'], d['estado']).lower()}.")
    return dict(d)


def cobrar(cfg, did: str, reuniao_id: str, quem: str, situacao: str) -> None:
    with _tb(cfg).tx() as c:
        _evento(c, did, "cobrada", None, None, quem, reuniao_id, situacao)


def repactuar(cfg, did: str, novo_prazo, motivo: str, reuniao_id: str, quem: str = "dono") -> dict:
    """Novo prazo, sempre com motivo e só por você (quem cobra não é quem se dá mais prazo)."""
    if quem != "dono":
        raise PermissionError("Só o dono repactua o prazo de uma decisão.")
    if len((motivo or "").strip()) < 10:
        raise ValueError("Repactuar exige o motivo (o que mudou).")
    p = ler_prazo(novo_prazo)
    if p <= date.today() or p > date.today() + timedelta(days=PRAZO_MAXIMO_DIAS):
        raise ValueError(f"O novo prazo precisa ser depois de hoje e em até {PRAZO_MAXIMO_DIAS} dias.")
    with _tb(cfg).tx() as c:
        d = _aberta(c, did)
        c.execute("UPDATE decisoes SET prazo=?, estado='em_andamento', estado_em=?, repactuacoes=repactuacoes+1 WHERE id=?",
                  (p.isoformat(), _agora(), did))
        _evento(c, did, "repactuada", d["prazo"], p.isoformat(), quem, reuniao_id, motivo.strip())
    return {"ok": True, "prazo": p.isoformat()}


def cancelar(cfg, did: str, motivo: str, reuniao_id: str, quem: str = "dono") -> dict:
    if quem != "dono":
        raise PermissionError("Só o dono cancela uma decisão.")
    if len((motivo or "").strip()) < 10:
        raise ValueError("Cancelar exige o motivo.")
    with _tb(cfg).tx() as c:
        d = _aberta(c, did)
        c.execute("UPDATE decisoes SET estado='cancelada', estado_em=?, evidencia=? WHERE id=?", (_agora(), motivo.strip(), did))
        _evento(c, did, "cancelada", d["estado"], "cancelada", quem, reuniao_id, motivo.strip())
    return {"ok": True}


def nao_tratadas(cfg, andar: int, reuniao_id: str) -> list[dict]:
    """Atrasadas do andar que esta reunião ainda não repactuou nem cancelou."""
    atualizar(cfg)
    tratadas = set()
    with _tb(cfg).tx() as c:
        for r in c.execute("SELECT decisao_id FROM decisoes_eventos WHERE reuniao_id=? AND tipo IN ('repactuada','cancelada')",
                           (reuniao_id,)):
            tratadas.add(r["decisao_id"])
    return [d for d in listar(cfg, andar, abertas=True) if d["estado"] == "atrasada" and d["id"] not in tratadas]


def resumo(cfg) -> dict:
    atualizar(cfg)
    with _tb(cfg).tx() as c:
        por = {r["estado"]: r["n"] for r in c.execute("SELECT estado, COUNT(*) n FROM decisoes GROUP BY estado")}
        no_prazo = c.execute("SELECT COUNT(*) FROM decisoes d WHERE estado='cumprida' AND substr(estado_em,1,10) <= prazo").fetchone()[0]
    feitas = por.get("cumprida", 0)
    return {"por_estado": por, "cumpridas_no_prazo": no_prazo,
            "pct_no_prazo": round(100 * no_prazo / feitas, 1) if feitas else None}
