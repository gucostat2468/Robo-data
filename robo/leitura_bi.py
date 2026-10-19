"""Leitura de planilhas pela Bárbara (especialista em Power BI) — conferida pelo Heitor.

Para cada planilha (as REAIS publicadas em Bases-Tratadas e as SINTÉTICAS do laboratório, sempre marcadas como tal):
  1. entende do que se trata pelos cabeçalhos (tema) — e diz "não reconheci" quando não reconhece;
  2. explica cada cabeçalho: papel (identificador, data, categoria, métrica), significado e a regra de negócio;
  3. CONFERE as regras nos dados (NPS de 0 a 10, valor não negativo, conversões ≤ cliques, data no futuro…) e conta
     quantas linhas quebram cada regra — número, não opinião;
  4. propõe o modelo estrela (fato, dimensões, calendário) e as medidas DAX com a explicação de cada uma;
  5. calcula os NÚMEROS-ÂNCORA (o que cada medida tem que mostrar no Power BI sem filtro e por segmento): é assim que
     você confere se montou o relatório certo.
O Heitor refaz os números por outro caminho (soma em numpy, contagem por segmento) antes de qualquer publicação.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from robo.limpeza import normalizar_nome_coluna, sem_acento

# --------------------------------------------------------------------------------------------- temas (pelos cabeçalhos)
TEMAS = [
    ("Pesquisa de satisfação (NPS)", r"nps|recomend|indicaria", "Mede a lealdade: quem recomendaria a marca.",
     ["Qual é o NPS geral e de cada segmento?", "Onde estão os detratores?", "O NPS melhora mês a mês?"]),
    ("Satisfação (CSAT/CES)", r"csat|satisf|esforco", "Mede satisfação ou esforço numa interação.",
     ["Qual o % de satisfeitos (top-2-box)?", "Que segmento puxa a nota para baixo?"]),
    ("Vendas / varejo", r"venda|receita|faturamento|ticket|loja|pdv|sku", "Quanto se vendeu, onde e por qual canal.",
     ["Quanto vendemos e onde?", "Qual canal tem maior ticket médio?", "Como as vendas evoluem no tempo?"]),
    ("Pessoas / RH", r"salario|departamento|cargo|tempo_de_casa|admiss|colaborador", "Quadro de pessoas, salários e tempo de casa.",
     ["Como os salários se distribuem por departamento?", "Há grupos de perfil (júnior/sênior)?"]),
    ("Financeiro / contábil", r"centro_de_custo|conta_contabil|lancament|despesa|custo", "Lançamentos por centro de custo e conta.",
     ["Onde está o gasto?", "Há lançamentos negativos (estornos)?", "Como o gasto evolui no mês?"]),
    ("Marketing / mídia", r"investimento|cliques|ctr|conversoes|impress|campanha", "Investimento em mídia e o que ele trouxe.",
     ["Qual canal converte mais por real investido (CPA)?", "Cliques viram conversão?"]),
    ("Logística / entregas", r"transportadora|prazo|atraso|envio|entrega|frete", "Prazo e atraso das entregas.",
     ["Qual transportadora atrasa mais?", "Há atrasos fora do padrão (anomalias)?"]),
]

# --------------------------------------------------------------------------------------------- glossário dos cabeçalhos
# (padrão no nome normalizado, significado, regra de negócio, tipo de conferência, agregação natural)
GLOSSARIO = [
    (r"(^|_)id($|_)|codigo|matricula", "Identificador da linha (uma linha = um registro)", "Não pode repetir nem ficar vazio", "unico", None),
    (r"nps|recomend", "Nota de recomendação de 0 a 10", "Inteiro de 0 a 10; promotor 9–10, neutro 7–8, detrator 0–6", "nps", "nps"),
    (r"csat|satisf", "Nota de satisfação", "Dentro da escala da pesquisa (1–5 ou 1–10)", "nao_negativo", "media"),
    (r"ctr|percent|taxa|pct", "Percentual (0 a 100)", "Entre 0 e 100", "percentual", "media"),
    (r"valor_lancado|lancament", "Valor lançado na contabilidade (R$)", "Pode ser negativo (estorno) — conferir se é esperado", "estorno", "soma"),
    (r"valor|venda|receita|faturamento|preco|ticket", "Valor monetário (R$)", "Não negativo", "nao_negativo", "soma"),
    (r"investimento|custo|gasto|despesa", "Valor investido/gasto (R$)", "Não negativo", "nao_negativo", "soma"),
    (r"salario|remuneracao", "Salário mensal (R$)", "Positivo; acima do salário mínimo", "nao_negativo", "media"),
    (r"cliques|conversoes|quantidade|qtd|unidades|impress|volume", "Contagem/quantidade", "Inteiro não negativo", "contagem", "soma"),
    (r"atraso", "Dias de atraso", "Não negativo; atraso fora do padrão é investigado", "atraso", "media"),
    (r"prazo|tempo|dias|anos", "Duração (dias/anos)", "Não negativa", "nao_negativo", "media"),
    (r"data|dt_|_em$|envio|admiss", "Data do evento", "Não pode estar no futuro nem antes de 2000", "data", None),
]
METRICA_PRINCIPAL = [r"nps", r"csat|satisf", r"atraso", r"valor_lancado", r"venda|receita|faturamento", r"conversoes",
                     r"investimento", r"salario", r"valor"]
PAPEL_DA_REGRA = {"unico": ("id",), "data": ("data",)}
SEGMENTO_PREFERIDO = r"curso|regiao|departamento|centro_de_custo|canal|transportadora|loja|segmento|categoria|modalidade"


def _slug(nome: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", sem_acento(str(nome)).lower()).strip("_")
    return s[:40] or "base"


def _num(x) -> float | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return float(x)


def _papel(serie: pd.Series, col: str) -> str:
    from robo.analise import papel_coluna
    return papel_coluna(serie, col, 30, ["id", "*_id", "id_*", "codigo*"])


# --------------------------------------------------------------------------------------------- leitura de uma planilha
def ler(df: pd.DataFrame, nome: str, origem: str) -> dict:
    """Tudo o que a Bárbara entrega sobre UMA planilha. `df` já tratado (cabeçalho certo, sem Total)."""
    rotulo_original = {normalizar_nome_coluna(c): str(c) for c in df.columns}
    df = df.copy()
    df.columns = [normalizar_nome_coluna(c) for c in df.columns]
    df = df[[c for c in df.columns if not c.startswith("_")]]  # colunas de auditoria do robô não entram na análise
    for c in df.columns:  # datas que chegaram como texto ISO
        if df[c].dtype == object and df[c].dropna().astype(str).str.match(r"^\d{4}-\d{2}-\d{2}").mean() > 0.9:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    colunas, regras = [], []
    for col in df.columns:
        s = df[col]
        papel = _papel(s, col)
        if pd.api.types.is_datetime64_any_dtype(s):
            papel = "data"
        elif papel == "id" and pd.api.types.is_numeric_dtype(s) and any(
                re.search(x[0], col) for x in GLOSSARIO if x[3] not in ("unico", "data")):
            papel = "numero"  # "Valor da Venda" com todos os valores diferentes continua sendo valor, não identificador
        # o glossário só vale para o papel certo: "Canal de Venda" é categoria, não valor de venda
        g = next((x for x in GLOSSARIO if re.search(x[0], col) and papel in PAPEL_DA_REGRA.get(x[3], ("numero",))), None)
        info = {"coluna": col, "rotulo": rotulo_original.get(col, col), "papel": papel,
                "preenchimento": round(float(s.notna().mean()), 4) if len(s) else 0.0,
                "distintos": int(s.nunique()), "exemplo": str(s.dropna().iloc[0])[:40] if s.notna().any() else "",
                "significado": g[1] if g else _significado_padrao(papel),
                "regra": g[2] if g else "", "agregacao": (g[4] or "soma") if (g and papel == "numero") else
                ("soma" if papel == "numero" else None)}
        if papel == "numero" and info["agregacao"] is None:
            info["agregacao"] = "soma"
        colunas.append(info)
        if g:
            r = _conferir_regra(g[3], s, col)
            if r:
                regras.append(r)
    regras += _regras_cruzadas(df)
    tema = _tema(list(df.columns))
    metricas = [c for c in colunas if c["papel"] == "numero" and c["agregacao"]]
    # a métrica principal é a que responde à pergunta do tema (logística → atraso, não prazo)
    metricas.sort(key=lambda c: next((i for i, p in enumerate(METRICA_PRINCIPAL) if re.search(p, c["coluna"])), 99))
    dims = [c for c in colunas if c["papel"] == "categoria"]
    datas = [c for c in colunas if c["papel"] == "data"]
    seg = next((d for d in dims if re.search(SEGMENTO_PREFERIDO, d["coluna"])), dims[0] if dims else None)
    tabela = f"fato_{_slug(Path(nome).stem)}"
    medidas, ancoras = _medidas(df, tabela, metricas, seg, datas)
    return {
        "nome": nome, "origem": origem, "linhas": int(len(df)), "colunas_qtd": int(len(df.columns)),
        "assinatura": hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()[:16],
        "tema": tema, "colunas": colunas, "regras": regras,
        "modelo": {"fato": tabela, "metricas": [m["coluna"] for m in metricas],
                   "dimensoes": [{"tabela": f"dim_{d['coluna']}", "chave": d["coluna"], "valores": d["distintos"]} for d in dims],
                   "calendario": datas[0]["coluna"] if datas else None,
                   "relacoes": [f"dim_{d['coluna']}[{d['coluna']}] 1 → * {tabela}[{d['coluna']}] (filtro único)" for d in dims]
                   + ([f"dim_calendario[data] 1 → * {tabela}[{datas[0]['coluna']}] (marcar como tabela de datas)"] if datas else [])},
        "segmento": seg["coluna"] if seg else None, "medidas": medidas, "ancoras": ancoras,
        "por_segmento": _por_segmento(df, seg, metricas),
        "visuais": _visuais(tema, seg, metricas, datas),
        "amostra": _amostra(df, dims, metricas, datas),
        "achados": _achados(tema, regras, ancoras, df, seg, metricas),
    }


def _amostra(df, dims, metricas, datas, limite: int = 5000) -> dict:
    """As linhas que o relatório interativo filtra no navegador (filtro cruzado, segmentação): só categorias, métricas e a
    data — nunca identificador nem texto livre. Até 5.000 linhas; acima disso o painel avisa que é amostra."""
    cols = [d["coluna"] for d in dims] + [m["coluna"] for m in metricas] + ([datas[0]["coluna"]] if datas else [])
    parte = df[cols].head(limite)
    saida = {}
    for c in cols:
        serie = parte[c]
        if datas and c == datas[0]["coluna"]:
            saida[c] = [None if pd.isna(v) else pd.Timestamp(v).strftime("%Y-%m-%d") for v in serie]
        elif any(c == m["coluna"] for m in metricas):
            saida[c] = [None if pd.isna(v) else float(v) for v in pd.to_numeric(serie, errors="coerce")]
        else:
            saida[c] = [None if pd.isna(v) else str(v) for v in serie]
    return {"linhas": int(len(parte)), "total": int(len(df)), "colunas": saida,
            "dimensoes": [{"coluna": d["coluna"], "rotulo": d["rotulo"]} for d in dims],
            "medidas": [{"coluna": m["coluna"], "rotulo": m["rotulo"], "nome": _nome_medida(m), "agregacao": m["agregacao"]} for m in metricas],
            "data": datas[0]["coluna"] if datas else None}


def _significado_padrao(papel: str) -> str:
    return {"categoria": "Categoria para filtrar e comparar (vira dimensão)", "numero": "Número (vira medida)",
            "id": "Identificador", "data": "Data", "texto_livre": "Texto livre (comentário): não agrega; vira análise de texto",
            "texto": "Texto com muitos valores diferentes", "vazia": "Coluna vazia: não serve para análise"}.get(papel, "")


def _tema(colunas: list[str]) -> dict:
    pontos = []
    for nome, padrao, desc, perguntas in TEMAS:
        n = sum(bool(re.search(padrao, c)) for c in colunas)
        if n:
            pontos.append((n, nome, desc, perguntas))
    if not pontos:
        return {"nome": "Não reconheci o tema pelos cabeçalhos", "descricao": "Os nomes das colunas não batem com nenhum tema "
                "conhecido. A análise segue genérica (perfil + medidas) até alguém registrar o tema.", "perguntas": [],
                "certeza": 0}
    pontos.sort(reverse=True)
    n, nome, desc, perguntas = pontos[0]
    return {"nome": nome, "descricao": desc, "perguntas": perguntas, "certeza": round(min(1.0, n / 2), 2),
            "evidencia": [c for c in colunas if re.search(next(t[1] for t in TEMAS if t[0] == nome), c)]}


def _conferir_regra(tipo: str, s: pd.Series, col: str) -> dict | None:
    v = pd.to_numeric(s, errors="coerce") if tipo not in ("unico", "data") else s
    total = int(s.notna().sum())
    if tipo == "unico":
        ruins = int(s.duplicated(keep=False).sum() + s.isna().sum())
        texto = "IDs repetidos ou vazios"
    elif tipo == "nps":
        x = v.dropna()
        ruins = int(((x < 0) | (x > 10) | (x != x.round())).sum())
        texto = "notas fora de 0–10 ou não inteiras"
    elif tipo == "percentual":
        x = v.dropna()
        ruins = int(((x < 0) | (x > 100)).sum())
        texto = "percentuais fora de 0–100"
    elif tipo in ("nao_negativo", "contagem"):
        x = v.dropna()
        ruins = int((x < 0).sum()) + (int((x != x.round()).sum()) if tipo == "contagem" else 0)
        texto = "valores negativos" + (" ou não inteiros" if tipo == "contagem" else "")
    elif tipo == "estorno":
        x = v.dropna()
        ruins = int((x < 0).sum())
        return {"coluna": col, "regra": "Lançamento negativo = estorno", "violacoes": ruins, "total": total,
                "nivel": "aviso" if ruins else "ok", "texto": f"{ruins} lançamento(s) negativo(s): confirmar se são estornos"}
    elif tipo == "atraso":
        x = v.dropna()
        neg = int((x < 0).sum())
        q1, q3 = (x.quantile(0.25), x.quantile(0.75)) if len(x) else (0, 0)
        lim = q3 + 3 * (q3 - q1)
        fora = int((x > lim).sum()) if len(x) and q3 > q1 else 0
        return {"coluna": col, "regra": "Atraso não negativo; fora do padrão (> Q3 + 3×IQR) é investigado", "violacoes": neg + fora,
                "total": total, "nivel": "aviso" if neg + fora else "ok",
                "texto": f"{fora} atraso(s) fora do padrão (> {lim:.1f}) e {neg} negativo(s)", "limite": round(float(lim), 2)}
    elif tipo == "data":
        x = pd.to_datetime(s, errors="coerce")
        ruins = int(((x > pd.Timestamp(date.today()) + pd.Timedelta(days=1)) | (x < pd.Timestamp("2000-01-01"))).sum())
        texto = "datas no futuro ou antes de 2000"
    else:
        return None
    return {"coluna": col, "regra": texto.capitalize(), "violacoes": ruins, "total": total,
            "nivel": "erro" if ruins else "ok", "texto": f"{ruins} de {total} com {texto}" if ruins else "nenhuma violação"}


def _regras_cruzadas(df: pd.DataFrame) -> list[dict]:
    regras = []
    cl = next((c for c in df.columns if re.search(r"cliques", c)), None)
    cv = next((c for c in df.columns if re.search(r"conversoes", c)), None)
    if cl and cv:
        ruins = int((pd.to_numeric(df[cv], errors="coerce") > pd.to_numeric(df[cl], errors="coerce")).sum())
        regras.append({"coluna": f"{cv} × {cl}", "regra": "Conversões não podem passar dos cliques", "violacoes": ruins,
                       "total": int(len(df)), "nivel": "erro" if ruins else "ok",
                       "texto": f"{ruins} linha(s) com mais conversões que cliques" if ruins else "nenhuma violação"})
    pz = next((c for c in df.columns if re.search(r"prazo", c)), None)
    at = next((c for c in df.columns if re.search(r"atraso", c)), None)
    if pz and at:
        n = int((pd.to_numeric(df[at], errors="coerce") > 0).sum())
        regras.append({"coluna": at, "regra": "Entregas com atraso (> 0 dia)", "violacoes": n, "total": int(len(df)),
                       "nivel": "info", "texto": f"{n} de {len(df)} entregas chegaram depois do prazo"})
    return regras


# --------------------------------------------------------------------------------------------- medidas DAX + âncoras
def _nome_medida(m: dict) -> str:
    base = m["rotulo"]
    return {"soma": f"Total {base}", "media": f"Média {base}", "nps": "NPS"}.get(m["agregacao"], base)


def _medidas(df, tabela, metricas, seg, datas):
    t = f"'{tabela}'"
    medidas = [{"nome": "Linhas", "dax": f"Linhas = COUNTROWS ( {t} )",
                "explicacao": "Conta as linhas da fato no filtro atual (cada linha = um registro). Base para toda taxa.",
                "contexto": "Respeita todos os filtros e segmentações da página."}]
    ancoras = {"Linhas": int(len(df))}
    for m in metricas:
        col, x = m["coluna"], pd.to_numeric(df[m["coluna"]], errors="coerce")
        nome = _nome_medida(m)
        if m["agregacao"] == "nps":
            dax = (f"NPS =\nVAR Respostas = CALCULATE ( COUNTROWS ( {t} ), NOT ISBLANK ( {t}[{col}] ) )\n"
                   f"VAR Promotores = CALCULATE ( COUNTROWS ( {t} ), {t}[{col}] >= 9 )\n"
                   f"VAR Detratores = CALCULATE ( COUNTROWS ( {t} ), {t}[{col}] <= 6 )\n"
                   f"RETURN DIVIDE ( Promotores - Detratores, Respostas ) * 100")
            validos = x.dropna()
            valor = (float(((validos >= 9).sum() - (validos <= 6).sum()) / len(validos) * 100) if len(validos) else None)
            expl = ("% de promotores (9–10) menos % de detratores (0–6), sobre quem respondeu. CALCULATE troca o filtro só "
                    "da contagem; DIVIDE evita erro quando não há respostas no filtro.")
        elif m["agregacao"] == "media":
            dax = f"{nome} = AVERAGE ( {t}[{col}] )"
            valor = _num(x.mean())
            expl = "Média simples das linhas visíveis no filtro (ignora vazios). Para comparar grupos de tamanhos diferentes."
        else:
            dax = f"{nome} = SUM ( {t}[{col}] )"
            valor = _num(x.sum())
            expl = "Soma das linhas visíveis no filtro. É aditiva: a soma dos segmentos dá o total."
        medidas.append({"nome": nome, "dax": dax, "explicacao": expl, "contexto": "Filtro de linha não existe aqui: "
                        "a medida é calculada no contexto de filtro de cada célula do visual."})
        ancoras[nome] = round(valor, 4) if valor is not None else None
    soma = [m for m in metricas if m["agregacao"] == "soma"]
    nomes = {m["coluna"]: _nome_medida(m) for m in metricas}
    cl = next((m["coluna"] for m in soma if "cliques" in m["coluna"]), None)
    cv = next((m["coluna"] for m in soma if "conversoes" in m["coluna"]), None)
    inv = next((m["coluna"] for m in soma if "investimento" in m["coluna"]), None)
    if cl and cv:
        medidas.append({"nome": "Taxa de conversão", "dax": f"Taxa de conversão = DIVIDE ( [{nomes[cv]}], [{nomes[cl]}] )",
                        "explicacao": "Conversões por clique. Razão de somas (não média de razões): pesa cada canal pelo volume.",
                        "contexto": "Formate como porcentagem."})
        ancoras["Taxa de conversão"] = round(float(df[cv].sum() / df[cl].sum()), 6) if df[cl].sum() else None
    if inv and cv:
        medidas.append({"nome": "CPA (custo por conversão)", "dax": f"CPA = DIVIDE ( [{nomes[inv]}], [{nomes[cv]}] )",
                        "explicacao": "Quanto custou cada conversão. Menor é melhor.", "contexto": "Formate como moeda."})
        ancoras["CPA (custo por conversão)"] = round(float(df[inv].sum() / df[cv].sum()), 4) if df[cv].sum() else None
    if soma and seg:
        p = nomes[soma[0]["coluna"]]
        medidas.append({"nome": f"% do total ({p})", "dax": f"% do total = DIVIDE ( [{p}], CALCULATE ( [{p}], ALL ( 'dim_{seg['coluna']}' ) ) )",
                        "explicacao": f"Participação de cada {seg['rotulo']} no total. ALL remove o filtro da dimensão só no "
                                      "denominador: o total fica fixo enquanto o numerador muda a cada linha do visual.",
                        "contexto": "Use em matriz ou barras ordenadas."})
    if soma and datas:
        p = nomes[soma[0]["coluna"]]
        medidas.append({"nome": f"Variação mês a mês ({p})",
                        "dax": (f"Variação MoM =\nVAR Atual = [{p}]\nVAR Anterior = CALCULATE ( [{p}], DATEADD ( 'dim_calendario'[data], -1, MONTH ) )\n"
                                "RETURN DIVIDE ( Atual - Anterior, Anterior )"),
                        "explicacao": "Compara com o mês anterior. Exige dim_calendario marcada como tabela de datas e relacionada à fato.",
                        "contexto": "Use num visual com o mês no eixo."})
    return medidas, ancoras


def _por_segmento(df, seg, metricas) -> dict | None:
    if not seg:
        return None
    col = seg["coluna"]
    linhas = []
    for valor, g in df.groupby(col, dropna=False):
        item = {"segmento": str(valor), "linhas": int(len(g))}
        for m in metricas:
            x = pd.to_numeric(g[m["coluna"]], errors="coerce")
            nome = _nome_medida(m)
            if m["agregacao"] == "nps":
                v = x.dropna()
                item[nome] = round(float(((v >= 9).sum() - (v <= 6).sum()) / len(v) * 100), 2) if len(v) else None
            elif m["agregacao"] == "media":
                item[nome] = round(float(x.mean()), 4) if x.notna().any() else None
            else:
                item[nome] = round(float(x.sum()), 4)
        linhas.append(item)
    principal = _nome_medida(metricas[0]) if metricas else "linhas"
    linhas.sort(key=lambda r: -(r.get(principal) or 0) if metricas else -r["linhas"])
    return {"coluna": col, "rotulo": seg["rotulo"], "principal": principal, "linhas": linhas}


def _visuais(tema, seg, metricas, datas) -> list[dict]:
    v = [{"visual": "Cartões (KPI)", "pergunta": "Qual é o número agora?", "porque": "Leitura em 1 segundo no topo da página",
          "nao_usar": "Para comparar grupos (use barras)"}]
    if seg:
        v.append({"visual": "Barras horizontais ordenadas", "pergunta": f"Qual {seg['rotulo']} vai melhor/pior?",
                  "porque": "Comparar categorias com rótulos legíveis", "nao_usar": "Para tendência no tempo"})
    if datas:
        v.append({"visual": "Linha por mês", "pergunta": "Está melhorando ou piorando?", "porque": "Tempo no eixo X mostra tendência",
                  "nao_usar": "Com poucas datas (menos de 4 pontos)"})
    if len([m for m in metricas if m["agregacao"] != "nps"]) >= 2:
        v.append({"visual": "Dispersão", "pergunta": "Uma métrica anda junto com a outra?", "porque": "Mostra relação entre duas medidas",
                  "nao_usar": "Para mostrar total"})
    if "NPS" in tema["nome"]:
        v.append({"visual": "Barras 100% empilhadas (promotor/neutro/detrator)", "pergunta": "Qual a composição do NPS por segmento?",
                  "porque": "Mostra por que o NPS sobe ou cai", "nao_usar": "Com mais de 8 segmentos"})
    if "Financeiro" in tema["nome"]:
        v.append({"visual": "Cascata (waterfall)", "pergunta": "Como cada conta forma o total?", "porque": "Mostra contribuição +/−",
                  "nao_usar": "Para muitas categorias pequenas"})
    v.append({"visual": "Matriz com formatação condicional", "pergunta": "Onde está o detalhe?", "porque": "Tabela para quem precisa do número exato",
              "nao_usar": "Como visual principal da página"})
    return v


def _achados(tema, regras, ancoras, df, seg, metricas) -> list[str]:
    a = [f"Tema: {tema['nome']} — {len(df)} linhas."]
    ruins = [r for r in regras if r["nivel"] == "erro" and r["violacoes"]]
    a += [f"Regra quebrada em {r['coluna']}: {r['texto']}." for r in ruins[:3]]
    if not ruins:
        a.append("Nenhuma regra de negócio quebrada nas colunas conferidas.")
    seg_info = _por_segmento(df, seg, metricas) if seg and metricas else None
    if seg_info and len(seg_info["linhas"]) >= 2:
        p = seg_info["principal"]
        top, fim = seg_info["linhas"][0], seg_info["linhas"][-1]
        a.append(f"{p}: maior em {top['segmento']} ({_fmt(top.get(p))}) e menor em {fim['segmento']} ({_fmt(fim.get(p))}).")
    return a


def _fmt(v) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# --------------------------------------------------------------------------------------------- conferência (Heitor)
def reconciliar(df: pd.DataFrame, leitura: dict) -> list[str]:
    df = df.copy()
    df.columns = [normalizar_nome_coluna(c) for c in df.columns]
    div = []
    if leitura["ancoras"]["Linhas"] != len(df):
        div.append(f"{leitura['nome']}: linhas {leitura['ancoras']['Linhas']} × {len(df)}")
    metr = {c["coluna"]: c for c in leitura["colunas"] if c["coluna"] in leitura["modelo"]["metricas"]}
    for col, m in metr.items():
        arr = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
        nome = _nome_medida(m)
        if m["agregacao"] == "soma":
            refeito = float(np.nansum(arr))
        elif m["agregacao"] == "media":
            ok = arr[~np.isnan(arr)]
            refeito = float(ok.sum() / len(ok)) if len(ok) else None
        else:
            ok = arr[~np.isnan(arr)]
            refeito = float((np.count_nonzero(ok >= 9) - np.count_nonzero(ok <= 6)) * 100 / len(ok)) if len(ok) else None
        pub = leitura["ancoras"].get(nome)
        if (pub is None) != (refeito is None) or (pub is not None and abs(pub - refeito) > max(1e-3, 1e-9 * abs(refeito))):
            div.append(f"{leitura['nome']} › {nome}: painel {pub}, conferência {refeito}")
    seg = leitura.get("por_segmento")
    if seg:
        if sum(r["linhas"] for r in seg["linhas"]) != len(df):
            div.append(f"{leitura['nome']}: soma das linhas por {seg['rotulo']} ≠ total")
        for col, m in metr.items():
            if m["agregacao"] == "soma":
                nome = _nome_medida(m)
                total = float(np.nansum(pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)))
                if abs(sum(r.get(nome) or 0 for r in seg["linhas"]) - total) > 1e-2 * max(1, abs(total)):
                    div.append(f"{leitura['nome']} › {nome}: soma por {seg['rotulo']} ≠ total")
    return div


# --------------------------------------------------------------------------------------------- fontes
def planilhas_reais(cfg, limite: int = 8) -> list[tuple[str, pd.DataFrame]]:
    """As últimas planilhas publicadas em Bases-Tratadas (as reais da empresa)."""
    pasta = Path(getattr(cfg, "tratadas", "") or "")
    if not pasta or not pasta.exists():
        return []
    arquivos = sorted([p for p in pasta.rglob("*") if p.suffix.lower() in (".xlsx", ".csv") and not p.name.startswith("~$")],
                      key=lambda p: p.stat().st_mtime, reverse=True)[:limite]
    saida = []
    for p in arquivos:
        try:
            df = pd.read_csv(p, sep=None, engine="python") if p.suffix.lower() == ".csv" else pd.read_excel(p, sheet_name=0)
            if len(df):
                saida.append((p.name, df))
        except Exception:
            continue
    return saida


def planilhas_sinteticas(dia: date | None = None) -> list[tuple[str, pd.DataFrame]]:
    """Uma planilha de cada área do laboratório (dados SINTÉTICOS, semente do dia: muda todo dia, igual no mesmo dia)."""
    from robo import laboratorio
    dia = dia or date.today()
    saida = []
    for i, area in enumerate(laboratorio.AREAS):
        caso = laboratorio.gerar(area, int(dia.strftime("%Y%m%d")) * 10 + i)
        saida.append((f"laboratorio_{area}.xlsx", pd.DataFrame(caso["rotulos"])))
    return saida


def analisar_tudo(cfg) -> tuple[list[dict], list[str]]:
    leituras, divergencias = [], []
    for origem, fonte in (("real", planilhas_reais(cfg)), ("sintética", planilhas_sinteticas())):
        for nome, df in fonte:
            try:
                le = ler(df, nome, origem)
            except Exception as e:  # uma planilha estranha não derruba as outras
                divergencias.append(f"{nome}: não consegui ler ({type(e).__name__}: {e})")
                continue
            divergencias += reconciliar(df, le)
            leituras.append(le)
    return leituras, divergencias
