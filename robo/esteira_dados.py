"""Esteira de dados genérica — o que vem DEPOIS da limpeza, para qualquer planilha (vendas, RH, logística, financeiro,
pesquisa, estoque...). Três etapas, cada uma com a sua prova:

  1. qualidade()      as dimensões de qualidade (DAMA) e os valores suspeitos (suspeitos()): completude, unicidade, validade, consistência e atualidade,
                      por coluna. Exatidão NÃO é medida: sem uma fonte de referência ninguém consegue (e o relatório diz).
  2. modelo_estrela() fato + dimensões + calendário prontos para o Power BI, as relações (1:*) e as medidas DAX.
                      Prova: a fato tem as mesmas linhas da base e cada chave de dimensão é única.
  3. aprender()       Machine Learning supervisionado quando o usuário escolhe uma coluna alvo. Regras que impedem
                      "modelo bonito que mente":
                        - linha de base primeiro (chutar a classe mais comum / a média); o modelo só "vale" se a
                          superar com folga maior que a oscilação da validação cruzada;
                        - vazamento: coluna que sozinha acerta o alvo quase 100% é retirada e listada;
                        - divisão por TEMPO quando há data (treina no passado, testa no futuro); senão aleatória fixa;
                        - o teste final é usado UMA vez, depois de escolher o modelo só com o treino;
                        - importância por permutação no teste (o quanto o erro piora sem a coluna), não "peso" interno;
                        - base pequena ou classe rara demais: recusa com o motivo, em vez de inventar.
                      Dado sintético é aceito (marcado no manifesto pela origem); o modelo aprende o mundo DAQUELE dado.

Tudo determinístico (random_state fixo): a mesma planilha gera os mesmos números.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime

import numpy as np
import pandas as pd

from robo.limpeza import normalizar_nome_coluna, sem_acento

log = logging.getLogger("robo")

SEMENTE = 42
MIN_LINHAS_ML = 100
MIN_POR_CLASSE = 10
MAX_CLASSES = 20
MAX_CATEGORIAS_FEATURE = 50
MAX_LINHAS_ML = 50_000
LIMIAR_VAZAMENTO = 0.98
MOTIVO_FORA = {"id": "identificador", "auditoria": "controle", "vazia": "vazia", "texto_livre": "texto livre"}


# =============================================================================== 1. qualidade
def _fora_da_grafia(serie: pd.Series) -> tuple[int, int]:
    """(linhas escritas numa grafia diferente da mais comum do mesmo valor, linhas preenchidas). 'São Paulo' × 'sao
    paulo ' contam como o mesmo valor (ignora maiúsculas, acentos e espaços)."""
    v = serie.dropna().astype(str)
    if v.empty:
        return 0, 0
    cont = v.value_counts()
    vistos, fora = set(), 0
    for valor, q in cont.items():  # em ordem de frequência: o 1º de cada grupo é a grafia de referência
        k = " ".join(sem_acento(valor).lower().split())
        if k in vistos:
            fora += int(q)
        vistos.add(k)
    return fora, len(v)


def padronizar_categorias(df: pd.DataFrame, rel=None, tabela: str = "", max_distintos: int = 200) -> pd.DataFrame:
    """Padronização: valores de texto que só diferem em maiúsculas, acentos ou espaços viram a grafia MAIS FREQUENTE
    ('sudeste ' e 'SUDESTE' → 'Sudeste'). Cada troca fica registrada (coluna, de → para, quantas linhas). Colunas com
    muitos valores diferentes (nomes, textos livres) não são mexidas: o risco de juntar coisas distintas é maior."""
    df = df.copy()
    for col in df.columns:
        if str(col).startswith("_") or pd.api.types.is_numeric_dtype(df[col]) or \
                pd.api.types.is_datetime64_any_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
            continue
        v = df[col].dropna()
        if v.empty or not all(isinstance(x, str) for x in v.head(50)) or v.nunique() > max_distintos:
            continue
        cont = v.astype(str).value_counts()
        grupos: dict[str, list[str]] = {}
        for valor in cont.index:  # já em ordem de frequência: o 1º de cada grupo é a grafia que fica
            grupos.setdefault(" ".join(sem_acento(valor).lower().split()), []).append(valor)
        troca = {o: g[0] for g in grupos.values() if len(g) > 1 for o in g[1:]}
        if not troca:
            continue
        df[col] = df[col].map(lambda x: troca.get(x, x) if isinstance(x, str) else x)
        if rel is not None:
            exemplos = [f"'{o}' → '{d}' ({int(cont[o])})" for o, d in list(troca.items())[:5]]
            rel.info(f"Grafias diferentes do mesmo valor unificadas ({len(troca)} variação(ões))", tabela=tabela,
                     coluna=col, quantidade=int(sum(cont[o] for o in troca)), exemplos=exemplos)
    return df


DATAS_FUTURAS_OK = ("venc", "previs", "prazo", "agend", "validade", "expira", "fim", "termino", "renova", "proxim")


def suspeitos(df: pd.DataFrame, papeis: dict, hoje: datetime | None = None, limite: int = 20_000) -> pd.DataFrame:
    """Valores que provavelmente estão ERRADOS no conteúdo (a limpeza não tem como adivinhar o certo, então aponta):
      - idade fora de 0–120;
      - negativo numa coluna que é positiva em mais de 98% das linhas (provável sinal trocado; estorno legítimo
        aparece em volume e não é apontado);
      - valor muito acima do padrão da coluna (3 × intervalo interquartil na escala log: pega o erro de digitação de
        1000x sem apontar a cauda natural de valores, horas, prazos);
      - data no futuro (exceto colunas de vencimento, previsão, prazo...);
      - mesmo identificador em mais de uma linha (quase-duplicata: uma das duas está errada).
    Devolve [linha, chave, coluna, valor, regra]; chave = o 1º identificador da base (para achar a linha na origem)."""
    hoje = pd.Timestamp(hoje or datetime.now())
    ids = [c for c, p in papeis.items() if p == "id" and c in df.columns]
    achados = []

    def add(mascara, col, regra):
        for i in df.index[mascara.fillna(False).to_numpy()]:
            achados.append({"linha": int(i), "chave": df.at[i, ids[0]] if ids else None, "coluna": col,
                            "valor": df.at[i, col], "regra": regra})

    for col in df.columns:
        p = papeis.get(col, "")
        if p == "numero":
            x = pd.to_numeric(df[col], errors="coerce")
            v = x.dropna()
            if len(v) < 20:
                continue
            if "idade" in str(col).lower():
                add((x < 0) | (x > 120), col, "idade impossível (fora de 0 a 120)")
                continue
            neg = v < 0
            if 0 < neg.mean() <= 0.02 and v.median() > 0:
                add(x < 0, col, "negativo numa coluna positiva (sinal trocado?)")
            pos = v[v > 0]
            if pos.nunique() > 20:
                lg = np.log10(pos)
                q1, q3 = lg.quantile(.25), lg.quantile(.75)
                if q3 > q1:
                    add(x > 10 ** (q3 + 3 * (q3 - q1)), col, "valor muito acima do padrão (digitação?)")
        elif p == "data" and not any(k in str(col).lower() for k in DATAS_FUTURAS_OK):
            d = pd.to_datetime(df[col], errors="coerce")
            add(d > hoje + pd.Timedelta(days=1), col, "data no futuro")
    for col in ids[:1]:
        rep = df[col].notna() & df[col].duplicated(keep=False)
        add(rep, col, "identificador repetido (quase-duplicata)")
    out = pd.DataFrame(achados, columns=["linha", "chave", "coluna", "valor", "regra"])
    return out.head(limite)


def qualidade(df: pd.DataFrame, papeis: dict, rel=None, hoje: datetime | None = None) -> dict:
    """Devolve {colunas: DataFrame por coluna, tabela: {...}, notas: [...]}. Nota de 0 a 100 = média das dimensões
    que se aplicam à coluna (as que não se aplicam ficam vazias, não contam como 100)."""
    hoje = hoje or datetime.now()
    n = len(df)
    perdas = {}
    consist_rel = {}
    for o in (rel.ocorrencias if rel is not None else []):
        if o.coluna and "esvaziados" in o.mensagem:
            perdas[o.coluna] = perdas.get(o.coluna, 0) + int(o.quantidade or 0)
        if o.coluna and "misturados" in o.mensagem:
            consist_rel[o.coluna] = consist_rel.get(o.coluna, 0) + int(o.quantidade or 0)
    sus = suspeitos(df, papeis, hoje)
    por_col = sus.groupby("coluna").size().to_dict() if len(sus) else {}
    linhas = []
    for col in df.columns:
        papel = papeis.get(col, "")
        if papel == "auditoria":
            continue
        s = df[col]
        preench = int(s.notna().sum())
        item = {"coluna": col, "papel": papel, "completude": round(100 * preench / n, 1) if n else 0.0,
                "unicidade": None, "validade": None, "consistencia": None, "atualidade_dias": None}
        if papel == "id":
            v = s.dropna()
            item["unicidade"] = round(100 * v.nunique() / len(v), 1) if len(v) else None
        if papel in ("numero", "data") or col in perdas:  # inválido = não converteu (esvaziado) ou suspeito
            perdidos = perdas.get(col, 0)
            ruins = perdidos + (por_col.get(col, 0) if papel != "id" else 0)
            item["validade"] = round(100 * (1 - ruins / (preench + perdidos)), 1) if preench + perdidos else None
        item["suspeitos"] = int(por_col.get(col, 0))
        if papel in ("categoria", "texto"):
            fora, total = _fora_da_grafia(s)
            item["consistencia"] = round(100 * (1 - fora / total), 1) if total else None
        elif col in consist_rel and preench:
            item["consistencia"] = round(max(0.0, 100 * (1 - consist_rel[col] / preench)), 1)
        if papel == "data" and preench:
            item["atualidade_dias"] = int((pd.Timestamp(hoje) - pd.to_datetime(s).max()).days)
        dims = [item[k] for k in ("completude", "unicidade", "validade", "consistencia") if item[k] is not None]
        item["nota"] = round(sum(dims) / len(dims), 1) if dims else None
        item["situacao"] = "OK" if item["nota"] is not None and item["nota"] >= 95 else \
            "Atenção" if item["nota"] is not None and item["nota"] >= 80 else "Crítico"
        linhas.append(item)
    cols = pd.DataFrame(linhas)
    duplicadas = int(df.drop(columns=[c for c in df.columns if str(c).startswith("_")]).duplicated().sum()) if n else 0
    tabela = {"linhas": n, "colunas": len(cols), "linhas_duplicadas": duplicadas,
              "nota_geral": round(float(cols["nota"].dropna().mean()), 1) if len(cols) and cols["nota"].notna().any()
              else None,
              "criticas": cols.loc[cols["situacao"] == "Crítico", "coluna"].tolist() if len(cols) else []}
    notas = ["Exatidão (o valor bate com a realidade?) não pode ser medida sem uma fonte de referência: confira por "
             "amostragem com o sistema de origem."]
    datas = cols.dropna(subset=["atualidade_dias"]) if len(cols) else cols
    if len(datas):
        r = datas.sort_values("atualidade_dias").iloc[0]
        notas.append(f"Dado mais recente ({r['coluna']}) tem {int(r['atualidade_dias'])} dia(s).")
    if len(sus):
        tabela["suspeitos"] = sus.groupby("regra").size().to_dict()
    return {"colunas": cols, "tabela": tabela, "notas": notas, "suspeitos": sus}


# =============================================================================== 2. modelo estrela
def _sufixo(col: str) -> str:
    return normalizar_nome_coluna(col).removeprefix("id_")


def modelo_estrela(df: pd.DataFrame, papeis: dict, tabela: str, rel, metricas: list[dict] | None = None) -> dict:
    """Uma dimensão por coluna de categoria (2+ valores), calendário pela 1ª data, o resto fica na fato.
    Devolve {tabelas, fato, relacoes, dax, conferencias}."""
    from robo import modelagem
    dims = {}
    for c, p in papeis.items():
        if p == "categoria" and c in df.columns and df[c].nunique(dropna=True) >= 2:
            nome = f"dim_{_sufixo(c)}"
            chave = f"id_{_sufixo(c)}"
            if chave in df.columns or nome in dims:
                continue
            dims[nome] = {"colunas": [c], "chave": chave}
    datas = [c for c, p in papeis.items() if p == "data" and c in df.columns]
    modelo = {"fato": f"fato_{normalizar_nome_coluna(tabela)}", "dimensoes": dims}
    if datas:
        modelo["calendario"] = datas[0]
    tabelas = modelagem.modelar(df, tabela, modelo, rel)
    fato_nome = modelo["fato"]
    fato = tabelas[fato_nome]
    relacoes = [{"de": f"{d}[{dims[d]['chave']}]", "para": f"{fato_nome}[{dims[d]['chave']}]", "cardinalidade": "1:*",
                 "filtro": "único (dimensão → fato)"} for d in dims if d in tabelas]
    if "dim_calendario" in tabelas:
        relacoes.append({"de": "dim_calendario[data]", "para": f"{fato_nome}[{datas[0]}]", "cardinalidade": "1:*",
                         "filtro": "único (dimensão → fato)"})
    conf = [{"conferencia": "Modelo estrela: linhas da fato = linhas da base", "ok": len(fato) == len(df),
             "detalhe": f"fato {len(fato)} · base {len(df)}"}]
    repetidas = [d for d in dims if d in tabelas and tabelas[d][dims[d]["chave"]].duplicated().any()]
    sem_chave = [d for d in dims if d in tabelas and
                 int(fato[dims[d]["chave"]].isna().sum()) != int(df[dims[d]["colunas"][0]].isna().sum())]
    conf.append({"conferencia": "Modelo estrela: chaves únicas nas dimensões e toda linha ligada",
                 "ok": not repetidas and not sem_chave,
                 "detalhe": "; ".join([f"{d}: chave repetida" for d in repetidas] +
                                      [f"{d}: linhas sem chave" for d in sem_chave]) or f"{len(dims)} dimensão(ões) OK"})
    return {"tabelas": tabelas, "fato": fato_nome, "relacoes": relacoes,
            "dax": medidas_dax(fato_nome, metricas or [], "dim_calendario" in tabelas), "conferencias": conf}


def _nome_medida(texto: str) -> str:
    return " ".join(w.capitalize() for w in str(texto).replace("_", " ").split())


def medidas_dax(fato: str, metricas: list[dict], tem_calendario: bool) -> str:
    """Texto pronto para colar no Power BI (Modelagem > Nova medida), uma medida por bloco, com o porquê."""
    f = f"'{fato}'"
    blocos = ["-- Medidas sugeridas pelo Robô de Planilhas. No Power BI: guia Modelagem > Nova medida > cole UMA medida",
              "-- por vez (do nome até o fim da fórmula). Medida (e não coluna calculada) porque respeita os filtros",
              "-- e segmentações do relatório e não ocupa memória por linha.", "",
              "-- Quantas linhas (registros) há no contexto atual (filtros aplicados).",
              f"Qtd Registros = COUNTROWS({f})", ""]
    for m in metricas:
        c = m["coluna"]
        nome = _nome_medida(c)
        if m["op"] == "soma":
            blocos += [f"-- {c} é aditivo (valor/quantidade): somar faz sentido em qualquer recorte.",
                       f"Total {nome} = SUM({f}[{c}])", "",
                       f"-- Participação no total: o recorte atual ÷ o total ignorando filtros da fato.",
                       f"% {nome} no Total = DIVIDE([Total {nome}], CALCULATE([Total {nome}], ALL({f})))", ""]
            if tem_calendario:
                blocos += [f"-- Mesmo período do ano anterior (exige dim_calendario marcada como tabela de datas).",
                           f"{nome} Ano Anterior = CALCULATE([Total {nome}], SAMEPERIODLASTYEAR('dim_calendario'[data]))",
                           "",
                           f"Var % {nome} vs Ano Anterior = DIVIDE([Total {nome}] - [{nome} Ano Anterior], "
                           f"[{nome} Ano Anterior])", ""]
        else:
            blocos += [f"-- {c} não é aditivo: use MÉDIA. Nunca some médias de grupos (cada grupo tem um tamanho).",
                       f"Média {nome} = AVERAGE({f}[{c}])", "",
                       f"-- Mediana: resiste a valores extremos; compare com a média para ver se há distorção.",
                       f"Mediana {nome} = MEDIAN({f}[{c}])", ""]
    return "\n".join(blocos)


# =============================================================================== 3. Machine Learning
def _sklearn():
    try:
        import sklearn  # noqa: F401
        return True
    except ImportError:
        return False


def _tipo_tarefa(y: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(y) or not pd.api.types.is_numeric_dtype(y):
        return "classificacao"
    return "classificacao" if y.nunique() <= 10 and (y.dropna() == y.dropna().round()).all() else "regressao"


def _preparar(df: pd.DataFrame, papeis: dict, alvo: str) -> tuple[pd.DataFrame, list[str], list[str], list[str]]:
    """Variáveis explicativas: números, categorias (até 50 valores) e partes da data. IDs, texto livre, colunas de
    auditoria e o próprio alvo ficam fora (com o motivo)."""
    X = pd.DataFrame(index=df.index)
    num, cat, fora = [], [], []
    for c in df.columns:
        p = papeis.get(c, "")
        if c == alvo:
            continue
        if p in ("id", "auditoria", "vazia", "texto_livre"):
            fora.append(f"{c} ({MOTIVO_FORA[p]})")
        elif p == "numero":
            X[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
            num.append(c)
        elif p == "data":
            d = pd.to_datetime(df[c], errors="coerce")
            for parte, v in (("mes", d.dt.month), ("dia_semana", d.dt.dayofweek)):
                X[f"{c}__{parte}"] = v.astype(float)
                num.append(f"{c}__{parte}")
        elif p in ("categoria", "texto"):
            if df[c].nunique() > MAX_CATEGORIAS_FEATURE:
                fora.append(f"{c} (mais de {MAX_CATEGORIAS_FEATURE} valores diferentes)")
                continue
            X[c] = df[c].astype("string").fillna("(vazio)").astype(str)
            cat.append(c)
    return X, num, cat, fora


def _pipeline(tipo: str, num: list[str], cat: list[str], linear: bool):
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.pipeline import Pipeline, make_pipeline
    from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
    if linear:
        prep = ColumnTransformer([
            ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), num),
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=5, sparse_output=False), cat)])
        est = LogisticRegression(max_iter=2000, class_weight="balanced") if tipo == "classificacao" else Ridge(alpha=1.0)
    else:
        prep = ColumnTransformer([
            ("num", "passthrough", num),
            ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1), cat)])
        kw = {"random_state": SEMENTE, "max_iter": 200, "categorical_features": list(range(len(num), len(num) + len(cat)))
              if cat else None}
        est = (HistGradientBoostingClassifier(class_weight="balanced", **kw) if tipo == "classificacao"
               else HistGradientBoostingRegressor(**kw))
    return Pipeline([("prep", prep), ("modelo", est)])


def _vazamentos(X: pd.DataFrame, y: pd.Series, tipo: str, num: list[str], cat: list[str]) -> list[dict]:
    """Coluna que SOZINHA acerta o alvo quase sempre = provável vazamento (é o resultado disfarçado, ou só existe
    depois dele). Teste: árvore rasa com só essa coluna, validação cruzada de 3 partes."""
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import OrdinalEncoder
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
    achados = []
    amostra = X.sample(min(len(X), 5000), random_state=SEMENTE).index
    for c in num + cat:
        x = X.loc[amostra, [c]]
        if c in cat:
            x = OrdinalEncoder().fit_transform(x)
        else:
            x = x.fillna(x.median()).to_numpy()
        arv = (DecisionTreeClassifier(max_depth=4, random_state=SEMENTE) if tipo == "classificacao"
               else DecisionTreeRegressor(max_depth=4, random_state=SEMENTE))
        try:
            s = float(np.mean(cross_val_score(arv, x, y.loc[amostra], cv=3,
                                              scoring="accuracy" if tipo == "classificacao" else "r2")))
        except ValueError:
            continue
        if s >= LIMIAR_VAZAMENTO:
            achados.append({"coluna": c.split("__")[0], "variavel": c, "acerto_sozinha": round(s, 3)})
    return achados


def _metricas(tipo: str, y, p, proba=None) -> dict:
    from sklearn import metrics as m
    if tipo == "classificacao":
        r = {"acuracia": m.accuracy_score(y, p), "acuracia_balanceada": m.balanced_accuracy_score(y, p),
             "f1_macro": m.f1_score(y, p, average="macro", zero_division=0)}
        if proba is not None and len(np.unique(y)) == 2:
            r["auc"] = m.roc_auc_score(y, proba)
        return {k: round(float(v), 4) for k, v in r.items()}
    return {k: round(float(v), 4) for k, v in {"mae": m.mean_absolute_error(y, p),
                                                 "rmse": math.sqrt(m.mean_squared_error(y, p)),
                                                 "r2": m.r2_score(y, p)}.items()}


def aprender(df: pd.DataFrame, papeis: dict, alvo: str) -> dict:
    """ML supervisionado com as regras da docstring do módulo. Devolve {ok, motivo?, ...} — nunca levanta erro por
    causa dos dados: o motivo vai para o relatório."""
    inicio = time.perf_counter()
    alvo_n = normalizar_nome_coluna(alvo)
    if alvo_n not in df.columns:
        return {"ok": False, "alvo": alvo, "motivo": f"A coluna alvo '{alvo}' não existe na base tratada "
                f"(colunas: {', '.join(map(str, df.columns[:15]))}...)."}
    if not _sklearn():
        return {"ok": False, "alvo": alvo_n, "motivo": "A biblioteca scikit-learn não está instalada neste computador "
                "(pip install scikit-learn)."}
    from sklearn.dummy import DummyClassifier, DummyRegressor
    from sklearn.inspection import permutation_importance
    from sklearn.model_selection import KFold, StratifiedKFold, TimeSeriesSplit, cross_val_score

    base = df[df[alvo_n].notna()].copy()
    datas = [c for c, p in papeis.items() if p == "data" and c in base.columns and base[c].notna().mean() > 0.9]
    temporal = bool(datas)
    if temporal:
        base = base.sort_values(datas[0], kind="stable")
    if len(base) > MAX_LINHAS_ML:
        base = base.iloc[-MAX_LINHAS_ML:] if temporal else base.sample(MAX_LINHAS_ML, random_state=SEMENTE)
    y = base[alvo_n]
    tipo = _tipo_tarefa(y)
    saida = {"ok": False, "alvo": alvo_n, "tipo": tipo, "n": int(len(base)),
             "divisao": f"por tempo ({datas[0]}): treino = 80% mais antigo, teste = 20% mais recente" if temporal
             else "aleatória fixa (semente 42): 80% treino, 20% teste"}
    if len(base) < MIN_LINHAS_ML:
        return {**saida, "motivo": f"Só {len(base)} linhas com o alvo preenchido; o mínimo para um teste honesto é "
                                   f"{MIN_LINHAS_ML}."}
    if tipo == "classificacao":
        y = y.astype(str)
        cont = y.value_counts()
        if len(cont) > MAX_CLASSES:
            return {**saida, "motivo": f"O alvo tem {len(cont)} categorias; o limite é {MAX_CLASSES}."}
        if len(cont) < 2:
            return {**saida, "motivo": "O alvo tem um único valor: não há o que prever."}
        if cont.min() < MIN_POR_CLASSE:
            return {**saida, "motivo": f"A categoria '{cont.idxmin()}' tem só {int(cont.min())} casos; o mínimo é "
                                       f"{MIN_POR_CLASSE} por categoria."}
        saida["classes"] = {str(k): int(v) for k, v in cont.items()}
    else:
        y = y.astype(float)
    X, num, cat, fora = _preparar(base, papeis, alvo_n)
    saida["fora"] = fora
    vaz = _vazamentos(X, y, tipo, num, cat)
    saida["vazamentos"] = vaz
    tiradas = {v["variavel"] for v in vaz}
    num = [c for c in num if c not in tiradas]
    cat = [c for c in cat if c not in tiradas]
    if not num and not cat:
        return {**saida, "motivo": "Não sobrou nenhuma variável explicativa utilizável."}
    X = X[num + cat]
    corte = int(len(X) * 0.8)
    if temporal:
        Xtr, Xte, ytr, yte = X.iloc[:corte], X.iloc[corte:], y.iloc[:corte], y.iloc[corte:]
    else:
        from sklearn.model_selection import train_test_split
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=SEMENTE,
                                              stratify=y if tipo == "classificacao" else None)
    if tipo == "classificacao" and (ytr.nunique() < 2 or yte.nunique() < 2):
        return {**saida, "motivo": "Treino ou teste ficou com uma única categoria (o alvo muda com o tempo); "
                                   "não dá para avaliar com honestidade."}
    cv = TimeSeriesSplit(5) if temporal else (StratifiedKFold(5, shuffle=True, random_state=SEMENTE)
                                              if tipo == "classificacao" else KFold(5, shuffle=True, random_state=SEMENTE))
    score = "balanced_accuracy" if tipo == "classificacao" else "neg_mean_absolute_error"
    candidatos = {"Linha de base (" + ("classe mais comum" if tipo == "classificacao" else "média") + ")":
                  DummyClassifier(strategy="most_frequent") if tipo == "classificacao" else DummyRegressor(),
                  "Regressão " + ("logística" if tipo == "classificacao" else "linear (Ridge)"):
                  _pipeline(tipo, num, cat, True),
                  "Gradient boosting (árvores)": _pipeline(tipo, num, cat, False)}
    comparacao = []
    for nome, est in candidatos.items():
        try:
            s = cross_val_score(est, Xtr, ytr, cv=cv, scoring=score)
        except ValueError as e:
            comparacao.append({"modelo": nome, "erro": str(e)[:200]})
            continue
        sinal = 1 if tipo == "classificacao" else -1
        comparacao.append({"modelo": nome, "cv_media": round(float(sinal * s.mean()), 4),
                           "cv_desvio": round(float(s.std()), 4)})
    validos = [c for c in comparacao if "cv_media" in c]
    linha_base = validos[0] if validos and validos[0]["modelo"].startswith("Linha") else None
    modelos = [c for c in validos if not c["modelo"].startswith("Linha")]
    if not linha_base or not modelos:
        return {**saida, "comparacao": comparacao, "motivo": "A validação cruzada não pôde ser feita."}
    maior_melhor = tipo == "classificacao"
    melhor = (max if maior_melhor else min)(modelos, key=lambda c: c["cv_media"])
    ganho = (melhor["cv_media"] - linha_base["cv_media"]) * (1 if maior_melhor else -1)
    supera_cv = ganho > 2 * max(melhor["cv_desvio"], 1e-9)
    est = candidatos[melhor["modelo"]].fit(Xtr, ytr)
    base_est = candidatos[linha_base["modelo"]].fit(Xtr, ytr)
    p = est.predict(Xte)
    proba = est.predict_proba(Xte)[:, 1] if tipo == "classificacao" and ytr.nunique() == 2 else None
    m_teste = _metricas(tipo, yte, p, proba)
    m_base = _metricas(tipo, yte, base_est.predict(Xte),
                       base_est.predict_proba(Xte)[:, 1] if proba is not None else None)
    m_treino = _metricas(tipo, ytr, est.predict(Xtr))
    chave = "acuracia_balanceada" if tipo == "classificacao" else "mae"
    supera_teste = (m_teste[chave] > m_base[chave]) if maior_melhor else (m_teste[chave] < m_base[chave])
    vale = bool(supera_cv and supera_teste)
    imp = permutation_importance(est, Xte, yte, scoring=score, n_repeats=5, random_state=SEMENTE)
    importancias = sorted(({"variavel": c, "importancia": round(float(v), 4), "desvio": round(float(d), 4)}
                           for c, v, d in zip(Xte.columns, imp.importances_mean, imp.importances_std)),
                          key=lambda r: -r["importancia"])
    sobreajuste = (m_treino[chave] - m_teste[chave] > 0.15) if maior_melhor else \
        (m_teste[chave] > 1.5 * max(m_treino[chave], 1e-9) and m_teste[chave] - m_treino[chave] > 0)
    previsoes = pd.DataFrame({"linha": Xte.index, "real": yte.to_numpy(), "previsto": p})
    if proba is not None:
        previsoes["probabilidade"] = np.round(proba, 4)
    avisos = []
    if vaz:
        avisos.append("Colunas retiradas por vazamento: " + ", ".join(f"{v['coluna']} (acerta {100 * v['acerto_sozinha']:.0f}% "
                      "sozinha)" for v in vaz) + ". Confirme se elas só existem depois do resultado.")
    if sobreajuste:
        avisos.append("O modelo vai bem melhor no treino do que no teste (sobreajuste): decorou parte dos dados.")
    if tipo == "classificacao" and saida["classes"] and max(saida["classes"].values()) / saida["n"] > 0.9:
        avisos.append("Classes muito desbalanceadas: acurácia comum engana; olhe a acurácia balanceada.")
    return {**saida, "ok": True, "comparacao": comparacao, "escolhido": melhor["modelo"], "vale": vale,
            "ganho_cv": round(float(ganho), 4), "metrica_principal": chave, "teste": m_teste, "teste_linha_base": m_base,
            "treino": m_treino, "importancias": importancias[:12], "previsoes": previsoes, "avisos": avisos,
            "n_treino": int(len(Xtr)), "n_teste": int(len(Xte)), "segundos": round(time.perf_counter() - inicio, 1),
            "veredito": ("O modelo SUPERA a linha de base no treino (validação cruzada) e no teste: pode ser usado como "
                         "apoio, acompanhando o desempenho." if vale else
                         "O modelo NÃO supera a linha de base com segurança: não use para decidir. "
                         "Falta sinal nas colunas atuais (ou o alvo depende de algo que a planilha não tem).")}
