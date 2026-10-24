"""Catálogo de regras de negócio da Fábrica de Planilhas (dados SINTÉTICOS para a empresa inteira treinar).

Cada regra descreve uma planilha como ela existe numa empresa de verdade: colunas, tipos, faixas, chave, os erros que
costumam aparecer, o INDICADOR que ela alimenta e como calcular esse indicador a partir da versão limpa (o gabarito).
A planilha é gerada limpa (a verdade), depois a sujeira é plantada pelo laboratório (robo/laboratorio.py:
aplicar_nivel + escrever_sujo) — por isso a resposta certa é sempre conhecida.

Regras novas sem programar: config.yaml → fabrica: regras_extra: caminho de um .json com uma lista de regras simples
(ver `regra_de_arquivo`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class Regra:
    id: str
    nome: str
    area: str                       # comercial, marketing, pesquisa, rh, financeiro, operacoes, educacao
    descricao: str
    chave: str                      # coluna que identifica a linha (nunca repete)
    segmento: str                   # coluna de categoria usada no gabarito
    metrica: str                    # coluna numérica usada no gabarito
    op: str                         # soma | media | nps (como a métrica vira número)
    moeda: bool
    indicador: str                  # o que a planilha alimenta, em linguagem de negócio
    erros_plausiveis: list[str] = field(default_factory=list)
    gerar: object = None            # (rng, n) -> dict rótulo -> lista
    calcular_indicador: object = None   # (df limpo, colunas normalizadas) -> número


def _datas(rng, n, inicio=date(2025, 1, 1), dias=640):
    hoje = date.today()
    return [min(inicio + timedelta(days=int(x)), hoje) for x in rng.integers(0, dias, n)]


def _ids(rng, n, base=100_000):
    return rng.permutation(np.arange(base, base + n))


def _escolha(rng, valores, n, pesos=None):
    p = None if pesos is None else np.array(pesos, dtype=float) / sum(pesos)
    return rng.choice(valores, n, p=p)


UFS = ["SP", "RJ", "MG", "BA", "PR", "RS", "PE", "CE", "GO", "SC"]
REGIOES = ["Sudeste", "Sul", "Nordeste", "Norte", "Centro-Oeste"]


# ------------------------------------------------------------------------------------------------ geradores
# Pesos verdadeiros dos atributos na nota NPS (pesquisa de alunos): Conteúdo pesa mais, depois Atendimento, e
# Infraestrutura quase nada. É a verdade que o gabarito guarda para conferir a análise de drivers.
PESOS_NPS = {"Nota Conteúdo": 0.6, "Nota Atendimento": 0.3, "Nota Infraestrutura": 0.05}


def _nps(rng, n):
    curso = _escolha(rng, ["Administração", "Direito", "Enfermagem", "Engenharia", "Pedagogia", "Psicologia"], n)
    base = {"Administração": 7.5, "Direito": 8.0, "Enfermagem": 6.5, "Engenharia": 7.0, "Pedagogia": 8.6, "Psicologia": 7.8}
    atributos = {a: np.clip(np.round(rng.normal(7.5, 1.8, n)), 0, 10).astype(int) for a in PESOS_NPS}
    efeito = sum(peso * (atributos[a] - 7.5) for a, peso in PESOS_NPS.items())
    nota = np.clip(np.round(np.array([base[c] for c in curso]) + efeito + rng.normal(0, 1.3, n)), 0, 10).astype(int)
    return {"ID Resposta": _ids(rng, n), "Curso": curso, "Modalidade": _escolha(rng, ["EAD", "Presencial", "Semipresencial"], n, [5, 3, 2]),
            "UF": _escolha(rng, UFS, n), **atributos, "Nota NPS": nota, "Data da Resposta": _datas(rng, n)}


def _csat(rng, n):
    canal = _escolha(rng, ["Telefone", "Chat", "E-mail", "WhatsApp", "Loja"], n, [3, 3, 1, 4, 2])
    csat = np.clip(np.round(rng.normal(4.0, 0.9, n)), 1, 5).astype(int)
    ces = np.clip(np.round(rng.normal(3.0, 1.1, n)), 1, 7).astype(int)
    return {"Protocolo": _ids(rng, n, 500_000), "Canal de Atendimento": canal, "Motivo": _escolha(
        rng, ["Cobrança", "Entrega", "Troca", "Dúvida", "Cancelamento"], n), "Nota CSAT": csat, "Nota CES": ces,
            "Data do Atendimento": _datas(rng, n)}


def _churn(rng, n):
    plano = _escolha(rng, ["Básico", "Padrão", "Premium"], n, [5, 3, 2])
    mensal = {"Básico": 49.9, "Padrão": 89.9, "Premium": 149.9}
    entrada = _datas(rng, n, date(2024, 1, 1), 700)
    cancelou = rng.random(n) < np.where(plano == "Básico", 0.28, np.where(plano == "Padrão", 0.18, 0.09))
    return {"ID Cliente": _ids(rng, n, 700_000), "Plano": plano, "Coorte (mês de entrada)": [d.strftime("%Y-%m") for d in entrada],
            "Mensalidade": np.round([mensal[p] * rng.uniform(0.9, 1.1) for p in plano], 2),
            "Cancelou": np.where(cancelou, "Sim", "Não"), "Data de Entrada": entrada}


def _rfm(rng, n):
    seg = _escolha(rng, ["Varejo", "Atacado", "Online"], n, [5, 2, 3])
    freq = rng.poisson(np.where(seg == "Atacado", 14, 5)) + 1
    return {"ID Cliente": _ids(rng, n, 300_000), "Canal": seg, "Última Compra": _datas(rng, n, date(2025, 6, 1), 480),
            "Frequência (pedidos)": freq, "Valor Total": np.round(freq * rng.lognormal(5.2, 0.5, n), 2)}


def _abc(rng, n):
    cat = _escolha(rng, ["Bebidas", "Mercearia", "Higiene", "Limpeza", "Frios", "Hortifruti"], n)
    fat = np.round(rng.pareto(1.3, n) * 900 + 50, 2)   # cauda longa: poucos SKUs fazem a maior parte (curva ABC)
    return {"SKU": [f"SKU-{x}" for x in _ids(rng, n, 10_000)], "Categoria": cat, "Fornecedor": _escolha(
        rng, ["Alfa", "Beta", "Gama", "Delta", "Ômega"], n), "Faturamento": fat, "Margem (%)": np.round(rng.uniform(5, 45, n), 1)}


def _funil(rng, n):
    origem = _escolha(rng, ["Google Ads", "Meta Ads", "Indicação", "Orgânico", "Evento"], n, [4, 3, 1, 3, 1])
    etapa = _escolha(rng, ["Lead", "MQL", "SQL", "Proposta", "Ganho", "Perdido"], n, [40, 25, 12, 8, 6, 9])
    return {"ID Oportunidade": _ids(rng, n, 900_000), "Origem do Lead": origem, "Etapa do Funil": etapa,
            "Valor da Oportunidade": np.round(rng.lognormal(8.2, 0.7, n), 2), "Data de Criação": _datas(rng, n)}


def _folha(rng, n):
    cargo = _escolha(rng, ["Analista", "Assistente", "Coordenador", "Gerente", "Técnico"], n, [5, 4, 2, 1, 3])
    base = {"Analista": 6200, "Assistente": 3100, "Coordenador": 9800, "Gerente": 16500, "Técnico": 4300}
    return {"Matrícula": _ids(rng, n, 20_000), "Departamento": _escolha(rng, ["Comercial", "Operações", "TI", "Financeiro", "RH"], n),
            "Cargo": cargo, "Salário Base": np.round([base[c] * rng.uniform(0.85, 1.2) for c in cargo], 2),
            "Horas Extras": np.round(rng.exponential(4, n), 1), "Data de Admissão": _datas(rng, n, date(2012, 1, 1), 5000)}


def _ponto(rng, n):
    return {"ID Registro": _ids(rng, n, 1_000_000), "Equipe": _escolha(rng, ["Loja Centro", "Loja Norte", "CD Guarulhos", "Escritório"], n),
            "Turno": _escolha(rng, ["Manhã", "Tarde", "Noite"], n, [4, 4, 2]),
            "Horas Trabalhadas": np.round(np.clip(rng.normal(8.1, 0.9, n), 2, 12), 2),
            "Atraso (min)": np.round(np.clip(rng.exponential(6, n) - 3, 0, None)), "Data": _datas(rng, n, date(2026, 1, 1), 280)}


def _estoque(rng, n):
    demanda = np.round(rng.gamma(2.0, 6.0, n), 1)
    estoque = np.round(np.clip(rng.normal(demanda * 9, demanda * 4), 0, None))
    return {"ID Posição": _ids(rng, n, 40_000), "Loja": _escolha(rng, [f"Loja {i:02d}" for i in range(1, 13)], n),
            "Categoria": _escolha(rng, ["Bebidas", "Mercearia", "Higiene", "Limpeza"], n),
            "Estoque (un)": estoque, "Demanda Diária (un)": demanda,
            "Em Ruptura": np.where(estoque <= 0, "Sim", "Não")}


def _logistica(rng, n):
    transp = _escolha(rng, ["Rápida Log", "Econômica", "Expressa BR", "Correios"], n)
    atraso = np.round(np.abs(rng.normal(np.where(transp == "Econômica", 2.5, 0.8), 1.2)), 1)
    return {"Pedido": _ids(rng, n, 5_000_000), "Transportadora": transp, "UF Destino": _escolha(rng, UFS, n),
            "Prazo Prometido (dias)": rng.integers(2, 12, n), "Atraso (dias)": atraso, "Data de Envio": _datas(rng, n)}


def _financeiro(rng, n):
    tipo = _escolha(rng, ["A Pagar", "A Receber"], n, [55, 45])
    return {"Título": _ids(rng, n, 80_000), "Tipo": tipo, "Centro de Custo": _escolha(
        rng, ["Administrativo", "Comercial", "Fábrica", "Logística", "TI"], n),
            "Valor do Título": np.round(rng.lognormal(7.5, 0.9, n), 2),
            "Situação": _escolha(rng, ["Em aberto", "Pago", "Vencido", "Conciliado"], n, [3, 5, 1, 2]),
            "Vencimento": _datas(rng, n, date(2026, 1, 1), 300)}


def _leads(rng, n):
    canal = _escolha(rng, ["Google", "Meta", "LinkedIn", "TikTok", "E-mail"], n, [4, 4, 2, 1, 1])
    custo = np.round(rng.uniform(300, 15000, n), 2)
    leads = np.round(custo / rng.uniform(25, 90, n))
    return {"ID Campanha": _ids(rng, n, 60_000), "Canal": canal, "Investimento": custo, "Leads": leads,
            "MQL": np.round(leads * rng.uniform(0.2, 0.5, n)), "Data": _datas(rng, n, date(2026, 1, 1), 280)}


def _educacao(rng, n):
    curso = _escolha(rng, ["Administração", "Direito", "Enfermagem", "Engenharia", "Pedagogia"], n)
    freq = np.round(np.clip(rng.normal(82, 12, n), 20, 100), 1)
    nota = np.round(np.clip(rng.normal(6.8, 1.8, n) + (freq - 80) / 25, 0, 10), 1)
    evadiu = rng.random(n) < np.clip((80 - freq) / 60 + 0.05, 0.02, 0.9)
    return {"Matrícula": _ids(rng, n, 2_000_000), "Curso": curso, "Semestre": rng.integers(1, 11, n),
            "Média Final": nota, "Frequência (%)": freq, "Evadiu": np.where(evadiu, "Sim", "Não")}


def _vendas(rng, n):
    regiao = _escolha(rng, REGIOES, n, [5, 2, 3, 1, 1])
    qtd = rng.integers(1, 40, n)
    preco = np.round(rng.lognormal(4.2, 0.6, n), 2)
    return {"Nota Fiscal": _ids(rng, n, 7_000_000), "Região": regiao, "Vendedor": _escolha(
        rng, ["Ana", "Bruno", "Carla", "Diego", "Eduarda", "Fábio", "Gisele", "Heitor"], n),
            "Quantidade": qtd, "Valor da Venda": np.round(qtd * preco, 2), "Data da Venda": _datas(rng, n)}


def _pesquisa_mercado(rng, n):
    marca = _escolha(rng, ["Nossa Marca", "Concorrente A", "Concorrente B", "Concorrente C"], n, [3, 3, 2, 2])
    lembranca = rng.random(n) < np.where(marca == "Nossa Marca", 0.62, 0.45)
    return {"ID Entrevista": _ids(rng, n, 3_000_000), "Marca Avaliada": marca, "Faixa Etária": _escolha(
        rng, ["18-24", "25-34", "35-44", "45-59", "60+"], n), "Lembrança Espontânea": np.where(lembranca, "Sim", "Não"),
            "Nota de Consideração": np.clip(np.round(rng.normal(6.5, 2.0, n)), 0, 10).astype(int),
            "Data da Entrevista": _datas(rng, n, date(2026, 3, 1), 200)}


def _nps_de(serie) -> float:
    x = pd.to_numeric(serie, errors="coerce").dropna()   # quem não respondeu não entra na conta
    return float(((x >= 9).mean() - (x <= 6).mean()) * 100) if len(x) else 0.0


def _taxa_sim(df, col):
    return float((df[col].astype(str).str.strip().str.lower() == "sim").mean())


REGRAS: list[Regra] = [
    Regra("nps", "Pesquisa NPS de alunos", "pesquisa", "Respostas de NPS por curso, modalidade e UF.", "ID Resposta", "Curso",
          "Nota NPS", "nps", False, "NPS = % promotores (9–10) − % detratores (0–6)",
          ["nota 99 = não sabe", "nota como texto", "resposta duplicada", "data em texto"], _nps,
          lambda d, c: _nps_de(d[c["Nota NPS"]])),
    Regra("csat_ces", "Satisfação e esforço no atendimento", "pesquisa", "CSAT (1–5) e CES (1–7) por canal e motivo.",
          "Protocolo", "Canal de Atendimento", "Nota CSAT", "media", False, "CSAT top-2-box = % de notas 4 e 5",
          ["escala invertida", "nota fora da escala", "protocolo repetido"], _csat,
          lambda d, c: float((d[c["Nota CSAT"]].dropna() >= 4).mean() * 100)),
    Regra("churn", "Base de assinantes (churn e coorte)", "comercial", "Assinantes por plano e coorte de entrada.",
          "ID Cliente", "Plano", "Mensalidade", "media", True, "Churn = % de clientes que cancelaram",
          ["cancelamento com data anterior à entrada", "mensalidade zerada", "plano escrito de jeitos diferentes"], _churn,
          lambda d, c: _taxa_sim(d, c["Cancelou"]) * 100),
    Regra("rfm", "Clientes para RFM", "comercial", "Recência, frequência e valor por cliente.", "ID Cliente", "Canal",
          "Valor Total", "soma", True, "RFM: valor médio por cliente e frequência média",
          ["cliente duplicado com nome diferente", "valor negativo (estorno)"], _rfm,
          lambda d, c: float(d[c["Valor Total"]].mean())),
    Regra("curva_abc", "Faturamento por SKU (curva ABC)", "comercial", "Faturamento e margem por SKU e categoria.", "SKU",
          "Categoria", "Faturamento", "soma", True, "Curva ABC: % de SKUs que fazem 80% do faturamento",
          ["SKU com espaço no fim", "faturamento em texto americano"], _abc,
          lambda d, c: float((d[c["Faturamento"]].sort_values(ascending=False).cumsum()
                              <= 0.8 * d[c["Faturamento"]].sum()).mean() * 100)),
    Regra("funil", "Funil comercial por origem do lead", "marketing", "Oportunidades por origem e etapa do funil.",
          "ID Oportunidade", "Origem do Lead", "Valor da Oportunidade", "soma", True,
          "Conversão = ganhos ÷ oportunidades, por origem", ["etapa fora da ordem", "valor em milhar ('1,2 mil')"], _funil,
          lambda d, c: float((d[c["Etapa do Funil"]] == "Ganho").mean() * 100)),
    Regra("folha", "Folha de pagamento", "rh", "Salário base e horas extras por departamento e cargo.", "Matrícula",
          "Departamento", "Salário Base", "soma", True, "Custo de folha = soma dos salários base",
          ["matrícula repetida", "salário abaixo do mínimo", "CPF misturado"], _folha,
          lambda d, c: float(d[c["Salário Base"]].sum())),
    Regra("ponto", "Ponto e frequência", "rh", "Horas trabalhadas e atrasos por equipe e turno.", "ID Registro", "Equipe",
          "Horas Trabalhadas", "media", False, "Horas médias por dia e % de registros com atraso",
          ["batida duplicada", "horas acima de 12", "data em número de série"], _ponto,
          lambda d, c: float((d[c["Atraso (min)"]] > 0).mean() * 100)),
    Regra("estoque", "Estoque e ruptura", "operacoes", "Estoque e demanda diária por loja e categoria.", "ID Posição", "Loja",
          "Estoque (un)", "soma", False, "Ruptura = % de posições com estoque zero",
          ["estoque negativo", "loja escrita de jeitos diferentes"], _estoque,
          lambda d, c: _taxa_sim(d, c["Em Ruptura"]) * 100),
    Regra("logistica", "Entregas e prazo", "operacoes", "Atraso por transportadora e UF de destino.", "Pedido",
          "Transportadora", "Atraso (dias)", "media", False, "OTIF simplificado = % entregues sem atraso",
          ["atraso negativo", "atraso fora do padrão"], _logistica,
          lambda d, c: float((d[c["Atraso (dias)"]] <= 0).mean() * 100)),
    Regra("financeiro", "Contas a pagar e a receber", "financeiro", "Títulos por centro de custo, tipo e situação.",
          "Título", "Centro de Custo", "Valor do Título", "soma", True, "Inadimplência = % do valor vencido",
          ["valor com menos no fim (SAP)", "vencimento em texto"], _financeiro,
          lambda d, c: float(d.loc[d[c["Situação"]] == "Vencido", c["Valor do Título"]].sum()
                             / max(1e-9, d[c["Valor do Título"]].sum()) * 100)),
    Regra("leads", "Campanhas e leads (CAC, MQL)", "marketing", "Investimento, leads e MQL por canal.", "ID Campanha",
          "Canal", "Investimento", "soma", True, "Custo por lead = investimento ÷ leads",
          ["MQL maior que leads", "investimento em texto"], _leads,
          lambda d, c: float(d[c["Investimento"]].sum() / max(1e-9, d[c["Leads"]].sum()))),
    Regra("educacao", "Notas, frequência e evasão", "educacao", "Desempenho acadêmico por curso e semestre.", "Matrícula",
          "Curso", "Média Final", "media", False, "Evasão = % de alunos que evadiram",
          ["nota acima de 10", "frequência acima de 100%"], _educacao,
          lambda d, c: _taxa_sim(d, c["Evadiu"]) * 100),
    Regra("vendas", "Vendas por região e vendedor", "comercial", "Notas fiscais com quantidade e valor.", "Nota Fiscal",
          "Região", "Valor da Venda", "soma", True, "Ticket médio = valor ÷ notas",
          ["nota fiscal repetida", "valor em padrão americano"], _vendas,
          lambda d, c: float(d[c["Valor da Venda"]].mean())),
    Regra("pesquisa_mercado", "Pesquisa de mercado (marca)", "pesquisa", "Lembrança e consideração por marca e faixa etária.",
          "ID Entrevista", "Marca Avaliada", "Nota de Consideração", "media", False,
          "Lembrança espontânea = % que citou a marca sem ajuda", ["marca escrita de jeitos diferentes", "faixa etária vazia"],
          _pesquisa_mercado, lambda d, c: _taxa_sim(d, c["Lembrança Espontânea"]) * 100),
]
POR_ID = {r.id: r for r in REGRAS}


def regra_de_arquivo(item: dict) -> Regra:
    """Regra simples vinda de um .json (sem programar). Formato:
    {"id": "...", "nome": "...", "area": "...", "segmento": {"nome": "Loja", "valores": ["A", "B"]},
     "metrica": {"nome": "Valor", "min": 10, "max": 900, "moeda": true}, "op": "soma", "indicador": "..."}"""
    seg, met = item["segmento"], item["metrica"]

    def gerar(rng, n):
        return {"ID": _ids(rng, n), seg["nome"]: _escolha(rng, list(seg["valores"]), n),
                met["nome"]: np.round(rng.uniform(float(met["min"]), float(met["max"]), n), 2), "Data": _datas(rng, n)}
    return Regra(str(item["id"]), str(item["nome"]), str(item.get("area") or "outra"), str(item.get("descricao") or ""), "ID",
                 seg["nome"], met["nome"], str(item.get("op") or "soma"), bool(met.get("moeda")),
                 str(item.get("indicador") or f"{item.get('op', 'soma')} de {met['nome']}"), [], gerar,
                 lambda d, c: float(d[c[met["nome"]]].sum()))


def catalogo(cfg=None) -> list[Regra]:
    regras = list(REGRAS)
    extra = ((getattr(cfg, "dados", {}) or {}).get("fabrica") or {}).get("regras_extra") if cfg else None
    if extra:
        try:
            for item in json.loads(Path(extra).read_text(encoding="utf-8")):
                regras.append(regra_de_arquivo(item))
        except (OSError, ValueError, KeyError, TypeError):
            pass  # arquivo de regras com problema não derruba a fábrica: fica só o catálogo nativo
    return regras


def caso(regra: Regra, n: int, semente: int) -> dict:
    """O "caso" no formato do laboratório (rótulos → valores) para plantar sujeira e conhecer a verdade."""
    rng = np.random.default_rng(semente)
    rotulos = regra.gerar(rng, int(n))
    return {"area": regra.id, "n": int(n), "rotulos": {k: list(v) if not isinstance(v, list) else v for k, v in rotulos.items()},
            "segmento": regra.segmento, "metrica": regra.metrica, "op": regra.op, "moeda": regra.moeda}


def gabarito(regra: Regra, limpo: pd.DataFrame) -> dict:
    """A resposta certa, calculada da versão limpa: linhas, soma/média da métrica, linhas por segmento e o indicador."""
    from robo.limpeza import normalizar_nome_coluna
    cols = {c: normalizar_nome_coluna(c) for c in regra.gerar(np.random.default_rng(0), 3)}
    met, seg = cols[regra.metrica], cols[regra.segmento]
    x = pd.to_numeric(limpo[met], errors="coerce")
    try:
        indicador = regra.calcular_indicador(limpo, cols)
    except Exception:
        indicador = None
    return {"linhas": int(len(limpo)), "metrica": met, "segmento": seg, "soma_metrica": round(float(x.sum()), 4),
            "media_metrica": round(float(x.mean()), 6) if x.notna().any() else None, "nulos_metrica": int(x.isna().sum()),
            "por_segmento": {str(k): int(v) for k, v in limpo[seg].value_counts().items()},
            "indicador": {"nome": regra.indicador, "valor": None if indicador is None else round(float(indicador), 6)},
            **({"drivers": {"alvo": met, "ordem": [normalizar_nome_coluna(a) for a in sorted(PESOS_NPS, key=lambda a: -PESOS_NPS[a])],
                            "pesos": {normalizar_nome_coluna(a): w for a, w in PESOS_NPS.items()}}} if regra.id == "nps" else {})}
