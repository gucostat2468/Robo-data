"""Treino de SQL com os dados que EXISTEM: cada exercício roda no PostgreSQL, sobre a tabela que a esteira carregou,
e tem que bater com o gabarito da fábrica (a resposta certa, calculada da versão limpa por outro caminho).

Por que existe: a biblioteca consultas_sql/ foi escrita para planilhas REAIS (tratado.fato_nps, tratado.vendas…) que
ainda não chegaram. Nenhuma daquelas consultas tinha onde rodar. Aqui o insumo é o que a empresa tem de verdade:
  - laboratorio.treino_<regra>  cópia bruta de cada planilha da fábrica, como chegou;
  - treino.treino_<regra>       a mesma planilha tratada pela esteira;
  - treino.lotes                o registro de cada carga (linhas que entraram e saíram);
  - fabrica_lotes.gabarito      a verdade conhecida de cada lote (linhas, soma, média, contagem por segmento, indicador).

Níveis (os mesmos das demandas):
  básico        contagem de linhas do lote                          → gabarito.linhas
  médio         soma e média da métrica (+ NPS na regra de NPS)     → gabarito.soma_metrica / media_metrica / indicador
  difícil       linhas por segmento com participação (janela)       → gabarito.por_segmento
  profissional  reconciliação bruto × tratado × registro da carga   → treino.lotes e gabarito.linhas (CTE)

Honestidade: o SQL é escrito pelo molde do exercício, não "pensado" pelo funcionário. O que é real é a execução no
banco (transação somente leitura) e a conferência contra a resposta conhecida. Quando a IA estiver ligada, o passo
seguinte é o funcionário escrever o SQL a partir da pergunta, conferido do mesmo jeito.
"""

from __future__ import annotations

import json
import math
import re

import numpy as np

NIVEIS = ("basico", "medio", "dificil", "profissional")
RE_ARQUIVO = re.compile(r"^TREINO_[A-Za-z0-9_]+\.(xlsx|csv)$")  # só nomes da fábrica entram no texto do SQL
AREAS_DE_DADOS = ("Engenharia de Dados", "Análise de Dados", "Estatística", "Qualidade de Dados",
                  "Customer Insights e Pesquisa")


def _regra(regra_id: str):
    from robo import regras_negocio
    return next(r for r in regras_negocio.REGRAS if r.id == regra_id)


def _colunas(regra) -> tuple[str, str]:
    from robo.limpeza import normalizar_nome_coluna as nn
    cols = {c: nn(c) for c in regra.gerar(np.random.default_rng(0), 3)}
    return cols[regra.metrica], cols[regra.segmento]


def _ident(nome: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", nome):
        raise ValueError(f"nome de coluna/tabela inesperado: {nome}")
    return nome


def montar(regra_id: str, arquivo: str, nivel: str) -> dict:
    """O exercício: pergunta, SQL (somente leitura) e o que conferir. Não toca no banco."""
    if not RE_ARQUIVO.match(arquivo or ""):
        raise ValueError(f"arquivo fora do padrão da fábrica: {arquivo!r}")
    if nivel not in NIVEIS:
        raise ValueError(f"nível desconhecido: {nivel}")
    regra = _regra(regra_id)
    met, seg = (_ident(x) for x in _colunas(regra))
    tab = f"treino.treino_{_ident(regra.id)}"
    arq = arquivo.replace("'", "''")
    onde = f"WHERE _arquivo_origem = '{arq}'"
    if nivel == "basico":
        return {"pergunta": f"Quantas linhas o lote {arquivo} tem depois de tratado?",
                "sql": f"SELECT count(*) AS linhas FROM {tab} {onde}", "confere": "linhas"}
    if nivel == "medio":
        extra = ""
        if regra.id == "nps":
            extra = (f", round(100 * (avg(({met} >= 9)::int) - avg(({met} <= 6)::int))::numeric, 6) AS nps")
        return {"pergunta": f"Qual a soma e a média de {met} no lote {arquivo}?"
                            + (" E o NPS?" if extra else ""),
                "sql": f"SELECT round(sum({met})::numeric, 4) AS soma, round(avg({met})::numeric, 6) AS media{extra} "
                       f"FROM {tab} {onde}", "confere": "metrica"}
    if nivel == "dificil":
        return {"pergunta": f"Quantas linhas por {seg} e qual a participação de cada um no lote {arquivo}?",
                "sql": f"SELECT {seg} AS segmento, count(*) AS linhas, "
                       f"round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct "
                       f"FROM {tab} {onde} GROUP BY {seg} ORDER BY linhas DESC, segmento",
                "confere": "segmentos"}
    return {"pergunta": f"A carga do lote {arquivo} fecha? (linhas brutas × tratadas × registro da carga)",
            "sql": f"WITH bruto AS (SELECT count(*) AS n FROM laboratorio.treino_{_ident(regra.id)} {onde}), "
                   f"tratado AS (SELECT count(*) AS n FROM {tab} {onde}), "
                   f"carga AS (SELECT linhas_entrada, linhas_saida FROM treino.lotes WHERE arquivo = '{arq}' "
                   f"ORDER BY processado_em DESC LIMIT 1) "
                   f"SELECT bruto.n AS linhas_brutas, tratado.n AS linhas_tratadas, carga.linhas_entrada, "
                   f"carga.linhas_saida, bruto.n - tratado.n AS descartadas FROM bruto, tratado, carga",
            "confere": "reconciliacao"}


def _perto(a, b, tol=1e-3) -> bool:
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


def conferir(exercicio: dict, colunas: list, linhas: list, gabarito: dict) -> list[str]:
    """Diferenças entre o resultado do SQL e o gabarito (lista vazia = confere)."""
    if not linhas:
        return ["o SQL não devolveu nenhuma linha"]
    linha = dict(zip(colunas, linhas[0]))
    tipo, dif = exercicio["confere"], []
    if tipo == "linhas":
        if int(linha["linhas"]) != int(gabarito["linhas"]):
            dif.append(f"linhas: SQL {linha['linhas']} × gabarito {gabarito['linhas']}")
    elif tipo == "metrica":
        if not _perto(linha["soma"], gabarito["soma_metrica"]):
            dif.append(f"soma: SQL {linha['soma']} × gabarito {gabarito['soma_metrica']}")
        if gabarito.get("media_metrica") is not None and not _perto(linha["media"], gabarito["media_metrica"]):
            dif.append(f"média: SQL {linha['media']} × gabarito {gabarito['media_metrica']}")
        ind = (gabarito.get("indicador") or {}).get("valor")
        if "nps" in linha and ind is not None and not _perto(linha["nps"], ind):
            dif.append(f"NPS: SQL {linha['nps']} × gabarito {ind}")
    elif tipo == "segmentos":
        obtido = {str(dict(zip(colunas, l))["segmento"]): int(dict(zip(colunas, l))["linhas"]) for l in linhas}
        esperado = {str(k): int(v) for k, v in (gabarito.get("por_segmento") or {}).items()}
        if obtido != esperado:
            faltam = sorted(set(esperado) ^ set(obtido))[:5]
            dif.append(f"contagem por segmento diferente do gabarito (segmentos divergentes: {faltam or 'contagens'})")
        soma_pct = sum(float(dict(zip(colunas, l))["participacao_pct"]) for l in linhas)
        if abs(soma_pct - 100) > 0.05 * len(linhas):
            dif.append(f"participações somam {soma_pct:.2f}%, não 100%")
    elif tipo == "reconciliacao":
        if int(linha["linhas_tratadas"]) != int(gabarito["linhas"]):
            dif.append(f"tratadas: SQL {linha['linhas_tratadas']} × gabarito {gabarito['linhas']}")
        if int(linha["linhas_brutas"]) != int(linha["linhas_entrada"] or -1):
            dif.append(f"brutas {linha['linhas_brutas']} × registro da carga {linha['linhas_entrada']}")
        if int(linha["linhas_tratadas"]) != int(linha["linhas_saida"] or -1):
            dif.append(f"tratadas {linha['linhas_tratadas']} × registro da carga {linha['linhas_saida']}")
    return dif


def lotes_com_gabarito(cfg) -> list[dict]:
    """Lotes da fábrica conferidos (a esteira acertou o gabarito), do mais novo para o mais velho."""
    from robo import fabrica
    with fabrica._tb(cfg).tx() as c:
        linhas = [dict(r) for r in c.execute(
            "SELECT id, regra, arquivo, gabarito FROM fabrica_lotes WHERE estado='conferido_ok' AND gabarito IS NOT NULL "
            "ORDER BY id DESC LIMIT 200")]
    return [{**l, "gabarito": json.loads(l["gabarito"])} for l in linhas if RE_ARQUIVO.match(l["arquivo"] or "")]


def lotes_no_banco(cfg, lotes: list[dict]) -> list[dict]:
    """Só os lotes cuja tabela tratada existe no PostgreSQL e tem as linhas daquele arquivo."""
    from robo.banco import Banco
    saida = []
    with Banco(cfg.banco, cfg.base).conectar() as conn:
        for l in lotes:
            tab = f"treino.treino_{l['regra']}"
            if not conn.execute("SELECT to_regclass(%s)", (tab,)).fetchone()[0]:
                continue
            if conn.execute(f"SELECT 1 FROM {tab} WHERE _arquivo_origem = %s LIMIT 1", (l["arquivo"],)).fetchone():
                saida.append(l)
    return saida


def executar(cfg, regra: str, arquivo: str, nivel: str, gabarito: dict) -> dict:
    """Roda o exercício em transação somente leitura e confere. Devolve {sql, colunas, linhas, diferencas, confere}."""
    from robo import consultas
    from robo.banco import Banco
    ex = montar(regra, arquivo, nivel)
    r = consultas.executar_texto(Banco(cfg.banco, cfg.base), ex["sql"])
    linhas = [list(l) for l in r["linhas"]]
    dif = conferir(ex, r["colunas"], linhas, gabarito)
    return {**ex, "colunas": r["colunas"], "linhas": linhas, "duracao": r["duracao"], "diferencas": dif,
            "confere": not dif}
