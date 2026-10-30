"""Cenários sintéticos com GABARITO TRIPLO — a prova de que a esteira (robo/entrega.py) é confiável.

Um cenário é uma planilha de clientes (até 100 mil linhas) gerada em três camadas:

  1. MUNDO LIMPO com regra conhecida: a chance de cancelar é uma fórmula que nós escrevemos (chamados, uso do app,
     atraso de pagamento e plano pesam; região, canal, idade, dia de vencimento e campanha NÃO pesam — são ruído).
     Uma coluna de vazamento (motivo_cancelamento só existe para quem cancelou) é plantada de propósito.
  2. SUJEIRA com manifesto: cada erro plantado é anotado (id do cliente, coluna, tipo, valor certo):
       grafia ('sudeste ', 'SUDESTE'), duplicata exata, quase-duplicata (mesmo id, valor diferente), idade impossível,
       valor negativo, data no futuro, erro de digitação 1000x, vazios, e formatos (R$ 1.234,56, data em texto).
  3. GABARITO TRIPLO:
       números — linhas depois da limpeza, soma do valor como está na planilha e a soma "verdadeira" sem os erros;
       erros   — a lista exata do que foi plantado (para medir quanto a esteira detecta e quanto alarma à toa);
       ML      — o veredito esperado ("vale"), os fatores verdadeiros, o ruído e o vazamento.

placar() roda a esteira de verdade (entrega.entregar) em cada cenário, lê o que ela gravou e compara com o gabarito.
Determinístico: mesma semente, mesma planilha, mesmo placar.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("robo")

MAX_LINHAS = 100_000
REGIOES = (["Sudeste", "Sul", "Nordeste", "Norte", "Centro-Oeste"], [42, 15, 26, 9, 8])
PLANOS = (["Básico", "Padrão", "Premium"], [50, 32, 18])
CANAIS = ["Site", "Loja", "Indicação", "Parceiro"]
CAMPANHAS = ["CMP-A", "CMP-B", "CMP-C", "CMP-D", "CMP-E", "CMP-F"]
MOTIVOS = ["Preço", "Atendimento", "Mudou de cidade", "Concorrente", "Qualidade"]
MENSAL = {"Básico": 59.9, "Padrão": 99.9, "Premium": 179.9}
DRIVERS = ["chamados_90d", "uso_app_horas", "atraso_pagamento_dias", "plano"]
RUIDO = ["regiao", "canal_aquisicao", "idade", "dia_vencimento", "codigo_campanha"]
VAZAMENTO = "motivo_cancelamento"

# taxas de cada erro (fração das linhas); "nivel" multiplica
TAXAS = {"grafia": 0.03, "duplicata": 0.01, "quase_duplicata": 0.004, "idade_impossivel": 0.004,
         "valor_negativo": 0.003, "data_futura": 0.003, "digitacao_1000x": 0.002, "vazio": 0.02, "formato": 0.05}


def _mundo(rng, n: int, hoje: date) -> pd.DataFrame:
    regiao = rng.choice(REGIOES[0], n, p=np.array(REGIOES[1]) / sum(REGIOES[1]))
    plano = rng.choice(PLANOS[0], n, p=np.array(PLANOS[1]) / sum(PLANOS[1]))
    entrada = pd.Timestamp("2023-01-01") + pd.to_timedelta(rng.integers(0, (hoje - date(2023, 1, 1)).days - 30, n), "D")
    chamados = rng.poisson(np.where(plano == "Básico", 2.2, np.where(plano == "Padrão", 1.6, 1.1)))
    uso = np.round(rng.gamma(2.0, 6.0, n), 1)
    atraso = np.round(rng.gamma(1.2, 4.0, n)).astype(int)
    z = (-2.0 + 0.45 * chamados - 0.06 * uso + 0.05 * atraso
         + np.where(plano == "Básico", 0.5, np.where(plano == "Premium", -0.6, 0.0)))
    cancelou = rng.random(n) < 1 / (1 + np.exp(-z))
    df = pd.DataFrame({
        "ID Cliente": np.arange(1, n + 1) + 500_000,
        "Data de Entrada": entrada.normalize(),
        "Região": regiao, "Plano": plano,
        "Canal de Aquisição": rng.choice(CANAIS, n),
        "Idade": rng.integers(18, 80, n),
        "Valor Mensal": np.round([MENSAL[p] * f for p, f in zip(plano, rng.uniform(0.85, 1.15, n))], 2),
        "Chamados 90d": chamados, "Uso App Horas": uso, "Atraso Pagamento Dias": atraso,
        "Dia Vencimento": rng.integers(1, 29, n), "Código Campanha": rng.choice(CAMPANHAS, n),
        "Cancelou": np.where(cancelou, "Sim", "Não"),
        "Motivo Cancelamento": np.where(cancelou, rng.choice(MOTIVOS, n), "(não cancelou)"),
    })
    return df


def _variante(rng, v: str) -> str:
    opcoes = [v.lower(), v.upper(), f"{v} ", f" {v}", v.lower() + "  "]
    if any(c in v for c in "áéíóúãõâêç"):
        from robo.limpeza import sem_acento
        opcoes.append(sem_acento(v))
    return opcoes[int(rng.integers(len(opcoes)))]


def gerar(n: int = 10_000, semente: int = 1, nivel: float = 1.0) -> dict:
    """Devolve {sujo: DataFrame (o que vai para a planilha), limpo: DataFrame (a verdade), manifesto: [...],
    gabarito: {...}}."""
    if not 200 <= n <= MAX_LINHAS:
        raise ValueError(f"linhas deve estar entre 200 e {MAX_LINHAS:,}".replace(",", "."))
    rng = np.random.default_rng(semente)
    hoje = date.today()  # o mundo termina hoje: data depois disso é erro (relativo, para o teste não envelhecer)
    limpo = _mundo(rng, n, hoje)
    sujo = limpo.astype(object).copy()
    manifesto: list[dict] = []
    usados: set[int] = set()

    def escolher(tipo: str) -> list[int]:
        k = max(2, int(round(TAXAS[tipo] * nivel * n)))
        livres = np.setdiff1d(np.arange(n), np.fromiter(usados, int)) if usados else np.arange(n)
        idx = sorted(int(i) for i in rng.choice(livres, min(k, len(livres)), replace=False))
        usados.update(idx)
        return idx

    def anotar(i, tipo, coluna, certo, escrito):
        manifesto.append({"id": int(limpo.at[i, "ID Cliente"]), "tipo": tipo, "coluna": coluna,
                          "certo": None if pd.isna(certo) else str(certo), "escrito": str(escrito)})

    # erros de CONTEÚDO (a esteira deve DETECTAR; não tem como adivinhar o valor certo)
    for i in escolher("idade_impossivel"):
        v = int(rng.choice([-5, 150, 230, 999]))
        anotar(i, "idade_impossivel", "Idade", limpo.at[i, "Idade"], v)
        sujo.at[i, "Idade"] = v
    for i in escolher("valor_negativo"):
        v = -float(limpo.at[i, "Valor Mensal"])
        anotar(i, "valor_negativo", "Valor Mensal", limpo.at[i, "Valor Mensal"], v)
        sujo.at[i, "Valor Mensal"] = v
    for i in escolher("digitacao_1000x"):
        v = round(float(limpo.at[i, "Valor Mensal"]) * 1000, 2)
        anotar(i, "digitacao_1000x", "Valor Mensal", limpo.at[i, "Valor Mensal"], v)
        sujo.at[i, "Valor Mensal"] = v
    for i in escolher("data_futura"):
        v = pd.Timestamp(hoje) + timedelta(days=int(rng.integers(400, 4000)))
        anotar(i, "data_futura", "Data de Entrada", limpo.at[i, "Data de Entrada"].date(), v.date())
        sujo.at[i, "Data de Entrada"] = v
    quase = escolher("quase_duplicata")
    # erros que a esteira deve CORRIGIR sozinha
    for i in escolher("grafia"):
        col = "Região" if rng.random() < 0.7 else "Plano"
        v = _variante(rng, str(limpo.at[i, col]))
        anotar(i, "grafia", col, limpo.at[i, col], v)
        sujo.at[i, col] = v
    for i in escolher("vazio"):
        col = str(rng.choice(["Uso App Horas", "Canal de Aquisição", "Atraso Pagamento Dias"]))
        anotar(i, "vazio", col, limpo.at[i, col], "")
        sujo.at[i, col] = None
    for i in escolher("formato"):
        if rng.random() < 0.5:
            v = float(limpo.at[i, "Valor Mensal"])
            sujo.at[i, "Valor Mensal"] = "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            anotar(i, "formato", "Valor Mensal", v, sujo.at[i, "Valor Mensal"])
        else:
            d = limpo.at[i, "Data de Entrada"]
            sujo.at[i, "Data de Entrada"] = d.strftime("%d/%m/%Y")
            anotar(i, "formato", "Data de Entrada", d.date(), sujo.at[i, "Data de Entrada"])
    linhas = [sujo]
    dup = escolher("duplicata")
    for i in dup:
        anotar(i, "duplicata", "(linha inteira)", "", "cópia exata")
    linhas.append(sujo.iloc[dup])
    copia = sujo.iloc[quase].copy()
    for j, i in enumerate(quase):
        anotar(i, "quase_duplicata", "Valor Mensal", limpo.at[i, "Valor Mensal"], "mesmo id, valor diferente")
        copia.iat[j, copia.columns.get_loc("Valor Mensal")] = round(float(limpo.at[i, "Valor Mensal"]) + 0.01, 2)
    linhas.append(copia)
    sujo = pd.concat(linhas, ignore_index=True)
    sujo = sujo.sample(frac=1, random_state=semente).reset_index(drop=True)  # duplicatas espalhadas, não no fim

    # gabarito de NÚMEROS: o que a esteira deve produzir lendo a planilha como ela é (sem as cópias exatas)
    sem_dup = sujo.drop_duplicates()
    valores = pd.to_numeric(sem_dup["Valor Mensal"].map(_valor), errors="coerce")
    gabarito = {
        "semente": semente, "linhas_geradas": n, "nivel": nivel, "referencia": hoje.isoformat(),
        "numeros": {"linhas_planilha": int(len(sujo)), "linhas_apos_limpeza": int(len(sem_dup)),
                    "duplicatas_exatas": int(len(sujo) - len(sem_dup)),
                    "soma_valor_mensal_como_esta": round(float(valores.sum()), 2),
                    "soma_valor_mensal_verdadeira": round(float(limpo["Valor Mensal"].sum()), 2),
                    "regioes": sorted(REGIOES[0]), "planos": sorted(PLANOS[0]),
                    "taxa_cancelamento": round(float((limpo["Cancelou"] == "Sim").mean()), 4)},
        "erros": {t: sorted({m["id"] for m in manifesto if m["tipo"] == t}) for t in TAXAS},
        "ml": {"alvo": "cancelou", "vale": True, "drivers": DRIVERS, "ruido": RUIDO, "vazamento": VAZAMENTO},
    }
    return {"sujo": sujo, "limpo": limpo, "manifesto": manifesto, "gabarito": gabarito}


def _valor(v):
    if isinstance(v, str):
        return float(v.replace("R$", "").strip().replace(".", "").replace(",", "."))
    return v


def gravar(cen: dict, pasta: Path, nome: str | None = None) -> Path:
    """Planilha (o que a esteira recebe) + gabarito e manifesto (ficam de fora, só o placar lê)."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    nome = nome or f"cenario_clientes_s{cen['gabarito']['semente']}_n{cen['gabarito']['linhas_geradas']}"
    arq = pasta / f"{nome}.xlsx"
    cen["sujo"].to_excel(arq, index=False, sheet_name="clientes")
    (pasta / f"{nome}.gabarito.json").write_text(
        json.dumps({**cen["gabarito"], "manifesto": cen["manifesto"]}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    return arq


# =============================================================================== placar
DETECTAVEIS = ("idade_impossivel", "valor_negativo", "data_futura", "digitacao_1000x", "quase_duplicata")


def _item(nome: str, ok: bool, detalhe: str, grupo: str) -> dict:
    return {"grupo": grupo, "verificacao": nome, "ok": bool(ok), "detalhe": detalhe}


def avaliar(pasta_entrega: Path, gab: dict) -> dict:
    """Compara o que a esteira gravou (base_tratada, indicadores, manifesto) com o gabarito."""
    pasta = Path(pasta_entrega)
    base = pd.read_excel(pasta / "base_tratada.xlsx")
    ind = pd.read_excel(pasta / "indicadores.xlsx", sheet_name=None)
    man = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    g = gab["numeros"]
    itens = []
    # números
    itens.append(_item("Linhas depois da limpeza (cópias exatas removidas)", len(base) == g["linhas_apos_limpeza"],
                       f"esteira {len(base)} · gabarito {g['linhas_apos_limpeza']}", "Números"))
    soma = float(pd.to_numeric(base["valor_mensal"], errors="coerce").sum())
    itens.append(_item("Soma do valor mensal (lido como está)", abs(soma - g["soma_valor_mensal_como_esta"]) < 0.01,
                       f"esteira {soma:,.2f} · gabarito {g['soma_valor_mensal_como_esta']:,.2f} · sem os erros seria "
                       f"{g['soma_valor_mensal_verdadeira']:,.2f}", "Números"))
    itens.append(_item("Certificado da própria esteira", bool(man.get("todas_ok")),
                       f"{sum(c['ok'] for c in man['conferencias'])} de {len(man['conferencias'])}", "Números"))
    # correções automáticas
    for col, certo in (("regiao", g["regioes"]), ("plano", g["planos"])):
        achado = sorted(base[col].dropna().astype(str).unique())
        itens.append(_item(f"Grafias de {col} unificadas", achado == certo,
                           f"{len(achado)} valores: {', '.join(achado[:8])}", "Correções"))
    # detecção
    sus = ind.get("suspeitos", pd.DataFrame(columns=["chave", "regra"]))
    ids_sus = set(pd.to_numeric(sus.get("chave", pd.Series(dtype=float)), errors="coerce").dropna().astype(int))
    plantados = set()
    for t in DETECTAVEIS:
        ids = set(gab["erros"][t])
        plantados |= ids
        achou = len(ids & ids_sus)
        itens.append(_item(f"Detecção: {t.replace('_', ' ')}", achou / len(ids) >= 0.9 if ids else True,
                           f"{achou} de {len(ids)} ({100 * achou / max(1, len(ids)):.0f}%)", "Detecção"))
    falsos = len(ids_sus - plantados)
    precisao = len(ids_sus & plantados) / max(1, len(ids_sus))
    itens.append(_item("Alarmes falsos (suspeito sem erro plantado)", precisao >= 0.8,
                       f"{falsos} de {len(ids_sus)} clientes apontados · precisão {100 * precisao:.0f}%", "Detecção"))
    # ML
    ml = man.get("ml") or {}
    gm = gab["ml"]
    itens.append(_item("ML: veredito", ml.get("ok") and ml.get("vale") == gm["vale"],
                       ml.get("veredito") or ml.get("motivo") or "não rodou", "ML"))
    vaz = [v["coluna"] for v in ml.get("vazamentos", [])]
    itens.append(_item("ML: vazamento retirado", gm["vazamento"] in vaz, f"retiradas: {', '.join(vaz) or 'nenhuma'}", "ML"))
    imp = [x for x in ml.get("importancias", []) if x["importancia"] > 0]
    top = [x["variavel"] for x in imp[:len(gm["drivers"])]]
    acertos = len(set(top) & set(gm["drivers"]))
    itens.append(_item("ML: fatores verdadeiros no topo", acertos >= len(gm["drivers"]) - 1,
                       f"{acertos} de {len(gm['drivers'])} no topo: {', '.join(top)}", "ML"))
    ruido_alto = [x["variavel"] for x in imp if x["variavel"] in gm["ruido"] and
                  x["importancia"] > 2 * max(x.get("desvio", 0), 0.005)]
    itens.append(_item("ML: ruído ignorado", not ruido_alto, f"ruído com peso: {', '.join(ruido_alto) or 'nenhum'}", "ML"))
    return {"itens": itens, "ok": sum(i["ok"] for i in itens), "total": len(itens)}


def placar(cfg, cenarios: int = 3, linhas: int = 5000, pasta: Path | None = None, semente_inicial: int = 1,
           nivel: float = 1.0) -> dict:
    """Gera N cenários, roda a esteira completa em cada um e compara com o gabarito. Grava placar.json."""
    from robo import entrega
    if linhas > MAX_LINHAS:
        raise ValueError(f"máximo de {MAX_LINHAS:,} linhas".replace(",", "."))
    pasta = Path(pasta or Path(cfg.logs) / "placar") / datetime.now().strftime("%Y%m%d_%H%M%S")
    resultados = []
    for k in range(cenarios):
        sem = semente_inicial + k
        inicio = time.perf_counter()
        cen = gerar(linhas, sem, nivel)
        arq = gravar(cen, pasta / "planilhas")
        r = entrega.entregar(cfg, arq, pasta / "entregas", alvo="Cancelou")
        av = avaliar(Path(r["pasta"]), cen["gabarito"])
        resultados.append({"semente": sem, "linhas": linhas, "segundos": round(time.perf_counter() - inicio, 1),
                           "entrega": r["pasta"], **av})
    total = sum(x["total"] for x in resultados)
    ok = sum(x["ok"] for x in resultados)
    falhas: dict[str, int] = {}
    for x in resultados:
        for i in x["itens"]:
            if not i["ok"]:
                falhas[i["verificacao"]] = falhas.get(i["verificacao"], 0) + 1
    res = {"gerado_em": datetime.now().isoformat(timespec="seconds"), "cenarios": resultados, "acertos": ok,
           "verificacoes": total, "pct": round(100 * ok / max(1, total), 1), "falhas": falhas, "pasta": str(pasta)}
    (pasta / "placar.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return res
