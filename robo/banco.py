"""Carga no PostgreSQL em camadas (arquitetura "medalhão", padrão de mercado para ELT).

  bruto      Dados EXATAMENTE como vieram da planilha (tudo texto) + linha de origem.
             Recebe TUDO o que chegou, inclusive arquivos reprovados (veja robo.lotes para o status):
             serve de auditoria e permite reconstruir tudo sem a planilha original.
  tratado    Resultado da limpeza/validação do robô, com tipos corretos (número, data...).
  analitico  Visões e tabelas criadas por VOCÊ em SQL (pasta modelos_sql/). É aqui que acontece
             o "T" do ELT: transformações dentro do banco, prontas para o Power BI.
  robo       Controle: tabela "lotes" com cada carga feita (status, linhas, erros).

Regras de segurança:
- Tudo de um arquivo acontece numa TRANSAÇÃO: ou entra inteiro, ou nada entra.
- Tabelas nunca são apagadas (DROP). Colunas novas são adicionadas; tipos só são "alargados"
  (ex.: inteiro -> decimal, data -> data e hora). Conflito real (texto numa coluna numérica) reprova.
- Reprocessar o mesmo arquivo não duplica dados (modo padrão "por_arquivo").
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

from robo.limpeza import _texto_de, normalizar_nome_coluna
from robo.modelagem import tabela_calendario

log = logging.getLogger("robo")

MODOS_CARGA = {"por_arquivo", "substituir", "mesclar", "anexar"}

# tipo do PostgreSQL -> "largura" (para saber se dá para alargar automaticamente)
ALARGAMENTOS = {
    ("bigint", "double precision"): "double precision",
    ("double precision", "bigint"): "double precision",
    ("date", "timestamp without time zone"): "timestamp without time zone",
    ("timestamp without time zone", "date"): "timestamp without time zone",
}


class ErroBancoIndisponivel(Exception):
    """Banco fora do ar / senha errada / rede: problema temporário -> o arquivo espera e tenta de novo."""


class ErroBancoNaoExiste(ErroBancoIndisponivel):
    pass


class ErroCargaDados(Exception):
    """Problema nos dados ou na estrutura (ex.: texto em coluna numérica) -> o arquivo é reprovado."""


def _psycopg():
    try:
        import psycopg
        from psycopg import sql
        return psycopg, sql
    except ImportError as e:  # pragma: no cover
        raise ErroBancoIndisponivel("Biblioteca psycopg não instalada. Rode instalar.bat novamente.") from e


def tipo_pg(serie: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(serie):
        return "boolean"
    if pd.api.types.is_integer_dtype(serie):
        return "bigint"
    if pd.api.types.is_float_dtype(serie):
        return "double precision"
    if pd.api.types.is_datetime64_any_dtype(serie):
        v = serie.dropna()
        return "date" if v.empty or (v == v.dt.normalize()).all() else "timestamp without time zone"
    return "text"


def _valor_pg(v, tipo: str):
    """Converte um valor do pandas para o tipo Python que o psycopg entende."""
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.date() if tipo == "date" else v.to_pydatetime()
    if tipo == "date" and isinstance(v, datetime):
        return v.date()
    if tipo == "text" and not isinstance(v, str):
        return _texto_de(v)
    return v


class Banco:
    def __init__(self, cfg_banco: dict, pasta_projeto: Path):
        self.cfg = cfg_banco
        self.schemas = {"bruto": "bruto", "tratado": "tratado", "analitico": "analitico", "controle": "robo",
                        **(cfg_banco.get("schemas") or {})}
        pasta_modelos = Path(cfg_banco.get("pasta_modelos") or "modelos_sql")
        self.pasta_modelos = pasta_modelos if pasta_modelos.is_absolute() else pasta_projeto / pasta_modelos

    @property
    def habilitado(self) -> bool:
        return bool(self.cfg.get("habilitado"))

    # ------------------------------------------------------------------ conexão
    def _parametros(self, banco: str | None = None) -> dict:
        import os
        senha = self.cfg.get("senha") or ""
        variavel = self.cfg.get("senha_variavel_ambiente")
        if variavel and os.environ.get(variavel):
            senha = os.environ[variavel]
        return {
            "host": self.cfg.get("host", "localhost"),
            "port": int(self.cfg.get("porta", 5432)),
            "dbname": banco or self.cfg.get("banco", "robo_dados"),
            "user": self.cfg.get("usuario", "postgres"),
            "password": senha,
            "connect_timeout": int(self.cfg.get("tempo_limite_conexao", 5)),
            "application_name": "robo_planilhas",
        }

    def conectar(self, banco: str | None = None):
        psycopg, _ = _psycopg()
        try:
            return psycopg.connect(**self._parametros(banco))
        except psycopg.OperationalError as e:
            m = str(e).lower()
            classe = ErroBancoNaoExiste if (("database" in m and "does not exist" in m)
                                            or ("banco de dados" in m and "não existe" in m)) else ErroBancoIndisponivel
            raise classe(_explicar_erro_conexao(str(e), self._parametros(banco))) from e

    def criar_banco_se_preciso(self) -> bool:
        """Conecta no banco 'postgres' (sempre existe) e cria o banco do robô se ainda não existir."""
        psycopg, sql = _psycopg()
        nome = self.cfg.get("banco", "robo_dados")
        try:
            with self.conectar(nome):
                return False
        except ErroBancoNaoExiste:
            pass
        with self.conectar("postgres") as conn:
            conn.autocommit = True
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
        log.info("Banco de dados '%s' criado no PostgreSQL", nome)
        return True

    def inicializar(self, conn) -> None:
        _, sql = _psycopg()
        for schema in self.schemas.values():
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        conn.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS {}.lotes (
                lote_id        text PRIMARY KEY,
                arquivo        text NOT NULL,
                status         text NOT NULL,
                processado_em  timestamptz NOT NULL DEFAULT now(),
                linhas_entrada integer,
                linhas_saida   integer,
                erros          integer,
                avisos         integer,
                tabelas        text[],
                mensagem       text,
                ocorrencias    jsonb
            )""").format(sql.Identifier(self.schemas["controle"])))
        # uma linha por erro/aviso: base das consultas de qualidade ("quais erros mais se repetem?")
        conn.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS {}.ocorrencias (
                lote_id        text NOT NULL,
                arquivo        text NOT NULL,
                processado_em  timestamptz NOT NULL DEFAULT now(),
                status_lote    text,
                nivel          text NOT NULL,
                tabela         text,
                coluna         text,
                mensagem       text NOT NULL,
                quantidade     integer,
                exemplos       text
            )""").format(sql.Identifier(self.schemas["controle"])))

    def testar(self) -> dict:
        try:
            criado = self.criar_banco_se_preciso()
            with self.conectar() as conn:
                self.inicializar(conn)
                versao = conn.execute("SHOW server_version").fetchone()[0]
            return {"ok": True, "versao": versao, "banco_criado": criado,
                    "mensagem": f"Conectado ao PostgreSQL {versao}, banco '{self.cfg.get('banco', 'robo_dados')}'"}
        except ErroBancoIndisponivel as e:
            return {"ok": False, "mensagem": str(e)}

    # ------------------------------------------------------------------ estrutura
    def _colunas_existentes(self, conn, schema: str, tabela: str) -> dict[str, str]:
        linhas = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position", (schema, tabela)).fetchall()
        return {c: t for c, t in linhas}

    def _garantir_tabela(self, conn, schema: str, tabela: str, colunas: dict[str, str]) -> dict[str, str]:
        """Cria a tabela ou adapta a existente (novas colunas / alargamento de tipo). Devolve os tipos finais."""
        _, sql = _psycopg()
        existentes = self._colunas_existentes(conn, schema, tabela)
        alvo = sql.Identifier(schema, tabela)
        if not existentes:
            definicao = sql.SQL(", ").join(sql.SQL("{} {}").format(sql.Identifier(c), sql.SQL(t)) for c, t in colunas.items())
            conn.execute(sql.SQL("CREATE TABLE {} ({})").format(alvo, definicao))
            return dict(colunas)
        finais = dict(existentes)
        for col, tipo in colunas.items():
            atual = existentes.get(col)
            if atual is None:
                conn.execute(sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(alvo, sql.Identifier(col), sql.SQL(tipo)))
                finais[col] = tipo
                log.info("Coluna nova %s.%s.%s (%s)", schema, tabela, col, tipo)
            elif atual == tipo or atual == "text":
                continue
            elif (atual, tipo) in ALARGAMENTOS:
                novo = ALARGAMENTOS[(atual, tipo)]
                if novo != atual:
                    try:
                        conn.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN {} TYPE {}").format(
                            alvo, sql.Identifier(col), sql.SQL(novo)))
                    except Exception as e:
                        raise ErroCargaDados(f"Não consegui mudar {schema}.{tabela}.{col} de {atual} para {novo} "
                                             f"(talvez uma view em analitico dependa dela): {e}") from e
                    finais[col] = novo
            else:
                raise ErroCargaDados(
                    f"Conflito de tipo em {schema}.{tabela}.{col}: no banco é '{atual}', no arquivo veio '{tipo}'. "
                    f"Corrija a planilha ou force o tipo com 'tipos:' na regra do config.yaml.")
        return finais

    def _copiar(self, conn, schema: str, tabela: str, df: pd.DataFrame, tipos: dict[str, str]) -> int:
        _, sql = _psycopg()
        if df.empty:
            return 0
        colunas = list(df.columns)
        comando = sql.SQL("COPY {} ({}) FROM STDIN").format(
            sql.Identifier(schema, tabela), sql.SQL(", ").join(sql.Identifier(c) for c in colunas))
        tipos_colunas = [tipos.get(c, "text") for c in colunas]
        with conn.cursor().copy(comando) as copia:
            for linha in df.astype(object).itertuples(index=False, name=None):
                copia.write_row([_valor_pg(v, t) for v, t in zip(linha, tipos_colunas)])
        return len(df)

    def _apagar(self, conn, schema: str, tabela: str, onde: str, params=()):
        _, sql = _psycopg()
        conn.execute(sql.SQL("DELETE FROM {} WHERE " + onde).format(sql.Identifier(schema, tabela)), params)

    # ------------------------------------------------------------------ camadas
    def carregar_bruto(self, conn, base: str, brutas: dict[str, pd.DataFrame], arquivo: str, lote_id: str) -> list[str]:
        """Grava o conteúdo original (texto) de cada aba em bruto.<base>[_<aba>]."""
        schema = self.schemas["bruto"]
        gravadas = []
        self.esperado_bruto: dict[str, int] = {}
        varias = len(brutas) > 1
        for aba, df in brutas.items():
            tabela = f"{base}_{normalizar_nome_coluna(aba)}" if varias else base
            nomes, vistos = [], set()
            for c in df.columns:
                # colunas da planilha não podem colidir com as de controle (que começam com "_")
                n = normalizar_nome_coluna(c).lstrip("_") or "coluna"
                while n in vistos:
                    n = f"{n}_x"
                vistos.add(n)
                nomes.append(n)
            dados = pd.DataFrame({n: [None if pd.isna(v) else _texto_de(v) for v in df[c]] for n, c in zip(nomes, df.columns)})
            # abas empilhadas têm a linha no formato "Fev!12": vira aba "Fev" + linha 12
            origem = [str(i).rsplit("!", 1) if "!" in str(i) else [aba, i] for i in df.index]
            dados.insert(0, "_linha_origem", [int(linha) for _, linha in origem])
            dados["_aba"] = [a for a, _ in origem]
            dados["_arquivo_origem"] = arquivo
            dados["_lote_id"] = lote_id
            dados["_carregado_em"] = pd.Timestamp(datetime.now())
            tipos = {c: "text" for c in dados.columns}
            tipos.update({"_linha_origem": "bigint", "_carregado_em": "timestamp without time zone"})
            tipos = self._garantir_tabela(conn, schema, tabela, tipos)
            self._apagar(conn, schema, tabela, "_arquivo_origem = %s", (arquivo,))
            self._copiar(conn, schema, tabela, dados, tipos)
            self.esperado_bruto[tabela] = len(dados)
            gravadas.append(f"{schema}.{tabela}")
        return gravadas

    def carregar_tratado(self, conn, base: str, tabelas: dict[str, pd.DataFrame], arquivo: str, lote_id: str,
                         destino: dict, modelo: dict | None) -> list[str]:
        schema = self.schemas["tratado"]
        modo = str(destino.get("modo") or self.cfg.get("modo_carga_padrao") or "por_arquivo").lower()
        if modo not in MODOS_CARGA:
            raise ErroCargaDados(f"Modo de carga '{modo}' inválido (use: {', '.join(sorted(MODOS_CARGA))})")
        chave = [normalizar_nome_coluna(c) for c in (destino.get("chave") or [])]
        dims_cfg = {normalizar_nome_coluna(k): v for k, v in ((modelo or {}).get("dimensoes") or {}).items()}

        tabelas = {n: df.copy() for n, df in tabelas.items()}
        gravadas = []
        self.esperado_tratado: dict[tuple, int] = {}
        self.chaves_estrangeiras: list[tuple] = []

        # 1) dimensões: chaves estáveis entre cargas (o mesmo curso mantém o mesmo id para sempre)
        for nome, df in list(tabelas.items()):
            if nome in dims_cfg:
                mapa = self._mesclar_dimensao(conn, schema, nome, df, dims_cfg[nome])
                for outro, fato in tabelas.items():
                    col_chave = df.columns[0]
                    if outro != nome and col_chave in fato.columns:
                        fato[col_chave] = pd.array([mapa.get(v) if not pd.isna(v) else None for v in fato[col_chave]],
                                                   dtype="Int64")
                gravadas.append(f"{schema}.{nome}")
            elif nome == "dim_calendario":
                self._mesclar_calendario(conn, schema, df)
                gravadas.append(f"{schema}.{nome}")

        # 2) fatos / tabelas simples
        unica = len([n for n in tabelas if n not in dims_cfg and n != "dim_calendario"]) == 1
        for nome, df in tabelas.items():
            if nome in dims_cfg or nome == "dim_calendario":
                continue
            if modelo:
                tabela = nome                      # fato_xxx definido no modelo
            elif unica:
                tabela = normalizar_nome_coluna(destino["tabela"]) if destino.get("tabela") else base
            else:
                tabela = f"{base}_{nome}"          # várias abas
            df = df.copy()
            if "_arquivo_origem" not in df.columns:
                df["_arquivo_origem"] = arquivo
            df["_lote_id"] = lote_id
            tipos = self._garantir_tabela(conn, schema, tabela, {c: tipo_pg(df[c]) for c in df.columns})
            if modo == "substituir":
                _, sql = _psycopg()
                conn.execute(sql.SQL("TRUNCATE {}").format(sql.Identifier(schema, tabela)))
            elif modo == "por_arquivo":
                self._apagar(conn, schema, tabela, "_arquivo_origem = %s", (arquivo,))
            elif modo == "mesclar":
                if not chave or any(c not in df.columns for c in chave):
                    raise ErroCargaDados(f"Modo 'mesclar' precisa de 'chave' com colunas existentes (recebi {chave})")
                self._apagar_por_chave(conn, schema, tabela, df, chave)
            self._copiar(conn, schema, tabela, df, tipos)
            self.esperado_tratado[(schema, tabela)] = len(df)
            for nome_dim, dim in tabelas.items():
                if nome_dim in dims_cfg and dim.columns[0] in df.columns:
                    self.chaves_estrangeiras.append((schema, tabela, dim.columns[0], nome_dim))
            gravadas.append(f"{schema}.{tabela}")
        return gravadas

    def reconciliar(self, conn, lote_id: str, esperado_bruto: dict[str, int]) -> list[str]:
        """DBA: confere DENTRO da transação (antes do commit) se o banco recebeu exatamente o esperado.
        Levanta ErroCargaDados se algo não bater — a carga inteira é desfeita."""
        _, sql = _psycopg()
        conferidos, divergencias = [], []
        alvos = [((self.schemas["bruto"], t), n) for t, n in esperado_bruto.items()] + list(getattr(self, "esperado_tratado", {}).items())
        for (schema, tabela), n in alvos:
            obtido = conn.execute(sql.SQL("SELECT count(*) FROM {} WHERE _lote_id = %s").format(
                sql.Identifier(schema, tabela)), (lote_id,)).fetchone()[0]
            if obtido != n:
                divergencias.append(f"{schema}.{tabela}: esperado {n}, no banco {obtido}")
            else:
                conferidos.append(f"{schema}.{tabela} ({n})")
        for schema, fato, chave, dim in getattr(self, "chaves_estrangeiras", []):
            orfas = conn.execute(sql.SQL(
                "SELECT count(*) FROM {} f LEFT JOIN {} d ON f.{} = d.{} WHERE f._lote_id = %s AND f.{} IS NOT NULL AND d.{} IS NULL"
            ).format(sql.Identifier(schema, fato), sql.Identifier(schema, dim), sql.Identifier(chave), sql.Identifier(chave),
                     sql.Identifier(chave), sql.Identifier(chave)), (lote_id,)).fetchone()[0]
            if orfas:
                divergencias.append(f"{schema}.{fato}.{chave}: {orfas} chave(s) sem correspondência em {dim}")
            else:
                conferidos.append(f"integridade {fato} → {dim}")
        if divergencias:
            raise ErroCargaDados("DBA barrou a carga na reconciliação: " + "; ".join(divergencias))
        return conferidos

    def _apagar_por_chave(self, conn, schema, tabela, df, chave):
        _, sql = _psycopg()
        temp = "_robo_chaves"
        conn.execute(sql.SQL("CREATE TEMP TABLE {} ON COMMIT DROP AS SELECT {} FROM {} WITH NO DATA").format(
            sql.Identifier(temp), sql.SQL(", ").join(sql.Identifier(c) for c in chave), sql.Identifier(schema, tabela)))
        tipos = self._colunas_existentes(conn, schema, tabela)
        with conn.cursor().copy(sql.SQL("COPY {} ({}) FROM STDIN").format(
                sql.Identifier(temp), sql.SQL(", ").join(sql.Identifier(c) for c in chave))) as copia:
            for linha in df[chave].drop_duplicates().astype(object).itertuples(index=False, name=None):
                copia.write_row([_valor_pg(v, tipos.get(c, "text")) for v, c in zip(linha, chave)])
        condicao = sql.SQL(" AND ").join(
            sql.SQL("t.{c} IS NOT DISTINCT FROM k.{c}").format(c=sql.Identifier(c)) for c in chave)
        conn.execute(sql.SQL("DELETE FROM {} t USING {} k WHERE {}").format(
            sql.Identifier(schema, tabela), sql.Identifier(temp), condicao))
        conn.execute(sql.SQL("DROP TABLE {}").format(sql.Identifier(temp)))

    def _mesclar_dimensao(self, conn, schema, nome, df, definicao) -> dict:
        """Insere só os membros novos da dimensão e devolve {id_do_arquivo: id_definitivo_no_banco}."""
        _, sql = _psycopg()
        col_chave = df.columns[0]
        naturais = [c for c in df.columns if c != col_chave]
        tipos = self._garantir_tabela(conn, schema, nome, {c: tipo_pg(df[c]) for c in df.columns})
        existentes = conn.execute(sql.SQL("SELECT {}, {} FROM {}").format(
            sql.Identifier(col_chave), sql.SQL(", ").join(sql.Identifier(c) for c in naturais),
            sql.Identifier(schema, nome))).fetchall()

        def chave_natural(valores):
            return tuple(None if v is None or (isinstance(v, float) and math.isnan(v)) else
                         (_valor_pg(v, tipos.get(c, "text"))) for v, c in zip(valores, naturais))

        por_natural = {chave_natural(r[1:]): r[0] for r in existentes}
        proximo = max([r[0] for r in existentes] or [0]) + 1
        mapa, novos = {}, []
        for linha in df.astype(object).itertuples(index=False, name=None):
            id_arquivo, valores = linha[0], linha[1:]
            natural = chave_natural(valores)
            if natural not in por_natural:
                por_natural[natural] = proximo
                novos.append((proximo, *valores))
                proximo += 1
            mapa[id_arquivo] = por_natural[natural]
        if novos:
            self._copiar(conn, schema, nome, pd.DataFrame(novos, columns=df.columns), tipos)
        return mapa

    def _mesclar_calendario(self, conn, schema, df):
        _, sql = _psycopg()
        tipos = self._garantir_tabela(conn, schema, "dim_calendario", {c: tipo_pg(df[c]) for c in df.columns})
        minimo, maximo = df["data"].min(), df["data"].max()
        atual = conn.execute(sql.SQL("SELECT min(data), max(data) FROM {}").format(
            sql.Identifier(schema, "dim_calendario"))).fetchone()
        if atual[0] is not None:
            minimo = min(minimo, pd.Timestamp(atual[0]))
            maximo = max(maximo, pd.Timestamp(atual[1]))
        completo = tabela_calendario(pd.Series([minimo, maximo]))
        conn.execute(sql.SQL("TRUNCATE {}").format(sql.Identifier(schema, "dim_calendario")))
        self._copiar(conn, schema, "dim_calendario", completo, tipos)

    def executar_modelos(self, conn) -> list[str]:
        """Executa os .sql de modelos_sql/ em ordem alfabética. Arquivos que começam com '_' são ignorados."""
        if not self.pasta_modelos.exists():
            return []
        executados = []
        for arquivo in sorted(self.pasta_modelos.glob("*.sql")):
            if arquivo.name.startswith("_"):
                continue
            comando = arquivo.read_text(encoding="utf-8-sig")
            try:
                with conn.transaction():  # savepoint: o erro aponta exatamente qual modelo falhou
                    conn.execute(comando)
            except Exception as e:
                raise ErroCargaDados(f"O modelo SQL '{arquivo.name}' falhou: {e}".strip()) from e
            executados.append(arquivo.name)
        return executados

    def registrar_lote(self, conn, dados: dict):
        _, sql = _psycopg()
        conn.execute(sql.SQL("""
            INSERT INTO {}.lotes (lote_id, arquivo, status, linhas_entrada, linhas_saida, erros, avisos,
                                  tabelas, mensagem, ocorrencias)
            VALUES (%(lote_id)s, %(arquivo)s, %(status)s, %(linhas_entrada)s, %(linhas_saida)s, %(erros)s,
                    %(avisos)s, %(tabelas)s, %(mensagem)s, %(ocorrencias)s)
            ON CONFLICT (lote_id) DO UPDATE SET status = EXCLUDED.status, linhas_saida = EXCLUDED.linhas_saida,
                erros = EXCLUDED.erros, avisos = EXCLUDED.avisos, tabelas = EXCLUDED.tabelas,
                mensagem = EXCLUDED.mensagem, ocorrencias = EXCLUDED.ocorrencias, processado_em = now()
        """).format(sql.Identifier(self.schemas["controle"])),
            {**dados, "ocorrencias": json.dumps(dados.get("ocorrencias") or [], ensure_ascii=False, default=str)})
        tabela = sql.Identifier(self.schemas["controle"], "ocorrencias")
        conn.execute(sql.SQL("DELETE FROM {} WHERE lote_id = %s").format(tabela), (dados["lote_id"],))
        linhas = [(dados["lote_id"], dados["arquivo"], dados["status"], o.get("nivel"), o.get("tabela") or None,
                   o.get("coluna") or None, o.get("mensagem"), o.get("quantidade"), " | ".join(o.get("exemplos") or []))
                  for o in dados.get("ocorrencias") or [] if o.get("nivel") in ("ERRO", "AVISO")]
        if linhas:
            with conn.cursor() as cur:
                cur.executemany(sql.SQL(
                    "INSERT INTO {} (lote_id, arquivo, status_lote, nivel, tabela, coluna, mensagem, quantidade, exemplos) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)").format(tabela), linhas)

    # ------------------------------------------------------------------ painel
    def resumo(self) -> dict:
        """Tabelas por camada com quantidade de linhas e últimas cargas (para o painel)."""
        with self.conectar() as conn:
            self.inicializar(conn)
            conn.commit()
            schemas = [self.schemas[k] for k in ("bruto", "tratado", "analitico")]
            objetos = conn.execute("""
                SELECT table_schema, table_name, table_type FROM information_schema.tables
                WHERE table_schema = ANY(%s) ORDER BY table_schema, table_name""", (schemas,)).fetchall()
            _, sql = _psycopg()
            tabelas = []
            for schema, nome, tipo in objetos:
                linhas = None
                if tipo == "BASE TABLE":
                    linhas = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(schema, nome))).fetchone()[0]
                tabelas.append({"schema": schema, "nome": nome, "tipo": "tabela" if tipo == "BASE TABLE" else "visão",
                                "linhas": linhas})
            lotes = conn.execute(sql.SQL(
                "SELECT lote_id, arquivo, status, processado_em, linhas_saida, erros, avisos, tabelas "
                "FROM {}.lotes ORDER BY processado_em DESC LIMIT 15").format(
                sql.Identifier(self.schemas["controle"]))).fetchall()
        return {
            "tabelas": tabelas,
            "lotes": [dict(zip(["lote_id", "arquivo", "status", "processado_em", "linhas_saida", "erros", "avisos",
                                "tabelas"], l)) for l in lotes],
        }


def _explicar_erro_conexao(msg: str, p: dict) -> str:
    m = msg.lower()
    if "password authentication failed" in m or "autenticação do tipo senha falhou" in m:
        return f"Senha do PostgreSQL recusada para o usuário '{p['user']}'. Confira a senha em Configurações > Banco."
    if ("database" in m and "does not exist" in m) or ("banco de dados" in m and "não existe" in m):
        return f"O banco '{p['dbname']}' não existe."
    if ("role" in m and "does not exist" in m) or ("função" in m and "não existe" in m):
        return f"O usuário '{p['user']}' não existe no PostgreSQL. Confira o usuário em Configurações > Banco."
    if "connection refused" in m or "could not connect" in m or "timeout" in m or "conexão recusada" in m:
        return (f"Não consegui conectar em {p['host']}:{p['port']}. O PostgreSQL está instalado e ligado? "
                "(Windows: Serviços > postgresql-x64 > Iniciar)")
    return f"Falha ao conectar no PostgreSQL: {msg.strip()}"
