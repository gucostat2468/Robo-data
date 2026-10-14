"""Limpeza e padronização de uma tabela.

Ordem das etapas (cada uma fica registrada no relatório):
 1. Erros de fórmula do Excel (#REF!, #DIV/0!, #N/D...)
 2. Nomes de colunas padronizados (sem acento, minúsculo, com "_")
 3. Renomear / remover colunas (regras do config.yaml)
 4. Textos: espaços extras e marcadores de "vazio" (-, N/A, null...)
 5. Linhas e colunas totalmente vazias
 6. Linhas de "Total" / "Subtotal"
 7. Tipos: número, data ou texto (forçados pela regra ou inferidos)
 8. Padronização de maiúsculas/minúsculas (regra)
 9. Linhas duplicadas
"""

from __future__ import annotations

import fnmatch
import re
import unicodedata
from datetime import date, datetime

import numpy as np
import pandas as pd

from robo.relatorio import Relatorio

ERROS_EXCEL = {
    "#ref!", "#div/0!", "#value!", "#valor!", "#name?", "#nome?", "#num!", "#núm!",
    "#null!", "#nulo!", "#n/a", "#n/d", "#spill!", "#despejar!", "#calc!", "#getting_data",
}

FORMATOS_DATA = (
    "%d/%m/%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%y",
    "%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
    "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d",
)

_RE_MOEDA = re.compile(r"^(r\$|us\$|u\$s|\$|€|£)\s*", re.IGNORECASE)
_RE_NUM_VIRGULA = re.compile(r"^(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$")   # 1.234,56 | 1234,5 | 12
_RE_NUM_PONTO = re.compile(r"^(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")     # 1,234.56 | 1234.5 | 12
_RE_TOTAL = re.compile(r"^(sub\s*-?\s*)?total(\s+geral)?\s*:?$", re.IGNORECASE)

TIPOS_VALIDOS = {"texto", "inteiro", "decimal", "data", "datahora"}


# ----------------------------------------------------------------------------
# utilitários
# ----------------------------------------------------------------------------
def sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar_nome_coluna(nome) -> str:
    """'  Data de Admissão (R$) ' -> 'data_de_admissao_r'"""
    s = sem_acento(str(nome)).lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if not s:
        s = "coluna"
    if s[0].isdigit():
        s = f"c_{s}"
    return s


def _nomes_unicos(nomes: list[str]) -> list[str]:
    vistos: dict[str, int] = {}
    saida = []
    for n in nomes:
        if n in vistos:
            vistos[n] += 1
            novo = f"{n}_{vistos[n]}"
            while novo in vistos:
                vistos[n] += 1
                novo = f"{n}_{vistos[n]}"
            vistos[novo] = 1
            saida.append(novo)
        else:
            vistos[n] = 1
            saida.append(n)
    return saida


def _eh_numero_nativo(v) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, (bool, np.bool_))


def _eh_data_nativa(v) -> bool:
    return isinstance(v, (datetime, date, pd.Timestamp, np.datetime64))


def _texto_de(v) -> str:
    """Converte qualquer valor em texto sem o '.0' que o Excel coloca em números inteiros."""
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    if isinstance(v, pd.Timestamp) or isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M:%S") if (v.hour or v.minute or v.second) else v.strftime("%d/%m/%Y")
    return str(v)


def numero_de(v, decimal: str = ","):
    """Converte '1.234,56', 'R$ 10,00', '45%', '(1.000)' em número. Devolve None se não for número."""
    if _eh_numero_nativo(v):
        return None if pd.isna(v) else float(v)
    if not isinstance(v, str):
        return None
    s = v.strip().replace(" ", " ")
    negativo = False
    if s.startswith("(") and s.endswith(")"):
        negativo, s = True, s[1:-1].strip()
    if s.startswith("-"):
        negativo, s = not negativo, s[1:].strip()
    s = _RE_MOEDA.sub("", s)
    if s.startswith("-"):
        negativo, s = not negativo, s[1:].strip()
    percentual = s.endswith("%")
    if percentual:
        s = s[:-1].strip()
    s = s.replace(" ", "")
    if decimal == ",":
        if not _RE_NUM_VIRGULA.match(s):
            return None
        s = s.replace(".", "").replace(",", ".")
    else:
        if not _RE_NUM_PONTO.match(s):
            return None
        s = s.replace(",", "")
    x = float(s)
    if percentual:
        x /= 100
    return -x if negativo else x


def data_de(v):
    if _eh_data_nativa(v):
        try:
            return pd.Timestamp(v)
        except (ValueError, OverflowError):
            return None
    if not isinstance(v, str):
        return None
    s = v.strip()
    for fmt in FORMATOS_DATA:
        try:
            return pd.Timestamp(datetime.strptime(s, fmt))
        except ValueError:
            continue
    return None


def _detectar_decimal(valores) -> str:
    textos = [v for v in valores if isinstance(v, str)]
    virgula = sum(numero_de(v, ",") is not None for v in textos)
    ponto = sum(numero_de(v, ".") is not None for v in textos)
    return "." if ponto > virgula else ","


def _linhas(serie: pd.Series, mascara) -> list:
    return [f"linha {i}" for i in serie.index[mascara][:5]]


def _eh_identificador(coluna: str, padroes: list[str]) -> bool:
    return any(fnmatch.fnmatch(coluna, p) for p in padroes)


# ----------------------------------------------------------------------------
# conversões de tipo
# ----------------------------------------------------------------------------
def _como_numero(serie: pd.Series, decimal: str) -> pd.Series:
    convertida = pd.Series([numero_de(v, decimal) if not pd.isna(v) else None for v in serie],
                           index=serie.index, dtype="float64")
    nao_nulos = convertida.dropna()
    if len(nao_nulos) and (nao_nulos == nao_nulos.round()).all() and nao_nulos.abs().max() < 2**53:
        return convertida.astype("Int64")
    return convertida


def _como_data(serie: pd.Series) -> pd.Series:
    return pd.Series([data_de(v) if not pd.isna(v) else pd.NaT for v in serie],
                     index=serie.index, dtype="datetime64[ns]")


def _como_texto(serie: pd.Series) -> pd.Series:
    return pd.Series([pd.NA if pd.isna(v) else _texto_de(v) for v in serie], index=serie.index, dtype=object)


def _converter(serie: pd.Series, tipo: str, decimal: str) -> pd.Series:
    if tipo in ("inteiro", "decimal"):
        s = _como_numero(serie, decimal)
        if tipo == "decimal":
            s = s.astype("float64")
        else:
            nao_nulos = s.dropna()
            if len(nao_nulos) and not (nao_nulos == nao_nulos.round()).all():
                return s  # o validador acusa as casas decimais
            s = s.astype("Int64")
        return s
    if tipo == "data":
        return _como_data(serie).dt.normalize()
    if tipo == "datahora":
        return _como_data(serie)
    return _como_texto(serie)


def _inferir(serie: pd.Series, coluna: str, cfg: dict, tabela: str, rel: Relatorio) -> pd.Series:
    valores = serie.dropna()
    if valores.empty:
        return _como_texto(serie)
    if _eh_identificador(coluna, cfg.get("padroes_identificador", [])):
        return _como_texto(serie)

    textos = [v for v in valores if isinstance(v, str)]
    # códigos com zero à esquerda (ex.: CEP 01310-100, matrícula 00123) continuam texto
    if any(len(t) > 1 and t.isdigit() and t.startswith("0") for t in textos):
        return _como_texto(serie)

    limiar = float(cfg.get("limiar_conversao", 0.95))
    total = len(valores)

    if all(_eh_numero_nativo(v) for v in valores):
        return _como_numero(serie, ",")
    if all(_eh_data_nativa(v) for v in valores):
        return _como_data(serie)

    decimal = _detectar_decimal(valores)
    ok_num = sum(numero_de(v, decimal) is not None for v in valores)
    if ok_num / total >= limiar:
        convertida = _como_numero(serie, decimal)
        _registrar_perdas(serie, convertida, coluna, tabela, "número", rel)
        if any(isinstance(v, str) and v.strip().endswith("%") for v in valores):
            rel.info("Percentuais convertidos para decimal (45% -> 0,45)", tabela=tabela, coluna=coluna)
        return convertida

    ok_data = sum(data_de(v) is not None for v in valores)
    if ok_data / total >= limiar:
        convertida = _como_data(serie)
        _registrar_perdas(serie, convertida, coluna, tabela, "data", rel)
        return convertida

    return _como_texto(serie)


def _registrar_perdas(original, convertida, coluna, tabela, tipo, rel: Relatorio):
    perdidos = original.notna() & convertida.isna()
    if perdidos.any():
        exemplos = [f"linha {i}: '{original[i]}'" for i in original.index[perdidos][:5]]
        rel.aviso(f"Valores que não são {tipo} foram esvaziados (coluna é {tipo} em ≥ limiar)",
                  tabela=tabela, coluna=coluna, quantidade=int(perdidos.sum()), exemplos=exemplos)


# ----------------------------------------------------------------------------
# pipeline de limpeza
# ----------------------------------------------------------------------------
def limpar_tabela(df: pd.DataFrame, tabela: str, cfg: dict, regra: dict, rel: Relatorio) -> pd.DataFrame:
    df = df.copy()
    linhas_iniciais = len(df)

    # 1. erros de fórmula do Excel
    for col in df.columns:
        mascara = df[col].map(lambda v: isinstance(v, str) and v.strip().lower() in ERROS_EXCEL)
        if mascara.any():
            exemplos = [f"linha {i}: {df.at[i, col]}" for i in df.index[mascara][:5]]
            if cfg.get("erros_excel", "erro") == "anular":
                rel.aviso("Erros de fórmula do Excel foram esvaziados", tabela=tabela, coluna=str(col),
                          quantidade=int(mascara.sum()), exemplos=exemplos)
            else:
                rel.erro("Células com erro de fórmula do Excel (#REF!, #DIV/0!, #N/D...)", tabela=tabela,
                         coluna=str(col), quantidade=int(mascara.sum()), exemplos=exemplos)
            # esvazia nos dois modos para as próximas checagens enxergarem o restante da coluna
            df.loc[mascara, col] = pd.NA

    # 2. nomes de colunas
    originais = [str(c) for c in df.columns]
    novos = _nomes_unicos([normalizar_nome_coluna(c) for c in originais])
    df.columns = novos
    alterados = [f"'{o}' -> {n}" for o, n in zip(originais, novos) if o != n]
    if alterados:
        rel.info("Nomes de colunas padronizados", tabela=tabela, quantidade=len(alterados), exemplos=alterados)

    # 3. renomear / remover (regra)
    renomear = {normalizar_nome_coluna(k): normalizar_nome_coluna(v) for k, v in (regra.get("renomear") or {}).items()}
    if renomear:
        faltando = [k for k in renomear if k not in df.columns]
        if faltando:
            rel.aviso("Colunas para renomear não encontradas", tabela=tabela, exemplos=faltando)
        df = df.rename(columns=renomear)
    remover = [normalizar_nome_coluna(c) for c in (regra.get("remover_colunas") or [])]
    remover = [c for c in remover if c in df.columns]
    if remover:
        df = df.drop(columns=remover)
        rel.info("Colunas removidas pela regra", tabela=tabela, exemplos=remover)

    # 4. textos e marcadores de vazio
    nulos = {sem_acento(str(v)).strip().lower() for v in cfg.get("valores_nulos", [])}
    contagem_nulos = 0

    def _limpar_valor(v):
        nonlocal contagem_nulos
        if isinstance(v, str):
            s = re.sub(r"\s+", " ", v.replace(" ", " ").replace("​", "")).strip()
            if sem_acento(s).lower() in nulos:
                contagem_nulos += 1
                return pd.NA
            return s
        return v

    df = df.map(_limpar_valor).astype(object)
    if contagem_nulos:
        rel.info("Marcadores de vazio (-, N/A, null...) convertidos para vazio", tabela=tabela, quantidade=contagem_nulos)

    # 5. linhas e colunas vazias
    colunas_vazias = [c for c in df.columns if df[c].isna().all()]
    if colunas_vazias:
        df = df.drop(columns=colunas_vazias)
        rel.aviso("Colunas totalmente vazias removidas", tabela=tabela, quantidade=len(colunas_vazias), exemplos=colunas_vazias)
    antes = len(df)
    df = df.dropna(how="all")
    if antes - len(df):
        rel.info("Linhas totalmente vazias removidas", tabela=tabela, quantidade=antes - len(df))

    # 6. linhas de total
    if cfg.get("remover_linhas_total", True) and len(df.columns):
        def _eh_total(linha):
            preenchidos = linha.dropna()
            return len(preenchidos) > 0 and isinstance(preenchidos.iloc[0], str) and bool(_RE_TOTAL.match(preenchidos.iloc[0]))
        mascara = df.apply(_eh_total, axis=1) if len(df) else pd.Series(dtype=bool)
        if len(mascara) and mascara.any():
            rel.aviso("Linhas de Total/Subtotal removidas (evita contar valores em dobro)", tabela=tabela,
                      quantidade=int(mascara.sum()), exemplos=[f"linha {i}" for i in df.index[mascara][:5]])
            df = df[~mascara]

    # 7. tipos
    tipos_forcados = {normalizar_nome_coluna(k): str(v).lower() for k, v in (regra.get("tipos") or {}).items()}
    for col, tipo in tipos_forcados.items():
        if tipo not in TIPOS_VALIDOS:
            rel.erro(f"Tipo '{tipo}' inválido no config.yaml (use: {', '.join(sorted(TIPOS_VALIDOS))})", tabela=tabela, coluna=col)
        elif col not in df.columns:
            rel.aviso("Coluna com tipo definido na regra não existe no arquivo", tabela=tabela, coluna=col)

    for col in list(df.columns):
        original = df[col]
        tipo = tipos_forcados.get(col)
        if tipo in TIPOS_VALIDOS:
            decimal = _detectar_decimal(original.dropna())
            convertida = _converter(original, tipo, decimal)
            falhas = original.notna() & convertida.isna()
            if falhas.any():
                rel.erro(f"Valores que não puderam ser convertidos para '{tipo}'", tabela=tabela, coluna=col,
                         quantidade=int(falhas.sum()),
                         exemplos=[f"linha {i}: '{original[i]}'" for i in original.index[falhas][:5]])
            if tipo == "inteiro" and convertida.dtype == "float64":
                quebrados = convertida.notna() & (convertida != convertida.round())
                rel.erro("Coluna definida como 'inteiro' tem valores com casas decimais", tabela=tabela, coluna=col,
                         quantidade=int(quebrados.sum()),
                         exemplos=[f"linha {i}: {convertida[i]}" for i in convertida.index[quebrados][:5]])
            df[col] = convertida
        elif cfg.get("inferir_tipos", True):
            df[col] = _inferir(original, col, cfg, tabela, rel)
        else:
            df[col] = _como_texto(original)

    # 8. maiúsculas/minúsculas
    for col, modo in (regra.get("texto") or {}).items():
        col = normalizar_nome_coluna(col)
        if col not in df.columns:
            continue
        funcao = {"maiusculo": str.upper, "minusculo": str.lower, "titulo": str.title}.get(str(modo).lower())
        if funcao:
            df[col] = df[col].map(lambda v: funcao(v) if isinstance(v, str) else v)

    # 9. duplicadas
    remover_dup = regra.get("remover_duplicadas", cfg.get("remover_duplicadas", True))
    if remover_dup and len(df):
        dup = df.duplicated(keep="first")
        if dup.any():
            rel.aviso("Linhas duplicadas (idênticas em todas as colunas) removidas", tabela=tabela,
                      quantidade=int(dup.sum()), exemplos=[f"linha {i}" for i in df.index[dup][:5]])
            df = df[~dup]

    rel.info(f"Limpeza concluída: {linhas_iniciais} -> {len(df)} linhas, {len(df.columns)} colunas", tabela=tabela)
    return df
