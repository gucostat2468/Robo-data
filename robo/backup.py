"""Backups (Dora, DBA): uma vez por dia, tudo no seu computador. Nada some:
  - o 1º backup de CADA MÊS fica para sempre; dos demais, guarda os últimos N (rodízio só dos diários);
  - cada backup fica registrado na tabela backups_registro (protegida), com hash SHA-256 e contagem de linhas.

SQLite (logs/trabalho.db — a memória da empresa inteira, a fonte de tudo):
  cópia online pela API oficial de backup do SQLite (não para a operação), conferida com PRAGMA integrity_check,
  compactada (.db.gz) em logs/backups_sqlite/, com manifesto (linhas por tabela + SHA-256). Roda mesmo sem PostgreSQL.
  Restaurar: feche o robô, descompacte o .db.gz (7-Zip) e coloque no lugar de logs/trabalho.db.

PostgreSQL:

Dois jeitos, nesta ordem:
  1. pg_dump (vem junto com o PostgreSQL no Windows: C:\\Program Files\\PostgreSQL\\<versão>\\bin):
     cópia completa (estrutura + dados) num arquivo .dump, restaurável com pg_restore.
  2. Se o pg_dump não for encontrado: exportação em Python de TODAS as tabelas do robô para CSV compactado (.csv.gz),
     com um manifesto (manifesto.json) de quantas linhas cada tabela tinha. Guarda os dados, não a estrutura.

Onde fica: logs/backups/<data_hora>/  ·  Configuração (config.yaml):
  backup: {habilitado: true, manter: 7, intervalo_horas: 24}
Restaurar um .dump (Prompt de Comando):
  "C:\\Program Files\\PostgreSQL\\16\\bin\\pg_restore.exe" -U postgres -d robo_dados --clean --if-exists "<arquivo>.dump"
"""

from __future__ import annotations

import glob
import gzip
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("robo")
PADRAO = {"habilitado": True, "manter": 7, "intervalo_horas": 24, "manter_sqlite": 30}
SCHEMAS = ("bruto", "tratado", "analitico", "robo", "analise")


def _c(cfg) -> dict:
    return {**PADRAO, **(cfg.dados.get("backup") or {})}


def pasta(cfg) -> Path:
    return Path(cfg.logs) / "backups"


def localizar_pg_dump() -> str | None:
    achado = shutil.which("pg_dump")
    if achado:
        return achado
    candidatos = sorted(glob.glob(r"C:\Program Files\PostgreSQL\*\bin\pg_dump.exe"),
                        key=lambda p: [int(x) for x in Path(p).parts[-3].split(".") if x.isdigit()] or [0])
    return candidatos[-1] if candidatos else None


def ultimo(cfg) -> dict | None:
    try:
        return json.loads((pasta(cfg) / "ultimo.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def fazer_backup(cfg) -> dict:
    """Faz o backup agora. Nunca levanta exceção: o resultado diz o que aconteceu."""
    if not cfg.banco.get("habilitado"):
        return {"ok": False, "motivo": "PostgreSQL desligado nas Configurações: não há o que copiar."}
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = pasta(cfg) / carimbo
    inicio = datetime.now()
    try:
        from robo.banco import Banco
        b = Banco(cfg.banco, cfg.base)
        p = b._parametros()
        from robo.banco import ErroBancoNaoExiste
        try:
            with b.conectar():
                pass
        except ErroBancoNaoExiste:  # 1º dia, antes da 1ª carga: não é falha, só não há o que copiar ainda
            return {"ok": False, "pulado": True, "motivo": f"O banco '{p['dbname']}' ainda não foi criado (nenhuma "
                                                          "planilha carregada): nada a copiar ainda."}
        destino.mkdir(parents=True, exist_ok=True)
        pg_dump = localizar_pg_dump()
        if pg_dump:
            arquivo = destino / f"{p['dbname']}.dump"
            env = {**os.environ, "PGPASSWORD": p["password"]}
            r = subprocess.run([pg_dump, "-h", str(p["host"]), "-p", str(p["port"]), "-U", p["user"], "-F", "c",
                                "-f", str(arquivo), p["dbname"]], env=env, capture_output=True, text=True, timeout=3600)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip()[:400] or "pg_dump falhou")
            resultado = {"ok": True, "metodo": "pg_dump", "arquivos": [arquivo.name],
                         "tamanho_mb": round(arquivo.stat().st_size / 1024 ** 2, 2)}
        else:
            resultado = _exportar_csv(b, destino)
    except Exception as e:
        shutil.rmtree(destino, ignore_errors=True)
        resultado = {"ok": False, "motivo": f"{type(e).__name__}: {e}"}
        log.error("Backup do PostgreSQL falhou: %s", resultado["motivo"])
    resultado.update({"data_hora": inicio.strftime("%Y-%m-%d %H:%M:%S"), "pasta": str(destino) if resultado["ok"] else "",
                      "segundos": round((datetime.now() - inicio).total_seconds(), 1)})
    pasta(cfg).mkdir(parents=True, exist_ok=True)
    (pasta(cfg) / "ultimo.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    if resultado["ok"]:
        _rodizio(cfg)
        log.info("Backup do PostgreSQL concluído (%s) em %s", resultado["metodo"], destino)
    return resultado


def _exportar_csv(banco, destino: Path) -> dict:
    manifesto = {}
    with banco.conectar() as conn:
        tabelas = conn.execute(
            "SELECT table_schema, table_name FROM information_schema.tables WHERE table_type = 'BASE TABLE' "
            "AND table_schema = ANY(%s) ORDER BY 1, 2", (list(SCHEMAS),)).fetchall()
        for schema, tabela in tabelas:
            arquivo = destino / f"{schema}.{tabela}.csv.gz"
            with gzip.open(arquivo, "wb") as f, conn.cursor().copy(
                    f'COPY "{schema}"."{tabela}" TO STDOUT WITH (FORMAT csv, HEADER true)') as copia:
                for bloco in copia:
                    f.write(bytes(bloco))
            linhas = conn.execute(f'SELECT count(*) FROM "{schema}"."{tabela}"').fetchone()[0]
            manifesto[f"{schema}.{tabela}"] = linhas
    (destino / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=1), encoding="utf-8")
    tamanho = sum(x.stat().st_size for x in destino.iterdir()) / 1024 ** 2
    return {"ok": True, "metodo": "csv", "arquivos": sorted(x.name for x in destino.iterdir()), "tabelas": len(manifesto),
            "linhas": sum(manifesto.values()), "tamanho_mb": round(tamanho, 2),
            "observacao": "pg_dump não encontrado: dados exportados em CSV compactado (sem a estrutura das tabelas)"}


def _mensais(nomes: list[str]) -> set[str]:
    """O 1º backup de cada mês (pelo carimbo AAAAMMDD no nome): esses nunca são apagados."""
    primeiro: dict[str, str] = {}
    for n in sorted(nomes):
        carimbo = "".join(ch for ch in n if ch.isdigit())[:8]
        if len(carimbo) == 8:
            primeiro.setdefault(carimbo[:6], n)
    return set(primeiro.values())


def _rodizio(cfg) -> None:
    manter = max(1, int(_c(cfg)["manter"]))
    dirs = sorted((d for d in pasta(cfg).iterdir() if d.is_dir()), key=lambda d: d.name)
    fixos = _mensais([d.name for d in dirs])
    for d in dirs[:-manter]:
        if d.name not in fixos:
            shutil.rmtree(d, ignore_errors=True)


# =============================================================================== SQLite (memória da empresa)
def pasta_sqlite(cfg) -> Path:
    return Path(cfg.logs) / "backups_sqlite"


ESQUEMA_REGISTRO = """CREATE TABLE IF NOT EXISTS backups_registro (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, tipo TEXT, ok INTEGER, arquivo TEXT, sha256 TEXT, tamanho_mb REAL,
  linhas INTEGER, integridade TEXT, detalhe TEXT);"""


def _registrar(cfg, tipo: str, r: dict) -> None:
    from robo.trabalho import Trabalho, proteger
    try:
        with Trabalho(cfg).tx() as c:
            c.executescript(ESQUEMA_REGISTRO)
            proteger(c)
            c.execute("INSERT INTO backups_registro (data_hora, tipo, ok, arquivo, sha256, tamanho_mb, linhas, integridade, "
                      "detalhe) VALUES (?,?,?,?,?,?,?,?,?)",
                      (datetime.now().isoformat(timespec="seconds"), tipo, int(bool(r.get("ok"))), r.get("arquivo"),
                       r.get("sha256"), r.get("tamanho_mb"), r.get("linhas"), r.get("integridade"),
                       r.get("motivo") or r.get("metodo")))
    except Exception:
        log.exception("Não consegui registrar o backup %s", tipo)


def backup_sqlite(cfg) -> dict:
    """Cópia online do trabalho.db, conferida e compactada. Nunca levanta exceção."""
    import hashlib
    import sqlite3
    origem = Path(cfg.logs) / "trabalho.db"
    if not origem.exists():
        return {"ok": False, "pulado": True, "motivo": "trabalho.db ainda não existe: nada a copiar."}
    destino = pasta_sqlite(cfg)
    destino.mkdir(parents=True, exist_ok=True)
    nome = f"trabalho_{datetime.now():%Y%m%d_%H%M%S}.db"
    temp = destino / f"{nome}.parcial"
    inicio = datetime.now()
    try:
        src, dst = sqlite3.connect(origem, timeout=60), sqlite3.connect(temp)
        try:
            src.backup(dst)  # API oficial: cópia consistente mesmo com o robô gravando (WAL)
            integridade = dst.execute("PRAGMA integrity_check").fetchone()[0]
            tabelas = [r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            contagens = {t: dst.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tabelas}
        finally:
            dst.close()
            src.close()
        if integridade != "ok":
            raise RuntimeError(f"cópia não passou na conferência de integridade: {integridade}")
        final = destino / f"{nome}.gz"
        h = hashlib.sha256()
        with open(temp, "rb") as f, gzip.open(final, "wb", compresslevel=6) as g:
            for bloco in iter(lambda: f.read(1 << 20), b""):
                h.update(bloco)
                g.write(bloco)
        temp.unlink()
        r = {"ok": True, "metodo": "sqlite_backup", "arquivo": final.name, "sha256": h.hexdigest(),
             "tamanho_mb": round(final.stat().st_size / 1024 ** 2, 3), "linhas": sum(contagens.values()),
             "tabelas": len(contagens), "integridade": integridade,
             "segundos": round((datetime.now() - inicio).total_seconds(), 2),
             "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        (destino / f"{nome}.manifesto.json").write_text(json.dumps({**r, "contagens": contagens}, ensure_ascii=False,
                                                                    indent=1), encoding="utf-8")
        (destino / "ultimo.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        _rodizio_sqlite(cfg)
        log.info("Backup do SQLite concluído: %s (%s tabelas, %s linhas)", final.name, r["tabelas"], r["linhas"])
    except Exception as e:
        temp.unlink(missing_ok=True)
        r = {"ok": False, "motivo": f"{type(e).__name__}: {e}"}
        log.error("Backup do SQLite falhou: %s", r["motivo"])
    _registrar(cfg, "sqlite", r)
    return r


TABELAS_COM_HISTORIA = ("treino_tentativas", "experiencias", "rotinas_execucoes", "licoes_funcionario", "decisoes")


def _contagens(caminho: Path) -> tuple[str, dict]:
    import sqlite3
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    try:
        integridade = con.execute("PRAGMA integrity_check").fetchone()[0]
        tabelas = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return integridade, {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tabelas}
    finally:
        con.close()


def restaurar_sqlite(cfg, arquivo: Path, substituir: bool = False) -> dict:
    """Traz para este computador a memória da empresa de um backup (trabalho_*.db.gz ou .db) — ex.: a memória criada em
    outro computador. Nada se perde:
      - o arquivo é descompactado numa cópia temporária e conferido (integridade e, se houver manifesto, SHA-256);
      - se este computador JÁ tem história registrada, recusa — a não ser com substituir=True, que antes faz um backup
        da memória atual e guarda o arquivo atual renomeado (nunca apaga);
      - recusa com o robô aberto (o arquivo estaria em uso)."""
    import hashlib
    import shutil
    from robo.monitor import TravaInstancia
    arquivo = Path(arquivo)
    if not arquivo.exists():
        raise FileNotFoundError(f"não achei {arquivo}")
    logs = Path(cfg.logs)
    destino = logs / "trabalho.db"
    temp = logs / f"restauracao_{datetime.now():%Y%m%d_%H%M%S}.db.parcial"
    logs.mkdir(parents=True, exist_ok=True)
    with TravaInstancia(logs):  # levanta erro claro se o robô estiver aberto
        h = hashlib.sha256()
        abrir = gzip.open if arquivo.suffix == ".gz" else open
        with abrir(arquivo, "rb") as f, open(temp, "wb") as g:
            for bloco in iter(lambda: f.read(1 << 20), b""):
                h.update(bloco)
                g.write(bloco)
        try:
            manifesto = arquivo.with_name(arquivo.name.replace(".db.gz", ".db").replace(".db", ".db.manifesto.json", 1))
            esperado = json.loads(manifesto.read_text(encoding="utf-8")).get("sha256") if manifesto.exists() else None
            if esperado and esperado != h.hexdigest():
                raise ValueError(f"o SHA-256 não confere com o manifesto ({manifesto.name}): arquivo corrompido ou alterado")
            integridade, contagens = _contagens(temp)
            if integridade != "ok":
                raise ValueError(f"o backup não passou na conferência de integridade: {integridade}")
            passos = [f"backup conferido: integridade ok, {len(contagens)} tabelas, {sum(contagens.values())} linhas"
                      + (", SHA-256 igual ao manifesto" if esperado else "")]
            if destino.exists():
                _, atuais = _contagens(destino)
                historia = {t: atuais.get(t, 0) for t in TABELAS_COM_HISTORIA if atuais.get(t)}
                if historia and not substituir:
                    raise ValueError("este computador já tem história registrada (" + ", ".join(f"{t}: {n}" for t, n in historia.items())
                                     + "). Nada foi mudado. Para trocar mesmo assim (a memória atual é guardada), use --substituir.")
                if historia:
                    b = backup_sqlite(cfg)
                    if not b.get("ok"):
                        raise RuntimeError(f"não consegui fazer o backup da memória atual antes de trocar: {b.get('motivo')}")
                    passos.append(f"memória atual guardada antes da troca: {b['arquivo']}")
                guardado = logs / f"trabalho_antes_da_restauracao_{datetime.now():%Y%m%d_%H%M%S}.db"
                for sufixo in ("", "-wal", "-shm"):
                    atual = Path(str(destino) + sufixo)
                    if atual.exists():
                        shutil.move(str(atual), str(guardado) + sufixo)
                passos.append(f"arquivo atual guardado como {guardado.name}")
            temp.replace(destino)
        finally:
            temp.unlink(missing_ok=True)
    passos.append(f"memória restaurada em {destino}")
    r = {"ok": True, "arquivo": str(arquivo), "sha256": h.hexdigest(), "tabelas": len(contagens),
         "linhas": sum(contagens.values()), "contagens": contagens, "passos": passos}
    _registrar(cfg, "restauracao_sqlite", {**r, "integridade": "ok", "metodo": f"restaurado de {arquivo.name}"})
    return r


def _rodizio_sqlite(cfg) -> None:
    manter = max(1, int(_c(cfg)["manter_sqlite"]))
    arquivos = sorted(p.name for p in pasta_sqlite(cfg).glob("trabalho_*.db.gz"))
    fixos = _mensais(arquivos)
    for n in arquivos[:-manter]:
        if n not in fixos:
            (pasta_sqlite(cfg) / n).unlink(missing_ok=True)  # o manifesto fica: prova de que o backup existiu


def ultimo_sqlite(cfg) -> dict | None:
    try:
        return json.loads((pasta_sqlite(cfg) / "ultimo.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _vencido(u: dict | None, horas: float) -> bool:
    if not (u and u.get("ok") and u.get("data_hora")):
        return True
    return datetime.now() - datetime.strptime(u["data_hora"], "%Y-%m-%d %H:%M:%S") >= timedelta(hours=horas)


def rotina(cfg) -> dict | None:
    """Chamado pelo robô: faz os backups que venceram (SQLite sempre; PostgreSQL se ligado). Avisa a DBA se falhar."""
    c = _c(cfg)
    if not c.get("habilitado", True):
        return None
    if _vencido(ultimo_sqlite(cfg), float(c["intervalo_horas"])):
        rs = backup_sqlite(cfg)
        if not rs["ok"] and not rs.get("pulado"):
            try:
                from robo.canal import Canal
                Canal(cfg).postar("dba", f"Backup do SQLite (memória da empresa) FALHOU: {rs['motivo']}. Tento de novo na "
                                         "próxima hora.", "banco", "alerta")
            except Exception:
                pass
    if not cfg.banco.get("habilitado"):
        return None
    u = ultimo(cfg)
    if u and u.get("ok") and u.get("data_hora") and datetime.now() - datetime.strptime(u["data_hora"], "%Y-%m-%d %H:%M:%S") < timedelta(hours=float(c["intervalo_horas"])):
        return None
    r = fazer_backup(cfg)
    if r.get("pulado"):
        return r
    _registrar(cfg, "postgresql", {**r, "arquivo": ",".join(r.get("arquivos") or [])[:300]})
    try:
        from robo.canal import Canal
        texto = (f"Backup do PostgreSQL feito ({r['metodo']}, {r['tamanho_mb']} MB, {r['segundos']} s). Guardo os últimos "
                 f"{c['manter']}." if r["ok"] else f"Backup do PostgreSQL FALHOU: {r['motivo']}. Vou tentar de novo na próxima hora.")
        Canal(cfg).postar("dba", texto, "banco", "acontecimento" if r["ok"] else "alerta")
    except Exception:
        pass
    return r
