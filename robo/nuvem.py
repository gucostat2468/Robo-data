"""Empresa na nuvem GRÁTIS: trabalha em turnos no GitHub Actions e guarda tudo num PostgreSQL gratuito (ex.: Neon).

    python -m robo turno --minutos 20

Como funciona um turno (o arquivo .github/workflows/empresa_nuvem.yml chama de 2 em 2 horas):
  1. RESTAURA a memória: baixa do PostgreSQL o último instantâneo do SQLite (conferido por SHA-256). Na 1ª vez, usa a
     memória que já existia no projeto (nuvem/memoria_inicial.db.gz, conferida pelo manifesto);
  2. TRABALHA: as mesmas rotinas do robô (treino de todos os andares, laboratório, RH, alçadas, PDCA, lições, estudo,
     reunião, auditoria, ronda de TI, canal e registro total), no ritmo normal da empresa;
  3. SALVA a cada 10 minutos e no fim, nesta ordem: registro total → instantâneo do SQLite → cópia incremental de todas
     as tabelas para o schema robo. A ordem garante que, se a máquina do GitHub cair no meio, nada que já foi salvo
     se perde e nada fica com número repetido (o próximo turno continua do último instantâneo).

A ESTEIRA também roda na nuvem: a fábrica gera planilhas sintéticas (TREINO_*) e o monitor as processa como se fossem
reais. Elas vão só para os schemas laboratorio e treino do PostgreSQL (nunca para bruto, tratado, analitico ou analise).

O que NÃO roda na nuvem: o backup com pg_dump (o próprio PostgreSQL gratuito guarda o histórico, e os instantâneos
ficam lá dentro). Planilhas suas não chegam à nuvem: a pasta de entrada da nuvem só recebe as da fábrica.

Variáveis (Secrets do GitHub — nunca no código, nunca no log):
  ROBO_PG_URL            postgresql://usuario:senha@host/banco?sslmode=require (copiada do painel do Neon)
  ROBO_PG_SENHA_LEITURA  senha que VOCÊ escolhe para o usuário robo_leitura (o do app do celular)
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("robo")

RAIZ = Path(__file__).resolve().parents[1]
MEMORIA_INICIAL = RAIZ / "nuvem" / "memoria_inicial.db.gz"
MANTER_INSTANTANEOS = 6
NAO_RODAM_NA_NUVEM = {"memoria_pg", "registro", "canal", "treino", "laboratorio"}  # cuidadas à parte no turno
LIMITE_MB_PADRAO = 500  # plano gratuito: avisa com 80% (o Neon gratuito dá 0,5 a 1 GB por projeto)


# =============================================================================== configuração
def url_do_ambiente(amb: dict | None = None) -> str:
    """Endereço do PostgreSQL montado SÓ de variáveis de ambiente (nunca de arquivo). Duas formas:
      ROBO_PG_URL                         a URL inteira (GitHub Actions + Neon, o caminho grátis de hoje);
      DB_USER, DB_PASS, DB_NAME           o padrão do Google Cloud Run + Cloud SQL. Com INSTANCE_CONNECTION_NAME a
                                          conexão vai pelo Unix socket /cloudsql/<instância> (sem IP público, sem
                                          porta aberta); sem ela, por DB_HOST e DB_PORT.
    Devolve '' quando nada está definido."""
    from psycopg.conninfo import make_conninfo
    amb = os.environ if amb is None else amb
    url = (amb.get("ROBO_PG_URL") or "").strip()
    if url:
        return url
    if not (amb.get("DB_USER") and amb.get("DB_NAME")):
        return ""
    instancia = (amb.get("INSTANCE_CONNECTION_NAME") or "").strip()
    host = f"/cloudsql/{instancia}" if instancia else (amb.get("DB_HOST") or "localhost")
    return make_conninfo("", host=host, port=None if instancia else (amb.get("DB_PORT") or "5432"),
                         user=amb["DB_USER"], password=amb.get("DB_PASS") or "", dbname=amb["DB_NAME"])


def config_da_nuvem(pasta: Path, url: str, senha_leitura: str = ""):
    """Config montada só da memória (nada de senha em arquivo). As pastas ficam na máquina temporária do turno."""
    from psycopg.conninfo import conninfo_to_dict
    from robo.config import carregar_config
    c = conninfo_to_dict(url)
    pasta = Path(pasta)
    for sub in ("entrada", "logs", "agentes", "habilidades"):
        (pasta / sub).mkdir(parents=True, exist_ok=True)
    host = c.get("host", "localhost")
    local = host in ("localhost", "127.0.0.1") or host.startswith("/")  # Unix socket (Cloud SQL) não usa SSL
    banco = {"habilitado": True, "host": host, "porta": int(c.get("port") or 5432),
             "banco": c.get("dbname", "neondb"), "usuario": c.get("user", "postgres"), "senha": c.get("password", ""),
             "sslmode": c.get("sslmode") or ("" if local else "require"),
             "usuario_leitura": "robo_leitura", "senha_leitura": senha_leitura, "tempo_limite_conexao": 20}
    return carregar_config(pasta / "config_nuvem_inexistente.yaml", sobrescrever={
        "pastas": {k: str(pasta / k) for k in ("entrada", "logs", "agentes", "habilidades")},
        "banco": banco, "rotinas": {"agendador": "robo"}, "backup": {"copia_extra": "", "postgres": False},
        # lotes menores na nuvem: cabem no turno de 20 min e no plano gratuito do banco
        "fabrica": {"linhas_min": 1000, "linhas_max": 5000},
        # o grupo do Telegram também atende pela nuvem (token em ROBO_TELEGRAM_TOKEN, nos Secrets do GitHub)
        "telegram": {"habilitado": bool(os.environ.get("ROBO_TELEGRAM_CHAT")),
                     "chat_id": os.environ.get("ROBO_TELEGRAM_CHAT", ""), "dono_id": os.environ.get("ROBO_TELEGRAM_DONO", "")}})


def _conectar(cfg):
    from robo.banco import Banco
    return Banco(cfg.banco, cfg.base).conectar()


# =============================================================================== instantâneos (o SQLite inteiro)
ESQUEMA_PG = """CREATE SCHEMA IF NOT EXISTS robo;
CREATE TABLE IF NOT EXISTS robo.instantaneos_sqlite (
  id BIGSERIAL PRIMARY KEY, data_hora TIMESTAMPTZ DEFAULT now(), sha256 TEXT NOT NULL, tamanho BIGINT, linhas BIGINT,
  tabelas INTEGER, conteudo BYTEA NOT NULL);"""


def _sha_descompactado(dados_gz: bytes) -> str:
    return hashlib.sha256(gzip.decompress(dados_gz)).hexdigest()


def restaurar(cfg) -> dict:
    """Traz a memória para a máquina do turno. Ordem: último instantâneo do banco; senão, a memória inicial do projeto;
    senão, começa vazia (e diz isso). Sempre confere o SHA-256 antes de usar."""
    destino = Path(cfg.logs) / "trabalho.db"
    if destino.exists():
        return {"origem": "local", "arquivo": str(destino)}
    with _conectar(cfg) as conn:
        conn.execute(ESQUEMA_PG)
        r = conn.execute("SELECT id, sha256, conteudo FROM robo.instantaneos_sqlite ORDER BY id DESC LIMIT 1").fetchone()
    from robo import registro_total
    if r:
        dados = bytes(r[2])
        if _sha_descompactado(dados) != r[1]:
            raise RuntimeError(f"o instantâneo {r[0]} do banco não confere com o próprio SHA-256: não vou usar memória corrompida")
        destino.write_bytes(gzip.decompress(dados))
        saida = {"origem": f"instantaneo {r[0]}", "sha256": r[1]}
    elif MEMORIA_INICIAL.exists():
        from robo import backup
        r = backup.restaurar_sqlite(cfg, MEMORIA_INICIAL)
        saida = {"origem": "memoria_inicial", "sha256": r["sha256"], "linhas": r["linhas"]}
    else:
        return {"origem": "vazia"}
    saida["arquivos"] = registro_total.restaurar_arquivos(cfg)  # canal, estado da TI, âncora, equipe… de volta
    return saida


def salvar_instantaneo(cfg) -> dict:
    from robo import backup
    b = backup.backup_sqlite(cfg)  # cópia online conferida (integrity_check) e compactada
    if not b.get("ok"):
        raise RuntimeError(f"não consegui copiar a memória: {b.get('motivo')}")
    arq = backup.pasta_sqlite(cfg) / b["arquivo"]
    dados = arq.read_bytes()
    with _conectar(cfg) as conn:
        conn.execute(ESQUEMA_PG)
        conn.execute("INSERT INTO robo.instantaneos_sqlite (sha256, tamanho, linhas, tabelas, conteudo) VALUES (%s,%s,%s,%s,%s)",
                     (b["sha256"], len(dados), b["linhas"], b["tabelas"], dados))
        # só os instantâneos (cópias do arquivo) giram; a memória de verdade fica nas tabelas robo.memoria_*, que nunca
        # perdem linha
        conn.execute("DELETE FROM robo.instantaneos_sqlite WHERE id NOT IN (SELECT id FROM robo.instantaneos_sqlite "
                     "ORDER BY id DESC LIMIT %s)", (MANTER_INSTANTANEOS,))
    return {"linhas": b["linhas"], "tabelas": b["tabelas"], "tamanho_kb": round(len(dados) / 1024)}


def garantir_leitura(cfg) -> bool:
    """Usuário robo_leitura (o do app do celular): só SELECT, transações somente leitura, só no schema robo."""
    senha = (cfg.banco or {}).get("senha_leitura")
    if not senha:
        return False
    from psycopg import sql
    with _conectar(cfg) as conn:
        existe = conn.execute("SELECT 1 FROM pg_roles WHERE rolname='robo_leitura'").fetchone()
        comando = "ALTER ROLE robo_leitura WITH LOGIN PASSWORD {}" if existe else "CREATE ROLE robo_leitura WITH LOGIN PASSWORD {}"
        conn.execute(sql.SQL(comando).format(sql.Literal(senha)))
        conn.execute("ALTER ROLE robo_leitura SET default_transaction_read_only = on")
        banco = sql.Identifier(cfg.banco["banco"])
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO robo_leitura").format(banco))
        conn.execute("CREATE SCHEMA IF NOT EXISTS robo")
        conn.execute("GRANT USAGE ON SCHEMA robo TO robo_leitura")
        conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA robo TO robo_leitura")
        conn.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA robo GRANT SELECT ON TABLES TO robo_leitura")
    return True


def tamanho_mb(cfg) -> float:
    with _conectar(cfg) as conn:
        return round(conn.execute("SELECT pg_database_size(current_database())").fetchone()[0] / 1024 ** 2, 1)


# =============================================================================== o turno
def salvar(cfg) -> dict:
    """Registro total → instantâneo → cópia incremental (essa ordem nunca deixa número repetido para trás)."""
    from robo import cobertura_banco, memoria, registro_total, rotinas
    rotinas.executar(cfg, "registro", lambda: registro_total.capturar(cfg))
    try:  # quais tabelas têm dados e por que as vazias estão vazias (vai junto no instantâneo e no espelho)
        cobertura_banco.salvar_relatorio(cfg, cobertura_banco.levantar(cfg))
    except Exception:
        log.exception("Turno na nuvem: levantamento de cobertura falhou")
    inst = salvar_instantaneo(cfg)
    rotinas.executar(cfg, "memoria_pg", lambda: memoria.sincronizar_postgres(cfg))
    garantir_leitura(cfg)  # tabelas novas também ficam legíveis no celular
    return inst


def _esteira(monitor) -> int:
    """Uma passada do monitor na pasta de entrada da nuvem (planilhas da fábrica). Falha aqui não derruba o turno."""
    try:
        return len(monitor.ciclo(forcar=True))
    except Exception:
        log.exception("Turno na nuvem: a esteira falhou nesta volta")
        return 0


def turno(cfg, minutos: float = 20, salvar_a_cada_min: float = 10, pausa_s: float = 15, parar=None) -> dict:
    """parar: threading.Event opcional. Quando é ligado (SIGTERM do Cloud Run, Ctrl+C), o turno sai do laço e SALVA
    a memória antes de devolver (encerramento gracioso: nada do que foi feito se perde)."""
    from robo import rotinas
    from robo.monitor import Monitor
    inicio = time.monotonic()
    fim = inicio + minutos * 60
    origem = restaurar(cfg)
    log.info("Turno na nuvem: memória restaurada de %s", origem["origem"])
    sessao = rotinas.abrir_sessao(cfg)["sessao"]
    garantir_leitura(cfg)
    for nome in rotinas.ROTINAS:  # cada uma decide se está na hora (backup diário, reunião semanal…)
        if nome not in NAO_RODAM_NA_NUVEM:
            rotinas.executar(cfg, nome, rotinas.funcao(cfg, nome))
    from robo import pos_processamento
    monitor = Monitor(cfg, ao_processar=lambda r: pos_processamento.registrar(cfg, r))
    planilhas = _esteira(monitor)
    ultimo_salvo = time.monotonic()
    voltas = 0
    while time.monotonic() < fim and not (parar is not None and parar.is_set()):
        voltas += 1
        for nome in ("canal", "registro", "treino", "laboratorio", "fabrica", "demandas", "telegram"):
            rotinas.executar(cfg, nome, rotinas.funcao(cfg, nome))
        planilhas += _esteira(monitor)
        rotinas.batimento(cfg, sessao)
        if time.monotonic() - ultimo_salvo >= salvar_a_cada_min * 60:
            salvar(cfg)
            ultimo_salvo = time.monotonic()
        espera = max(0.0, min(pausa_s, fim - time.monotonic()))
        if parar is not None:
            parar.wait(espera)
        else:
            time.sleep(espera)
    planilhas += _esteira(monitor)
    for nome in ("fabrica", "ronda_ti", "rh_desempenho", "alcadas"):  # fecham o turno (a fábrica confere o gabarito)
        if nome in rotinas.ROTINAS:
            rotinas.executar(cfg, nome, rotinas.funcao(cfg, nome))
    inst = salvar(cfg)
    mb = tamanho_mb(cfg)
    limite = float(os.environ.get("ROBO_LIMITE_MB") or LIMITE_MB_PADRAO)
    alerta = mb >= 0.8 * limite
    if alerta:
        try:
            from robo.canal import Canal
            Canal(cfg).postar("dba", f"O banco gratuito da nuvem está com {mb} MB de {limite:.0f} MB (80%+). Nada foi apagado; "
                                     "é hora de decidir: arquivar em backup criptografado ou mudar de plano.", "banco", "alerta")
        except Exception:
            pass
    return {"origem": origem["origem"], "minutos": round((time.monotonic() - inicio) / 60, 1), "voltas": voltas,
            "planilhas_processadas": planilhas,
            "memoria": inst, "banco_mb": mb, "limite_mb": limite, "alerta_espaco": alerta}


def resumo_do_turno(cfg) -> dict:
    """Números do que aconteceu (sem nenhum segredo): vão para o log público do GitHub."""
    import sqlite3
    c = sqlite3.connect(f"file:{Path(cfg.logs) / 'trabalho.db'}?mode=ro", uri=True)
    try:
        q = lambda s: c.execute(s).fetchone()[0]  # noqa: E731
        hoje = datetime.now().strftime("%Y-%m-%d")
        return {"tentativas_total": q("SELECT COUNT(*) FROM treino_tentativas"),
                "tentativas_hoje": q(f"SELECT COUNT(*) FROM treino_tentativas WHERE data_hora >= '{hoje}'"),
                "acertos_hoje": q(f"SELECT COALESCE(SUM(acertou),0) FROM treino_tentativas WHERE data_hora >= '{hoje}'"),
                "pessoas_hoje": q(f"SELECT COUNT(DISTINCT funcionario) FROM treino_tentativas WHERE data_hora >= '{hoje}'"),
                "conversas_total": q("SELECT COUNT(*) FROM interacoes"),
                "registros_de_log": q("SELECT COUNT(*) FROM logs_sistema") if c.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='logs_sistema'").fetchone() else 0}
    finally:
        c.close()


def mascarar_para_o_github(url: str) -> None:
    """No GitHub Actions, esconde host, usuário e senha do log público (o GitHub troca por ***)."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    from psycopg.conninfo import conninfo_to_dict
    c = conninfo_to_dict(url)
    for valor in (c.get("host"), c.get("user"), c.get("password"), os.environ.get("ROBO_PG_SENHA_LEITURA")):
        if valor:
            print(f"::add-mask::{valor}", flush=True)


def manifesto_inicial() -> dict | None:
    m = MEMORIA_INICIAL.with_name(MEMORIA_INICIAL.name.replace(".db.gz", ".db.manifesto.json"))
    return json.loads(m.read_text(encoding="utf-8")) if m.exists() else None
