"""Ciência de dados do 2º andar: drivers do indicador, segmentação de clientes e anomalias. Só numpy e pandas.

Métodos (os mesmos usados em pesquisa de mercado e CX):
  - Drivers (key driver analysis): para cada atributo numérico, a correlação de Pearson com o indicador e o peso na
    regressão linear padronizada (betas), mais o R² do modelo e o VIF de cada atributo. VIF acima de 5 = atributo
    muito parecido com outro (colinearidade): o peso dele na regressão não é confiável, use a correlação.
    Regra de leitura: driver mostra ASSOCIAÇÃO, não causa.
  - Segmentação: k-means nas colunas numéricas padronizadas (z-score), testando de 2 a 5 grupos e escolhendo o de
    maior coeficiente de silhueta (amostra de até 1.500 linhas). Semente fixa: o mesmo dado dá o mesmo resultado.
  - Anomalias: regra de Tukey (fora de Q1 − 3×IQR ou Q3 + 3×IQR, "fora extremo") por coluna numérica.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SEMENTE = 42
# Colunas que são número mas não são medida: código, CEP e partes de data. Compara o 1º TERMO do nome, não o começo
# do texto — antes 'dias_entrega', 'anos_de_casa' e 'mesas' ficavam de fora (achado do treino contínuo, nível 4).
IGNORAR_TERMOS = {"id", "cod", "codigo", "cep", "ano", "mes", "dia", "semana", "trimestre"}


def _numericas(df: pd.DataFrame, excluir: list[str] | None = None) -> list[str]:
    excluir = set(excluir or [])
    return [c for c in df.columns if c not in excluir and pd.api.types.is_numeric_dtype(df[c])
            and not pd.api.types.is_bool_dtype(df[c]) and not str(c).startswith("_")
            and str(c).lower().split("_")[0] not in IGNORAR_TERMOS and not str(c).lower().endswith("_id")
            and df[c].nunique(dropna=True) > 2]


# --------------------------------------------------------------------------- drivers
def drivers(df: pd.DataFrame, alvo: str, atributos: list[str] | None = None) -> dict:
    atributos = atributos or _numericas(df, [alvo])
    if not atributos:
        return {"ok": False, "motivo": "não há atributos numéricos (notas, valores) para comparar com o indicador"}
    d = df[[alvo] + atributos].apply(pd.to_numeric, errors="coerce").dropna()
    if len(d) < 30:
        return {"ok": False, "motivo": f"só {len(d)} linha(s) completas; drivers precisam de pelo menos 30"}
    d = d.loc[:, d.std() > 0]
    atributos = [a for a in atributos if a in d.columns]
    if alvo not in d.columns or not atributos:
        return {"ok": False, "motivo": "o indicador ou os atributos não variam (todos iguais)"}
    d = d.astype(float)  # colunas do pipeline são nulláveis (Int64/Float64): o numpy precisa de float puro
    z = (d - d.mean()) / d.std()
    X, y = z[atributos].to_numpy(dtype=float), z[alvo].to_numpy(dtype=float)
    betas, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ betas
    r2 = float(1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum())
    vif = {}
    for i, a in enumerate(atributos):
        if len(atributos) == 1:
            vif[a] = 1.0
            continue
        outros = np.delete(X, i, axis=1)
        coef, *_ = np.linalg.lstsq(outros, X[:, i], rcond=None)
        resid = X[:, i] - outros @ coef
        r2_i = 1 - (resid ** 2).sum() / ((X[:, i] - X[:, i].mean()) ** 2).sum()
        vif[a] = float(1 / max(1 - r2_i, 1e-9))
    linhas = [{"atributo": a, "correlacao": float(np.corrcoef(d[a], d[alvo])[0, 1]), "beta": float(b), "vif": vif[a],
               "colinear": vif[a] > 5} for a, b in zip(atributos, betas)]
    soma = sum(abs(l["beta"]) for l in linhas) or 1
    for l in linhas:
        l["peso_pct"] = 100 * abs(l["beta"]) / soma
    linhas.sort(key=lambda l: -abs(l["correlacao"]))
    return {"ok": True, "alvo": alvo, "n": len(d), "r2": r2, "drivers": linhas}


# --------------------------------------------------------------------------- segmentação
def _kmeans(X: np.ndarray, k: int, rng: np.random.Generator, iteracoes: int = 100) -> tuple[np.ndarray, np.ndarray]:
    centros = X[rng.choice(len(X), 1)]
    for _ in range(1, k):  # k-means++ (início espalhado)
        d2 = ((X[:, None, :] - centros[None]) ** 2).sum(-1).min(1)
        centros = np.vstack([centros, X[rng.choice(len(X), 1, p=d2 / d2.sum())]])
    for _ in range(iteracoes):
        rotulos = ((X[:, None, :] - centros[None]) ** 2).sum(-1).argmin(1)
        novos = np.array([X[rotulos == j].mean(0) if (rotulos == j).any() else centros[j] for j in range(k)])
        if np.allclose(novos, centros):
            break
        centros = novos
    return rotulos, centros


def _silhueta(X: np.ndarray, rotulos: np.ndarray) -> float:
    # distâncias por produto escalar: n×n (não n×n×colunas) — 3.000 linhas × 20 colunas usava ~720 MB
    if len(X) > 4000:  # amostra fixa: a silhueta é uma estimativa de qualidade, não precisa de todas as linhas
        idx = np.random.default_rng(0).choice(len(X), 4000, replace=False)
        X, rotulos = X[idx], rotulos[idx]
    sq = (X ** 2).sum(1)
    dist = np.sqrt(np.maximum(sq[:, None] + sq[None, :] - 2 * X @ X.T, 0))
    s = []
    for i in range(len(X)):
        mesmo = rotulos == rotulos[i]
        if mesmo.sum() <= 1:
            s.append(0.0)
            continue
        a = dist[i, mesmo].sum() / (mesmo.sum() - 1)
        b = min(dist[i, rotulos == j].mean() for j in set(rotulos.tolist()) if j != rotulos[i])
        s.append((b - a) / max(a, b))
    return float(np.mean(s))


def segmentar(df: pd.DataFrame, colunas: list[str] | None = None, k_max: int = 5) -> dict:
    colunas = colunas or _numericas(df)
    if len(colunas) < 1:
        return {"ok": False, "motivo": "não há colunas numéricas para segmentar"}
    d = df[colunas].apply(pd.to_numeric, errors="coerce").dropna().astype(float)
    d = d.loc[:, d.std() > 0]
    if len(d) < 30 or d.shape[1] == 0:
        return {"ok": False, "motivo": f"só {len(d)} linha(s) completas; segmentação precisa de pelo menos 30"}
    media, desvio = d.mean(), d.std()
    Z = ((d - media) / desvio).to_numpy(dtype=float)
    rng = np.random.default_rng(SEMENTE)
    amostra = Z[rng.choice(len(Z), min(len(Z), 1500), replace=False)]
    melhor = None
    for k in range(2, k_max + 1):
        rot, centros = _kmeans(amostra, k, np.random.default_rng(SEMENTE))
        if len(set(rot.tolist())) < k:
            continue
        s = _silhueta(amostra, rot)
        if not melhor or s > melhor[0]:
            melhor = (s, k, centros)
    if not melhor:
        return {"ok": False, "motivo": "não foi possível separar grupos distintos"}
    s, k, centros = melhor
    rotulos = ((Z[:, None, :] - centros[None]) ** 2).sum(-1).argmin(1)
    grupos = []
    for j in range(k):
        sub = d[rotulos == j]
        perfil = {c: float(sub[c].mean()) for c in d.columns}
        destaque = sorted(d.columns, key=lambda c: -abs(centros[j][list(d.columns).index(c)]))[:2]
        grupos.append({"grupo": j + 1, "tamanho": int(len(sub)), "pct": 100 * len(sub) / len(d), "medias": perfil,
                       "marca": {c: ("acima" if centros[j][list(d.columns).index(c)] > 0 else "abaixo") for c in destaque}})
    grupos.sort(key=lambda g: -g["tamanho"])
    qualidade = "boa" if s >= 0.5 else "razoável" if s >= 0.25 else "fraca"
    return {"ok": True, "k": k, "silhueta": s, "qualidade": qualidade, "colunas": list(d.columns), "n": len(d),
            "grupos": grupos, "medias_gerais": {c: float(media[c]) for c in d.columns}}


# --------------------------------------------------------------------------- anomalias
def anomalias(df: pd.DataFrame, colunas: list[str] | None = None, limite: int = 20) -> dict:
    colunas = colunas or _numericas(df)
    achados = []
    for c in colunas:
        s = pd.to_numeric(df[c], errors="coerce")
        v = s.dropna()
        if len(v) < 10:
            continue
        q1, q3 = v.quantile(.25), v.quantile(.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        baixo, alto = q1 - 3 * iqr, q3 + 3 * iqr
        fora = s[(s < baixo) | (s > alto)]
        if len(fora):
            linhas = df.loc[fora.index, "_linha_origem"].tolist() if "_linha_origem" in df.columns else list(fora.index)
            achados.append({"coluna": c, "quantidade": int(len(fora)), "faixa_normal": (float(baixo), float(alto)),
                            "exemplos": [(l, float(x)) for l, x in zip(linhas[:5], fora.head(5))]})
    return {"ok": True, "colunas_avaliadas": len(colunas), "achados": achados[:limite]}


# --------------------------------------------------------------------------- textos (o que o funcionário fala)
def _n(v: float, casas: int = 2) -> str:
    return f"{v:.{casas}f}".replace(".", ",")


def texto_drivers(r: dict) -> tuple[str, list[dict]]:
    if not r["ok"]:
        return f"Não consegui rodar a análise de drivers: {r['motivo']}.", []
    top = r["drivers"][0]
    resumo = (f"O que mais anda junto com {r['alvo']} é **{top['atributo']}** (correlação {_n(top['correlacao'])}). "
              f"Os atributos explicam {_n(100 * r['r2'], 0)}% da variação de {r['alvo']} (n={r['n']}).")
    tabela = "\n".join(f"{i}. {d['atributo']}: correlação {_n(d['correlacao'])} · peso {_n(d['peso_pct'], 0)}%"
                       + (" · ⚠ muito parecido com outro atributo (VIF " + _n(d['vif'], 1) + "): confie mais na correlação"
                          if d["colinear"] else "") for i, d in enumerate(r["drivers"], 1))
    secoes = [{"titulo": "Ranking dos drivers", "texto": tabela},
              {"titulo": "Como ler", "texto": "Correlação vai de −1 a 1: quanto mais perto de 1, mais o atributo sobe junto com "
               "o indicador. O peso vem da regressão padronizada e soma 100%. Driver mostra associação, não causa: "
               "use para priorizar o que investigar, não como prova."}]
    return resumo, secoes


def texto_segmentos(r: dict) -> tuple[str, list[dict]]:
    if not r["ok"]:
        return f"Não consegui segmentar: {r['motivo']}.", []
    resumo = (f"Encontrei **{r['k']} grupos** de clientes (separação {r['qualidade']}, silhueta {_n(r['silhueta'])}), "
              f"usando {', '.join(r['colunas'])} em {r['n']} linhas.")
    linhas = []
    for g in r["grupos"]:
        marca = ", ".join(f"{c} {lado} da média" for c, lado in g["marca"].items())
        linhas.append(f"Grupo {g['grupo']}: {g['tamanho']} ({_n(g['pct'], 0)}%) — {marca}. Médias: "
                      + "; ".join(f"{c} {_n(v)}" for c, v in g["medias"].items()))
    return resumo, [{"titulo": "Os grupos", "texto": "\n".join(linhas)},
                    {"titulo": "Como ler", "texto": "k-means nas colunas padronizadas, de 2 a 5 grupos, escolhendo o de maior "
                     "silhueta (0 = grupos se misturam, 1 = bem separados; abaixo de 0,25 a separação é fraca e não deve virar "
                     "persona sem outra evidência)."}]


def texto_anomalias(r: dict) -> tuple[str, list[dict]]:
    if not r["achados"]:
        return f"Não encontrei valores fora do padrão nas {r['colunas_avaliadas']} coluna(s) numérica(s).", []
    resumo = f"Encontrei valores fora do padrão em **{len(r['achados'])} coluna(s)**."
    linhas = [f"{a['coluna']}: {a['quantidade']} valor(es) fora de {_n(a['faixa_normal'][0])} a {_n(a['faixa_normal'][1])}; "
              f"exemplos (linha, valor): " + ", ".join(f"{l}: {_n(v)}" for l, v in a["exemplos"]) for a in r["achados"]]
    return resumo, [{"titulo": "Onde estão", "texto": "\n".join(linhas)},
                    {"titulo": "Como ler", "texto": "Regra de Tukey extrema: abaixo de Q1 − 3×IQR ou acima de Q3 + 3×IQR. "
                     "Não é erro com certeza: confira na planilha de origem antes de excluir."}]


# --------------------------------------------------------------------------- provas técnicas
def provas() -> dict:
    rng = np.random.default_rng(1)
    n = 300
    x1, x2, x3 = rng.normal(size=n), rng.normal(size=n), rng.normal(size=n)
    df = pd.DataFrame({"nps": 3 * x1 + 0.3 * x2 + rng.normal(scale=0.5, size=n), "atendimento": x1, "preco": x2, "app": x3})
    r = drivers(df, "nps")
    nulavel = df.assign(atendimento=df["atendimento"].astype("Float64"), nps=df["nps"].astype("Float64"))
    r_nulavel = drivers(nulavel, "nps")
    blobs = pd.DataFrame({"a": np.r_[rng.normal(0, .3, 100), rng.normal(5, .3, 80)],
                          "b": np.r_[rng.normal(0, .3, 100), rng.normal(5, .3, 80)]})
    s = segmentar(blobs)
    limpo = pd.DataFrame({"v": rng.normal(10, 1, 200)})
    sujo = limpo.copy()
    sujo.loc[7, "v"] = 500
    return {
        "cd_senior_drivers": [("Acha o driver plantado (atendimento) em 1º", r["ok"] and r["drivers"][0]["atributo"] == "atendimento"),
                              ("Não inventa driver com poucos dados", not drivers(df.head(10), "nps")["ok"]),
                              ("Funciona com colunas nulláveis do pipeline (Float64)", r_nulavel["ok"])],
        "cd_pleno_segmentos": [("Separa dois grupos claros", s["ok"] and s["k"] == 2),
                               ("Funciona com colunas nulláveis (Float64)", segmentar(blobs.astype("Float64"))["ok"]),
                               ("Tamanhos certos (100 e 80)", s["ok"] and sorted(g["tamanho"] for g in s["grupos"]) == [80, 100])],
        "cd_junior_anomalias": [("Não acusa dado normal", not anomalias(limpo)["achados"]),
                                ("Pega o valor plantado", bool(anomalias(sujo)["achados"]))],
    }
