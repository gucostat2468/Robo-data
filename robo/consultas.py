"""Biblioteca de consultas SQL por problema de negócio (pasta consultas_sql/).

Cada arquivo .sql começa com um cabeçalho que o painel mostra:
    -- titulo: NPS geral com margem de erro
    -- pergunta: Qual é o NPS e quão confiável é esse número?
    -- como_ler: ...
    -- requer: tratado.fato_nps (nota_nps)

Você pode criar as suas: copie um arquivo, troque o SQL e o cabeçalho. Subpastas viram categorias.
A execução pelo painel é SOMENTE LEITURA (o banco recusa qualquer alteração) e tem tempo limite.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from robo.config import RAIZ_PROJETO

PASTA_PADRAO = RAIZ_PROJETO / "consultas_sql"
RE_CAMPO = re.compile(r"^--\s*(titulo|pergunta|como_ler|requer)\s*:\s*(.+)$", re.IGNORECASE)
LIMITE_LINHAS = 1000


def _categoria(pasta: Path) -> str:
    return re.sub(r"^\d+[\s_-]*", "", pasta.name).strip() or pasta.name


def _cabecalho(texto: str) -> dict:
    campos = {}
    for linha in texto.splitlines():
        m = RE_CAMPO.match(linha.strip())
        if m:
            campos[m.group(1).lower()] = m.group(2).strip()
        elif linha.strip() and not linha.strip().startswith("--"):
            break
    return campos


def listar(pasta: Path = PASTA_PADRAO) -> list[dict]:
    if not pasta.exists():
        return []
    itens = []
    for arq in sorted(pasta.rglob("*.sql")):
        if arq.name.startswith("_"):
            continue
        rel = arq.relative_to(pasta).as_posix()
        cab = _cabecalho(arq.read_text(encoding="utf-8-sig"))
        itens.append({
            "id": rel,
            "categoria": _categoria(arq.parent) if arq.parent != pasta else "Minhas consultas",
            "titulo": cab.get("titulo") or arq.stem.replace("_", " "),
            "pergunta": cab.get("pergunta", ""),
            "como_ler": cab.get("como_ler", ""),
            "requer": cab.get("requer", ""),
        })
    return itens


def caminho_seguro(id_consulta: str, pasta: Path = PASTA_PADRAO) -> Path:
    alvo = (pasta / id_consulta).resolve()
    if pasta.resolve() not in alvo.parents or alvo.suffix.lower() != ".sql" or not alvo.is_file():
        raise ValueError("Consulta não encontrada")
    return alvo


def ler(id_consulta: str, pasta: Path = PASTA_PADRAO) -> dict:
    arq = caminho_seguro(id_consulta, pasta)
    item = next((i for i in listar(pasta) if i["id"] == id_consulta), {})
    return {**item, "sql": arq.read_text(encoding="utf-8-sig"), "caminho": str(arq)}


def executar(banco, id_consulta: str, pasta: Path = PASTA_PADRAO, limite: int = LIMITE_LINHAS) -> dict:
    """Roda a consulta da biblioteca em transação SOMENTE LEITURA com tempo limite de 60 s."""
    return executar_texto(banco, caminho_seguro(id_consulta, pasta).read_text(encoding="utf-8-sig"), limite)


# funções do servidor que têm efeito mesmo numa transação somente leitura (administração, arquivos, sinais, sessão)
FUNCOES_PROIBIDAS = re.compile(
    r"\b(pg_terminate_backend|pg_cancel_backend|pg_reload_conf|pg_rotate_logfile|pg_switch_wal|pg_promote|"
    r"pg_read_file|pg_read_binary_file|pg_ls_\w+|pg_stat_file|pg_stat_reset\w*|pg_create_\w+|pg_drop_\w+|"
    r"pg_advisory\w*|pg_notify|set_config|lo_\w+|dblink\w*|pg_file_\w+|pg_logdir_ls|pg_import_system_collations|"
    r"txid_current|pg_current_xact_id)\s*\(", re.IGNORECASE)


def _sem_textos(sql: str) -> str:
    """Tira comentários e textos entre aspas (para procurar ';' e palavras só no código SQL)."""
    sql = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"\$(\w*)\$.*?\$\1\$", "''", sql, flags=re.S)       # $$ ... $$
    return re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "''", sql)  # 'texto' e "identificador"


def validar_leitura(texto: str) -> None:
    """Camadas antes do banco (o banco é a última): um comando só, sem controle de transação nem funções perigosas."""
    codigo = _sem_textos(texto).strip().rstrip(";").strip()
    if not codigo:
        raise ValueError("Consulta vazia.")
    if ";" in codigo:
        raise ValueError("Consulta recusada: rode um comando por vez (sem ';' no meio).")
    if not re.match(r"^\(?\s*(select|with|values|table|explain)\b", codigo, re.IGNORECASE):
        raise ValueError("Consulta recusada: o painel roda somente leitura (SELECT/WITH).")
    if re.search(r"\b(commit|rollback|begin|start\s+transaction|savepoint|set|reset|copy|call|do|lock|notify|listen|"
                 r"prepare|execute|deallocate|discard|vacuum|analyze\s+\w|grant|revoke)\b",
                 re.sub(r"\bexplain\s+(\(.*?\)\s*)?analyze\b", "explain", codigo, flags=re.IGNORECASE | re.S),
                 re.IGNORECASE):
        raise ValueError("Consulta recusada: só leitura (sem SET, COPY, COMMIT, CALL, DO, LOCK…).")
    m = FUNCOES_PROIBIDAS.search(codigo)
    if m:
        raise ValueError(f"Consulta recusada: a função {m.group(1)} tem efeito no servidor e não é permitida aqui.")


def executar_texto(banco, texto: str, limite: int = LIMITE_LINHAS) -> dict:
    """Roda qualquer SQL de leitura escrito pelo dono, em camadas:
    1. validar_leitura: um comando só, começa com SELECT/WITH, sem SET/COPY/controle de transação/funções perigosas;
    2. conexão em modo somente leitura (psycopg read_only) + SET TRANSACTION READ ONLY;
    3. a transação SEMPRE é desfeita no fim (force_rollback), mesmo que algo tenha passado;
    4. tempo limite de 60 s.
    O mais forte de tudo é usar um usuário do PostgreSQL que só tem SELECT (banco.usuario_leitura no config)."""
    validar_leitura(texto)
    inicio = time.perf_counter()
    with banco.conectar(leitura=True) as conn:
        conn.read_only = True
        with conn.transaction(force_rollback=True):
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout = '60s'")
            cur = conn.execute(texto, prepare=True)  # protocolo estendido: o servidor aceita um comando só
            colunas = [d.name for d in cur.description] if cur.description else []
            linhas = cur.fetchmany(limite + 1) if colunas else []
    return {
        "colunas": colunas,
        "linhas": linhas[:limite],
        "truncado": len(linhas) > limite,
        "duracao": round(time.perf_counter() - inicio, 3),
    }


def disponibilidade(banco, itens: list[dict] | None = None) -> list[dict]:
    """Cada consulta com 'disponivel' e, se não estiver, o motivo: as tabelas do cabeçalho 'requer' existem e têm
    linhas? Assim a tela mostra "precisa de planilha real de NPS" em vez de deixar a consulta quebrar."""
    itens = listar() if itens is None else itens
    saida, cache, sem_acesso = [], {}, {}
    with banco.conectar(leitura=True) as conn:
        for c in itens:
            tabelas = re.findall(r"\b([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\b", c.get("requer") or "")
            faltam = []
            for tab in tabelas:
                if tab not in cache:
                    try:
                        with conn.transaction():  # um erro (ex.: sem permissão) não contamina a próxima checagem
                            existe = conn.execute("SELECT to_regclass(%s)", (tab,)).fetchone()[0]
                            cache[tab] = bool(existe) and bool(conn.execute(f"SELECT 1 FROM {tab} LIMIT 1").fetchone())
                    except Exception as e:
                        cache[tab] = False
                        sem_acesso[tab] = type(e).__name__
                if not cache[tab]:
                    faltam.append(tab)
            motivo = ""
            if faltam and any(x in sem_acesso for x in faltam):
                motivo = "o usuário de leitura não tem acesso a " + ", ".join(x for x in faltam if x in sem_acesso)
            elif faltam:
                real = [x for x in faltam if x.split(".")[0] in ("tratado", "analitico", "analise")]
                motivo = (f"precisa de planilha REAL carregada ({', '.join(real)})" if real
                          else f"ainda sem dados em {', '.join(faltam)}")
            saida.append({**c, "disponivel": not faltam, "motivo": motivo})
    return saida


def explicar_erro(mensagem: str, requer: str = "") -> str:
    m = mensagem.lower()
    if "does not exist" in m or "não existe" in m:
        alvo = re.search(r'(?:relation|relação|column|coluna) "([^"]+)"', mensagem)
        nome = f" ({alvo.group(1)})" if alvo else ""
        return (f"Esta consulta usa uma tabela ou coluna que ainda não existe no seu banco{nome}. "
                f"Ela precisa de: {requer or 'ver cabeçalho do arquivo'}. Carregue a planilha correspondente "
                "ou edite o .sql trocando pelos nomes das suas tabelas/colunas.")
    if "read-only" in m or "somente leitura" in m:
        return "Consultas do painel são somente leitura: comandos que alteram dados (INSERT, UPDATE, CREATE...) são bloqueados."
    if "statement timeout" in m or "tempo limite" in m:
        return "A consulta passou de 60 segundos e foi interrompida. Filtre um período menor."
    return mensagem
