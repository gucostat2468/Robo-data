"""Backup do PostgreSQL (Dora, DBA): uma vez por dia, guardando os últimos N, tudo no seu computador.

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
PADRAO = {"habilitado": True, "manter": 7, "intervalo_horas": 24}
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


def _rodizio(cfg) -> None:
    manter = max(1, int(_c(cfg)["manter"]))
    antigos = sorted((d for d in pasta(cfg).iterdir() if d.is_dir()), key=lambda d: d.name)[:-manter]
    for d in antigos:
        shutil.rmtree(d, ignore_errors=True)


def rotina(cfg) -> dict | None:
    """Chamado pelo robô: faz o backup se já passou o intervalo. Avisa a DBA no canal quando falha."""
    c = _c(cfg)
    if not c.get("habilitado", True) or not cfg.banco.get("habilitado"):
        return None
    u = ultimo(cfg)
    if u and u.get("ok") and u.get("data_hora") and datetime.now() - datetime.strptime(u["data_hora"], "%Y-%m-%d %H:%M:%S") < timedelta(hours=float(c["intervalo_horas"])):
        return None
    r = fazer_backup(cfg)
    if r.get("pulado"):
        return r
    try:
        from robo.canal import Canal
        texto = (f"Backup do PostgreSQL feito ({r['metodo']}, {r['tamanho_mb']} MB, {r['segundos']} s). Guardo os últimos "
                 f"{c['manter']}." if r["ok"] else f"Backup do PostgreSQL FALHOU: {r['motivo']}. Vou tentar de novo na próxima hora.")
        Canal(cfg).postar("dba", texto, "banco", "acontecimento" if r["ok"] else "alerta")
    except Exception:
        pass
    return r
