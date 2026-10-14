"""Regras de qualidade. Qualquer ERRO aqui impede o envio para Bases-Tratadas.

Regras disponíveis no config.yaml (todas opcionais, por padrão de nome de arquivo):
  colunas_obrigatorias: [col1, col2]       -> as colunas precisam existir
  nao_nulos: [col1]                        -> não pode haver célula vazia
  chave_unica: [col1, col2]                -> a combinação não pode se repetir
  faixas: {nota: {min: 0, max: 10}}        -> valores numéricos/datas dentro da faixa
  valores_permitidos: {uf: [SP, RJ, MG]}   -> só aceita a lista (sem diferenciar maiúsculas)
  minimo_linhas: 1                         -> quantidade mínima de linhas
"""

from __future__ import annotations

import pandas as pd

from robo.limpeza import normalizar_nome_coluna, sem_acento
from robo.relatorio import Relatorio


def _cols(lista) -> list[str]:
    return [normalizar_nome_coluna(c) for c in (lista or [])]


def _linhas(df: pd.DataFrame, mascara) -> list[str]:
    return [f"linha {i}" for i in df.index[mascara][:5]]


def validar_tabela(df: pd.DataFrame, tabela: str, regra: dict, rel: Relatorio) -> None:
    minimo = int(regra.get("minimo_linhas", 1))
    if len(df) < minimo:
        rel.erro(f"Tabela com {len(df)} linha(s) de dados após a limpeza (mínimo exigido: {minimo})", tabela=tabela)
    if len(df.columns) == 0:
        rel.erro("Nenhuma coluna com dados foi encontrada", tabela=tabela)
        return

    obrigatorias = _cols(regra.get("colunas_obrigatorias"))
    faltando = [c for c in obrigatorias if c not in df.columns]
    if faltando:
        rel.erro("Colunas obrigatórias ausentes", tabela=tabela, quantidade=len(faltando), exemplos=faltando)

    for col in _cols(regra.get("nao_nulos")):
        if col not in df.columns:
            if col not in faltando:
                rel.erro("Coluna que não pode ter vazios não existe no arquivo", tabela=tabela, coluna=col)
            continue
        vazios = df[col].isna()
        if vazios.any():
            rel.erro("Células vazias em coluna obrigatória", tabela=tabela, coluna=col,
                     quantidade=int(vazios.sum()), exemplos=_linhas(df, vazios))

    chave = _cols(regra.get("chave_unica"))
    if chave:
        ausentes = [c for c in chave if c not in df.columns]
        if ausentes:
            rel.erro("Colunas da chave única não existem no arquivo", tabela=tabela, exemplos=ausentes)
        else:
            dup = df.duplicated(subset=chave, keep=False)
            if dup.any():
                exemplos = [f"linha {i}: " + ", ".join(f"{c}={df.at[i, c]}" for c in chave) for i in df.index[dup][:5]]
                rel.erro(f"Chave única repetida ({' + '.join(chave)})", tabela=tabela,
                         quantidade=int(dup.sum()), exemplos=exemplos)

    for col, faixa in (regra.get("faixas") or {}).items():
        col = normalizar_nome_coluna(col)
        if col not in df.columns:
            rel.erro("Coluna com faixa definida não existe no arquivo", tabela=tabela, coluna=col)
            continue
        serie = df[col]
        eh_data = pd.api.types.is_datetime64_any_dtype(serie)
        if not eh_data and not pd.api.types.is_numeric_dtype(serie):
            rel.erro("Coluna com faixa definida não é numérica nem data", tabela=tabela, coluna=col)
            continue
        conv = (lambda v: pd.Timestamp(v)) if eh_data else float
        fora = pd.Series(False, index=df.index)
        if faixa.get("min") is not None:
            fora |= (serie < conv(faixa["min"])).fillna(False).astype(bool)
        if faixa.get("max") is not None:
            fora |= (serie > conv(faixa["max"])).fillna(False).astype(bool)
        if fora.any():
            rel.erro(f"Valores fora da faixa permitida ({faixa.get('min')} a {faixa.get('max')})", tabela=tabela,
                     coluna=col, quantidade=int(fora.sum()),
                     exemplos=[f"linha {i}: {serie[i]}" for i in df.index[fora][:5]])

    for col, permitidos in (regra.get("valores_permitidos") or {}).items():
        col = normalizar_nome_coluna(col)
        if col not in df.columns:
            rel.erro("Coluna com valores permitidos não existe no arquivo", tabela=tabela, coluna=col)
            continue
        aceitos = {sem_acento(str(v)).strip().lower() for v in permitidos}
        invalidos = df[col].notna() & ~df[col].map(lambda v: sem_acento(str(v)).strip().lower() in aceitos)
        if invalidos.any():
            rel.erro("Valores fora da lista permitida", tabela=tabela, coluna=col, quantidade=int(invalidos.sum()),
                     exemplos=[f"linha {i}: '{df.at[i, col]}'" for i in df.index[invalidos][:5]])
