"""Trabalho real do 5º andar para nuvem, AWS e Linux: quatro verificações que rodam NESTE computador (ou no turno da
nuvem) e devolvem o que acharam. Nenhuma cria recurso na nuvem, abre porta, muda permissão ou gasta dinheiro.

  restauracao_backup   o backup mais recente do SQLite VOLTA? Descompacta numa pasta temporária, roda o
                       integrity_check e compara o número de tabelas com o banco vivo (backup que não restaura não é
                       backup). Ícaro, Sênior de AWS/Linux.
  prontidao_nuvem      o projeto está pronto para rodar num servidor? Dockerfile (usuário sem root, porta por
                       variável), turno da nuvem, segredos fora do repositório. Heloísa, Head de AWS.
  postgres_saude       tamanho do banco contra o limite do plano, tabelas com muita linha morta, conexões e consultas
                       presas. Somente leitura.
  segredos_repo        procura senha, token e chave escritos nos arquivos do projeto (o repositório é PÚBLICO).

Cada função `detalhe_*` devolve um dicionário com tudo o que foi medido; `chk_*` devolve só os problemas (o formato
da ronda de TI em robo/ti.py).
"""

from __future__ import annotations

import gzip
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from robo.config import RAIZ_PROJETO

LIMITE_MB_PADRAO = 500  # plano gratuito do banco da nuvem (o turno avisa com 80%)

# padrões de segredo (o achado mostra o arquivo e a linha, nunca o segredo)
SEGREDOS = [
    ("URL de banco com senha", re.compile(r"postgres(?:ql)?://[^:\s/'\"]+:[^@\s'\"]{3,}@")),
    ("token do Telegram", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}")),
    ("chave de API (sk-…)", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("chave da AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("senha escrita", re.compile(r"(?i)\b(senha|password|passwd)\s*[:=]\s*['\"][^'\"\s{}$%<]{6,}['\"]")),
]
EXTENSOES = {".py", ".yaml", ".yml", ".md", ".bat", ".vbs", ".json", ".toml", ".cfg", ".ini", ".txt", ".sql", ".js",
             ".html", ".env"}


# =============================================================================== backup que restaura
def _idade_horas(db: Path) -> float:
    """Idade do banco pela primeira sessão registrada (o arquivo muda a toda hora; a data dele não serve)."""
    from datetime import datetime
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        primeiras = []
        for tabela, coluna in (("sessoes", "aberto_em"), ("treino_tentativas", "data_hora"), ("jobs", "inicio")):
            try:
                v = c.execute(f"SELECT MIN({coluna}) FROM {tabela}").fetchone()[0]
            except sqlite3.Error:
                continue
            if v:
                primeiras.append(str(v)[:19].replace(" ", "T"))
    finally:
        c.close()
    if not primeiras:
        return 0.0
    try:
        return (datetime.now() - datetime.fromisoformat(min(primeiras))).total_seconds() / 3600
    except ValueError:
        return 0.0


def detalhe_restauracao(cfg) -> dict:
    from robo import backup
    pasta = backup.pasta_sqlite(cfg)
    arqs = sorted(pasta.glob("*.db.gz"), key=lambda p: p.stat().st_mtime, reverse=True) if pasta.exists() else []
    vivo = Path(cfg.logs) / "trabalho.db"
    if not arqs and (not vivo.exists() or _idade_horas(vivo) < 26):
        # computador novo: o backup é diário; antes de 26 h de banco ainda não é falha não ter um
        return {"ok": True, "problemas": [], "aplicavel": False, "motivo": "banco com menos de um dia: backup ainda não venceu",
                "pasta": str(pasta)}
    if not arqs:
        return {"ok": False, "problemas": ["nenhum backup do SQLite encontrado para testar a restauração"],
                "pasta": str(pasta)}
    arq = arqs[0]
    with tempfile.TemporaryDirectory() as d:
        destino = Path(d) / "restaurado.db"
        with gzip.open(arq, "rb") as origem, open(destino, "wb") as saida:
            shutil.copyfileobj(origem, saida)
        c = sqlite3.connect(destino)
        try:
            integridade = c.execute("PRAGMA integrity_check").fetchone()[0]
            tabelas = c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            linhas = sum(c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                         for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                               "AND name NOT LIKE 'sqlite_%'").fetchall())
        finally:
            c.close()
    tabelas_vivo = None
    if vivo.exists():
        cv = sqlite3.connect(f"file:{vivo}?mode=ro", uri=True)
        try:
            tabelas_vivo = cv.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        finally:
            cv.close()
    problemas = []
    if integridade != "ok":
        problemas.append(f"backup {arq.name} restaurou com defeito: {integridade}")
    if tabelas_vivo is not None and tabelas < tabelas_vivo - 10:
        problemas.append(f"backup {arq.name} tem {tabelas} tabelas e o banco vivo {tabelas_vivo}: backup antigo demais")
    return {"ok": not problemas, "problemas": problemas, "arquivo": arq.name, "integridade": integridade,
            "tabelas": tabelas, "linhas": linhas, "tabelas_vivo": tabelas_vivo, "tamanho_kb": round(arq.stat().st_size / 1024)}


def chk_restauracao_backup(cfg) -> list[str]:
    """Ícaro (Sênior de AWS/Linux): o último backup volta inteiro?"""
    return detalhe_restauracao(cfg)["problemas"]


# =============================================================================== pronto para servidor
def detalhe_prontidao(cfg) -> dict:
    raiz = RAIZ_PROJETO
    itens = []

    def item(nome, ok, detalhe=""):
        itens.append({"item": nome, "ok": bool(ok), "detalhe": detalhe})
    docker = raiz / "Dockerfile"
    texto = docker.read_text(encoding="utf-8") if docker.exists() else ""
    item("Dockerfile existe", docker.exists(), str(docker.name))
    item("Container não roda como root", bool(re.search(r"^\s*USER\s+(?!root)\S+", texto, re.M)), "linha USER")
    item("Porta vem da variável PORT", "PORT" in texto, "Cloud Run e similares mandam a porta")
    item("Turno da nuvem no GitHub Actions", (raiz / ".github" / "workflows" / "empresa_nuvem.yml").exists())
    item("config.yaml fora do repositório", "config.yaml" in (raiz / ".gitignore").read_text(encoding="utf-8")
         if (raiz / ".gitignore").exists() else False)
    req = (raiz / "requisitos.txt").read_text(encoding="utf-8") if (raiz / "requisitos.txt").exists() else ""
    soltas = [l.split("#")[0].strip() for l in req.splitlines() if l.strip() and not l.startswith("#")
              and ">=" not in l and "==" not in l]
    item("Toda dependência com versão mínima", not soltas, ", ".join(soltas))
    problemas = [f"{i['item']}: não" + (f" ({i['detalhe']})" if i["detalhe"] else "") for i in itens if not i["ok"]]
    return {"ok": not problemas, "problemas": problemas, "itens": itens}


def chk_prontidao_nuvem(cfg) -> list[str]:
    """Heloísa (Head de AWS): o projeto está pronto para rodar num servidor, sem segredo no código?"""
    return detalhe_prontidao(cfg)["problemas"]


# =============================================================================== saúde do PostgreSQL
def detalhe_postgres(cfg) -> dict:
    if not (cfg.banco or {}).get("habilitado"):
        return {"ok": True, "problemas": [], "aplicavel": False, "motivo": "PostgreSQL desligado"}
    from robo.banco import Banco
    limite = float(os.environ.get("ROBO_LIMITE_MB") or LIMITE_MB_PADRAO)
    with Banco(cfg.banco, cfg.base).conectar() as conn:
        mb = conn.execute("SELECT pg_database_size(current_database()) / 1024.0 / 1024").fetchone()[0]
        por_schema = [{"schema": s, "mb": round(float(m), 2)} for s, m in conn.execute(
            "SELECT n.nspname, sum(pg_total_relation_size(c.oid)) / 1024.0 / 1024 FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' "
            "AND n.nspname NOT IN ('pg_catalog', 'information_schema') GROUP BY 1 ORDER BY 2 DESC")]
        mortas = [{"tabela": f"{s}.{t}", "vivas": int(v), "mortas": int(m)} for s, t, v, m in conn.execute(
            "SELECT schemaname, relname, n_live_tup, n_dead_tup FROM pg_stat_user_tables "
            "WHERE n_live_tup > 10000 AND n_dead_tup > 0.2 * n_live_tup ORDER BY n_dead_tup DESC LIMIT 10")]
        conexoes = conn.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()").fetchone()[0]
        presas = [{"pid": p, "minutos": round(float(mi), 1), "estado": e} for p, mi, e in conn.execute(
            "SELECT pid, extract(epoch FROM now() - query_start) / 60, state FROM pg_stat_activity "
            "WHERE datname = current_database() AND state <> 'idle' AND pid <> pg_backend_pid() "
            "AND now() - query_start > interval '5 minutes'")]
    problemas = []
    if mb >= 0.8 * limite:
        problemas.append(f"banco com {mb:.0f} MB de {limite:.0f} MB (80%+ do limite do plano)")
    problemas += [f"{x['tabela']}: {x['mortas']} linhas mortas para {x['vivas']} vivas (precisa de VACUUM)" for x in mortas]
    problemas += [f"consulta presa há {x['minutos']} min (pid {x['pid']})" for x in presas]
    return {"ok": not problemas, "problemas": problemas, "aplicavel": True, "mb": round(float(mb), 1),
            "limite_mb": limite, "por_schema": por_schema, "mortas": mortas, "conexoes": conexoes, "presas": presas}


def chk_postgres_saude(cfg) -> list[str]:
    try:
        return detalhe_postgres(cfg)["problemas"]
    except Exception as e:
        return [f"não consegui medir o PostgreSQL ({type(e).__name__})"]


# =============================================================================== segredos no repositório
MARCADORES = {"senha", "password", "pass", "sua_senha", "suasenha", "usuario", "user", "xxxx", "***"}


def _e_marcador(trecho: str) -> bool:
    """'postgresql://usuario:senha@host' na documentação é molde, não segredo."""
    m = re.search(r"://[^:]+:([^@]+)@", trecho)
    return bool(m and m.group(1).strip("*").lower() in MARCADORES)


def _arquivos_versionados(raiz: Path) -> list[Path]:
    try:
        saida = subprocess.run(["git", "-C", str(raiz), "ls-files"], capture_output=True, text=True, timeout=20)
        if saida.returncode == 0:
            return [raiz / l for l in saida.stdout.splitlines() if l]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return [p for p in raiz.rglob("*") if p.is_file() and ".git" not in p.parts]


def detalhe_segredos(cfg, raiz: Path | None = None) -> dict:
    raiz = raiz or RAIZ_PROJETO
    achados, lidos = [], 0
    for arq in _arquivos_versionados(raiz):
        if arq.suffix.lower() not in EXTENSOES or not arq.exists() or arq.stat().st_size > 2_000_000:
            continue
        lidos += 1
        try:
            linhas = arq.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for n, linha in enumerate(linhas, 1):
            for nome, rx in SEGREDOS:
                m = rx.search(linha)
                if not m or "exemplo" in linha.lower() or "<" in linha or _e_marcador(m.group(0)):
                    continue
                rel = arq.relative_to(raiz).as_posix()
                if nome == "senha escrita" and rel.startswith("testes/"):
                    continue  # senha inventada de teste automático (nunca é a senha de ninguém)
                achados.append({"arquivo": rel, "linha": n, "tipo": nome})
    problemas = [f"{a['tipo']} em {a['arquivo']}:{a['linha']}" for a in achados[:20]]
    return {"ok": not achados, "problemas": problemas, "achados": achados, "arquivos_lidos": lidos}


def chk_segredos_repo(cfg) -> list[str]:
    return detalhe_segredos(cfg)["problemas"]
