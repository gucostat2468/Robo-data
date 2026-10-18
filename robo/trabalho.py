"""Memória de trabalho da empresa: conversas, solicitações (tarefas e projetos), etapas, aprovações e histórico.

Uma única infraestrutura atende a ficha do funcionário, o canal, a central de solicitações, o contexto de um arquivo
e o acompanhamento de uma tarefa. Fica em SQLite (logs/trabalho.db) porque:
  - vem com o Python (nada para instalar) e funciona com o PostgreSQL desligado;
  - tem transações ACID: um pedido e o seu histórico entram juntos ou não entram;
  - sobrevive a reinício do computador (modo WAL, gravação confirmada em disco).
O PostgreSQL continua sendo o lugar dos DADOS das planilhas.

Tipos de solicitação:
  conversa — pergunta respondida na hora (fica registrada, mas não tem plano)
  tarefa   — objetivo com plano, etapas, responsáveis, aprovações e revisão
  projeto  — conjunto de tarefas com um objetivo maior
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

ESTADOS = {
    "recebida": "Recebida", "em_triagem": "Em triagem", "aguardando_esclarecimento": "Aguardando esclarecimento",
    "planejada": "Planejada", "aguardando_aprovacao": "Aguardando aprovação", "na_fila": "Na fila",
    "em_execucao": "Em execução", "aguardando_dependencia": "Aguardando dependência", "em_revisao": "Em revisão",
    "reprovada_revisao": "Reprovada na revisão", "em_correcao": "Em correção", "concluida": "Concluída",
    "concluida_parcialmente": "Concluída parcialmente", "bloqueada": "Bloqueada", "falhou": "Falhou", "cancelada": "Cancelada",
}
FINAIS = {"concluida", "concluida_parcialmente", "falhou", "cancelada"}
# transições permitidas (qualquer estado não final pode ser cancelado ou bloqueado)
TRANSICOES = {
    "recebida": {"em_triagem", "concluida", "falhou"},
    "em_triagem": {"aguardando_esclarecimento", "planejada", "concluida", "falhou"},
    "aguardando_esclarecimento": {"em_triagem", "planejada"},
    "planejada": {"aguardando_aprovacao", "na_fila"},
    "aguardando_aprovacao": {"na_fila", "planejada"},
    "na_fila": {"em_execucao"},
    "em_execucao": {"aguardando_dependencia", "aguardando_aprovacao", "em_revisao", "concluida", "concluida_parcialmente",
                    "falhou"},
    "aguardando_dependencia": {"em_execucao", "na_fila"},
    "em_revisao": {"concluida", "concluida_parcialmente", "reprovada_revisao"},
    "reprovada_revisao": {"em_correcao", "falhou"},
    "em_correcao": {"em_execucao", "em_revisao"},
    "bloqueada": {"na_fila", "planejada", "em_triagem"},
}
ESTADOS_ETAPA = {"pendente", "aguardando_dependencia", "aguardando_aprovacao", "em_execucao", "concluida", "falhou",
                 "bloqueada", "pulada", "cancelada"}
PRIORIDADES = {"alta": 1, "media": 2, "baixa": 3}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS conversas (
  id TEXT PRIMARY KEY, funcionario TEXT NOT NULL, titulo TEXT, origem TEXT, criada_em TEXT, atualizada_em TEXT,
  contexto TEXT DEFAULT '{}', arquivada INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS mensagens (
  id INTEGER PRIMARY KEY AUTOINCREMENT, conversa_id TEXT NOT NULL REFERENCES conversas(id), autor TEXT, texto TEXT,
  natureza TEXT, dados TEXT DEFAULT '{}', solicitacao_id TEXT, criada_em TEXT);
CREATE INDEX IF NOT EXISTS ix_msg_conversa ON mensagens(conversa_id, id);
CREATE TABLE IF NOT EXISTS arquivos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, conversa_id TEXT REFERENCES conversas(id), solicitacao_id TEXT, caminho TEXT,
  nome TEXT, criado_em TEXT);
CREATE TABLE IF NOT EXISTS solicitacoes (
  id TEXT PRIMARY KEY, tipo TEXT NOT NULL, titulo TEXT, pedido TEXT, origem TEXT, prioridade TEXT DEFAULT 'media',
  estado TEXT NOT NULL, funcionario TEXT, andar INTEGER, conversa_id TEXT, projeto_id TEXT, modelo TEXT,
  plano TEXT DEFAULT '{}', resultado TEXT DEFAULT '{}', revisor TEXT, revisao TEXT DEFAULT '{}', tentativas INTEGER DEFAULT 0,
  criada_em TEXT, atualizada_em TEXT);
CREATE INDEX IF NOT EXISTS ix_sol_estado ON solicitacoes(estado);
CREATE TABLE IF NOT EXISTS etapas (
  id TEXT PRIMARY KEY, solicitacao_id TEXT NOT NULL REFERENCES solicitacoes(id), ordem INTEGER, titulo TEXT,
  funcionario TEXT, ferramenta TEXT, parametros TEXT DEFAULT '{}', depende TEXT DEFAULT '[]', risco TEXT,
  precisa_aprovacao INTEGER DEFAULT 0, estado TEXT, natureza TEXT, resultado TEXT DEFAULT '{}', tentativas INTEGER DEFAULT 0,
  inicio TEXT, fim TEXT);
CREATE INDEX IF NOT EXISTS ix_etapa_sol ON etapas(solicitacao_id, ordem);
CREATE TABLE IF NOT EXISTS aprovacoes (
  id TEXT PRIMARY KEY, solicitacao_id TEXT NOT NULL REFERENCES solicitacoes(id), etapa_id TEXT, pedido TEXT, risco TEXT,
  solicitante TEXT, aprovador TEXT DEFAULT 'dono', estado TEXT DEFAULT 'pendente', decidido_por TEXT, decidido_em TEXT,
  motivo TEXT, criada_em TEXT);
CREATE TABLE IF NOT EXISTS eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, solicitacao_id TEXT, data_hora TEXT, tipo TEXT, quem TEXT, de TEXT, para TEXT,
  texto TEXT, dados TEXT DEFAULT '{}');
CREATE INDEX IF NOT EXISTS ix_evento_sol ON eventos(solicitacao_id, id);
CREATE TABLE IF NOT EXISTS artefatos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, solicitacao_id TEXT, etapa_id TEXT, caminho TEXT, tipo TEXT, descricao TEXT,
  criado_em TEXT);
CREATE TABLE IF NOT EXISTS experiencias (
  id INTEGER PRIMARY KEY AUTOINCREMENT, funcionario TEXT NOT NULL, data_hora TEXT, tipo TEXT, resumo TEXT, detalhe TEXT,
  origem TEXT, referencia TEXT, andar INTEGER);
CREATE INDEX IF NOT EXISTS ix_exp_func ON experiencias(funcionario, data_hora);
CREATE TABLE IF NOT EXISTS handovers (
  id TEXT PRIMARY KEY, chave TEXT UNIQUE, andar INTEGER, area TEXT, responsavel TEXT, detectado_por TEXT, erro TEXT,
  causa TEXT, regra TEXT, como_verificar TEXT, exemplo TEXT, recorrencias INTEGER DEFAULT 1, estado TEXT DEFAULT 'aberto',
  backlog_id TEXT, criado_em TEXT, ultima_ocorrencia TEXT, atualizado_em TEXT);
CREATE TABLE IF NOT EXISTS boas_praticas (
  id TEXT PRIMARY KEY, handover_id TEXT UNIQUE, andar INTEGER, area TEXT, responsavel TEXT, problema TEXT, pratica TEXT,
  como_verificar TEXT, evidencia TEXT, criada_em TEXT);
CREATE TABLE IF NOT EXISTS reunioes (
  id TEXT PRIMARY KEY, inicio TEXT, fim TEXT, data_hora TEXT, ata TEXT, arquivo TEXT);
CREATE TABLE IF NOT EXISTS memoria (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT, chave TEXT, texto TEXT, origem TEXT, solicitacao_id TEXT, criada_em TEXT);
CREATE TABLE IF NOT EXISTS handover_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, handover_id TEXT, data_hora TEXT, tipo TEXT, de TEXT, para TEXT, quem TEXT, detalhe TEXT);
CREATE INDEX IF NOT EXISTS ix_hev ON handover_eventos(handover_id, id);
CREATE TRIGGER IF NOT EXISTS handover_eventos_sem_alterar BEFORE UPDATE ON handover_eventos
BEGIN SELECT RAISE(ABORT, 'histórico de handover é imutável'); END;
"""
# registro é permanente: nenhuma destas tabelas aceita DELETE (o que muda, muda de estado — e o histórico fica)
TABELAS_PERMANENTES = ("experiencias", "handovers", "handover_eventos", "boas_praticas", "memoria", "reunioes", "conversas",
                       "mensagens", "solicitacoes", "etapas", "aprovacoes", "eventos")
ESQUEMA += "".join(f"""CREATE TRIGGER IF NOT EXISTS {t}_sem_apagar BEFORE DELETE ON {t}
BEGIN SELECT RAISE(ABORT, 'registro permanente: {t} não pode ser apagado'); END;
""" for t in TABELAS_PERMANENTES)
COLUNAS_NOVAS = {"boas_praticas": {"valida": "INTEGER DEFAULT 1", "invalidada_em": "TEXT", "motivo_invalidacao": "TEXT"}}
_prontos: set[str] = set()

_travas: dict[str, threading.RLock] = {}
_trava_global = threading.Lock()


class ErroTransicao(ValueError):
    pass


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _j(v) -> str:
    return json.dumps(v if v is not None else {}, ensure_ascii=False, default=str)


def _l(texto, padrao=None):
    try:
        return json.loads(texto) if texto else (padrao if padrao is not None else {})
    except (TypeError, json.JSONDecodeError):
        return padrao if padrao is not None else {}


def novo_id(prefixo: str) -> str:
    return f"{prefixo}-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6]}"


class Trabalho:
    """Acesso transacional ao trabalho.db. Uma instância por chamada é barata (abre e fecha a conexão)."""

    def __init__(self, cfg=None, arquivo: Path | None = None):
        self.arquivo = Path(arquivo) if arquivo else Path(cfg.logs) / "trabalho.db"
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        with _trava_global:
            self.trava = _travas.setdefault(str(self.arquivo.resolve()), threading.RLock())
        if str(self.arquivo.resolve()) not in _prontos or not self.arquivo.exists():  # esquema uma vez por banco
            with self.tx() as c:
                c.executescript(ESQUEMA)
                for tabela, colunas in COLUNAS_NOVAS.items():
                    existentes = {r[1] for r in c.execute(f"PRAGMA table_info({tabela})")}
                    for col, tipo in colunas.items():
                        if col not in existentes:
                            c.execute(f"ALTER TABLE {tabela} ADD COLUMN {col} {tipo}")
            _prontos.add(str(self.arquivo.resolve()))

    @contextmanager
    def tx(self):
        """Transação: tudo dentro do bloco é gravado junto, ou nada é gravado."""
        with self.trava:
            conn = sqlite3.connect(self.arquivo, timeout=30)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=FULL")
                conn.execute("PRAGMA foreign_keys=ON")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    # ------------------------------------------------------------------ eventos (histórico de tudo)
    def _evento(self, c, sid, tipo, texto, quem="", de=None, para=None, dados=None):
        c.execute("INSERT INTO eventos (solicitacao_id, data_hora, tipo, quem, de, para, texto, dados) VALUES (?,?,?,?,?,?,?,?)",
                  (sid, _agora(), tipo, quem, de, para, texto, _j(dados)))

    def evento(self, sid, tipo, texto, quem="", dados=None):
        with self.tx() as c:
            self._evento(c, sid, tipo, texto, quem, dados=dados)

    # ------------------------------------------------------------------ conversas
    def criar_conversa(self, funcionario: str, titulo: str = "", origem: str = "ficha", contexto: dict | None = None) -> str:
        cid = novo_id("CONV")
        with self.tx() as c:
            c.execute("INSERT INTO conversas (id, funcionario, titulo, origem, criada_em, atualizada_em, contexto) "
                      "VALUES (?,?,?,?,?,?,?)", (cid, funcionario, titulo, origem, _agora(), _agora(), _j(contexto or {})))
        return cid

    def conversa(self, cid: str) -> dict | None:
        with self.tx() as c:
            r = c.execute("SELECT * FROM conversas WHERE id=?", (cid,)).fetchone()
            if not r:
                return None
            msgs = [dict(m) | {"dados": _l(m["dados"])} for m in
                    c.execute("SELECT * FROM mensagens WHERE conversa_id=? ORDER BY id", (cid,))]
            arqs = [dict(a) for a in c.execute("SELECT * FROM arquivos WHERE conversa_id=? ORDER BY id", (cid,))]
        return dict(r) | {"contexto": _l(r["contexto"]), "mensagens": msgs, "arquivos": arqs}

    def conversas(self, funcionario: str | None = None, limite: int = 50) -> list[dict]:
        sql = ("SELECT c.*, (SELECT COUNT(*) FROM mensagens m WHERE m.conversa_id=c.id) AS mensagens, "
               "(SELECT texto FROM mensagens m WHERE m.conversa_id=c.id ORDER BY id DESC LIMIT 1) AS ultima "
               "FROM conversas c WHERE arquivada=0")
        args: list = []
        if funcionario:
            sql += " AND funcionario=?"
            args.append(funcionario)
        sql += " ORDER BY atualizada_em DESC LIMIT ?"
        with self.tx() as c:
            return [dict(r) | {"contexto": _l(r["contexto"])} for r in c.execute(sql, args + [int(limite)])]

    def mensagem(self, cid: str, autor: str, texto: str, natureza: str = "", dados: dict | None = None,
                 solicitacao_id: str | None = None) -> int:
        with self.tx() as c:
            cur = c.execute("INSERT INTO mensagens (conversa_id, autor, texto, natureza, dados, solicitacao_id, criada_em) "
                            "VALUES (?,?,?,?,?,?,?)", (cid, autor, texto, natureza, _j(dados), solicitacao_id, _agora()))
            c.execute("UPDATE conversas SET atualizada_em=? WHERE id=?", (_agora(), cid))
            return cur.lastrowid

    def atualizar_contexto(self, cid: str, **mudancas) -> dict:
        with self.tx() as c:
            r = c.execute("SELECT contexto FROM conversas WHERE id=?", (cid,)).fetchone()
            ctx = _l(r["contexto"]) if r else {}
            ctx.update(mudancas)
            c.execute("UPDATE conversas SET contexto=?, atualizada_em=? WHERE id=?", (_j(ctx), _agora(), cid))
        return ctx

    def anexar(self, cid: str | None, caminho: str, solicitacao_id: str | None = None) -> int:
        with self.tx() as c:
            cur = c.execute("INSERT INTO arquivos (conversa_id, solicitacao_id, caminho, nome, criado_em) VALUES (?,?,?,?,?)",
                            (cid, solicitacao_id, str(caminho), Path(caminho).name, _agora()))
            return cur.lastrowid

    # ------------------------------------------------------------------ solicitações
    def criar_solicitacao(self, tipo: str, titulo: str, pedido: str, origem: str = "manual", funcionario: str | None = None,
                          andar: int | None = None, prioridade: str = "media", conversa_id: str | None = None,
                          projeto_id: str | None = None, modelo: str | None = None, estado: str = "recebida",
                          resultado: dict | None = None) -> str:
        assert tipo in ("conversa", "tarefa", "projeto"), tipo
        prioridade = prioridade if prioridade in PRIORIDADES else "media"
        sid = novo_id({"conversa": "PERG", "tarefa": "TAR", "projeto": "PROJ"}[tipo])
        with self.tx() as c:
            c.execute("INSERT INTO solicitacoes (id, tipo, titulo, pedido, origem, prioridade, estado, funcionario, andar, "
                      "conversa_id, projeto_id, modelo, resultado, criada_em, atualizada_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (sid, tipo, titulo[:200], pedido, origem, prioridade, estado, funcionario, andar, conversa_id, projeto_id,
                       modelo, _j(resultado), _agora(), _agora()))
            self._evento(c, sid, "criada", f"{tipo.capitalize()} registrada ({origem})", "dono" if origem == "manual" else "robo",
                         para=estado)
        return sid

    def mudar_estado(self, sid: str, novo: str, quem: str = "robo", texto: str = "", **campos) -> None:
        if novo not in ESTADOS:
            raise ErroTransicao(f"estado desconhecido: {novo}")
        with self.tx() as c:
            r = c.execute("SELECT estado FROM solicitacoes WHERE id=?", (sid,)).fetchone()
            if not r:
                raise ErroTransicao(f"solicitação {sid} não existe")
            atual = r["estado"]
            permitido = TRANSICOES.get(atual, set()) | ({"cancelada", "bloqueada"} if atual not in FINAIS else set())
            if novo != atual and novo not in permitido:
                raise ErroTransicao(f"{sid}: não pode ir de '{ESTADOS[atual]}' para '{ESTADOS[novo]}'")
            sets = ["estado=?", "atualizada_em=?"]
            vals = [novo, _agora()]
            for k, v in campos.items():
                assert k in ("plano", "resultado", "revisao", "revisor", "tentativas", "funcionario", "titulo", "prioridade")
                sets.append(f"{k}=?")
                vals.append(_j(v) if isinstance(v, (dict, list)) else v)
            c.execute(f"UPDATE solicitacoes SET {', '.join(sets)} WHERE id=?", vals + [sid])
            self._evento(c, sid, "estado", texto or f"{ESTADOS[atual]} → {ESTADOS[novo]}", quem, de=atual, para=novo)

    def atualizar(self, sid: str, **campos) -> None:
        with self.tx() as c:
            for k, v in campos.items():
                assert k in ("plano", "resultado", "revisao", "revisor", "tentativas", "prioridade")
                c.execute(f"UPDATE solicitacoes SET {k}=?, atualizada_em=? WHERE id=?",
                          (_j(v) if isinstance(v, (dict, list)) else v, _agora(), sid))

    def solicitacao(self, sid: str) -> dict | None:
        with self.tx() as c:
            r = c.execute("SELECT * FROM solicitacoes WHERE id=?", (sid,)).fetchone()
            if not r:
                return None
            etapas = [dict(e) | {"parametros": _l(e["parametros"]), "depende": _l(e["depende"], []),
                                 "resultado": _l(e["resultado"])}
                      for e in c.execute("SELECT * FROM etapas WHERE solicitacao_id=? ORDER BY ordem", (sid,))]
            aprov = [dict(a) for a in c.execute("SELECT * FROM aprovacoes WHERE solicitacao_id=? ORDER BY criada_em", (sid,))]
            eventos = [dict(e) | {"dados": _l(e["dados"])}
                       for e in c.execute("SELECT * FROM eventos WHERE solicitacao_id=? ORDER BY id", (sid,))]
            artefatos = [dict(a) for a in c.execute("SELECT * FROM artefatos WHERE solicitacao_id=? ORDER BY id", (sid,))]
            arquivos = [dict(a) for a in c.execute("SELECT * FROM arquivos WHERE solicitacao_id=? ORDER BY id", (sid,))]
            filhas = [dict(f) for f in c.execute("SELECT id, titulo, estado FROM solicitacoes WHERE projeto_id=?", (sid,))]
        return (dict(r) | {"plano": _l(r["plano"]), "resultado": _l(r["resultado"]), "revisao": _l(r["revisao"]),
                           "estado_nome": ESTADOS.get(r["estado"], r["estado"]), "etapas": etapas, "aprovacoes": aprov,
                           "eventos": eventos, "artefatos": artefatos, "arquivos": arquivos, "tarefas": filhas})

    def listar(self, estado: str | None = None, funcionario: str | None = None, andar: int | None = None,
               tipo: str | None = None, prioridade: str | None = None, origem: str | None = None, dias: int | None = None,
               texto: str | None = None, limite: int = 200) -> list[dict]:
        sql, args = "SELECT * FROM solicitacoes WHERE 1=1", []
        for campo, valor in (("estado", estado), ("funcionario", funcionario), ("andar", andar), ("tipo", tipo),
                             ("prioridade", prioridade), ("origem", origem)):
            if valor not in (None, ""):
                sql += f" AND {campo}=?"
                args.append(valor)
        if dias:
            sql += " AND criada_em>=?"
            args.append((datetime.now() - timedelta(days=int(dias))).isoformat(timespec="seconds"))
        if texto:
            sql += " AND (titulo LIKE ? OR pedido LIKE ?)"
            args += [f"%{texto}%"] * 2
        sql += " ORDER BY criada_em DESC LIMIT ?"
        with self.tx() as c:
            linhas = [dict(r) for r in c.execute(sql, args + [int(limite)])]
            pend = {r["solicitacao_id"]: r["n"] for r in c.execute(
                "SELECT solicitacao_id, COUNT(*) n FROM aprovacoes WHERE estado='pendente' GROUP BY solicitacao_id")}
        for l in linhas:
            l["estado_nome"] = ESTADOS.get(l["estado"], l["estado"])
            l["aprovacoes_pendentes"] = pend.get(l["id"], 0)
            l.pop("plano", None)
            l["resultado"] = _l(l["resultado"])
            l.pop("revisao", None)
        return linhas

    def contagem(self) -> dict:
        with self.tx() as c:
            por_estado = {r["estado"]: r["n"] for r in c.execute("SELECT estado, COUNT(*) n FROM solicitacoes GROUP BY estado")}
            pend = c.execute("SELECT COUNT(*) FROM aprovacoes WHERE estado='pendente'").fetchone()[0]
        return {"por_estado": por_estado, "aprovacoes_pendentes": pend, "total": sum(por_estado.values())}

    # ------------------------------------------------------------------ etapas
    def criar_etapas(self, sid: str, etapas: list[dict]) -> list[str]:
        ids = []
        with self.tx() as c:
            for i, e in enumerate(etapas, 1):
                eid = e.get("id") or f"{sid}-E{i}"
                c.execute("INSERT INTO etapas (id, solicitacao_id, ordem, titulo, funcionario, ferramenta, parametros, depende, "
                          "risco, precisa_aprovacao, estado) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          (eid, sid, i, e["titulo"], e.get("funcionario"), e.get("ferramenta"), _j(e.get("parametros") or {}),
                           _j(e.get("depende") or []), e.get("risco", "baixo"), int(bool(e.get("precisa_aprovacao"))),
                           e.get("estado", "pendente")))
                ids.append(eid)
        return ids

    def atualizar_etapa(self, eid: str, quem: str = "robo", **campos) -> None:
        with self.tx() as c:
            r = c.execute("SELECT solicitacao_id, estado, titulo FROM etapas WHERE id=?", (eid,)).fetchone()
            if not r:
                raise ErroTransicao(f"etapa {eid} não existe")
            for k, v in campos.items():
                assert k in ("estado", "natureza", "resultado", "tentativas", "inicio", "fim", "funcionario", "parametros")
                if k == "estado":
                    assert v in ESTADOS_ETAPA, v
                c.execute(f"UPDATE etapas SET {k}=? WHERE id=?", (_j(v) if isinstance(v, (dict, list)) else v, eid))
            if "estado" in campos and campos["estado"] != r["estado"]:
                self._evento(c, r["solicitacao_id"], "etapa", f"Etapa “{r['titulo']}”: {r['estado']} → {campos['estado']}",
                             quem, de=r["estado"], para=campos["estado"], dados={"etapa": eid})
            c.execute("UPDATE solicitacoes SET atualizada_em=? WHERE id=?", (_agora(), r["solicitacao_id"]))

    # ------------------------------------------------------------------ aprovações
    def pedir_aprovacao(self, sid: str, pedido: str, risco: str, solicitante: str, etapa_id: str | None = None,
                        aprovador: str = "dono") -> str:
        aid = novo_id("APR")
        with self.tx() as c:
            c.execute("INSERT INTO aprovacoes (id, solicitacao_id, etapa_id, pedido, risco, solicitante, aprovador, criada_em) "
                      "VALUES (?,?,?,?,?,?,?,?)", (aid, sid, etapa_id, pedido, risco, solicitante, aprovador, _agora()))
            self._evento(c, sid, "aprovacao_pedida", pedido, solicitante, dados={"aprovacao": aid, "risco": risco})
        return aid

    def decidir(self, aid: str, aprovado: bool, quem: str, motivo: str = "") -> dict:
        with self.tx() as c:
            a = c.execute("SELECT * FROM aprovacoes WHERE id=?", (aid,)).fetchone()
            if not a:
                raise ErroTransicao("aprovação não existe")
            if a["estado"] != "pendente":
                raise ErroTransicao("esta aprovação já foi decidida")
            if quem != a["aprovador"]:
                raise ErroTransicao(f"só {a['aprovador']} pode decidir esta aprovação")
            if quem == a["solicitante"]:
                raise ErroTransicao("ninguém aprova o próprio pedido")
            estado = "aprovada" if aprovado else "recusada"
            c.execute("UPDATE aprovacoes SET estado=?, decidido_por=?, decidido_em=?, motivo=? WHERE id=?",
                      (estado, quem, _agora(), motivo, aid))
            self._evento(c, a["solicitacao_id"], "aprovacao_decidida", f"{a['pedido']} — {estado}" + (f" ({motivo})" if motivo else ""),
                         quem, dados={"aprovacao": aid})
        return dict(a) | {"estado": estado}

    def aprovacoes_pendentes(self) -> list[dict]:
        with self.tx() as c:
            return [dict(a) for a in c.execute(
                "SELECT a.*, s.titulo FROM aprovacoes a JOIN solicitacoes s ON s.id=a.solicitacao_id "
                "WHERE a.estado='pendente' ORDER BY a.criada_em")]

    # ------------------------------------------------------------------ artefatos e memória
    def artefato(self, sid: str, caminho: str, tipo: str, descricao: str = "", etapa_id: str | None = None) -> None:
        with self.tx() as c:
            c.execute("INSERT INTO artefatos (solicitacao_id, etapa_id, caminho, tipo, descricao, criado_em) VALUES (?,?,?,?,?,?)",
                      (sid, etapa_id, str(caminho), tipo, descricao, _agora()))

    def lembrar(self, tipo: str, chave: str, texto: str, origem: str = "", solicitacao_id: str | None = None) -> None:
        """Memória organizacional: decisões, correções do dono e soluções aprovadas, reaproveitáveis depois."""
        with self.tx() as c:
            c.execute("INSERT INTO memoria (tipo, chave, texto, origem, solicitacao_id, criada_em) VALUES (?,?,?,?,?,?)",
                      (tipo, chave, texto, origem, solicitacao_id, _agora()))

    def memorias(self, tipo: str | None = None, chave: str | None = None, limite: int = 50) -> list[dict]:
        sql, args = "SELECT * FROM memoria WHERE 1=1", []
        if tipo:
            sql += " AND tipo=?"
            args.append(tipo)
        if chave:
            sql += " AND chave=?"
            args.append(chave)
        with self.tx() as c:
            return [dict(r) for r in c.execute(sql + " ORDER BY id DESC LIMIT ?", args + [int(limite)])]
