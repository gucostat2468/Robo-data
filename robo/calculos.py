"""Calculadora do canal: qualquer cálculo sobre as bases publicadas, pedido em português.

Exemplos que funcionam:
  "nps por região"                         "média de valor por loja onde canal = App"
  "csat da base satisfacao por curso"      "soma de vendas por região e canal"
  "quantas respostas por uf"               "percentual de modalidade"
  "mediana de idade onde região = Sul"     "correlação entre nota_nps e idade"
  "quais colunas tem a base nps"           "quais bases existem"

Como entende: palavras da operação (média, soma, NPS…), "de <coluna>", "por <coluna> [e <coluna>]",
"onde <coluna> = / > / < <valor>" e "na base <nome>" (sem base = a última publicada). O nome da coluna pode ser
aproximado ("regiao", "região", "Região do cliente") — é comparado sem acento e com tolerância a erro de digitação.
Os dados vêm de Bases-Tratadas (o que já passou por todas as conferências). Nada sai do seu computador.
"""

from __future__ import annotations

import difflib
import math
import re
from pathlib import Path

import pandas as pd

from robo import historico
from robo.limpeza import normalizar_nome_coluna, sem_acento

OPERACOES = [  # (operação, palavras, quem responde) — operação explícita (média, soma…) vale antes de NPS/CSAT:
    # em "média de nota nps", "nps" é o nome da coluna, não o pedido.
    ("correlacao", ["correlacao", "correlação", "relacao entre"], "analise_estatistica"),
    ("mediana", ["mediana"], "analise_estatistica"),
    ("desvio", ["desvio padrao", "desvio"], "analise_estatistica"),
    ("media", ["media", "média", "valor medio", "ticket medio"], "analise_estatistica"),
    ("soma", ["soma", "somar", "total de", "somatorio"], "excel_trade"),
    ("minimo", ["minimo", "menor valor", "mínimo"], "analise_perfil"),
    ("maximo", ["maximo", "maior valor", "máximo"], "analise_perfil"),
    ("distintos", ["distintos", "unicos", "diferentes"], "analise_perfil"),
    ("percentual", ["percentual", "porcentagem", "proporcao", "distribuicao", "participacao", "share"], "excel_pesquisa"),
    ("contagem", ["quantos", "quantas", "contagem", "quantidade de", "numero de", "conte", "contar"], "excel_pesquisa"),
    ("nps", ["nps", "net promoter"], "analise_indicadores"),
    ("csat", ["csat", "top 2 box", "top2box", "top-2-box", "satisfacao top"], "analise_indicadores"),
]
_CACHE: dict = {}


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", sem_acento(str(t)).lower()).strip()


# =============================================================================== onde estão os dados
def bases_publicadas(cfg) -> dict[str, dict]:
    """base -> {arquivo, saidas, data_hora} da publicação mais recente (Bases-Tratadas)."""
    from robo.analise import chave_base
    bases = {}
    for h in historico.ler(cfg.logs, 3000):  # mais recentes primeiro
        if h.get("status") != "sucesso":
            continue
        regra = cfg.regra_para(h.get("arquivo", "")) if hasattr(cfg, "regra_para") else {}
        b = chave_base(h.get("arquivo", ""), regra or {})
        if b in bases:
            continue
        exe = historico.ler_execucao(cfg.logs, h.get("id") or "") or {}
        saidas = [str(s) for s in exe.get("saidas") or [] if str(s).lower().endswith((".xlsx", ".csv"))]
        if not saidas:  # execuções antigas: o histórico guarda só o nome; o arquivo está em Bases-Tratadas
            saidas = [str(Path(cfg.tratadas) / n) for n in str(h.get("saidas") or "").split(" | ")
                      if n.lower().endswith((".xlsx", ".csv"))]
        saidas = [s for s in saidas if Path(s).exists()]
        if saidas:
            bases[b] = {"arquivo": h.get("arquivo"), "saidas": saidas, "data_hora": h.get("data_hora")}
    return bases


def carregar_base(cfg, base: str) -> tuple[pd.DataFrame, str]:
    """Tabela principal da base (a fato, se houver modelo estrela; senão a única tabela). Com cache por arquivo."""
    info = bases_publicadas(cfg)[base]
    caminho = Path(info["saidas"][0])
    chave = (str(caminho), caminho.stat().st_mtime_ns)
    if chave not in _CACHE:
        if caminho.suffix.lower() == ".csv":
            saida = getattr(cfg, "saida", {}) or {}  # o mesmo separador e decimal com que o robô gravou o CSV
            df = pd.read_csv(caminho, sep=saida.get("csv_separador", ";"), decimal=saida.get("csv_decimal", ","),
                             encoding="utf-8-sig")
        else:
            abas = pd.read_excel(caminho, sheet_name=None)
            nome = next((n for n in abas if not n.startswith("dim_") and n not in ("dicionario_dados", "log_qualidade")),
                        next(iter(abas)))
            df = abas[nome]
            # traz os atributos das dimensões para a fato (para segmentar por curso, região…)
            for n, dim in abas.items():
                if n.startswith("dim_") and n != "dim_calendario" and len(dim.columns) and dim.columns[0] in df.columns:
                    df = df.merge(dim, on=dim.columns[0], how="left")
        _CACHE.clear() if len(_CACHE) > 20 else None
        _CACHE[chave] = df
    return _CACHE[chave], info["arquivo"]


# =============================================================================== interpretação
def _achar_coluna(trecho: str, colunas: list[str]) -> str | None:
    t = normalizar_nome_coluna(trecho)
    if not t:
        return None
    if t in colunas:
        return t
    contem = [c for c in colunas if t in c or c in t]
    if contem:
        return min(contem, key=lambda c: abs(len(c) - len(t)))
    parecida = difflib.get_close_matches(t, colunas, n=1, cutoff=0.7)
    return parecida[0] if parecida else None


def _valor(texto: str):
    """Número em formato brasileiro (1.234,5) ou com ponto decimal (8.5); o resto continua texto."""
    t = texto.strip().strip("'\"")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?|-?\d+(,\d+)?", t):  # 1.234 / 1.234,5 / 85 / 8,5
        return float(t.replace(".", "").replace(",", "."))
    if re.fullmatch(r"-?\d+\.\d+", t):  # 8.5 (ponto decimal)
        return float(t)
    return t


def _base_pelo_nome(frase: str, bases: list[str]) -> str | None:
    """'pesquisa de alunos' → nps_pesquisa_alunos: todas as palavras da frase estão no nome da base (singular/plural)."""
    palavras = [w for w in re.findall(r"[a-z0-9]+", _norm(frase)) if len(w) >= 3 and w not in ("das", "dos", "base", "planilha")]
    if not palavras:
        return None
    achadas = []
    for b in bases:
        partes = [x for x in b.split("_") if x]
        if all(any(p[:5] == w[:5] and abs(len(p) - len(w)) <= 2 for p in partes) for w in palavras):
            achadas.append(b)
    return achadas[0] if len(achadas) == 1 else None


def interpretar(pergunta: str, bases: list[str]) -> dict | None:
    t = _norm(pergunta)
    base = None
    m = re.search(r"\b(?:na|da|do|no|em)\s+(?:base|arquivo|planilha)\s+([\w-]+)", t)
    if m:  # tira "na base nps" antes de procurar a operação ("nps" aqui é nome de base, não pedido de NPS)
        achada = difflib.get_close_matches(normalizar_nome_coluna(m.group(1)), bases, n=1, cutoff=0.6)
        base = achada[0] if achada else m.group(1)
        t = (t[:m.start()] + " " + t[m.end():]).strip()
    op, autor = None, None
    for nome, palavras, quem in OPERACOES:
        if any(re.search(rf"(^|\W){re.escape(_norm(p))}(\W|$)", t) for p in palavras):
            op, autor = nome, quem
            break
    if not op:
        return None
    pedido = {"op": op, "autor": autor, "base": base, "metrica": [], "por": [], "filtros": []}
    m = re.search(r"\b(?:onde|quando|com|para|filtrando)\s+(.+?)$", t)
    if m:
        for parte in re.split(r"\s+e\s+", m.group(1)):
            f = re.match(r"(.+?)\s*(>=|<=|!=|=|>|<|\bigual a\b|\be\b|\bmaior que\b|\bmenor que\b|\bdiferente de\b)\s*(.+)", parte)
            if f:
                sinal = {"igual a": "=", "e": "=", "maior que": ">", "menor que": "<", "diferente de": "!="}.get(f.group(2), f.group(2))
                pedido["filtros"].append((f.group(1).strip(), sinal, _valor(f.group(3))))
        t = t[:m.start()]
    m = re.search(r"\bpor\s+(.+?)$", t)
    if m:
        pedido["por"] = [x.strip() for x in re.split(r"\s+e\s+|,", m.group(1)) if x.strip()]
        t = t[:m.start()]
    m = re.search(r"\b(?:entre)\s+(.+?)\s+e\s+(.+?)$", t)
    if op == "correlacao" and m:
        pedido["metrica"] = [m.group(1), m.group(2)]
    else:
        m = re.search(r"\b(?:de|do|da|dos|das)\s+(.+?)$", t)
        if m:
            pedido["metrica"] = [m.group(1).strip()]
    return pedido


# =============================================================================== execução
def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(v)


def notas_nps(s: pd.Series) -> tuple[pd.Series, int]:
    """Só notas válidas de NPS: inteiros de 0 a 10. Códigos como 99 ('não sabe') ficam fora — e são contados."""
    v = pd.to_numeric(s, errors="coerce").dropna().astype(float)
    validas = v[(v >= 0) & (v <= 10) & (v == v.round())]
    return validas, int(len(v) - len(validas))


def _nps(s: pd.Series) -> tuple[float, int, float]:
    v, _ = notas_nps(s)
    n = len(v)
    if not n:
        return float("nan"), 0, float("nan")
    p, d = (v >= 9).mean(), (v <= 6).mean()
    return 100 * (p - d), n, 100 * 1.96 * math.sqrt(max(p + d - (p - d) ** 2, 0) / n)


def _f1(v) -> str:
    return f"{v:.1f}".replace(".", ",") if isinstance(v, float) and not math.isnan(v) else _fmt(v)


def _comparar_nps(grupos) -> str:
    """Maior × menor NPS entre grupos com pelo menos 30 respostas: a diferença é real ou pode ser acaso?"""
    validos = []
    for chave, sub in grupos:
        v, n, m = _nps(sub)
        if n >= 30 and not math.isnan(v):
            validos.append((v, m, " / ".join(map(str, chave)) if isinstance(chave, tuple) else str(chave)))
    if len(validos) < 2:
        return "Conclusão: poucos grupos com 30 respostas ou mais; não dá para afirmar diferença entre eles."
    (v1, m1, g1), (v2, m2, g2) = max(validos), min(validos)
    dif, margem_dif = v1 - v2, math.sqrt(m1 ** 2 + m2 ** 2)  # teste de diferença entre duas proporções independentes (95%)
    if dif > margem_dif:
        return (f"Conclusão: {g1} ({_f0(v1)}) está de fato acima de {g2} ({_f0(v2)}): a diferença de {_f0(dif)} pts "
                f"é maior que a margem da diferença (±{_f0(margem_dif)} pts, 95% de confiança).")
    return (f"Conclusão: a diferença entre {g1} ({_f0(v1)}) e {g2} ({_f0(v2)}) é de {_f0(dif)} pts, menor que a margem da "
            f"diferença (±{_f0(margem_dif)} pts): pode ser acaso. Não comunique como ranking.")


def _f0(v) -> str:
    return f"{v:.0f}".replace("-0", "0") if isinstance(v, float) and not math.isnan(v) else _fmt(v)


def _nps_explicado(s: pd.Series) -> str:
    """NPS sem casas decimais, com a conta aberta: % promotores − % detratores, quantidades, neutros e margem."""
    v, fora = notas_nps(s)
    n = len(v)
    if not n:
        return "sem notas válidas (0 a 10)" + (f"; {fora} valor(es) fora da escala ignorado(s)" if fora else "")
    prom, det = int((v >= 9).sum()), int((v <= 6).sum())
    neu = n - prom - det
    nps, _, margem = _nps(v)
    pp, pd_, pn = 100 * prom / n, 100 * det / n, 100 * neu / n
    return (f"NPS {_f0(nps)} = {_f1(pp)}% promotores ({prom}) − {_f1(pd_)}% detratores ({det}) = {_f1(nps)}, "
            f"arredondado para {_f0(nps)}; neutros {_f1(pn)}% ({neu}); n={n}; margem ±{_f0(margem)} pts"
            + (" ⚠ base pequena (menos de 30): use com cautela" if n < 30 else "")
            + (f" · {fora} valor(es) fora de 0–10 ignorado(s) (ex.: 99 = não sabe)" if fora else ""))


EXPLICA_NPS = ("Como ler: NPS = % de promotores (notas 9 e 10) − % de detratores (notas 0 a 6). Os neutros (7 e 8) não "
               "entram na subtração, mas contam no total, então diluem o resultado. Vai de −100 a +100. A margem é de 95% "
               "de confiança. Para comparar dois grupos, a diferença entre eles precisa ser maior que a margem da diferença "
               "(raiz da soma dos quadrados das duas margens); se não for, pode ser acaso.")
EXPLICA_CSAT = ("Como ler: CSAT (top-2-box) = % de quem deu as duas notas mais altas da escala (4 e 5 numa escala de 1 a 5) "
                "sobre o total de quem respondeu.")


ESCALAS_CSAT = (5, 7, 10)


def escala_csat(serie: pd.Series, declarada=None) -> tuple[int, str]:
    """A escala do CSAT, decidida UMA vez para a coluna inteira (nunca por grupo: numa pesquisa de 1 a 7, um segmento
    cuja maior nota foi 5 seria lido como 1 a 5 e teria o CSAT inflado). Prioridade: 'escala_csat' declarada na regra;
    sem ela, deduz pelo maior valor da coluna e diz que deduziu. Usada pela calculadora, conferência, Excel e análise."""
    if declarada is not None:
        try:
            return int(declarada), "declarada na regra"
        except (TypeError, ValueError):
            pass
    v = pd.to_numeric(serie, errors="coerce").dropna()
    maior = v.max() if len(v) else 5
    escala = 5 if maior <= 5 else 7 if maior <= 7 else 10
    return escala, (f"deduzida pelo maior valor ({_fmt(float(maior))}); declare 'escala_csat: {escala}' na regra "
                    f"para não depender disso")


def _csat_explicado(s: pd.Series, escala: int) -> str:
    v = pd.to_numeric(s, errors="coerce").dropna()
    fora = int(((v < 0) | (v > escala)).sum())
    v = v[(v >= 0) & (v <= escala)]  # nota acima da escala (ex.: 99 = 'não sabe') não conta como satisfeito
    if not len(v):
        return "sem notas válidas" + (f"; {fora} valor(es) fora da escala ignorado(s)" if fora else "")
    sat = int((v >= escala - 1).sum())
    return (f"CSAT {_f1(100 * sat / len(v))}% = {sat} de {len(v)} deram nota {escala - 1} ou {escala} (escala até {escala})"
            + (f"; {fora} valor(es) fora da escala ignorado(s)" if fora else "")
            + (" ⚠ base pequena (menos de 30)" if len(v) < 30 else ""))


def calcular(cfg, pergunta: str, fontes: dict | None = None, apelidos: bool = True) -> dict | None:
    """Devolve {autor, texto} ou None (não é um pedido de cálculo). Erros de entendimento viram resposta honesta.
    fontes = {nome: (DataFrame, arquivo)} calcula sobre essas tabelas (ex.: arquivo anexado a uma conversa)
    em vez das bases publicadas.
    apelidos=True aplica as correções do dono aprovadas para a empresa ('nota' = nota_nps — robo/aprendizado.py) e avisa
    na resposta; o laboratório passa False (a resposta certa dele não pode depender de correção de conversa)."""
    usados: list[dict] = []
    if apelidos and cfg is not None:
        from robo import aprendizado
        pergunta, usados = aprendizado.aplicar_apelidos(cfg, pergunta)
    r = _calcular(cfg, pergunta, fontes)
    if r and usados:
        aviso = "; ".join(f"“{u['termo']}” = coluna {u['coluna']}" for u in usados)
        r = {**r, "texto": f"{r['texto']}\n(Usei a correção que você aprovou para a empresa: {aviso}.)", "apelidos": usados}
        if r.get("calc"):  # deu resultado: é a prova de que a correção funciona
            from robo import aprendizado
            aprendizado.comprovar_apelido(cfg, usados, f"cálculo '{pergunta[:150]}' usou {aviso} e deu resultado")
    return r


def _calcular(cfg, pergunta: str, fontes: dict | None = None) -> dict | None:
    if fontes:
        bases = {b: {"arquivo": arq, "data_hora": "agora"} for b, (_, arq) in fontes.items()}
        carregar_base = lambda _cfg, b: (fontes[b][0], fontes[b][1])  # noqa: E731 (mesma assinatura da global)
    else:
        bases = bases_publicadas(cfg)
        carregar_base = globals()["carregar_base"]
    t = _norm(pergunta)
    if re.search(r"quais (sao as )?bases|bases (publicadas|existem|disponiveis)", t):
        if not bases:
            return {"autor": "gov_estagiaria", "texto": "Ainda não há base publicada em Bases-Tratadas."}
        return {"autor": "gov_estagiaria", "texto": "Bases publicadas: " + "; ".join(
            f"{b} (último arquivo {i['arquivo']}, {str(i['data_hora'])[:16]})" for b, i in bases.items())}
    pedido_colunas = re.search(r"(quais|que) colunas", t)
    pedido = None if pedido_colunas else interpretar(pergunta, list(bases))
    if not pedido and not pedido_colunas:
        return None
    if not bases:
        return {"autor": "canal_nina", "texto": "Ainda não há nenhuma base publicada para calcular. Assim que uma "
                                                "planilha for aprovada, é só perguntar de novo."}
    base = (pedido or {}).get("base")
    if pedido_colunas:
        m = re.search(r"base\s+([\w-]+)", t)
        base = difflib.get_close_matches(normalizar_nome_coluna(m.group(1)), list(bases), n=1, cutoff=0.5)[0] if m and \
            difflib.get_close_matches(normalizar_nome_coluna(m.group(1)), list(bases), n=1, cutoff=0.5) else None
    if base and base not in bases:
        return {"autor": "gov_estagiaria", "texto": f"Não encontrei a base '{base}'. Bases publicadas: {', '.join(bases)}."}
    if not base and pedido:  # sem base no pedido: a mais recente que tenha TODAS as colunas citadas
        citadas = pedido["metrica"] + pedido["por"] + [f[0] for f in pedido["filtros"]]
        for b in bases:
            tab = carregar_base(cfg, b)[0]
            cols = [c for c in tab.columns if not str(c).startswith("_")]
            implicita_ok = pedido["metrica"] or pedido["op"] not in ("nps", "csat") or _coluna_indicador(pedido["op"], tab)
            if implicita_ok and all(_achar_coluna(x, cols) for x in citadas):
                base = b
                break
        if not base and pedido["metrica"]:  # "NPS da pesquisa de alunos": a frase não é coluna — é o nome da base?
            pela_frase = _base_pelo_nome(pedido["metrica"][0], list(bases))
            if pela_frase:
                tab = carregar_base(cfg, pela_frase)[0]
                cols = [c for c in tab.columns if not str(c).startswith("_")]
                resto = pedido["por"] + [f[0] for f in pedido["filtros"]]
                if not _achar_coluna(pedido["metrica"][0], cols) and all(_achar_coluna(x, cols) for x in resto) and \
                        (pedido["op"] not in ("nps", "csat") or _coluna_indicador(pedido["op"], tab)):
                    base, pedido["metrica"] = pela_frase, []
                    citadas = resto
        if not base:
            return {"autor": "canal_nina", "texto": "Nenhuma base publicada tem tudo o que você pediu junto "
                                                    f"({pedido['op'].upper() if pedido['op'] in ('nps', 'csat') else pedido['op']}"
                                                    f"{' + ' + ', '.join(citadas) if citadas else ''}). Bases: {', '.join(bases)}. "
                                                    "Pergunte 'quais colunas tem a base X' para ver o que existe."}
    base = base or next(iter(bases))
    df, arquivo = carregar_base(cfg, base)
    colunas = [c for c in df.columns if not str(c).startswith("_")]
    if pedido_colunas:
        return {"autor": "gov_estagiaria", "texto": f"A base {base} ({arquivo}, {_milhar(len(df))} linhas) tem: "
                                                    + ", ".join(f"{c} ({_tipo(df[c])})" for c in colunas)}

    nao_achei = []
    metricas = [c for c in (_achar_coluna(x, colunas) for x in pedido["metrica"]) if c]
    if pedido["metrica"] and len(metricas) < len(pedido["metrica"]):
        nao_achei += [x for x in pedido["metrica"] if not _achar_coluna(x, colunas)]
    por = []
    for x in pedido["por"]:
        c = _achar_coluna(x, colunas)
        (por.append(c) if c else nao_achei.append(x))
    dados = df
    filtros_txt = []
    filtros_ok = []  # (coluna real, sinal, valor) — usados para refazer a conta no banco e montar o passo a passo
    for col_txt, sinal, valor in pedido["filtros"]:
        c = _achar_coluna(col_txt, colunas)
        if not c:
            nao_achei.append(col_txt)
            continue
        serie = dados[c]
        if isinstance(valor, float) and pd.api.types.is_numeric_dtype(serie):
            mask = {"=": serie == valor, "!=": serie != valor, ">": serie > valor, "<": serie < valor,
                    ">=": serie >= valor, "<=": serie <= valor}[sinal]
        else:
            if sinal not in ("=", "!="):
                return {"autor": "canal_nina", "texto": f"A coluna {c} é texto: para ela só dá para filtrar com = ou "
                                                        f"!= (ex.: {c} = valor). Maior/menor só em colunas numéricas."}
            if isinstance(valor, float):  # número digitado para coluna de texto (ex.: código 2025)
                valor = str(int(valor)) if valor.is_integer() else str(valor)
            alvo = _norm(valor)
            iguais = serie.astype(str).map(_norm) == alvo
            mask = ~iguais if sinal == "!=" else iguais
        dados = dados[mask.fillna(False)]
        filtros_ok.append((c, sinal, valor))
        filtros_txt.append(f"{c} {sinal} {valor if not isinstance(valor, float) else _fmt(valor)}")
    if nao_achei:
        sugestoes = "; ".join(f"'{x}' → talvez {difflib.get_close_matches(normalizar_nome_coluna(x), colunas, n=2, cutoff=0.4) or 'nenhuma parecida'}"
                              for x in nao_achei)
        return {"autor": "canal_nina", "texto": f"Não encontrei a(s) coluna(s) na base {base}: {sugestoes}. "
                                                f"Colunas disponíveis: {', '.join(colunas)}."}

    op = pedido["op"]
    if op in ("nps", "csat") and not metricas:
        metricas = [c for c in [_coluna_indicador(op, df)] if c]
    if op in ("media", "mediana", "soma", "minimo", "maximo", "desvio", "nps", "csat") and not metricas:
        numericas = [c for c in colunas if pd.api.types.is_numeric_dtype(df[c])]
        return {"autor": "canal_nina", "texto": f"De qual coluna? Numéricas na base {base}: {', '.join(numericas) or 'nenhuma'}."}
    if op in ("media", "mediana", "soma", "minimo", "maximo", "desvio", "nps", "csat", "correlacao"):
        texto_cols = [c for c in metricas if not pd.api.types.is_numeric_dtype(df[c])]
        if texto_cols:
            return {"autor": "canal_nina", "texto": f"A coluna {', '.join(texto_cols)} não é numérica, então não dá para "
                                                    f"calcular {op}. Para texto, peça contagem ou percentual "
                                                    f"(ex.: percentual de {texto_cols[0]})."}
    if not len(dados):
        return {"autor": pedido["autor"], "texto": f"Nenhuma linha da base {base} atende ao filtro ({'; '.join(filtros_txt)})."}

    escala, origem_escala = None, ""
    if op == "csat" and metricas:  # escala da coluna INTEIRA da base (não do filtro nem do grupo)
        declarada = cfg.regra_para(arquivo).get("escala_csat") if cfg is not None and arquivo else None
        escala, origem_escala = escala_csat(df[metricas[0]], declarada)
    titulo, tabela = _executar(op, dados, metricas, por, escala)
    contexto = f"Base {base} ({arquivo}), {_milhar(len(dados))} linha(s)" + (
        f", filtro: {'; '.join(filtros_txt)}" if filtros_txt else "") + "."
    if escala:
        tabela += f"\nEscala do CSAT: 1 a {escala} ({origem_escala})."
    return {"autor": pedido["autor"], "texto": f"{titulo} — {contexto}\n{tabela}",
            "calc": {"op": op, "metricas": metricas, "por": por, "filtros": filtros_ok, "base": base, "arquivo": arquivo,
                     "fonte": "arquivo" if fontes else "publicada", "dados": dados, "escala_csat": escala}}


def _coluna_indicador(op: str, df: pd.DataFrame) -> str | None:
    """Coluna numérica de NPS (0–10) ou CSAT/satisfação, reconhecida pelo nome."""
    palavra = r"nps|recomend" if op == "nps" else r"(^|_)(csat|satisf)"
    for c in df.columns:
        if not re.search(palavra, str(c)) or str(c).startswith(("id_", "_")) or not pd.api.types.is_numeric_dtype(df[c]):
            continue
        v = pd.to_numeric(df[c], errors="coerce").dropna()
        # nota de pesquisa: a grande maioria é inteiro de 0 a 10 (códigos como 99 = 'não sabe' podem existir e são
        # descartados na conta); tempo de atendimento em minutos não passa nesse teste
        validas, _ = notas_nps(v)
        if len(v) and len(validas) / len(v) >= 0.8:
            return c
    return None


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _tipo(s: pd.Series) -> str:
    if pd.api.types.is_datetime64_any_dtype(s):
        return "data"
    if pd.api.types.is_numeric_dtype(s):
        return "número"
    return "texto"


def _executar(op: str, df: pd.DataFrame, metricas: list[str], por: list[str], escala: int | None = None) -> tuple[str, str]:
    col = metricas[0] if metricas else None
    linhas: list[str] = []
    if op == "correlacao":
        if len(metricas) < 2:
            return "Correlação precisa de duas colunas (ex.: correlação entre nota_nps e idade)", ""
        a, b = (pd.to_numeric(df[m], errors="coerce") for m in metricas[:2])
        r = a.corr(b)
        # mesmos cortes da análise do 2º andar (robo/analise.py)
        forca = "forte" if abs(r) >= 0.7 else "moderada" if abs(r) >= 0.5 else "fraca" if abs(r) >= 0.3 else "praticamente nenhuma"
        return (f"Correlação de Pearson entre {metricas[0]} e {metricas[1]}: {_fmt(r)} ({forca}; correlação não prova causa)",
                f"n = {int((a.notna() & b.notna()).sum())}")

    def calc(sub: pd.DataFrame):
        if op == "nps":
            return _nps_explicado(sub[col])
        if op == "csat":
            return _csat_explicado(sub[col], escala or escala_csat(df[col])[0])
        if op == "contagem":
            return f"{len(sub):,}".replace(",", ".")
        if op == "distintos":
            return str(sub[col].nunique()) if col else str(len(sub.drop_duplicates()))
        s = pd.to_numeric(sub[col], errors="coerce")
        return _fmt(float({"media": s.mean, "mediana": s.median, "soma": s.sum, "minimo": s.min, "maximo": s.max,
                           "desvio": s.std}[op]()))

    nome_op = {"nps": "NPS", "csat": "CSAT (top-2-box)", "contagem": "Contagem", "distintos": "Valores distintos",
               "media": "Média", "mediana": "Mediana", "soma": "Soma", "minimo": "Mínimo", "maximo": "Máximo",
               "desvio": "Desvio padrão", "percentual": "Percentual"}[op]
    if op == "percentual":
        alvo = por or ([col] if col else [])
        if not alvo:
            return "Percentual de quê? (ex.: percentual de modalidade)", ""
        if por and col:  # % de cada valor de 'col' dentro de cada grupo
            tab = pd.crosstab([df[c] for c in por], df[col], normalize="index") * 100
            return (f"Percentual de {col} dentro de {', '.join(por)}",
                    "\n".join(f"{i}: " + ", ".join(f"{k} {_fmt(float(v))}%" for k, v in linha.items())
                              for i, linha in list(tab.iterrows())[:15]))
        dist = df[alvo[0]].value_counts(normalize=True, dropna=False).head(15) * 100
        return (f"Percentual de {alvo[0]}", "\n".join(f"{k}: {_fmt(float(v))}%" for k, v in dist.items()))
    titulo = f"{nome_op}" + (f" de {col}" if col else "") + (f" por {', '.join(por)}" if por else "")
    explica = {"nps": EXPLICA_NPS, "csat": EXPLICA_CSAT}.get(op)
    if not por:
        return titulo, calc(df) + (f"\n{explica}" if explica else "")
    if explica:  # total primeiro, para comparar cada grupo com a média geral
        linhas.append(f"Total: {calc(df)}")
    grupos = list(df.groupby(por, dropna=True, observed=True))
    for chave, sub in sorted(grupos, key=lambda g: -len(g[1]))[:15]:
        rotulo = " / ".join(map(str, chave)) if isinstance(chave, tuple) else str(chave)
        linhas.append(f"{rotulo}: {calc(sub)}")
    if len(grupos) > 15:
        linhas.append(f"… e mais {len(grupos) - 15} grupo(s)")
    if op == "nps":
        linhas.append(_comparar_nps([(k, sub[col]) for k, sub in grupos]))
    if explica:
        linhas.append(explica)
    return titulo, "\n".join(linhas)
