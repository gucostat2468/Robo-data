"""2º ANDAR — Análise e Qualidade.

Depois que uma planilha é APROVADA e publicada, cinco analistas trabalham sobre ela:

  Bia   · Perfil         o que tem em cada coluna (tipo, preenchimento, distribuição)
  Caio  · Indicadores    NPS / CSAT / CES com margem de erro, no geral e por segmento
  Davi  · Estatística    o que é diferença REAL (teste de significância com correção de Holm) e relações
  Eva   · Monitoramento  o que mudou em relação às cargas anteriores da mesma base
  Fábio · Relator        resumo executivo em linguagem simples

Princípios (o objetivo é ser CERTO, não sofisticado):
- Regras estatísticas clássicas e explicáveis; nada de caixa-preta.
- Base pequena nunca vira conclusão: grupos abaixo da base mínima são sinalizados e não entram em destaques.
- Muitas comparações geram falsos positivos: a correção de Holm controla isso.
- A análise NUNCA reprova nem atrasa a publicação: falhas viram observações no relatório.

Saídas: Bases-Relatorios/<base>_analise.xlsx, logs/analises/<id>.json (painel) e, com o PostgreSQL ligado,
tabelas no schema "analise" (prontas para o Power BI acompanhar a evolução entre ondas).
"""

from __future__ import annotations

import fnmatch
import json
import logging
import math
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from robo.limpeza import normalizar_nome_coluna, sem_acento

log = logging.getLogger("robo")

ANALISTAS = [
    {"id": "perfil", "nome": "Bia", "papel": "Perfil dos dados", "cor": "#EC4899",
     "descricao": "Descreve cada coluna: tipo, preenchimento, valores mais comuns, média, mediana e dispersão. "
                  "É o raio-X que evita conclusões sobre colunas vazias ou mal preenchidas."},
    {"id": "indicadores", "nome": "Caio", "papel": "Indicadores (NPS, CSAT, CES)", "cor": "#F59E0B",
     "descricao": "Reconhece colunas de NPS, CSAT e CES e calcula o indicador com margem de erro de 95%, "
                  "no geral e por segmento (curso, canal, UF...)."},
    {"id": "estatistica", "nome": "Davi", "papel": "Estatística", "cor": "#6366F1",
     "descricao": "Separa diferença real de acaso: testa cada segmento contra o restante com correção de Holm "
                  "e aponta relações entre variáveis numéricas (correlação, não causa)."},
    {"id": "monitoramento", "nome": "Eva", "papel": "Monitoramento", "cor": "#10B981",
     "descricao": "Compara esta carga com as anteriores da mesma base: volume, colunas novas ou sumidas, aumento de "
                  "vazios, médias que mudaram muito, categorias inéditas e variação dos indicadores."},
    {"id": "relator", "nome": "Fábio", "papel": "Relator", "cor": "#0EA5E9",
     "descricao": "Escreve o resumo executivo em linguagem simples: base, indicadores, destaques confiáveis, "
                  "alertas e cuidados de leitura."},
]

PADRAO_ANALISE = {
    "habilitado": True,
    "base_minima": 30,          # grupos menores não viram destaque
    "confianca": 0.95,
    "max_categorias": 30,       # acima disso a coluna não é tratada como segmento
    "max_segmentos": 10,        # quantas colunas de segmento analisar no máximo
    "variacao_alerta_pct": 30,  # mudança de média/volume que gera alerta no monitoramento
    "analistas_desligados": [],
}

MESES = {"janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"}


# =============================================================================== utilitários estatísticos
def _z_critico(confianca: float) -> float:
    return {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}.get(round(confianca, 2), 1.96)


def _p_valor(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2)) if np.isfinite(z) else 1.0


def holm(p_valores: list[float], alfa: float) -> list[bool]:
    """Correção de Holm-Bonferroni: controla o risco de 'achar' diferenças por acaso em muitas comparações."""
    ordem = sorted(range(len(p_valores)), key=lambda i: p_valores[i])
    m = len(p_valores)
    significativo = [False] * m
    for k, i in enumerate(ordem):
        if p_valores[i] <= alfa / (m - k):
            significativo[i] = True
        else:
            break
    return significativo


def _r(v, casas=1):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), casas)


# =============================================================================== papéis das colunas
def papel_coluna(serie: pd.Series, nome: str, max_categorias: int, padroes_id: list[str]) -> str:
    if nome.startswith("_"):
        return "auditoria"
    valores = serie.dropna()
    if valores.empty:
        return "vazia"
    if any(fnmatch.fnmatch(nome, p) for p in padroes_id):
        return "id"
    if pd.api.types.is_datetime64_any_dtype(serie):
        return "data"
    if pd.api.types.is_bool_dtype(serie):
        return "categoria"
    distintos = valores.nunique()
    if pd.api.types.is_numeric_dtype(serie):
        inteiros = (valores == valores.round()).all()
        if inteiros and distintos == len(valores) and len(valores) > 20:
            return "id"
        return "numero"
    textos = valores.astype(str)
    if distintos == len(valores) and len(valores) > 20 and textos.str.len().mean() < 25:
        return "id"
    if textos.str.len().mean() > 30 or (distintos > max_categorias and textos.str.contains(" ").mean() > 0.5):
        return "texto_livre"
    if distintos <= max_categorias:
        return "categoria"
    return "texto"


def _escala(valores: pd.Series) -> tuple[float, float]:
    return float(valores.min()), float(valores.max())


def detectar_indicadores(df: pd.DataFrame, papeis: dict, forcados: dict) -> dict:
    """Reconhece colunas de NPS (0-10), CSAT (1-5/7/10) e CES (1-5/7) pelo nome e pela faixa de valores."""
    achados = {}
    regras = {
        "nps": (r"(^|_)(nps|recomend|indicaria|likelihood)", lambda mn, mx: mn >= 0 and mx <= 10),
        "csat": (r"(^|_)(csat|satisf)", lambda mn, mx: mn >= 1 and mx <= 10),
        "ces": (r"(^|_)(ces|esforco|facilidade|effort)", lambda mn, mx: mn >= 1 and mx <= 7),
    }
    for tipo, (padrao, faixa_ok) in regras.items():
        coluna = forcados.get(tipo)
        if coluna:
            coluna = normalizar_nome_coluna(coluna)
            if coluna in df.columns and pd.api.types.is_numeric_dtype(df[coluna]):
                achados[tipo] = coluna
            continue
        for col in df.columns:
            if papeis.get(col) != "numero" or col in achados.values():
                continue
            if re.search(padrao, sem_acento(col)):
                v = df[col].dropna()
                # a grande maioria (≥ 80%) inteiros dentro da escala: códigos como 99 = 'não sabe' existem em pesquisa
                # de verdade e saem da conta (mesma regra da calculadora; antes um único 99 escondia o NPS inteiro —
                # achado do treino contínuo, competência "NPS com a base certa", nível 3)
                inteiros = v[v == v.round()]
                dentro = inteiros[[faixa_ok(x, x) for x in inteiros]] if len(inteiros) else inteiros
                if len(v) and len(dentro) / len(v) >= 0.8 and faixa_ok(*_escala(dentro)):
                    achados[tipo] = col
                    break
    return achados


# escalas escritas por extenso → nota de 1 a 5 (5 = melhor). Comparação sem acento e sem maiúsculas.
ESCALAS_TEXTO = [
    ("csat", {"muito satisfeito": 5, "totalmente satisfeito": 5, "extremamente satisfeito": 5, "satisfeito": 4,
              "nem satisfeito nem insatisfeito": 3, "neutro": 3, "indiferente": 3, "insatisfeito": 2,
              "muito insatisfeito": 1, "totalmente insatisfeito": 1, "extremamente insatisfeito": 1}),
    ("csat", {"otimo": 5, "excelente": 5, "muito bom": 5, "bom": 4, "regular": 3, "razoavel": 3, "ruim": 2,
              "pessimo": 1, "muito ruim": 1}),
    ("ces", {"muito facil": 5, "extremamente facil": 5, "facil": 4, "nem facil nem dificil": 3, "neutro": 3,
             "dificil": 2, "muito dificil": 1, "extremamente dificil": 1}),
]


def converter_escalas(df: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
    """Colunas de texto que são uma escala conhecida (≥ 90% dos valores, ≥ 3 níveis diferentes) ganham uma
    coluna numérica '<coluna>_nota' (1 a 5). Devolve (tabela, {tipo: coluna_nota}, {coluna_nota: coluna_texto})."""
    novas, origem, tipos = {}, {}, {}
    for col in df.columns:
        serie = df[col]
        if pd.api.types.is_numeric_dtype(serie) or pd.api.types.is_datetime64_any_dtype(serie) or str(col).startswith("_"):
            continue
        valores = serie.dropna().astype(str).map(lambda x: re.sub(r"\s+", " ", sem_acento(x).lower().strip(" .!")))
        if len(valores) < 5:
            continue
        for tipo, mapa in ESCALAS_TEXTO:
            convertidos = valores.map(mapa)
            if convertidos.notna().mean() >= 0.9 and convertidos.nunique() >= 3:
                nome = f"{col}_nota"
                novas[nome] = pd.Series(convertidos, index=valores.index).reindex(df.index).astype("Int64")
                origem[nome] = col
                tipos.setdefault(tipo, nome)
                break
    if not novas:
        return df, {}, {}
    return df.assign(**novas), tipos, origem


# =============================================================================== indicadores
def calcular_indicador(tipo: str, serie: pd.Series, z: float, escala: int | None = None) -> dict | None:
    """escala: a da coluna INTEIRA (ou da regra). Sem ela, deduz desta série — só serve para a coluna inteira."""
    v = serie.dropna().astype(float)
    n = len(v)
    if n == 0:
        return None
    if tipo == "nps":
        from robo.calculos import notas_nps
        v, _ = notas_nps(v)  # só inteiros de 0 a 10 (99 = 'não sabe' fica fora), igual em todo o robô
        n = len(v)
        if n == 0:
            return None
        p, d = (v >= 9).mean(), (v <= 6).mean()
        var = p + d - (p - d) ** 2
        return {"indicador": "NPS", "n": n, "valor": 100 * (p - d), "margem": 100 * z * math.sqrt(var / n),
                "variancia": var, "pct_promotores": 100 * p, "pct_neutros": 100 * (1 - p - d), "pct_detratores": 100 * d,
                "media": v.mean()}
    if escala is None:
        escala = 5 if v.max() <= 5 else 7 if v.max() <= 7 else 10
    v = v[v <= escala]  # nota acima da escala (ex.: 99 = 'não sabe') não conta como satisfeito
    n = len(v)
    if n == 0:
        return None
    corte = escala - 1 if tipo == "csat" else (escala - 2 if escala >= 7 else escala - 1)
    p = (v >= corte).mean()
    var = p * (1 - p)
    nome = "CSAT (top-2-box)" if tipo == "csat" else "CES (% fácil)"
    return {"indicador": nome, "n": n, "valor": 100 * p, "margem": 100 * z * math.sqrt(var / n), "variancia": var,
            "media": v.mean(), "escala": f"1 a {escala}"}


# =============================================================================== analistas
class Analise:
    def __init__(self, df: pd.DataFrame, tabela: str, arquivo: str, base: str, cfg_analise: dict, padroes_id: list[str],
                 forcados: dict | None = None, segmentos_forcados: list[str] | None = None):
        df, escalas, self.origem_escalas = converter_escalas(df)
        self.df, self.tabela, self.arquivo, self.base = df, tabela, arquivo, base
        self.c = {**PADRAO_ANALISE, **(cfg_analise or {})}
        self.z = _z_critico(float(self.c["confianca"]))
        self.papeis = {col: papel_coluna(df[col], col, int(self.c["max_categorias"]), padroes_id) for col in df.columns}
        self.indicadores_cols = detectar_indicadores(df, self.papeis, forcados or {})
        for tipo, col in escalas.items():
            self.indicadores_cols.setdefault(tipo, col)
        if segmentos_forcados:
            self.segmentos = [normalizar_nome_coluna(s) for s in segmentos_forcados if normalizar_nome_coluna(s) in df.columns]
        else:
            usadas = set(self.indicadores_cols.values()) | set(self.origem_escalas.values()) | set(self.origem_escalas)
            self.segmentos = [c for c, p in self.papeis.items() if p == "categoria" and 2 <= df[c].nunique() and
                              c not in usadas][: int(self.c["max_segmentos"])]
        if self.origem_escalas:
            self.observacoes_iniciais = [f"Escala escrita '{o}' convertida em nota de 1 a 5 ('{n}')"
                                         for n, o in self.origem_escalas.items()]
        self.observacoes: list[str] = list(getattr(self, "observacoes_iniciais", []))
        self.perfil = pd.DataFrame()
        self.indicadores = pd.DataFrame()
        self.destaques = pd.DataFrame()
        self.relacoes = pd.DataFrame()
        self.alertas = pd.DataFrame()
        self.resumo: list[str] = []
        self.foto: dict = {}

    # ---------------------------------------------------------------- Bia · Perfil
    def fazer_perfil(self):
        linhas = []
        n = len(self.df)
        for col in self.df.columns:
            s = self.df[col]
            v = s.dropna()
            item = {"coluna": col, "papel": self.papeis[col], "linhas": n, "preenchidos": len(v),
                    "pct_preenchido": _r(100 * len(v) / n if n else 0), "distintos": int(v.nunique())}
            if self.papeis[col] == "numero" and len(v):
                x = v.astype(float)
                item.update({"media": _r(x.mean(), 2), "mediana": _r(x.median(), 2), "desvio": _r(x.std(), 2),
                             "minimo": _r(x.min(), 2), "p25": _r(x.quantile(.25), 2), "p75": _r(x.quantile(.75), 2),
                             "maximo": _r(x.max(), 2)})
            elif self.papeis[col] == "data" and len(v):
                item.update({"minimo": v.min().strftime("%d/%m/%Y"), "maximo": v.max().strftime("%d/%m/%Y")})
            if self.papeis[col] in ("categoria", "texto") and len(v):
                top = v.astype(str).value_counts().head(5)
                item["mais_comuns"] = "; ".join(f"{k} ({100 * q / len(v):.0f}%)" for k, q in top.items())
            linhas.append(item)
        self.perfil = pd.DataFrame(linhas)

    def _escala(self, tipo: str, col: str) -> int | None:
        """Escala do CSAT/CES decidida uma vez pela coluna inteira (ou pela regra), igual para todos os segmentos."""
        if tipo == "nps":
            return None
        from robo.calculos import escala_csat
        return escala_csat(self.df[col], self.c.get("escala_csat") if tipo == "csat" else None)[0]

    # ---------------------------------------------------------------- Caio · Indicadores
    def fazer_indicadores(self):
        linhas = []
        minimo = int(self.c["base_minima"])
        for tipo, col in self.indicadores_cols.items():
            geral = calcular_indicador(tipo, self.df[col], self.z, self._escala(tipo, col))
            if not geral:
                continue
            linhas.append({"indicador": geral["indicador"], "coluna": col, "segmento_coluna": "(geral)", "segmento": "Total",
                           **{k: _r(v, 1) if isinstance(v, float) else v for k, v in geral.items() if k not in ("indicador", "variancia")},
                           "base_pequena": geral["n"] < minimo})
            for seg in self.segmentos:
                for grupo, sub in self.df.groupby(seg, dropna=True, observed=True):
                    r = calcular_indicador(tipo, sub[col], self.z, self._escala(tipo, col))
                    if r:
                        linhas.append({"indicador": r["indicador"], "coluna": col, "segmento_coluna": seg, "segmento": str(grupo),
                                       **{k: _r(v, 1) if isinstance(v, float) else v for k, v in r.items()
                                          if k not in ("indicador", "variancia")},
                                       "base_pequena": r["n"] < minimo})
        if not self.indicadores_cols:
            self.observacoes.append("Nenhuma coluna de NPS, CSAT ou CES reconhecida (dica: nomes como nota_nps, csat, ces).")
        self.indicadores = pd.DataFrame(linhas)

    # ---------------------------------------------------------------- Davi · Estatística
    def fazer_estatistica(self):
        minimo = int(self.c["base_minima"])
        candidatos = []
        alvos = [(t, c) for t, c in self.indicadores_cols.items()]
        if not alvos:  # sem indicador: compara as médias das variáveis numéricas
            alvos = [("media", c) for c, p in self.papeis.items() if p == "numero"][:6]
        for tipo, col in alvos:
            for seg in self.segmentos:
                if self.df[seg].nunique() < 2:
                    continue
                for grupo in self.df[seg].dropna().unique():
                    dentro = self.df.loc[self.df[seg] == grupo, col].dropna().astype(float)
                    fora = self.df.loc[(self.df[seg] != grupo) & self.df[seg].notna(), col].dropna().astype(float)
                    if len(dentro) < minimo or len(fora) < minimo:
                        continue
                    if tipo == "media":
                        a, b = dentro.mean(), fora.mean()
                        ep = math.sqrt(dentro.var() / len(dentro) + fora.var() / len(fora))
                        nome = f"Média de {col}"
                    else:
                        esc = self._escala(tipo, col)
                        ra, rb = calcular_indicador(tipo, dentro, self.z, esc), calcular_indicador(tipo, fora, self.z, esc)
                        a, b = ra["valor"], rb["valor"]
                        ep = 100 * math.sqrt(ra["variancia"] / ra["n"] + rb["variancia"] / rb["n"])
                        nome = ra["indicador"]
                    if not ep:
                        continue
                    z = (a - b) / ep
                    candidatos.append({"medida": nome, "segmento_coluna": seg, "segmento": str(grupo), "n_grupo": len(dentro),
                                       "valor_grupo": _r(a, 2), "valor_restante": _r(b, 2), "diferenca": _r(a - b, 2),
                                       "z": _r(z, 2), "p_valor": _p_valor(z)})
        if candidatos:
            sig = holm([c["p_valor"] for c in candidatos], 1 - float(self.c["confianca"]))
            for c, s in zip(candidatos, sig):
                c["significativo"] = s
                c["leitura"] = (("ACIMA" if c["diferenca"] > 0 else "ABAIXO") + " do restante — diferença real") if s \
                    else "dentro do esperado pelo acaso"
                c["p_valor"] = round(c["p_valor"], 4)
            self.destaques = pd.DataFrame(candidatos).sort_values(["significativo", "z"], ascending=[False, False],
                                                                  key=lambda s: s.abs() if s.name == "z" else s)

        numericas = [c for c, p in self.papeis.items() if p == "numero"]
        relacoes = []
        for i, a in enumerate(numericas):
            for b in numericas[i + 1:]:
                par = self.df[[a, b]].dropna().astype(float)
                if len(par) < minimo or par[a].std() == 0 or par[b].std() == 0:
                    continue
                r = par[a].corr(par[b])
                if abs(r) >= 0.3:
                    forca = "forte" if abs(r) >= 0.7 else "moderada" if abs(r) >= 0.5 else "fraca a moderada"
                    eh_driver = a in self.indicadores_cols.values() or b in self.indicadores_cols.values()
                    relacoes.append({"variavel_a": a, "variavel_b": b, "n": len(par), "correlacao": _r(r, 2),
                                     "forca": forca, "sentido": "mesma direção" if r > 0 else "direções opostas",
                                     "envolve_indicador": eh_driver})
        if relacoes:
            self.relacoes = pd.DataFrame(relacoes).sort_values("correlacao", key=lambda s: s.abs(), ascending=False)

    # ---------------------------------------------------------------- Eva · Monitoramento
    def tirar_foto(self) -> dict:
        foto = {"data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "arquivo": self.arquivo, "linhas": len(self.df),
                "colunas": {}, "indicadores": {}}
        for col in self.df.columns:
            if self.papeis[col] == "auditoria":
                continue
            s = self.df[col]
            item = {"papel": self.papeis[col], "pct_vazio": round(100 * s.isna().mean(), 2) if len(s) else 0}
            if self.papeis[col] == "numero" and s.notna().any():
                item.update({"media": float(s.astype(float).mean()), "desvio": float(s.astype(float).std() or 0)})
            if self.papeis[col] == "categoria":
                item["categorias"] = sorted(map(str, s.dropna().unique()))[:200]
            foto["colunas"][col] = item
        for tipo, col in self.indicadores_cols.items():
            r = calcular_indicador(tipo, self.df[col], self.z, self._escala(tipo, col))
            if r:
                foto["indicadores"][tipo] = {"valor": r["valor"], "variancia": r["variancia"], "n": r["n"], "nome": r["indicador"]}
        self.foto = foto
        return foto

    def fazer_monitoramento(self, anteriores: list[dict]):
        atual = self.foto or self.tirar_foto()
        alertas = []
        if not anteriores:
            self.observacoes.append("Primeira carga desta base: o monitoramento passa a comparar a partir da próxima.")
            self.alertas = pd.DataFrame(columns=["nivel", "tipo", "coluna", "mensagem"])
            return
        ultima = anteriores[-1]
        limite = float(self.c["variacao_alerta_pct"])

        def add(nivel, tipo, coluna, mensagem):
            alertas.append({"nivel": nivel, "tipo": tipo, "coluna": coluna, "mensagem": mensagem})

        if ultima["linhas"]:
            var = 100 * (atual["linhas"] - ultima["linhas"]) / ultima["linhas"]
            if abs(var) >= limite:
                add("atenção", "volume", "", f"Volume mudou {var:+.0f}% ({ultima['linhas']} → {atual['linhas']} linhas) "
                                              f"em relação a {ultima['arquivo']}")
        cols_ant, cols_at = set(ultima["colunas"]), set(atual["colunas"])
        for c in sorted(cols_ant - cols_at):
            add("atenção", "coluna sumiu", c, "Coluna existia na carga anterior e não veio agora (mudança de layout?)")
        for c in sorted(cols_at - cols_ant):
            add("informativo", "coluna nova", c, "Coluna nova em relação à carga anterior")
        vistas = {}
        for foto in anteriores:
            for c, item in foto["colunas"].items():
                vistas.setdefault(c, set()).update(item.get("categorias", []))
        for c in sorted(cols_at & cols_ant):
            a, u = atual["colunas"][c], ultima["colunas"][c]
            if a["pct_vazio"] - u["pct_vazio"] >= 10:
                add("atenção", "mais vazios", c, f"Vazios subiram de {u['pct_vazio']:.0f}% para {a['pct_vazio']:.0f}%")
            if "media" in a and "media" in u and u["media"]:
                var = 100 * (a["media"] - u["media"]) / abs(u["media"])
                if abs(var) >= limite:
                    add("atenção", "média mudou", c, f"Média mudou {var:+.0f}% ({u['media']:.2f} → {a['media']:.2f})")
            novas = sorted(set(a.get("categorias", [])) - vistas.get(c, set()))
            if novas and vistas.get(c):
                amostra = ", ".join(novas[:6]) + ("…" if len(novas) > 6 else "")
                add("informativo", "categoria inédita", c, f"{len(novas)} valor(es) nunca vistos: {amostra} (novo ou erro de digitação?)")
        for tipo, ind in atual["indicadores"].items():
            ant = ultima.get("indicadores", {}).get(tipo)
            if not ant:
                continue
            dif = ind["valor"] - ant["valor"]
            ep = 100 * math.sqrt(ind["variancia"] / ind["n"] + ant["variancia"] / ant["n"]) if ind["n"] and ant["n"] else 0
            sig = ep and abs(dif / ep) >= self.z
            add("atenção" if sig else "informativo", "indicador", ind["nome"],
                f"{ind['nome']}: {ant['valor']:.1f} → {ind['valor']:.1f} ({dif:+.1f} pts) — "
                + ("mudança significativa" if sig else "variação dentro da margem de erro (não é mudança real)"))
        self.alertas = pd.DataFrame(alertas, columns=["nivel", "tipo", "coluna", "mensagem"])

    # ---------------------------------------------------------------- Fábio · Relator
    def fazer_resumo(self):
        n = len(self.df)
        linhas = [f"Base “{self.base}” — arquivo {self.arquivo}: {n:,} registros e "
                  f"{sum(1 for p in self.papeis.values() if p != 'auditoria')} colunas.".replace(",", ".")]
        datas = [c for c, p in self.papeis.items() if p == "data"]
        if datas:
            d = self.df[datas[0]].dropna()
            if len(d):
                linhas.append(f"Período ({datas[0]}): {d.min():%d/%m/%Y} a {d.max():%d/%m/%Y}.")
        if not self.indicadores.empty:
            for _, r in self.indicadores[self.indicadores["segmento"] == "Total"].iterrows():
                casas = 0 if r["indicador"] == "NPS" else 1  # NPS sem casas decimais (padrão da casa)
                txt = f"{r['indicador']}: {r['valor']:.{casas}f} (margem ±{r['margem']:.{casas}f} pts; n={int(r['n'])})"
                if r["indicador"] == "NPS":
                    txt += f" — {r['pct_promotores']:.0f}% promotores e {r['pct_detratores']:.0f}% detratores"
                linhas.append(txt + ".")
        if not self.destaques.empty:
            sig = self.destaques[self.destaques["significativo"]]
            if len(sig):
                linhas.append(f"Diferenças reais (significativas a {100 * float(self.c['confianca']):.0f}% com correção de Holm):")
                for _, r in sig.head(6).iterrows():
                    linhas.append(f"  • {r['segmento_coluna']} = {r['segmento']}: {r['medida']} {r['valor_grupo']} vs "
                                  f"{r['valor_restante']} no restante ({r['diferenca']:+} ; n={r['n_grupo']}).")
            else:
                linhas.append("Nenhuma diferença entre segmentos é estatisticamente confiável nesta base — "
                              "evite comunicar ranking entre grupos.")
        if not self.relacoes.empty:
            for _, r in self.relacoes.head(3).iterrows():
                linhas.append(f"Relação {r['forca']} entre {r['variavel_a']} e {r['variavel_b']} (r={r['correlacao']}; "
                              f"{r['sentido']}). Correlação não prova causa.")
        if not self.alertas.empty:
            att = self.alertas[self.alertas["nivel"] == "atenção"]
            linhas.append(f"Monitoramento: {len(att)} alerta(s) de atenção e {len(self.alertas) - len(att)} informativo(s).")
            for _, r in att.head(4).iterrows():
                linhas.append(f"  • {r['mensagem']}" + (f" [{r['coluna']}]" if r["coluna"] else ""))
        if not self.perfil.empty:
            ruins = self.perfil[(self.perfil["pct_preenchido"] < 80) & (~self.perfil["papel"].isin(["auditoria", "vazia"]))]
            if len(ruins):
                linhas.append(f"Qualidade: {len(ruins)} coluna(s) com menos de 80% de preenchimento "
                              f"({', '.join(ruins['coluna'].head(5))}) — não sustente conclusões só nelas.")
        if not self.indicadores.empty:
            pequenos = int(self.indicadores["base_pequena"].sum())
            if pequenos:
                linhas.append(f"Cuidado: {pequenos} grupo(s) com menos de {self.c['base_minima']} respostas — "
                              "mostre no Power BI com aviso de base pequena.")
        linhas += [f"Observação: {o}" for o in self.observacoes]
        self.resumo = linhas


# =============================================================================== orquestração
def chave_base(arquivo: str, regra: dict) -> str:
    """Agrupa ondas da mesma base: nps_setembro.xlsx e nps_outubro.xlsx viram 'nps'."""
    destino = (regra or {}).get("destino") or {}
    if destino.get("tabela"):
        return normalizar_nome_coluna(destino["tabela"])
    # o nome do arquivo sem mês/ano/versão já agrupa as ondas (nps_setembro, nps_outubro → nps). Usar o padrão da
    # regra ('nps_*' → 'nps') juntava pesquisas DIFERENTES (alunos e professores) e escondia a mais antiga.
    partes = [p for p in normalizar_nome_coluna(Path(arquivo).stem).split("_")
              if p and not p.isdigit() and p not in MESES and not re.fullmatch(r"v\d+|\d{4}|t\d|s\d", p)]
    return "_".join(partes) or normalizar_nome_coluna(Path(arquivo).stem)


def _historico_fotos(pasta: Path, base: str) -> list[dict]:
    arq = pasta / f"historico_{base}.json"
    if not arq.exists():
        return []
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _guardar_foto(pasta: Path, base: str, foto: dict):
    fotos = (_historico_fotos(pasta, base) + [foto])[-24:]
    (pasta / f"historico_{base}.json").write_text(json.dumps(fotos, ensure_ascii=False, default=str), encoding="utf-8")


def analisar(tabelas: dict[str, pd.DataFrame], arquivo: str, id_execucao: str, cfg, regra: dict, ao_etapa=None) -> dict | None:
    """Roda os 5 analistas. Devolve um resumo para o painel. Nunca levanta exceção."""
    c = {**PADRAO_ANALISE, **(cfg.dados.get("analise") or {}), **((regra or {}).get("analise") or {}),
         "escala_csat": (regra or {}).get("escala_csat")}
    if not c.get("habilitado", True) or c.get("desligar"):
        return None
    desligados = set(c.get("analistas_desligados") or [])
    base = chave_base(arquivo, regra)
    pasta_hist = cfg.logs / "analises"
    pasta_hist.mkdir(parents=True, exist_ok=True)

    def sinal(etapa):
        if ao_etapa:
            try:
                ao_etapa(f"analise:{etapa}", arquivo)
            except Exception:
                pass

    resultados = []
    for nome_tab, df in tabelas.items():
        if df.empty:
            continue
        a = Analise(df, nome_tab, arquivo, base if len(tabelas) == 1 else f"{base}_{nome_tab}", c,
                    cfg.limpeza.get("padroes_identificador", []), c.get("indicadores"), c.get("segmentos"))
        etapas = [("perfil", a.fazer_perfil), ("indicadores", a.fazer_indicadores), ("estatistica", a.fazer_estatistica),
                  ("monitoramento", lambda: a.fazer_monitoramento(_historico_fotos(pasta_hist, a.base))),
                  ("relator", a.fazer_resumo)]
        for etapa, funcao in etapas:
            if etapa in desligados:
                continue
            sinal(etapa)
            try:
                funcao()
            except Exception as e:  # um analista com problema não derruba os outros nem a publicação
                log.exception("Analista %s falhou em %s", etapa, arquivo)
                a.observacoes.append(f"O analista de {etapa} não conseguiu concluir: {type(e).__name__}: {e}")
        try:
            _guardar_foto(pasta_hist, a.base, a.foto or a.tirar_foto())
        except Exception:
            log.exception("Não consegui guardar o histórico de monitoramento")
        resultados.append(a)

    if not resultados:
        return None
    saidas = _gravar(resultados, cfg, id_execucao)
    registros = lambda attr: [x for a in resultados if not getattr(a, attr).empty for x in getattr(a, attr).to_dict("records")]
    return {"base": base, "arquivo": arquivo, "resumo": [l for a in resultados for l in a.resumo],
            "_indicadores": registros("indicadores"), "_destaques": registros("destaques"), **saidas}


def _gravar(resultados: list[Analise], cfg, id_execucao: str) -> dict:
    from robo.escrita import _gravar_xlsx
    principal = resultados[0]
    planilhas = {"resumo": pd.DataFrame({"resumo_executivo": [l for a in resultados for l in a.resumo]})}
    for nome, attr in (("perfil", "perfil"), ("indicadores", "indicadores"), ("destaques", "destaques"),
                       ("relacoes", "relacoes"), ("alertas", "alertas")):
        partes = [getattr(a, attr).assign(tabela=a.tabela) for a in resultados if not getattr(a, attr).empty]
        if partes:
            planilhas[nome] = pd.concat(partes, ignore_index=True)
    destino = None
    try:
        cfg.relatorios.mkdir(parents=True, exist_ok=True)
        destino = cfg.relatorios / f"{principal.base}_analise.xlsx"
        _gravar_xlsx(planilhas, destino)
    except PermissionError:
        log.warning("%s está aberto no Excel; a análise ficou só no painel e no banco.", destino.name)
        destino = None
    detalhe = {"id": id_execucao, "arquivo": principal.arquivo, "base": principal.base,
               "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "relatorio": str(destino) if destino else None,
               "papeis": principal.papeis, "indicadores_detectados": principal.indicadores_cols,
               "segmentos": principal.segmentos,
               **{nome: json.loads(df.head(300).to_json(orient="records", force_ascii=False, date_format="iso"))
                  for nome, df in planilhas.items()}}
    (cfg.logs / "analises" / f"{id_execucao}.json").write_text(json.dumps(detalhe, ensure_ascii=False, default=str),
                                                                encoding="utf-8")
    if cfg.banco.get("habilitado"):
        try:
            _gravar_banco(cfg, id_execucao, principal, planilhas)
        except Exception as e:
            log.warning("Análise não foi gravada no PostgreSQL: %s", e)
    return {"relatorio": str(destino) if destino else None}


def _gravar_banco(cfg, lote_id: str, a: Analise, planilhas: dict):
    """Tabelas do schema 'analise': uma linha por item, com lote e base — a evolução entre ondas fica pronta para o Power BI."""
    from psycopg import sql

    from robo.banco import Banco
    banco = Banco(cfg.banco, cfg.base)
    colunas = {
        "resumo": ["resumo_executivo"],
        "indicadores": ["indicador", "coluna", "segmento_coluna", "segmento", "n", "valor", "margem", "media",
                        "pct_promotores", "pct_neutros", "pct_detratores", "base_pequena"],
        "destaques": ["medida", "segmento_coluna", "segmento", "n_grupo", "valor_grupo", "valor_restante", "diferenca",
                      "z", "p_valor", "significativo", "leitura"],
        "alertas": ["nivel", "tipo", "coluna", "mensagem"],
        "perfil": ["coluna", "papel", "linhas", "preenchidos", "pct_preenchido", "distintos", "media", "mediana",
                   "desvio", "minimo", "maximo"],
    }
    tipos = {"n": "bigint", "n_grupo": "bigint", "linhas": "bigint", "preenchidos": "bigint", "distintos": "bigint",
             "base_pequena": "boolean", "significativo": "boolean"}
    numericas = {"valor", "margem", "media", "pct_promotores", "pct_neutros", "pct_detratores", "valor_grupo",
                 "valor_restante", "diferenca", "z", "p_valor", "pct_preenchido", "mediana", "desvio"}
    with banco.conectar() as conn, conn.transaction():
        conn.execute("CREATE SCHEMA IF NOT EXISTS analise")
        for nome, cols in colunas.items():
            df = planilhas.get(nome)
            definicao = ", ".join(f"{c} {tipos.get(c, 'double precision' if c in numericas else 'text')}" for c in cols)
            conn.execute(f"CREATE TABLE IF NOT EXISTS analise.{nome} (lote_id text, base text, arquivo text, "
                         f"analisado_em timestamptz DEFAULT now(), {definicao})")
            conn.execute(sql.SQL("DELETE FROM {} WHERE lote_id = %s").format(sql.Identifier("analise", nome)), (lote_id,))
            if df is None or df.empty:
                continue
            linhas = []
            for registro in df.to_dict("records"):
                valores = []
                for c in cols:
                    v = registro.get(c)
                    if v is None or (isinstance(v, float) and not np.isfinite(v)) or (not isinstance(v, (list, dict)) and pd.isna(v)):
                        v = None
                    elif c in numericas:
                        v = float(v)
                    elif tipos.get(c) == "bigint":
                        v = int(v)
                    elif tipos.get(c) == "boolean":
                        v = bool(v)
                    else:
                        v = str(v)
                    valores.append(v)
                linhas.append((lote_id, a.base, a.arquivo, *valores))
            with conn.cursor() as cur:
                cur.executemany(sql.SQL("INSERT INTO {} (lote_id, base, arquivo, {}) VALUES ({})").format(
                    sql.Identifier("analise", nome), sql.SQL(", ").join(sql.Identifier(c) for c in cols),
                    sql.SQL(", ").join([sql.Placeholder()] * (len(cols) + 3))), linhas)
