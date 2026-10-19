"""Instala o banco REAL da empresa no PostgreSQL do seu computador, do jeito certo (uma vez só).

  python -m robo instalar-banco            (pede a senha do usuário 'postgres' que você criou ao instalar o PostgreSQL)

O que faz, em ordem (tudo idempotente: rodar de novo não estraga nada, só troca as senhas):
  1. cria dois usuários com senha forte gerada na hora:
       robo_app     — dono das tabelas do robô (grava);
       robo_leitura — só leitura (SELECT), para as consultas livres do painel e para o Power BI;
  2. cria o banco robo_dados (dono: robo_app) — e o robo_demonstracao, separado, para o modo demonstração — e os schemas bruto, tratado, analitico, robo (memória da empresa),
     analise, laboratorio e treino;
  3. dá ao robo_leitura leitura em tudo que existe e no que for criado depois, e deixa as transações dele somente leitura;
  4. grava no config.yaml só o que NÃO é segredo (servidor, porta, banco, usuários e os NOMES das variáveis de ambiente);
  5. as senhas vão para variáveis de ambiente do SEU usuário do Windows (setx ROBO_PG_SENHA / ROBO_PG_SENHA_LEITURA) —
     nunca para arquivo;
  6. prova que funcionou: conecta como robo_app, tenta CRIAR uma tabela como robo_leitura (tem que ser recusado) e copia
     a memória inteira da empresa (SQLite) para o schema robo.
"""

from __future__ import annotations

import os
import secrets
import subprocess
from pathlib import Path

SCHEMAS = ("bruto", "tratado", "analitico", "robo", "analise", "laboratorio", "treino")
VAR_APP, VAR_LEITURA = "ROBO_PG_SENHA", "ROBO_PG_SENHA_LEITURA"
BANCO_DEMONSTRACAO = "robo_demonstracao"  # o modo demonstração grava aqui, nunca no banco de produção


def _q(nome: str) -> str:
    return '"' + nome.replace('"', '""') + '"'


def instalar(caminho_config: Path, superusuario: str, senha_super: str, host: str = "localhost", porta: int = 5432,
             banco: str = "robo_dados", usuario_app: str = "robo_app", usuario_leitura: str = "robo_leitura",
             gravar_variaveis: bool = True, banco_demonstracao: str = BANCO_DEMONSTRACAO) -> dict:
    import psycopg
    from psycopg import sql

    senha_app, senha_leitura = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    base = {"host": host, "port": int(porta), "user": superusuario, "password": senha_super, "connect_timeout": 10}
    passos = []
    with psycopg.connect(dbname="postgres", autocommit=True, **base) as c:
        versao = c.execute("SHOW server_version").fetchone()[0]
        for papel, senha in ((usuario_app, senha_app), (usuario_leitura, senha_leitura)):
            existe = c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (papel,)).fetchone()
            comando = "ALTER ROLE {} WITH LOGIN PASSWORD {}" if existe else "CREATE ROLE {} WITH LOGIN PASSWORD {}"
            c.execute(sql.SQL(comando).format(sql.Identifier(papel), sql.Literal(senha)))
            passos.append(f"usuário {papel} {'atualizado (senha nova)' if existe else 'criado'}")
        c.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(sql.Identifier(usuario_leitura)))
        for nome in (banco, banco_demonstracao):
            novo = not c.execute("SELECT 1 FROM pg_database WHERE datname=%s", (nome,)).fetchone()
            if novo:
                c.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8'").format(sql.Identifier(nome), sql.Identifier(usuario_app)))
                passos.append(f"banco {nome} criado (dono {usuario_app})")
            else:
                c.execute(sql.SQL("ALTER DATABASE {} OWNER TO {}").format(sql.Identifier(nome), sql.Identifier(usuario_app)))
                passos.append(f"banco {nome} já existia: dono passou a ser {usuario_app}")
            c.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(nome), sql.Identifier(usuario_leitura)))
    for nome in (banco, banco_demonstracao):
        with psycopg.connect(dbname=nome, autocommit=True, **base) as c:
            c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            for s in SCHEMAS:
                c.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(sql.Identifier(s), sql.Identifier(usuario_app)))
                c.execute(sql.SQL("ALTER SCHEMA {} OWNER TO {}").format(sql.Identifier(s), sql.Identifier(usuario_app)))
                for (t,) in c.execute("SELECT tablename FROM pg_tables WHERE schemaname=%s", (s,)).fetchall():  # tabelas antigas
                    c.execute(sql.SQL("ALTER TABLE {} OWNER TO {}").format(sql.Identifier(s, t), sql.Identifier(usuario_app)))
                c.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(s), sql.Identifier(usuario_leitura)))
                c.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(sql.Identifier(s), sql.Identifier(usuario_leitura)))
                c.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} GRANT SELECT ON TABLES TO {}").format(
                    sql.Identifier(usuario_app), sql.Identifier(s), sql.Identifier(usuario_leitura)))
    passos.append(f"schemas {', '.join(SCHEMAS)} prontos em {banco} e {banco_demonstracao} (modo demonstração, separado); "
                  f"{usuario_leitura} lê tudo (inclusive o que for criado depois)")

    from robo.painel import configuracao
    arq = configuracao.garantir_arquivo(Path(caminho_config) if caminho_config else None)
    for chave, valor in (("habilitado", True), ("host", host), ("porta", int(porta)), ("banco", banco), ("usuario", usuario_app),
                         ("senha", ""), ("senha_variavel_ambiente", VAR_APP), ("usuario_leitura", usuario_leitura),
                         ("senha_leitura_variavel_ambiente", VAR_LEITURA)):
        configuracao._gravar(arq, "banco", chave, valor)
    passos.append(f"config.yaml atualizado ({arq}) — sem nenhuma senha dentro")

    os.environ[VAR_APP], os.environ[VAR_LEITURA] = senha_app, senha_leitura
    variaveis = "nesta sessão"
    if gravar_variaveis and os.name == "nt":
        for var, val in ((VAR_APP, senha_app), (VAR_LEITURA, senha_leitura)):
            subprocess.run(["setx", var, val], check=True, capture_output=True)
        variaveis = "permanentes no seu usuário do Windows (setx)"
    passos.append(f"senhas nas variáveis de ambiente {VAR_APP} e {VAR_LEITURA} ({variaveis})")

    # provas (só com a parte do banco: não dependem de a pasta de entrada já estar configurada)
    import yaml
    from robo.banco import Banco
    dados_banco = (yaml.safe_load(arq.read_text(encoding="utf-8")) or {}).get("banco") or {}
    b = Banco(dados_banco, arq.parent)
    with b.conectar() as conn:
        conn.execute("SELECT 1")
    passos.append(f"conectou como {usuario_app}")
    recusou = False
    try:
        with b.conectar(leitura=True) as conn:
            conn.execute("CREATE TABLE robo.teste_escrita_proibida (x int)")
    except Exception:
        recusou = True
    if not recusou:
        raise RuntimeError(f"{usuario_leitura} conseguiu criar tabela: as permissões não ficaram só leitura")
    passos.append(f"{usuario_leitura} tentou criar tabela e o banco recusou (só leitura de verdade)")
    try:
        from robo import memoria
        from robo.config import carregar_config
        s = memoria.sincronizar_postgres(carregar_config(arq))
        copiadas = {k: v for k, v in s.items() if k not in ("ok", "schema")}
        passos.append(f"memória da empresa copiada para {s['schema']}: {len(copiadas)} tabelas, {sum(copiadas.values())} linhas")
    except Exception as e:  # ex.: pasta de entrada ainda não configurada — o robô copia sozinho na 1ª hora aberto
        passos.append(f"cópia da memória fica para quando o robô abrir (agora não deu: {e})")
    return {"ok": True, "versao_postgres": versao, "passos": passos, "config": str(arq),
            "conexao": {"host": host, "porta": int(porta), "banco": banco, "usuario_app": usuario_app,
                        "usuario_leitura": usuario_leitura, "variavel_senha_app": VAR_APP, "variavel_senha_leitura": VAR_LEITURA},
            "senhas": {usuario_app: senha_app, usuario_leitura: senha_leitura}}
