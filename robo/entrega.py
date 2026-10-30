"""Pacote de entrega: uma planilha de pesquisa (ou de operação) vira, num comando, o que o analista entrega ao gestor.

    python -m robo entregar minha_pesquisa.xlsx [--destino PASTA] [--segmentos regiao,curso]

Roda NO COMPUTADOR DO DONO, com a base dele: nada vai para a nuvem nem para o GitHub (o repositório é público e a
base pode ter dado pessoal). Usa os mesmos motores que a empresa treina todo dia com as planilhas da fábrica:

  1. leitura e limpeza (robo/pipeline.py)            base tratada + diagnóstico de qualidade (o que foi corrigido)
  2. indicadores com margem de erro (robo/analise.py) NPS, CSAT, CES no geral e por segmento, com aviso de base pequena
  3. diferenças reais (teste com correção de Holm)    só o que não é acaso vira destaque
  4. drivers (robo/ciencia.py)                        o que mais anda junto com a nota + matriz importância × desempenho
  5. logística, quando a base tem prazo e atraso      % no prazo, atraso médio, lead time, por transportadora e região
  6. relatório executivo em HTML (um arquivo só, abre em qualquer navegador e funciona sem internet)

Saída: uma pasta Entrega_<base>_<data>/ com base_tratada.xlsx, indicadores.xlsx e relatorio.html.

Recomendações saem por REGRA a partir dos números (nunca inventadas): driver importante com nota baixa vira
prioridade; segmento significativamente abaixo vira alvo; transportadora significativamente pior vira conversa de SLA.
"""

from __future__ import annotations

import html
import logging
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

log = logging.getLogger("robo")

PALAVRAS_ATRASO = ("atraso",)
PALAVRAS_PRAZO = ("prazo", "lead_time", "dias_entrega", "sla")
PALAVRAS_TRANSP = ("transportadora", "carrier", "operador_logistico")
PALAVRAS_REGIAO = ("uf", "regiao", "estado", "uf_destino", "cidade")


# =============================================================================== cálculo
def _coluna(df: pd.DataFrame, palavras: tuple[str, ...], numerica: bool) -> str | None:
    for c in df.columns:
        nome = str(c).lower()
        if any(p == nome or p in nome.split("_") or nome.startswith(p) for p in palavras):
            if not numerica or pd.to_numeric(df[c], errors="coerce").notna().mean() > 0.8:
                return c
    return None


def _prop(p: float, n: int, z: float = 1.96) -> float:
    return 100 * z * math.sqrt(max(p * (1 - p), 0) / n) if n else 0.0


def logistica(df: pd.DataFrame, base_minima: int = 30) -> dict | None:
    """% no prazo (atraso ≤ 0), atraso médio dos atrasados e lead time (prazo + atraso), no geral e por grupo.
    Sem coluna de atraso numérica, não há o que medir (None). 'OTIF' aqui é simplificado: a base não diz se a entrega
    veio completa, então o nome honesto é % no prazo."""
    col_atraso = _coluna(df, PALAVRAS_ATRASO, numerica=True)
    if not col_atraso:
        return None
    col_prazo = _coluna(df, PALAVRAS_PRAZO, numerica=True)
    atraso = pd.to_numeric(df[col_atraso], errors="coerce")
    ok = atraso.notna()
    d = df.loc[ok].copy()
    d["_atraso"] = atraso[ok].astype(float)
    d["_no_prazo"] = d["_atraso"] <= 0
    if col_prazo:
        d["_lead"] = pd.to_numeric(d[col_prazo], errors="coerce").astype(float) + d["_atraso"].clip(lower=0)

    def resumo(g: pd.DataFrame) -> dict:
        n = len(g)
        p = float(g["_no_prazo"].mean()) if n else 0.0
        atrasados = g.loc[~g["_no_prazo"], "_atraso"]
        r = {"n": n, "pct_no_prazo": 100 * p, "margem": _prop(p, n), "atrasadas": int((~g["_no_prazo"]).sum()),
             "atraso_medio_dos_atrasados": float(atrasados.mean()) if len(atrasados) else 0.0,
             "base_pequena": n < base_minima}
        if "_lead" in g:
            r["lead_time_medio"] = float(g["_lead"].mean())
        return r
    saida = {"coluna_atraso": col_atraso, "coluna_prazo": col_prazo, "geral": resumo(d), "grupos": {}}
    for papel, palavras in (("transportadora", PALAVRAS_TRANSP), ("regiao", PALAVRAS_REGIAO)):
        col = _coluna(d, palavras, numerica=False)
        if not col or d[col].nunique() < 2:
            continue
        linhas = []
        for grupo, g in d.groupby(col, dropna=True, observed=True):
            r = resumo(g)
            fora = d.loc[d[col] != grupo]
            # o grupo é pior que o restante de verdade? teste de duas proporções (z), só com base suficiente
            if len(g) >= base_minima and len(fora) >= base_minima:
                p1, p2 = g["_no_prazo"].mean(), fora["_no_prazo"].mean()
                ep = math.sqrt(p1 * (1 - p1) / len(g) + p2 * (1 - p2) / len(fora))
                r["z"] = float((p1 - p2) / ep) if ep else 0.0
            linhas.append({"grupo": str(grupo), **r})
        linhas.sort(key=lambda x: x["pct_no_prazo"])
        saida["grupos"][papel] = {"coluna": col, "linhas": linhas}
    return saida


RE_SOMA = ("valor", "receita", "venda", "faturamento", "custo", "salario", "despesa", "investimento", "quantidade",
           "qtd", "volume", "preco", "total", "leads", "mql", "estoque", "horas")


def visao_geral(a, max_grupos: int = 12) -> dict:
    """Para QUALQUER planilha: as métricas numéricas (soma quando é valor/quantidade, média nas demais), a métrica
    principal por segmento e a evolução por mês quando há data. Nada de indicador de pesquisa aqui."""
    if a is None or a.df.empty:
        return {}
    usadas = set(a.indicadores_cols.values())
    numeros = [c for c, p in a.papeis.items() if p == "numero" and c not in usadas]
    def op(c):
        return "soma" if any(k in str(c).lower() for k in RE_SOMA) else "média"
    metricas = []
    for c in numeros[:6]:
        v = pd.to_numeric(a.df[c], errors="coerce").dropna()
        if len(v):
            metricas.append({"coluna": c, "op": op(c), "valor": float(v.sum() if op(c) == "soma" else v.mean()),
                             "n": int(len(v))})
    saida = {"metricas": metricas, "por_segmento": [], "por_mes": None}
    if not metricas:
        return saida
    def rank(m):  # dinheiro antes de quantidade: valor/receita/faturamento são a métrica principal do negócio
        nome = str(m["coluna"]).lower()
        return next((i for i, k in enumerate(RE_SOMA) if k in nome), len(RE_SOMA)) if m["op"] == "soma" else 99
    principal = min(metricas, key=rank)
    col, oper = principal["coluna"], principal["op"]
    saida["principal"] = principal
    base = a.df.assign(_v=pd.to_numeric(a.df[col], errors="coerce"))
    for seg in a.segmentos[:4]:
        g = base.groupby(seg, dropna=True, observed=True)["_v"]
        r = (g.sum() if oper == "soma" else g.mean()).dropna().sort_values(ascending=False)
        n = g.count()
        if len(r) >= 2:
            linhas = [{"grupo": str(k), "valor": float(v), "n": int(n.get(k, 0))} for k, v in r.head(max_grupos).items()]
            total = float(r.sum()) if oper == "soma" else None
            pareto = None
            if total and len(r) >= 5:  # quantos grupos (20% do total de grupos) concentram quanto do total
                k = max(1, round(0.2 * len(r)))
                pareto = {"grupos_top": k, "grupos": len(r), "pct": 100 * float(r.head(k).sum()) / total}
            saida["por_segmento"].append({"segmento": seg, "linhas": linhas, "total": total, "pareto": pareto,
                                          "outros": max(0, len(r) - max_grupos)})
    # valores fora do padrão (regra de Tukey: abaixo de Q1 − 3·IQR ou acima de Q3 + 3·IQR), por métrica
    saida["fora_do_padrao"] = []
    for m in metricas:
        v = pd.to_numeric(a.df[m["coluna"]], errors="coerce").dropna()
        q1, q3 = v.quantile(.25), v.quantile(.75)
        iqr = q3 - q1
        if iqr > 0:
            n_fora = int(((v < q1 - 3 * iqr) | (v > q3 + 3 * iqr)).sum())
            if n_fora:
                saida["fora_do_padrao"].append({"coluna": m["coluna"], "n": n_fora, "pct": 100 * n_fora / len(v)})
    datas = [c for c, p in a.papeis.items() if p == "data"]
    if datas:
        d = base.dropna(subset=[datas[0]])
        if len(d):
            mes = d[datas[0]].dt.to_period("M")
            g = d.groupby(mes)["_v"]
            r = (g.sum() if oper == "soma" else g.mean()).dropna()
            cont = g.count()
            # último mês com bem menos registros que os anteriores = mês ainda em andamento: fica fora da tendência
            # (senão toda base parcial "cai 90%" no último mês — alarme falso)
            parcial = len(cont) >= 4 and cont.iloc[-1] < 0.6 * cont.iloc[-4:-1].median()
            if len(r) >= 2:
                saida["por_mes"] = {"coluna_data": datas[0], "linhas": [(str(k), float(v)) for k, v in r.tail(18).items()]}
                saida["por_mes"]["mes_parcial"] = str(r.index[-1]) if parcial else None
                rt = r.iloc[:-1] if parcial else r
                if len(rt) >= 4:  # último mês completo × média dos 3 anteriores (descritivo, não é teste estatístico)
                    r = rt
                    ult, ant = float(r.iloc[-1]), float(r.iloc[-4:-1].mean())
                    if ant:
                        saida["tendencia"] = {"mes": str(r.index[-1]), "valor": ult, "media_3_anteriores": ant,
                                              "variacao_pct": 100 * (ult - ant) / abs(ant)}
    return saida


def prioridades(drv: dict, df: pd.DataFrame) -> list[dict]:
    """Matriz importância × desempenho (padrão de Customer Insights): importância = |correlação| com a nota;
    desempenho = média do atributo na própria escala (0 a 1). Importante e abaixo da mediana = melhorar primeiro."""
    if not drv or not drv.get("ok"):
        return []
    linhas = []
    for d in drv["drivers"]:
        v = pd.to_numeric(df[d["atributo"]], errors="coerce").dropna()
        if v.empty:
            continue
        escala = 5 if v.max() <= 5 else 7 if v.max() <= 7 else 10
        linhas.append({"atributo": d["atributo"], "importancia": abs(d["correlacao"]), "desempenho": v.mean() / escala,
                       "media": v.mean(), "escala": escala, "peso_pct": d["peso_pct"]})
    if not linhas:
        return []
    imp_med = sorted(x["importancia"] for x in linhas)[len(linhas) // 2]
    des_med = sorted(x["desempenho"] for x in linhas)[len(linhas) // 2]
    # notas quase iguais (menos de 3 pontos em 100 de distância) não separam "bom" de "ruim": aí só a importância conta
    empate = max(x["desempenho"] for x in linhas) - min(x["desempenho"] for x in linhas) < 0.03
    for x in linhas:
        alta, bom = x["importancia"] >= imp_med, x["desempenho"] >= des_med
        if empate:
            x["quadrante"] = "Mais importante" if alta else "Menor peso"
        else:
            x["quadrante"] = ("Melhorar primeiro" if alta and not bom else "Manter (é força)" if alta and bom
                              else "Acompanhar" if not alta and not bom else "Não priorizar")
    ordem = {"Melhorar primeiro": 0, "Mais importante": 0, "Manter (é força)": 1, "Acompanhar": 2,
             "Não priorizar": 3, "Menor peso": 3}
    return sorted(linhas, key=lambda x: (ordem[x["quadrante"]], -x["importancia"]))


def recomendacoes(a, prio: list[dict], logi: dict | None, rel, visao: dict | None = None) -> list[str]:
    """Só o que os números sustentam. Cada frase diz de onde veio."""
    rec = []
    vg = visao or {}
    pr = vg.get("principal")
    if pr and pr["op"] == "soma":
        for blo in vg.get("por_segmento", [])[:2]:
            lider = blo["linhas"][0]
            if blo["total"] and lider["valor"] / blo["total"] >= 0.5 and len(blo["linhas"]) >= 3:
                rec.append(f"Atenção à concentração: **{lider['grupo']}** responde por "
                           f"{_n(100 * lider['valor'] / blo['total'])}% do total de {pr['coluna']} "
                           f"(por {blo['segmento']}). Dependência de um grupo só é risco.")
            elif blo.get("pareto") and blo["pareto"]["pct"] >= 50:
                pa = blo["pareto"]
                rec.append(f"Foco nos maiores: {pa['grupos_top']} de {pa['grupos']} grupos de {blo['segmento']} "
                           f"concentram {_n(pa['pct'])}% do total de {pr['coluna']} (Pareto). Comece por eles.")
    t = vg.get("tendencia")
    if t and abs(t["variacao_pct"]) >= 15:
        rec.append(f"{'Queda' if t['variacao_pct'] < 0 else 'Alta'} no último mês ({t['mes']}): "
                   f"{pr['op'] if pr else ''} de {pr['coluna'] if pr else ''} {_n(abs(t['variacao_pct']))}% "
                   f"{'abaixo' if t['variacao_pct'] < 0 else 'acima'} da média dos 3 meses anteriores. Confirme se o "
                   f"mês está completo antes de concluir.")
    for f in vg.get("fora_do_padrao", [])[:2]:
        if f["pct"] >= 0.5:
            rec.append(f"Conferir {f['n']} valor(es) fora do padrão em **{f['coluna']}** ({_n(f['pct'])}% da base): "
                       "podem ser erro de digitação ou casos reais que merecem olhar.")
    if a is not None and not a.destaques.empty:
        med = a.destaques[a.destaques["significativo"] & ~a.destaques["medida"].astype(str).str.match(r"^(NPS|CSAT|CES)")]
        for _, r in med.head(1).iterrows():
            rec.append(f"Entender a diferença em **{r['segmento_coluna']} = {r['segmento']}**: {r['medida']} "
                       f"{_n(r['valor_grupo'], 2)} contra {_n(r['valor_restante'], 2)} no restante (diferença real, "
                       f"n={r['n_grupo']}).")
    for x in [p for p in prio if p["quadrante"] == "Melhorar primeiro"][:2]:
        rec.append(f"Priorizar **{x['atributo']}**: é dos atributos que mais andam junto com a nota (correlação "
                   f"{_n(x['importancia'], 2)}) e tem desempenho abaixo dos demais (média {_n(x['media'])} de "
                   f"{x['escala']}).")
    mais = [p for p in prio if p["quadrante"] == "Mais importante"][:1]
    for x in mais:
        rec.append(f"Priorizar **{x['atributo']}**: os atributos têm notas parecidas (média ~{_n(x['media'])} de "
                   f"{x['escala']}), então o maior ganho vem de melhorar o que mais pesa na nota (correlação "
                   f"{_n(x['importancia'], 2)}).")
    if a is not None and not a.destaques.empty:
        # só indicadores em que MAIOR é melhor (NPS, CSAT, CES): numa média qualquer (ex.: dias de atraso) não se sabe
        # se menos é pior ou melhor, então ela não vira recomendação
        ind = a.destaques["medida"].astype(str).str.match(r"^(NPS|CSAT|CES)")
        abaixo = a.destaques[a.destaques["significativo"] & (a.destaques["diferenca"] < 0) & ind]
        for _, r in abaixo.head(2).iterrows():
            casas = 0 if str(r["medida"]).startswith("NPS") else 1
            rec.append(f"Investigar **{r['segmento_coluna']} = {r['segmento']}**: {r['medida']} "
                       f"{_n(r['valor_grupo'], casas)} contra {_n(r['valor_restante'], casas)} no restante — diferença "
                       f"real (não é acaso; n={r['n_grupo']}).")
    if logi:
        for papel in ("transportadora", "regiao"):
            g = (logi["grupos"].get(papel) or {}).get("linhas") or []
            piores = [x for x in g if x.get("z") is not None and x["z"] <= -1.96 and not x["base_pequena"]]
            for x in piores[:1]:
                rec.append(f"Abrir conversa de SLA com **{x['grupo']}** ({papel}): {_n(x['pct_no_prazo'])}% no prazo, "
                           f"abaixo do restante de forma significativa (n={x['n']}).")
    if rel is not None and rel.erros:
        rec.insert(0, "Corrigir a origem dos dados antes de divulgar: a base teve problemas que a limpeza não resolve "
                      "sozinha (veja Qualidade dos dados).")
    if not rec:
        rec.append("Nenhuma ação se destaca com segurança estatística nesta base. Comunique os indicadores gerais e "
                   "evite ranking entre grupos.")
    return rec


# =============================================================================== confiabilidade
def pasta_entregas(cfg=None) -> Path:
    """Onde cada entrega fica guardada no computador: ROBO_PASTA_ENTREGAS, ou estudio.pasta no config.yaml, ou
    Documentos/Robo de Planilhas/Entregas (a pasta Documentos do Windows se chama 'Documents' por dentro)."""
    import os
    escolhida = os.environ.get("ROBO_PASTA_ENTREGAS") or ((getattr(cfg, "dados", {}) or {}).get("estudio") or {}).get("pasta")
    return Path(escolhida) if escolhida else Path.home() / "Documents" / "Robo de Planilhas" / "Entregas"


def _sha(caminho: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def certificar(t, rel, a, pasta: Path) -> list[dict]:
    """Conferências automáticas, cada uma feita por um caminho INDEPENDENTE do cálculo do relatório:
      1. linhas: entrada − removidas registradas = saída (nenhuma linha some sem explicação);
      2. somas das colunas numéricas: pandas × SQL (SQLite) — dois motores, o mesmo número;
      3. indicador de pesquisa: o NPS/CSAT do relatório refeito em SQL direto na base tratada;
      4. arquivos: a base tratada gravada é relida e tem as mesmas linhas.
    Devolve [{conferencia, ok, detalhe}]."""
    import sqlite3
    itens = []
    if not t.analisaveis:
        return [{"conferencia": "Leitura da planilha", "ok": False, "detalhe": "a planilha não pôde ser lida"}]
    nome, df = max(t.analisaveis.items(), key=lambda kv: len(kv[1]))
    removidas = sum(int(o.quantidade or 0) for o in rel.ocorrencias if "removid" in o.mensagem.lower() and o.quantidade)
    entrada, saida = int(t.linhas_entrada or 0), sum(len(x) for x in t.analisaveis.values())
    itens.append({"conferencia": "Linhas: entrada − removidas = saída", "ok": entrada - removidas == saida,
                  "detalhe": f"{entrada} − {removidas} = {entrada - removidas} · saída {saida}"})
    conn = sqlite3.connect(":memory:")
    try:
        base = df.copy()
        base.columns = [f"c{i}" for i in range(len(base.columns))]
        for col in base.columns:  # datas/objetos viram texto (o SQLite não tem esses tipos)
            if not pd.api.types.is_numeric_dtype(base[col]):
                base[col] = base[col].astype(str)
        base.to_sql("t", conn, index=False)
        nomes = dict(zip(base.columns, df.columns))
        numericas = [c for c in base.columns if pd.api.types.is_numeric_dtype(base[c]) and not str(nomes[c]).startswith("_")]
        divergentes, conferidas = [], 0
        for c in numericas[:10]:
            s_pd = float(pd.to_numeric(df[nomes[c]], errors="coerce").sum())
            s_sql = conn.execute(f"SELECT TOTAL({c}) FROM t").fetchone()[0] or 0.0
            conferidas += 1
            if abs(s_pd - s_sql) > 1e-6 * max(1.0, abs(s_pd)):
                divergentes.append(f"{nomes[c]}: {s_pd} × {s_sql}")
        if conferidas:
            itens.append({"conferencia": f"Somas de {conferidas} coluna(s) numérica(s): pandas × SQL",
                          "ok": not divergentes, "detalhe": "; ".join(divergentes) or "todas iguais"})
        if a is not None and not a.indicadores.empty:
            inv = {v: k for k, v in nomes.items()}
            for _, r in a.indicadores[(a.indicadores["segmento"] == "Total")].iterrows():
                if r["indicador"] != "NPS" or r["coluna"] not in inv:
                    continue
                c = inv[r["coluna"]]
                p, d, n = conn.execute(f"SELECT SUM({c} >= 9), SUM({c} <= 6), COUNT({c}) FROM t WHERE {c} BETWEEN 0 AND 10 "
                                       f"AND {c} = CAST({c} AS INTEGER)").fetchone()
                nps_sql = 100.0 * (p - d) / n if n else float("nan")
                itens.append({"conferencia": "NPS do relatório refeito em SQL", "ok": abs(nps_sql - float(r["valor"])) < 0.051,
                              "detalhe": f"relatório {_n(r['valor'])} · SQL {_n(nps_sql)} (n={n})"})
    finally:
        conn.close()
    arq = pasta / "base_tratada.xlsx"
    if arq.exists():
        relida = sum(len(x) for x in pd.read_excel(arq, sheet_name=None).values())
        gravada = sum(len(x) for x in t.tabelas.values())
        itens.append({"conferencia": "Base tratada gravada e relida", "ok": relida == gravada,
                      "detalhe": f"{gravada} linhas gravadas · {relida} relidas"})
    return itens


def gravar_manifesto(pasta: Path, original: Path | None, conferencias: list[dict], extra: dict) -> Path:
    """manifesto.json: o que entrou, o que saiu (com SHA-256 para provar que nada mudou depois), as conferências e
    quando. Fica junto da entrega, para sempre."""
    import json
    arquivos = {p.name: {"sha256": _sha(p), "bytes": p.stat().st_size} for p in sorted(pasta.iterdir())
                if p.is_file() and p.name != "manifesto.json"}
    dados = {"gerado_em": datetime.now().isoformat(timespec="seconds"),
             "original": {"nome": original.name, "sha256": _sha(original)} if original and original.exists() else None,
             "arquivos": arquivos, "conferencias": conferencias,
             "todas_ok": all(c["ok"] for c in conferencias) if conferencias else False, **extra}
    destino = pasta / "manifesto.json"
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return destino


# =============================================================================== HTML
COR = {"primaria": "#1F4E79", "texto": "#1A1A1A", "suave": "#5F6B7A", "linha": "#E3E7ED", "bom": "#2E7D32",
       "ruim": "#C62828", "neutro": "#8A97A8", "fundo": "#F6F8FB"}


def _n(v, casas: int = 1) -> str:
    """Número no padrão brasileiro: 1.234,5."""
    v = round(float(v), casas) + 0.0  # sem "-0"
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _e(x) -> str:
    return html.escape(str(x))


def _barras(itens: list[tuple[str, float, str]], sufixo: str = "", largura: int = 560, casas: int = 1) -> str:
    """Barras horizontais em SVG, sempre a partir do zero (escala truncada exagera diferenças)."""
    if not itens:
        return ""
    alt_linha, rotulo_w = 26, 170
    vals = [v for _, v, _ in itens]
    lo, hi = min(0.0, min(vals)), max(0.0, max(vals)) or 1.0
    area = largura - rotulo_w - 70
    escala = area / (hi - lo if hi > lo else 1)
    zero = rotulo_w + (0 - lo) * escala
    partes = [f'<svg viewBox="0 0 {largura} {alt_linha * len(itens) + 6}" width="100%" '
              f'style="max-width:{largura}px" role="img">']
    for i, (rot, v, cor) in enumerate(itens):
        y = i * alt_linha + 4
        x0, w = (zero, v * escala) if v >= 0 else (zero + v * escala, -v * escala)
        partes.append(f'<text x="{rotulo_w - 8}" y="{y + 15}" text-anchor="end" font-size="12" fill="{COR["texto"]}">'
                      f'{_e(rot[:26])}</text>')
        partes.append(f'<rect x="{x0:.1f}" y="{y + 3}" width="{max(w, 1):.1f}" height="16" rx="3" fill="{cor}"/>')
        partes.append(f'<text x="{x0 + max(w, 1) + 6:.1f}" y="{y + 15}" font-size="12" fill="{COR["suave"]}">'
                      f'{_n(v, casas)}{_e(sufixo)}</text>')
    partes.append(f'<line x1="{zero:.1f}" y1="0" x2="{zero:.1f}" y2="{alt_linha * len(itens) + 6}" '
                  f'stroke="{COR["linha"]}"/></svg>')
    return "".join(partes)


def _casas(r) -> int:
    return 0 if str(r["medida"]).startswith("NPS") else 1 if str(r["medida"]).startswith(("CSAT", "CES")) else 2


def _cor_dif(r) -> str:
    """Verde/vermelho só onde MAIOR é melhor (NPS, CSAT, CES); numa média qualquer, sem cor (não se sabe o sentido)."""
    if not str(r["medida"]).startswith(("NPS", "CSAT", "CES")):
        return ""
    return "pos" if r["diferenca"] > 0 else "neg"


def _card(titulo: str, valor: str, detalhe: str) -> str:
    return (f'<div class="card"><div class="ct">{_e(titulo)}</div><div class="cv">{_e(valor)}</div>'
            f'<div class="cd">{_e(detalhe)}</div></div>')


def _md(texto: str) -> str:
    """**negrito** simples, o resto escapado."""
    partes = _e(texto).split("**")
    return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(partes))


def montar_html(info: dict) -> str:
    a, rel, logi, prio, drv = info["analise"], info["relatorio"], info["logistica"], info["prioridades"], info["drivers"]
    cards, secoes = [], []
    if a is not None and not a.indicadores.empty:
        for _, r in a.indicadores[a.indicadores["segmento"] == "Total"].iterrows():
            casas = 0 if r["indicador"] == "NPS" else 1
            det = f"±{_n(r['margem'], casas)} pts · n={int(r['n'])}"
            if r["indicador"] == "NPS":
                det += f" · {r['pct_promotores']:.0f}% prom. / {r['pct_detratores']:.0f}% detr."
            cards.append(_card(r["indicador"], _n(r["valor"], casas), det))
    if logi:
        g = logi["geral"]
        cards.append(_card("Entregas no prazo", f"{_n(g['pct_no_prazo'])}%", f"±{_n(g['margem'])} pts · n={g['n']}"))
        cards.append(_card("Atraso médio (atrasadas)", f"{_n(g['atraso_medio_dos_atrasados'])} dias",
                           f"{g['atrasadas']} entregas atrasadas"))
        if "lead_time_medio" in g:
            cards.append(_card("Lead time médio", f"{_n(g['lead_time_medio'])} dias", "prazo + atraso"))
    vg = info.get("visao") or {}
    if not cards and vg.get("metricas"):  # planilha que não é pesquisa nem logística: as métricas dela
        for m in vg["metricas"][:3]:
            cards.append(_card(f"{'Total' if m['op'] == 'soma' else 'Média'} de {m['coluna']}",
                               _n(m["valor"], 0 if m["op"] == "soma" and abs(m["valor"]) >= 1000 else 2),
                               f"n={m['n']}"))
    if info.get("qualidade") and info["qualidade"]["tabela"]["nota_geral"] is not None:
        qt = info["qualidade"]["tabela"]
        cards.append(_card("Qualidade dos dados", f"{_n(qt['nota_geral'])}/100",
                           f"{len(qt['criticas'])} coluna(s) crítica(s) · {qt['linhas_duplicadas']} linha(s) repetida(s)"))
    ml = info.get("ml")
    if ml and ml.get("ok"):
        mp = ml["metrica_principal"]
        cards.append(_card(f"Modelo de ML ({ml['alvo']})", "vale a pena" if ml["vale"] else "não use",
                           f"{_ML_NOME[mp]} {_n(ml['teste'][mp], 3)} × linha de base {_n(ml['teste_linha_base'][mp], 3)}"))
    cards.append(_card("Registros analisados", f"{info['linhas']:,}".replace(",", "."),
                       f"{len(rel.erros)} erro(s) · {len(rel.avisos)} aviso(s) na limpeza"))

    conf = info.get("conferencias") or []
    if conf:
        ok = sum(1 for c in conf if c["ok"])
        secoes.append(f"<h2>Certificado de conferência: {ok} de {len(conf)} "
                      f"{'✅ todas batem' if ok == len(conf) else '⚠️ veja abaixo'}</h2><table><tr><th>Conferência</th>"
                      "<th>Resultado</th><th>Detalhe</th></tr>" +
                      "".join(f"<tr><td>{_e(c['conferencia'])}</td><td class='{'pos' if c['ok'] else 'neg'}'>"
                              f"{'OK' if c['ok'] else 'NÃO BATE'}</td><td>{_e(c['detalhe'])}</td></tr>" for c in conf) +
                      "</table><p class='nota'>Cada conferência refaz a conta por outro caminho (SQL × pandas, releitura "
                      "do arquivo). A impressão digital (SHA-256) do original e de cada arquivo está em manifesto.json."
                      "</p>")
    secoes.append("<h2>Recomendações</h2><ol>" + "".join(f"<li>{_md(x)}</li>" for x in info["recomendacoes"]) +
                  "</ol><p class='nota'>Geradas por regra a partir dos números desta base. Valide com o contexto do "
                  "negócio antes de decidir.</p>")
    if ml:
        secoes.append(_secao_ml(ml))
    if info.get("estrela"):
        secoes.append(_secao_estrela(info["estrela"]))
    if prio:
        classe = {"Melhorar primeiro": "q0", "Mais importante": "q0", "Manter (é força)": "q1"}
        linhas = "".join(f"<tr><td>{_e(x['atributo'])}</td><td>{_n(x['importancia'], 2)}</td><td>{_n(x['media'])} de "
                         f"{x['escala']}</td><td class='{classe.get(x['quadrante'], '')}'>{_e(x['quadrante'])}</td></tr>"
                         for x in prio)
        secoes.append(f"<h2>O que mais pesa na nota ({_e(drv['alvo'])})</h2>"
                      f"<p class='nota'>Correlação de cada atributo com a nota (n={drv['n']}; os atributos juntos "
                      f"explicam {100 * drv['r2']:.0f}% da variação). Correlação não prova causa.</p>"
                      + ("<p class='nota'>Os atributos têm notas parecidas: a prioridade vem só da importância.</p>"
                         if any(x["quadrante"] in ("Mais importante", "Menor peso") for x in prio) else "")
                      + "<table><tr><th>Atributo</th><th>Importância</th><th>Desempenho</th><th>Prioridade</th></tr>"
                      f"{linhas}</table>")
    if a is not None and not a.indicadores.empty:
        for (ind, seg), g in a.indicadores[a.indicadores["segmento"] != "Total"].groupby(["indicador", "segmento_coluna"]):
            g = g.sort_values("valor")
            itens = [(f"{r['segmento']}{' *' if r['base_pequena'] else ''}", float(r["valor"]),
                      COR["neutro"] if r["base_pequena"] else COR["primaria"]) for _, r in g.head(15).iterrows()]
            secoes.append(f"<h3>{_e(ind)} por {_e(seg)}</h3>{_barras(itens, casas=0 if ind == 'NPS' else 1)}"
                          + ("<p class='nota'>* base pequena (menos de 30): não compare.</p>"
                             if any(g["base_pequena"]) else ""))
    if vg.get("principal") and (a is None or a.indicadores.empty):
        pr = vg["principal"]
        nome = f"{'Total' if pr['op'] == 'soma' else 'Média'} de {pr['coluna']}"
        for blo in vg["por_segmento"]:
            itens = [(x["grupo"], x["valor"], COR["primaria"]) for x in blo["linhas"]]
            parte = ""
            if blo["total"]:
                lider = blo["linhas"][0]
                parte = (f"<p class='nota'>{_e(lider['grupo'])} responde por "
                         f"{_n(100 * lider['valor'] / blo['total'])}% do total"
                         + (f"; {blo['pareto']['grupos_top']} de {blo['pareto']['grupos']} grupos concentram "
                            f"{_n(blo['pareto']['pct'])}% (Pareto)" if blo.get("pareto") else "") + ".</p>")
            secoes.append(f"<h3>{_e(nome)} por {_e(blo['segmento'])}</h3>{_barras(itens, casas=0 if pr['op'] == 'soma' else 2)}"
                          + parte + (f"<p class='nota'>+{blo['outros']} grupo(s) menores não mostrados (estão no "
                                     "indicadores.xlsx).</p>" if blo["outros"] else ""))
        if vg.get("por_mes"):
            pm = vg["por_mes"]
            itens = [(k, v, COR["primaria"]) for k, v in pm["linhas"]]
            secoes.append(f"<h3>{_e(nome)} por mês ({_e(pm['coluna_data'])})</h3>"
                          f"{_barras(itens, casas=0 if pr['op'] == 'soma' else 2)}"
                          "<p class='nota'>Em ordem de tempo (mês mais antigo em cima)."
                          + (f" {_e(pm['mes_parcial'])} parece incompleto (bem menos registros) e não entra na "
                             "tendência." if pm.get("mes_parcial") else "") + "</p>")
    if a is not None and not a.perfil.empty:
        def resumo_col(r):
            if r.get("papel") == "numero" and pd.notna(r.get("minimo")):
                return f"{_n(r['minimo'], 2)} a {_n(r['maximo'], 2)} (mediana {_n(r['mediana'], 2)})"
            if r.get("papel") == "data" and isinstance(r.get("minimo"), str):
                return f"{r['minimo']} a {r['maximo']}"
            mc = r.get("mais_comuns")
            return "" if mc is None or (isinstance(mc, float) and math.isnan(mc)) else str(mc)[:120]
        p = a.perfil[~a.perfil["papel"].isin(["auditoria"])]
        secoes.append("<h2>Visão geral da base</h2><table><tr><th>Coluna</th><th>Tipo</th><th>Preenchido</th>"
                      "<th>Distintos</th><th>Resumo</th></tr>" +
                      "".join(f"<tr><td>{_e(r['coluna'])}</td><td>{_e(r['papel'])}</td><td>{_n(r['pct_preenchido'])}%"
                              f"</td><td>{int(r['distintos'])}</td><td>{_e(resumo_col(r))}</td></tr>"
                              for _, r in p.iterrows()) + "</table>")
    if a is not None and not a.destaques.empty:
        sig = a.destaques[a.destaques["significativo"]]
        if len(sig):
            secoes.append("<h2>Diferenças reais entre grupos</h2><table><tr><th>Grupo</th><th>Medida</th><th>Grupo</th>"
                          "<th>Restante</th><th>Diferença</th><th>n</th></tr>" +
                          "".join(f"<tr><td>{_e(r['segmento_coluna'])} = {_e(r['segmento'])}</td><td>{_e(r['medida'])}"
                                  f"</td><td>{_n(r['valor_grupo'], _casas(r))}</td><td>{_n(r['valor_restante'], _casas(r))}"
                                  f"</td><td class='{_cor_dif(r)}'>{'+' if r['diferenca'] > 0 else ''}"
                                  f"{_n(r['diferenca'], _casas(r))}</td><td>{r['n_grupo']}</td></tr>"
                                  for _, r in sig.head(10).iterrows()) +
                          "</table><p class='nota'>Significativas a 95% com correção de Holm (muitas comparações geram "
                          "falsos positivos; a correção controla isso).</p>")
    if logi:
        for papel, g in logi["grupos"].items():
            itens = [(f"{x['grupo']}{' *' if x['base_pequena'] else ''}", x["pct_no_prazo"],
                      COR["ruim"] if x.get("z") is not None and x["z"] <= -1.96 else
                      COR["neutro"] if x["base_pequena"] else COR["primaria"]) for x in g["linhas"][:15]]
            secoes.append(f"<h3>% no prazo por {_e(g['coluna'])}</h3>{_barras(itens, '%')}"
                          "<p class='nota'>Em vermelho: abaixo do restante de forma significativa. * base pequena.</p>")
    oc = rel.ocorrencias
    passos = [o_ for o_ in oc if o_.nivel == "INFO"]
    if passos:
        secoes.append("<h2>Limpeza e padronização feitas</h2><ul>" +
                      "".join(f"<li>{_e(o_.mensagem)}" + (f" <span class='nota'>({_e(o_.coluna)})</span>" if o_.coluna
                                                           else "") + "</li>" for o_ in passos[:40]) + "</ul>")
    if vg.get("fora_do_padrao"):
        secoes.append("<h3>Valores fora do padrão</h3><ul>" + "".join(
            f"<li>{_e(f['coluna'])}: {f['n']} valor(es) ({_n(f['pct'])}%)</li>" for f in vg["fora_do_padrao"]) +
            "</ul><p class='nota'>Regra de Tukey (3 × intervalo interquartil). Fora do padrão não quer dizer errado.</p>")
    if info.get("qualidade"):
        q = info["qualidade"]["colunas"]
        ruins = q[q["situacao"] != "OK"] if len(q) else q
        fmt = lambda v: "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{_n(v)}%"  # noqa: E731
        secoes.append("<h2>Qualidade dos dados (dimensões DAMA)</h2><p class='nota'>Completude = preenchido; unicidade = "
                      "identificador sem repetição; validade = valor no tipo certo; consistência = % de linhas na grafia de referência do valor "
                      "(maiúsculas, acentos, espaços). Nota = média das dimensões que se aplicam à coluna.</p>" +
                      ("<table><tr><th>Coluna</th><th>Completude</th><th>Unicidade</th><th>Validade</th>"
                       "<th>Consistência</th><th>Nota</th><th>Situação</th></tr>" +
                       "".join(f"<tr><td>{_e(r['coluna'])}</td><td>{fmt(r['completude'])}</td><td>{fmt(r['unicidade'])}"
                               f"</td><td>{fmt(r['validade'])}</td><td>{fmt(r['consistencia'])}</td>"
                               f"<td>{fmt(r['nota']).rstrip('%')}</td><td class='{'neg' if r['situacao'] == 'Crítico' else ''}'>"
                               f"{_e(r['situacao'])}</td></tr>" for _, r in ruins.iterrows()) + "</table>"
                       if len(ruins) else "<p>Todas as colunas com nota 95 ou mais.</p>") +
                      "".join(f"<p class='nota'>{_e(x)}</p>" for x in info["qualidade"]["notas"]))
    secoes.append("<h2>Ocorrências da leitura e da limpeza</h2>" + (
        "<table><tr><th>Nível</th><th>O que aconteceu</th><th>Coluna</th></tr>" +
        "".join(f"<tr><td>{_e(o.nivel)}</td><td>{_e(o.mensagem)}</td><td>{_e(o.coluna)}</td></tr>"
                for o in oc if o.nivel in ("ERRO", "AVISO"))[:20000] + "</table>"
        if any(o.nivel in ("ERRO", "AVISO") for o in oc) else "<p>Nenhum erro ou aviso na leitura e na limpeza.</p>"))
    if a is not None and a.resumo:
        leitura = [x for x in a.resumo if not ("Nenhuma coluna de NPS" in x and a.indicadores.empty
                                                 and (logi or vg.get("metricas")))]
        secoes.append("<h2>Leitura do analista</h2><ul>" + "".join(f"<li>{_e(x)}</li>" for x in leitura) + "</ul>")
    secoes.append("<h2>Metodologia</h2><ul><li>Esteira: leitura → limpeza e padronização (registrada) → qualidade "
                  "(DAMA) → análise → modelo estrela → ML opcional → certificado com conferências independentes.</li>"
                  "<li>ML: linha de base, validação cruzada no treino, teste usado uma vez, checagem de vazamento, "
                  "divisão por tempo quando há data.</li><li>NPS = % promotores (9–10) − % detratores (0–6); CSAT = top-2-box; "
                  "CES = % fácil.</li><li>Margem de erro a 95% de confiança.</li><li>Grupos com menos de 30 respostas "
                  "não viram destaque.</li><li>Diferenças entre grupos: teste z com correção de Holm.</li>"
                  "<li>Drivers: correlação e regressão padronizada; não provam causa.</li>"
                  "<li>Logística: no prazo = atraso ≤ 0. Sem informação de pedido completo, não é OTIF.</li>"
                  "<li>Valor/quantidade: soma; demais números: média. Pareto: 20% dos grupos × % do total.</li>"
                  "<li>Tendência: último mês × média dos 3 anteriores (descritivo, não é teste).</li></ul>")
    titulo = f"Relatório — {info['base']}"
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{_e(titulo)}</title><style>
body{{margin:0;background:{COR['fundo']};color:{COR['texto']};font:15px/1.5 "Segoe UI",Arial,sans-serif}}
main{{max-width:1000px;margin:0 auto;padding:24px 16px 48px}}
h1{{color:{COR['primaria']};margin:0 0 4px;font-size:26px}} h2{{color:{COR['primaria']};margin:32px 0 8px;font-size:20px}}
h3{{margin:20px 0 6px;font-size:16px}} .sub{{color:{COR['suave']};margin-bottom:20px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
.card{{background:#fff;border:1px solid {COR['linha']};border-radius:10px;padding:14px 16px}}
.ct{{color:{COR['suave']};font-size:13px}} .cv{{font-size:28px;font-weight:700;color:{COR['primaria']}}}
.cd{{color:{COR['suave']};font-size:12px}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}
th,td{{border-bottom:1px solid {COR['linha']};padding:6px 8px;text-align:left}} th{{background:{COR['fundo']}}}
.nota{{color:{COR['suave']};font-size:12px}} .pos{{color:{COR['bom']}}} .neg{{color:{COR['ruim']}}}
.q0{{color:{COR['ruim']};font-weight:600}} .q1{{color:{COR['bom']};font-weight:600}}
ol li{{margin-bottom:6px}} footer{{margin-top:40px;color:{COR['suave']};font-size:12px}}
</style></head><body><main>
<h1>{_e(titulo)}</h1><div class="sub">Arquivo {_e(info['arquivo'])} · gerado em {info['gerado_em']:%d/%m/%Y %H:%M} pelo
Robô de Planilhas</div><div class="cards">{''.join(cards)}</div>{''.join(secoes)}
<footer>Gerado no seu computador; nenhum dado saiu dele. Números conferíveis em indicadores.xlsx.</footer>
</main></body></html>"""


_ML_NOME = {"acuracia_balanceada": "acurácia balanceada", "mae": "erro médio (MAE)"}
_ML_ROTULO = {"acuracia": "Acurácia (acertos ÷ total)", "acuracia_balanceada": "Acurácia balanceada (média do acerto "
              "de cada classe)", "f1_macro": "F1 macro (equilíbrio entre achar e não alarmar)", "auc": "AUC (ordena "
              "bem quem tem mais chance; 0,5 = sorteio)", "mae": "MAE (erro médio, na unidade do alvo; menor é melhor)",
              "rmse": "RMSE (pune mais os erros grandes; menor é melhor)", "r2": "R² (quanto da variação explica; "
              "0 = igual à média)"}


def _secao_ml(ml: dict) -> str:
    if not ml.get("ok"):
        return (f"<h2>Machine Learning — {_e(ml.get('alvo'))}</h2><p><b>Não treinado:</b> {_e(ml.get('motivo'))}</p>"
                "<p class='nota'>Melhor recusar do que entregar um modelo que não dá para avaliar com honestidade.</p>")
    tipo = "classificação (prever uma categoria)" if ml["tipo"] == "classificacao" else "regressão (prever um número)"
    menor = ml["metrica_principal"] == "mae"
    linhas = "".join(f"<tr><td>{_e(c['modelo'])}{' ✔' if c['modelo'] == ml['escolhido'] else ''}</td>"
                     f"<td>{_n(c['cv_media'], 3) if 'cv_media' in c else '—'}</td>"
                     f"<td>{'±' + _n(c['cv_desvio'], 3) if 'cv_desvio' in c else _e(c.get('erro', ''))}</td></tr>"
                     for c in ml["comparacao"])
    teste = "".join(f"<tr><td>{_e(_ML_ROTULO.get(k, k))}</td><td>{_n(v, 3)}</td><td>{_n(ml['teste_linha_base'].get(k, float('nan')), 3)}</td>"
                    f"<td>{_n(ml['treino'][k], 3) if k in ml['treino'] else '—'}</td></tr>" for k, v in ml["teste"].items())
    imp = [(x["variavel"], x["importancia"], COR["primaria"]) for x in ml["importancias"] if x["importancia"] > 0][:10]
    return (f"<h2>Machine Learning — prever <i>{_e(ml['alvo'])}</i></h2>"
            f"<p class='{'pos' if ml['vale'] else 'neg'}'><b>{_e(ml['veredito'])}</b></p>"
            f"<p class='nota'>Tarefa: {tipo}. {ml['n']} linhas; divisão {_e(ml['divisao'])} "
            f"({ml['n_treino']} treino · {ml['n_teste']} teste). Determinístico (semente 42).</p>"
            + "".join(f"<p class='neg'>⚠️ {_e(x)}</p>" for x in ml["avisos"]) +
            f"<h3>1. Escolha do modelo só com o treino (validação cruzada, {_e(_ML_NOME[ml['metrica_principal']])}"
            f"{', menor é melhor' if menor else ', maior é melhor'})</h3>"
            f"<table><tr><th>Modelo</th><th>Média</th><th>Oscilação</th></tr>{linhas}</table>"
            "<h3>2. Prova final no teste (dados que o modelo nunca viu, usados uma única vez)</h3>"
            f"<table><tr><th>Métrica</th><th>Modelo</th><th>Linha de base</th><th>No treino</th></tr>{teste}</table>"
            + ("<p class='nota'>Com classes desiguais, a acurácia comum da linha de base parece alta só por chutar "
               "sempre a classe mais comum; por isso a decisão usa a acurácia balanceada.</p>"
               if ml["tipo"] == "classificacao" else "")
            + (f"<h3>3. O que mais ajuda a prever (importância por permutação no teste)</h3>{_barras(imp, casas=3)}"
               "<p class='nota'>Quanto a métrica piora quando a coluna é embaralhada. Ajuda a prever ≠ causa.</p>"
               if imp else "")
            + ("<p class='nota'>Fora do modelo: " + _e(", ".join(ml["fora"])) + ".</p>" if ml.get("fora") else "")
            + "<p class='nota'>As previsões do teste estão na aba ml_previsoes_teste do indicadores.xlsx.</p>")


def _secao_estrela(e: dict) -> str:
    tabs = "".join(f"<tr><td>{_e(n)}</td><td>{'fato' if n == e['fato'] else 'dimensão'}</td><td>{len(df)}</td>"
                   f"<td>{_e(', '.join(map(str, df.columns[:8])))}{'…' if len(df.columns) > 8 else ''}</td></tr>"
                   for n, df in e["tabelas"].items())
    rels = "".join(f"<li>{_e(r['de'])} → {_e(r['para'])} ({_e(r['cardinalidade'])}, filtro {_e(r['filtro'])})</li>"
                   for r in e["relacoes"])
    return ("<h2>Modelo pronto para o Power BI (esquema estrela)</h2>"
            "<p class='nota'>Arquivo modelo_powerbi.xlsx (uma aba por tabela) e medidas_dax.txt. Fato = os eventos e "
            "números; dimensões = os filtros. Relacionar sempre da dimensão (1) para a fato (*), filtro em direção "
            "única.</p>"
            f"<table><tr><th>Tabela</th><th>Tipo</th><th>Linhas</th><th>Colunas</th></tr>{tabs}</table>"
            + (f"<h3>Relações a criar (Modelagem &gt; Gerenciar relações)</h3><ul>{rels}</ul>" if rels else ""))


# =============================================================================== entrega
def entregar(cfg, arquivo, destino=None, segmentos: list[str] | None = None, alvo: str | None = None) -> dict:
    """Gera a pasta de entrega. Devolve {ok, pasta, arquivos, recomendacoes, erros}. Nunca altera o arquivo original."""
    from robo import analise, ciencia, esteira_dados, pipeline
    from robo.escrita import _gravar_xlsx
    from robo.relatorio import Relatorio
    caminho = Path(arquivo)
    rel = Relatorio(arquivo=caminho.name)
    t = pipeline._tratar(caminho, cfg, rel)
    base = caminho.stem
    pasta = Path(destino or caminho.parent) / f"Entrega_{base}_{datetime.now():%Y%m%d_%H%M%S}"
    pasta.mkdir(parents=True, exist_ok=True)
    if caminho.exists():  # cópia do original junto da entrega (o arquivo de origem nunca é alterado)
        import shutil
        shutil.copy2(caminho, pasta / f"original_{caminho.name}")
    arquivos = []
    a = drv = logi = qual = estrela = ml = None
    visao: dict = {}
    prio: list[dict] = []
    linhas = 0
    if t.analisaveis:
        nome, df = max(t.analisaveis.items(), key=lambda kv: len(kv[1]))  # a tabela principal
        df = esteira_dados.padronizar_categorias(df, rel, nome)  # 'sudeste ' e 'Sudeste' viram um valor só
        t.analisaveis[nome] = df
        if nome in t.tabelas:
            t.tabelas[nome] = df.reset_index(drop=True)
        linhas = len(df)
        c = {**analise.PADRAO_ANALISE, **(cfg.dados.get("analise") or {})}
        a = analise.Analise(df, nome, caminho.name, base, c, cfg.limpeza.get("padroes_identificador", []),
                            None, segmentos)
        for etapa in (a.fazer_perfil, a.fazer_indicadores, a.fazer_estatistica, a.fazer_resumo):
            try:
                etapa()
            except Exception as e:  # um analista com problema não derruba a entrega: vira observação
                log.exception("Entrega: %s falhou", etapa.__name__)
                a.observacoes.append(f"{etapa.__name__} não concluiu: {type(e).__name__}: {e}")
        nota = a.indicadores_cols.get("nps") or a.indicadores_cols.get("csat")
        if nota:
            drv = ciencia.drivers(a.df, nota)
            prio = prioridades(drv, a.df)
        logi = logistica(a.df, int(c["base_minima"]))
        visao = visao_geral(a)
        try:
            qual = esteira_dados.qualidade(a.df, a.papeis, rel)
        except Exception as e:  # noqa: BLE001 — etapa que falha vira observação, não derruba a entrega
            log.exception("Entrega: qualidade falhou")
            a.observacoes.append(f"qualidade não concluiu: {type(e).__name__}: {e}")
        try:
            estrela = esteira_dados.modelo_estrela(a.df, a.papeis, nome, rel, visao.get("metricas"))
            _gravar_xlsx(estrela["tabelas"], pasta / "modelo_powerbi.xlsx")
            (pasta / "medidas_dax.txt").write_text(estrela["dax"], encoding="utf-8")
            arquivos += ["modelo_powerbi.xlsx", "medidas_dax.txt"]
        except Exception as e:  # noqa: BLE001
            log.exception("Entrega: modelo estrela falhou")
            a.observacoes.append(f"modelo para o Power BI não concluiu: {type(e).__name__}: {e}")
        if alvo:
            try:
                ml = esteira_dados.aprender(a.df, a.papeis, alvo)
            except Exception as e:  # noqa: BLE001
                log.exception("Entrega: ML falhou")
                ml = {"ok": False, "alvo": alvo, "motivo": f"erro inesperado: {type(e).__name__}: {e}"}
        if t.tabelas:
            _gravar_xlsx({k: v for k, v in t.tabelas.items()}, pasta / "base_tratada.xlsx")
            arquivos.append("base_tratada.xlsx")
        planilhas = {"qualidade": rel.para_dataframe()}
        for nome_aba, df_aba in (("indicadores", a.indicadores), ("destaques", a.destaques), ("perfil", a.perfil),
                                 ("relacoes", a.relacoes)):
            if not df_aba.empty:
                planilhas[nome_aba] = df_aba
        if drv and drv.get("ok"):
            planilhas["drivers"] = pd.DataFrame(prio or drv["drivers"])
        for blo in visao.get("por_segmento", []):
            planilhas[f"por_{blo['segmento']}"[:31]] = pd.DataFrame(blo["linhas"])
        if visao.get("por_mes"):
            planilhas["por_mes"] = pd.DataFrame(visao["por_mes"]["linhas"], columns=["mes", "valor"])
        if logi:
            planilhas["logistica_geral"] = pd.DataFrame([logi["geral"]])
            for papel, g in logi["grupos"].items():
                planilhas[f"logistica_{papel}"] = pd.DataFrame(g["linhas"])
        if qual:
            planilhas["qualidade_dama"] = qual["colunas"]
        if estrela:
            planilhas["powerbi_relacoes"] = pd.DataFrame(estrela["relacoes"] or [{"de": "(sem dimensões)"}])
        if ml and ml.get("ok"):
            planilhas["ml_comparacao"] = pd.DataFrame(ml["comparacao"])
            planilhas["ml_importancia"] = pd.DataFrame(ml["importancias"])
            planilhas["ml_previsoes_teste"] = ml["previsoes"]
        _gravar_xlsx(planilhas, pasta / "indicadores.xlsx")
        arquivos.append("indicadores.xlsx")
    rec = recomendacoes(a, prio, logi, rel, visao)
    if qual and qual["tabela"]["criticas"]:
        rec.append(f"**Qualidade:** {len(qual['tabela']['criticas'])} coluna(s) em situação crítica "
                   f"({', '.join(map(str, qual['tabela']['criticas'][:5]))}): corrija na origem antes de usar em decisão.")
    if ml:
        rec.append(f"**Machine Learning ({ml.get('alvo')}):** " + (ml["veredito"] if ml.get("ok") else
                                                                   f"não treinado — {ml.get('motivo')}"))
    try:
        conferencias = certificar(t, rel, a, pasta) + (estrela["conferencias"] if estrela else [])
    except Exception as e:  # conferir nunca impede a entrega, mas a falha aparece no certificado
        log.exception("Entrega: certificado falhou")
        conferencias = [{"conferencia": "Certificado", "ok": False, "detalhe": f"{type(e).__name__}: {e}"}]
    info = {"analise": a, "relatorio": rel, "logistica": logi, "prioridades": prio, "visao": visao,
            "conferencias": conferencias, "qualidade": qual, "estrela": estrela, "ml": ml,
            "drivers": drv if drv and drv.get("ok") else None, "recomendacoes": rec, "base": base,
            "arquivo": caminho.name, "linhas": linhas, "gerado_em": datetime.now()}
    (pasta / "relatorio.html").write_text(montar_html(info), encoding="utf-8")
    arquivos.append("relatorio.html")
    extra = {"linhas": linhas, "recomendacoes": rec, "erros": [o.mensagem for o in rel.erros]}
    if qual:
        extra["qualidade"] = qual["tabela"]
    if ml:
        extra["ml"] = {k: v for k, v in ml.items() if k not in ("previsoes",)}
    gravar_manifesto(pasta, caminho, conferencias, extra)
    arquivos.append("manifesto.json")
    return {"ok": bool(t.analisaveis), "pasta": str(pasta), "arquivos": arquivos, "recomendacoes": rec,
            "erros": [o.mensagem for o in rel.erros], "linhas": linhas, "conferencias": conferencias,
            "qualidade": qual["tabela"] if qual else None,
            "ml": {k: v for k, v in ml.items() if k not in ("previsoes",)} if ml else None}
