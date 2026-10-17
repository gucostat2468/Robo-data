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
    """Roda a consulta em transação SOMENTE LEITURA com tempo limite de 60 s."""
    texto = caminho_seguro(id_consulta, pasta).read_text(encoding="utf-8-sig")
    sem_comentarios = re.sub(r"--[^\n]*|/\*.*?\*/", " ", texto, flags=re.S)
    if re.search(r"\b(commit|rollback|begin|start\s+transaction|savepoint|set\s+(session|transaction))\b",
                 sem_comentarios, re.IGNORECASE):
        raise ValueError("Consulta recusada: o painel só roda consultas de leitura (sem COMMIT/ROLLBACK/BEGIN).")
    inicio = time.perf_counter()
    with banco.conectar() as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout = '60s'")
            cur = conn.execute(texto)
            colunas = [d.name for d in cur.description] if cur.description else []
            linhas = cur.fetchmany(limite + 1) if colunas else []
        conn.rollback()
    return {
        "colunas": colunas,
        "linhas": linhas[:limite],
        "truncado": len(linhas) > limite,
        "duracao": round(time.perf_counter() - inicio, 3),
    }


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
