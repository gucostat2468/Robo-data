"""Modelagem para Power BI: dicionário de dados, modelo estrela (fato + dimensões)
e tabela calendário.

Configuração (opcional) dentro de uma regra do config.yaml:

  modelo:
    fato: fato_respostas
    dimensoes:
      dim_curso:                     # nome da tabela dimensão
        colunas: [curso, modalidade] # colunas que saem da fato e vão para a dimensão
        chave: id_curso              # chave criada (1, 2, 3...) e gravada na fato
    calendario: data_resposta        # cria dim_calendario a partir desta coluna de data
"""

from __future__ import annotations

import pandas as pd

from robo.limpeza import normalizar_nome_coluna
from robo.relatorio import Relatorio

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def tipo_amigavel(serie: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(serie):
        return "Verdadeiro/Falso"
    if pd.api.types.is_integer_dtype(serie):
        return "Número inteiro"
    if pd.api.types.is_float_dtype(serie):
        return "Número decimal"
    if pd.api.types.is_datetime64_any_dtype(serie):
        horas = serie.dropna()
        return "Data" if horas.empty or (horas == horas.dt.normalize()).all() else "Data e hora"
    return "Texto"


def dicionario_dados(tabelas: dict[str, pd.DataFrame]) -> pd.DataFrame:
    linhas = []
    for nome, df in tabelas.items():
        total = len(df)
        for col in df.columns:
            s = df[col]
            nao_nulos = s.dropna()
            tipo = tipo_amigavel(s)
            minimo = maximo = None
            if tipo not in ("Texto", "Verdadeiro/Falso") and len(nao_nulos):
                minimo, maximo = nao_nulos.min(), nao_nulos.max()
            linhas.append({
                "tabela": nome,
                "coluna": col,
                "tipo": tipo,
                "linhas": total,
                "preenchidos": int(len(nao_nulos)),
                "pct_vazios": round(100 * (1 - len(nao_nulos) / total), 2) if total else 0.0,
                "valores_distintos": int(nao_nulos.nunique()),
                "minimo": minimo,
                "maximo": maximo,
                "exemplo": str(nao_nulos.iloc[0]) if len(nao_nulos) else "",
            })
    return pd.DataFrame(linhas)


def tabela_calendario(datas: pd.Series) -> pd.DataFrame:
    datas = pd.to_datetime(datas.dropna())
    inicio = pd.Timestamp(datas.min().year, 1, 1)
    fim = pd.Timestamp(datas.max().year, 12, 31)
    d = pd.DataFrame({"data": pd.date_range(inicio, fim, freq="D")})
    d["ano"] = d["data"].dt.year
    d["trimestre"] = "T" + d["data"].dt.quarter.astype(str)
    d["mes_numero"] = d["data"].dt.month
    d["mes_nome"] = d["mes_numero"].map(lambda m: MESES[m - 1])
    d["mes_abrev"] = d["mes_nome"].str[:3]
    d["ano_mes"] = d["data"].dt.strftime("%Y-%m")
    d["dia"] = d["data"].dt.day
    d["dia_semana_numero"] = d["data"].dt.dayofweek + 1
    d["dia_semana"] = d["data"].dt.dayofweek.map(lambda x: DIAS[x])
    d["fim_de_semana"] = d["dia_semana_numero"] >= 6
    return d


def _chave(valores) -> tuple:
    return tuple(None if pd.isna(v) else v for v in valores)


def modelar(df: pd.DataFrame, tabela: str, modelo: dict, rel: Relatorio) -> dict[str, pd.DataFrame]:
    """Sem 'modelo' na regra devolve a tabela como está. Com 'modelo', devolve fato + dimensões."""
    if not modelo:
        return {tabela: df}

    fato = df.reset_index(drop=True).copy()
    saida: dict[str, pd.DataFrame] = {}

    for nome_dim, definicao in (modelo.get("dimensoes") or {}).items():
        nome_dim = normalizar_nome_coluna(nome_dim)
        colunas = [normalizar_nome_coluna(c) for c in definicao.get("colunas", [])]
        chave = normalizar_nome_coluna(definicao.get("chave") or f"id_{nome_dim.removeprefix('dim_')}")
        ausentes = [c for c in colunas if c not in fato.columns]
        if not colunas or ausentes:
            rel.erro("Colunas da dimensão não existem na tabela", tabela=nome_dim, exemplos=ausentes or ["(lista vazia)"])
            continue
        if chave in fato.columns:
            rel.erro(f"A chave '{chave}' já existe como coluna; escolha outro nome", tabela=nome_dim)
            continue
        dim = fato[colunas].drop_duplicates().dropna(how="all")
        dim = dim.sort_values(colunas, na_position="last", key=lambda s: s.astype(str)).reset_index(drop=True)
        dim.insert(0, chave, pd.array(range(1, len(dim) + 1), dtype="Int64"))
        posicao = fato.columns.get_loc(colunas[0])
        mapeamento = {_chave(r[1:]): r[0] for r in dim.astype(object).itertuples(index=False, name=None)}
        chaves_fato = [mapeamento.get(_chave(v)) for v in fato[colunas].astype(object).itertuples(index=False, name=None)]
        fato = fato.drop(columns=colunas)
        fato.insert(posicao, chave, pd.array(chaves_fato, dtype="Int64"))
        saida[nome_dim] = dim
        rel.info(f"Dimensão criada com {len(dim)} registros (relacionar {chave} 1:* com a fato)", tabela=nome_dim)

    col_cal = modelo.get("calendario")
    if col_cal:
        col_cal = normalizar_nome_coluna(col_cal)
        if col_cal not in fato.columns or not pd.api.types.is_datetime64_any_dtype(fato[col_cal]):
            rel.erro("Coluna do calendário não existe ou não é data", tabela="dim_calendario", coluna=col_cal)
        elif fato[col_cal].notna().any():
            saida["dim_calendario"] = tabela_calendario(fato[col_cal])
            rel.info(f"dim_calendario criada (relacionar data 1:* {col_cal}; marcar como tabela de datas)",
                     tabela="dim_calendario")

    nome_fato = normalizar_nome_coluna(modelo.get("fato") or f"fato_{tabela}")
    return {nome_fato: fato, **saida}
