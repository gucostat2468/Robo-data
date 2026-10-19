"""Registro total: tudo o que a empresa escreve em ARQUIVO também vai para o banco (SQLite → PostgreSQL), organizado.

Antes, parte da memória vivia só em arquivos (canal, atas, log do sistema, RH, conhecimento, estado da TI). Agora a
rotina 'registro' (a cada minuto) captura, sem duplicar e sem perder nada:

  logs_sistema      cada registro do robo.log (e dos robo.log.AAAA-MM-DD girados à meia-noite): data, nível, mensagem
                    completa (com o traceback, se houver) e a linha de origem;
  canal_mensagens   cada mensagem do canal da equipe, com todos os campos;
  arquivos_linhas   cada linha nova de qualquer arquivo que só cresce (.jsonl, .csv): RH, conhecimento, histórico…;
  arquivos_versoes  cada VERSÃO de arquivo que é reescrito (.json, .md, .yaml, .txt): atas de reunião, backlog, estado
                    da TI, relatórios de erro, config.yaml (com as senhas trocadas por ***), equipe contratada.

Regras: as quatro tabelas são imutáveis (o banco recusa apagar e alterar); a leitura é incremental por "cursor"
(posição já lida de cada arquivo, por geração — quando o arquivo é girado ou reescrito do zero, começa uma geração
nova e a anterior não se perde); o último registro de log só entra depois de completo (nunca pela metade).
`cobertura(cfg)` lista qualquer arquivo de texto que NÃO esteja coberto — o teste exige que a lista seja vazia.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path

from robo.trabalho import Trabalho, _agora, proteger

TABELAS = ("logs_sistema", "canal_mensagens", "arquivos_linhas", "arquivos_versoes")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS logs_sistema (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, nivel TEXT, mensagem TEXT, arquivo TEXT, geracao TEXT,
  linha_inicial INTEGER, capturado_em TEXT, UNIQUE (geracao, linha_inicial));
CREATE INDEX IF NOT EXISTS ix_logs_sistema_data ON logs_sistema(data_hora);
CREATE INDEX IF NOT EXISTS ix_logs_sistema_nivel ON logs_sistema(nivel, data_hora);
CREATE TABLE IF NOT EXISTS canal_mensagens (
  id INTEGER PRIMARY KEY, data_hora TEXT, canal TEXT, autor TEXT, nome TEXT, papel TEXT, tipo TEXT, texto TEXT,
  extra TEXT, capturado_em TEXT);
CREATE INDEX IF NOT EXISTS ix_canal_mensagens_data ON canal_mensagens(data_hora);
CREATE TABLE IF NOT EXISTS arquivos_linhas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, arquivo TEXT, geracao TEXT, n_linha INTEGER, conteudo TEXT, capturado_em TEXT,
  UNIQUE (arquivo, geracao, n_linha));
CREATE TABLE IF NOT EXISTS arquivos_versoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, arquivo TEXT, sha256 TEXT, tamanho INTEGER, modificado_em TEXT, conteudo TEXT,
  capturado_em TEXT, UNIQUE (arquivo, sha256));
CREATE TABLE IF NOT EXISTS registro_cursores (
  chave TEXT PRIMARY KEY, posicao INTEGER, linhas INTEGER, assinatura TEXT, atualizado_em TEXT);
""" + "".join(f"""
CREATE TRIGGER IF NOT EXISTS {t}_sem_alterar BEFORE UPDATE ON {t}
BEGIN SELECT RAISE(ABORT, 'registro permanente: {t} não pode ser alterado'); END;""" for t in TABELAS)

RE_LOG = re.compile(r"^(\d{2})/(\d{2})/(\d{4}) (\d{2}:\d{2}:\d{2}) \| (\w+)\s*\| ?(.*)$")
SEGREDOS = re.compile(r"(?im)^(\s*[\w.-]*(senha|password|secret|token|chave_api)[\w.-]*\s*:\s*)(\S.*)$")
TAMANHO_MAXIMO = 5 * 1024 ** 2
EXT_LINHAS = {".jsonl", ".csv"}
EXT_VERSOES = {".json", ".md", ".yaml", ".yml", ".txt"}
IGNORAR_DIRS = {"treino", "backups", "backups_sqlite", "laboratorio", "__pycache__"}
IGNORAR_ARQUIVOS = {"robo.lock"}
GERACAO_BYTES = 256


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        proteger(c)
    return tb


def _geracao(caminho: Path) -> str:
    """Identidade do arquivo = a 1ª linha completa (num arquivo que só cresce ela nunca muda; se o arquivo for girado,
    ela vai junto; se for reescrito do zero, muda — e começa uma geração nova, sem perder a anterior)."""
    with open(caminho, "rb") as f:
        inicio = f.read(GERACAO_BYTES)
    fim = inicio.find(b"\n")
    return hashlib.sha256(inicio[:fim + 1] if fim >= 0 else b"").hexdigest()[:16]


def _cursor(c, chave: str) -> dict:
    r = c.execute("SELECT posicao, linhas, assinatura FROM registro_cursores WHERE chave=?", (chave,)).fetchone()
    return dict(r) if r else {"posicao": 0, "linhas": 0, "assinatura": ""}


def _salvar_cursor(c, chave: str, posicao: int, linhas: int, assinatura: str = "") -> None:
    c.execute("INSERT INTO registro_cursores (chave, posicao, linhas, assinatura, atualizado_em) VALUES (?,?,?,?,?) "
              "ON CONFLICT(chave) DO UPDATE SET posicao=excluded.posicao, linhas=excluded.linhas, "
              "assinatura=excluded.assinatura, atualizado_em=excluded.atualizado_em", (chave, posicao, linhas, assinatura, _agora()))


def _novos_bytes(caminho: Path, posicao: int) -> tuple[bytes, int]:
    """Bytes completos (até a última quebra de linha) a partir da posição já lida."""
    tamanho = caminho.stat().st_size
    if tamanho <= posicao:
        return b"", posicao
    with open(caminho, "rb") as f:
        f.seek(posicao)
        dados = f.read(tamanho - posicao)
    fim = dados.rfind(b"\n")
    return (b"", posicao) if fim < 0 else (dados[:fim + 1], posicao + fim + 1)


# =============================================================================== log do sistema
def _arquivos_de_log(cfg) -> list[Path]:
    """robo.log e os girados (robo.log.AAAA-MM-DD), do mais antigo para o mais novo."""
    pasta = Path(cfg.logs)
    girados = sorted(p for p in pasta.glob("robo.log.*") if p.is_file())
    atual = pasta / "robo.log"
    return girados + ([atual] if atual.exists() else [])


def _capturar_log(c, caminho: Path) -> int:
    """O arquivo girado tem a MESMA geração do robo.log de antes (mesmo começo): continua de onde parou."""
    if caminho.stat().st_size == 0:
        return 0
    geracao = _geracao(caminho)
    chave = f"log:{geracao}"
    cur = _cursor(c, chave)
    dados, _ = _novos_bytes(caminho, cur["posicao"])
    if not dados:
        return 0
    registros, n, pos = [], cur["linhas"], cur["posicao"]
    for bruta in dados.split(b"\n")[:-1]:
        n += 1
        linha = bruta.decode("utf-8", errors="replace").rstrip("\r")
        m = RE_LOG.match(linha)
        if m or not registros:
            dd, mm, aaaa, hora, nivel, msg = m.groups() if m else ("", "", "", "", "TEXTO", linha)
            registros.append({"data_hora": f"{aaaa}-{mm}-{dd}T{hora}" if m else None, "nivel": nivel.upper(),
                              "linhas": [msg], "inicio": n, "pos_inicio": pos})
        else:
            registros[-1]["linhas"].append(linha)  # continuação (ex.: traceback)
        pos += len(bruta) + 1
    fim_linhas, fim_pos = n, pos
    # o último registro pode estar sendo escrito agora (traceback em várias linhas): só entra com o arquivo parado
    if registros and caminho.name == "robo.log" and time.time() - caminho.stat().st_mtime <= 3:
        ultimo = registros.pop()
        fim_linhas, fim_pos = ultimo["inicio"] - 1, ultimo["pos_inicio"]
    for r in registros:
        c.execute("INSERT OR IGNORE INTO logs_sistema (data_hora, nivel, mensagem, arquivo, geracao, linha_inicial, capturado_em) "
                  "VALUES (?,?,?,?,?,?,?)", (r["data_hora"], r["nivel"], "\n".join(r["linhas"]), caminho.name, geracao,
                                             r["inicio"], _agora()))
    _salvar_cursor(c, chave, fim_pos, fim_linhas)
    return len(registros)


# =============================================================================== canal
def _capturar_canal(c, caminho: Path) -> int:
    geracao = _geracao(caminho)
    chave = f"canal:{geracao}"
    cur = _cursor(c, chave)
    dados, nova_pos = _novos_bytes(caminho, cur["posicao"])
    n = 0
    for linha in dados.decode("utf-8", errors="replace").splitlines():
        if not linha.strip():
            continue
        try:
            m = json.loads(linha)
        except json.JSONDecodeError:
            c.execute("INSERT OR IGNORE INTO arquivos_linhas (arquivo, geracao, n_linha, conteudo, capturado_em) VALUES (?,?,?,?,?)",
                      (str(caminho.name), geracao, cur["linhas"] + n + 1, linha, _agora()))
            n += 1
            continue
        base = {"id", "data_hora", "canal", "autor", "nome", "papel", "tipo", "texto"}
        c.execute("INSERT OR IGNORE INTO canal_mensagens (id, data_hora, canal, autor, nome, papel, tipo, texto, extra, "
                  "capturado_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (m.get("id"), m.get("data_hora"), m.get("canal"), m.get("autor"), m.get("nome"), m.get("papel"),
                   m.get("tipo"), m.get("texto"), json.dumps({k: v for k, v in m.items() if k not in base}, ensure_ascii=False),
                   _agora()))
        n += 1
    _salvar_cursor(c, chave, nova_pos, cur["linhas"] + n)
    return n


# =============================================================================== arquivos que só crescem / reescritos
def _capturar_linhas(c, caminho: Path, nome: str) -> int:
    if caminho.stat().st_size == 0:
        return 0
    geracao = _geracao(caminho)
    chave = f"linhas:{nome}:{geracao}"
    cur = _cursor(c, chave)
    dados, nova_pos = _novos_bytes(caminho, cur["posicao"])
    n = cur["linhas"]
    for linha in dados.decode("utf-8", errors="replace").split("\n")[:-1]:
        n += 1
        c.execute("INSERT OR IGNORE INTO arquivos_linhas (arquivo, geracao, n_linha, conteudo, capturado_em) VALUES (?,?,?,?,?)",
                  (nome, geracao, n, linha.rstrip("\r"), _agora()))
    _salvar_cursor(c, chave, nova_pos, n)
    return n - cur["linhas"]


def sem_segredos(texto: str) -> str:
    return SEGREDOS.sub(lambda m: m.group(1) + "***", texto)


def _capturar_versao(c, caminho: Path, nome: str, redigir: bool = False) -> int:
    st = caminho.stat()
    if st.st_size > TAMANHO_MAXIMO:
        return 0
    chave = f"versao:{nome}"
    assinatura = f"{st.st_size}:{st.st_mtime_ns}"
    if _cursor(c, chave)["assinatura"] == assinatura:
        return 0  # não mudou desde a última olhada: nem lê
    texto = caminho.read_bytes().decode("utf-8", errors="replace")
    if redigir:
        texto = sem_segredos(texto)
    sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    cur = c.execute("INSERT OR IGNORE INTO arquivos_versoes (arquivo, sha256, tamanho, modificado_em, conteudo, capturado_em) "
                    "VALUES (?,?,?,?,?,?)", (nome, sha, st.st_size,
                                             datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"), texto, _agora()))
    _salvar_cursor(c, chave, st.st_size, 0, assinatura)
    return cur.rowcount


def _fontes(cfg) -> list[tuple[str, Path, str]]:
    """(tipo, caminho, nome registrado) de tudo que é texto e não está no trabalho.db."""
    logs = Path(cfg.logs)
    fontes = []
    if logs.exists():
        for p in sorted(logs.rglob("*")):
            rel = p.relative_to(logs)
            if not p.is_file() or rel.parts[0] in IGNORAR_DIRS or p.name in IGNORAR_ARQUIVOS:
                continue
            if p.name == "robo.log" or p.name.startswith("robo.log."):
                continue  # vai para logs_sistema
            if rel.as_posix() == "canal/mensagens.jsonl":
                fontes.append(("canal", p, "logs/" + rel.as_posix()))
            elif p.suffix.lower() in EXT_LINHAS:
                fontes.append(("linhas", p, "logs/" + rel.as_posix()))
            elif p.suffix.lower() in EXT_VERSOES:
                fontes.append(("versao", p, "logs/" + rel.as_posix()))
    pastas = cfg.pastas() if callable(getattr(cfg, "pastas", None)) else {}
    for rotulo, pasta in pastas.items():
        pasta = Path(pasta)
        if pasta == logs or not pasta.exists() or ("Erros" not in rotulo and "Relat" not in rotulo):
            continue
        for p in sorted(pasta.glob("*")):
            if p.is_file() and p.suffix.lower() in EXT_VERSOES | {".csv"}:
                fontes.append(("versao", p, f"{pasta.name}/{p.name}"))
    base = Path(getattr(cfg, "base", "") or ".")
    config = base / "config.yaml"
    if config.exists():
        fontes.append(("config", config, "config.yaml"))
    agentes = Path((cfg.dados.get("pastas") or {}).get("agentes") or base / "agentes")
    agentes = agentes if agentes.is_absolute() else base / agentes
    if agentes.exists():
        for p in sorted(agentes.rglob("*")):
            if p.is_file() and p.suffix.lower() in EXT_VERSOES:
                fontes.append(("versao", p, "agentes/" + p.relative_to(agentes).as_posix()))
    return fontes


def capturar(cfg) -> dict:
    """Captura tudo o que é novo. Idempotente: rodar de novo sem novidade não grava nada."""
    tb = _tb(cfg)
    contagem = {"logs_sistema": 0, "canal_mensagens": 0, "arquivos_linhas": 0, "arquivos_versoes": 0}
    with tb.tx() as c:
        for p in _arquivos_de_log(cfg):
            contagem["logs_sistema"] += _capturar_log(c, p)
        for tipo, p, nome in _fontes(cfg):
            try:
                if tipo == "canal":
                    contagem["canal_mensagens"] += _capturar_canal(c, p)
                elif tipo == "linhas":
                    contagem["arquivos_linhas"] += _capturar_linhas(c, p, nome)
                else:
                    contagem["arquivos_versoes"] += _capturar_versao(c, p, nome, redigir=(tipo == "config"))
            except FileNotFoundError:
                continue  # arquivo trocado enquanto líamos: entra na próxima rodada
    return {k: v for k, v in contagem.items() if v}


def cobertura(cfg) -> list[str]:
    """Arquivos de texto da pasta de logs que NÃO entram no banco. Tem que ser vazio."""
    logs = Path(cfg.logs)
    cobertos = {str(p) for _, p, _ in _fontes(cfg)} | {str(p) for p in _arquivos_de_log(cfg)}
    faltando = []
    for p in logs.rglob("*") if logs.exists() else []:
        rel = p.relative_to(logs)
        if not p.is_file() or rel.parts[0] in IGNORAR_DIRS or p.name in IGNORAR_ARQUIVOS:
            continue
        if p.name.startswith("trabalho.db") or p.suffix == ".trava" or p.suffix in (".tmp", ".parcial"):
            continue  # o próprio banco, travas de execução e arquivos temporários
        if str(p) not in cobertos:
            faltando.append(rel.as_posix())
    return sorted(faltando)


def resumo(cfg) -> dict:
    with _tb(cfg).tx() as c:
        return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABELAS}
