"""Laboratório: a empresa treina sem parar com planilhas de várias áreas, no Excel e no PostgreSQL.

Enquanto o notebook estiver ligado (não depende de celular, internet nem de créditos de nenhum serviço), a cada poucos
minutos o laboratório:
  1. gera uma planilha de uma área (educação/NPS, varejo, RH, financeiro, marketing, logística), com semente nova —
     cada rodada é um caso diferente — e SUJA de propósito: título acima do cabeçalho, nomes com acento e espaço,
     valores "R$ 1.234,56", datas em texto, linha duplicada e linha de Total;
  2. como o gerador conhece a resposta certa (a planilha nasceu limpa), cada etapa é conferida com a verdade:
       Leo/Lia (engenharia)   — o pipeline real em diagnóstico acha o cabeçalho, converte e limpa as linhas certas;
       Davi (análise)         — a calculadora entende o pedido e dá o número certo por segmento;
       cientistas             — drivers, segmentação e anomalias acham o que foi plantado;
       Dora (DBA)             — a mesma base carregada no PostgreSQL (schema laboratorio) dá o mesmo número em SQL;
       guilda Python          — revisão de uma biblioteca por rodada + avisos de depreciação do código do robô;
       TI                     — tempo por volume, para a visão estratégica (projeção para 100 e 300 mil linhas);
  3. acerto e erro vão para a memória de cada um; erro vira handover e o responsável pede ajuda a quem sabe.
Os dados do laboratório são SINTÉTICOS e ficam separados: pasta logs/laboratorio e schema laboratorio no banco.
Nada entra em Bases-Tratadas, no histórico de produção nem nas tabelas de produção.
"""

from __future__ import annotations

import copy
import json
import math
import shutil
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from robo.limpeza import normalizar_nome_coluna
from robo.trabalho import Trabalho, _agora

AREAS = ["educacao_nps", "varejo", "rh", "financeiro", "marketing", "logistica"]
ESQUEMA = """
CREATE TABLE IF NOT EXISTS laboratorio_exercicios (
  id INTEGER PRIMARY KEY AUTOINCREMENT, rodada TEXT, data_hora TEXT, area TEXT, semente INTEGER, etapa TEXT,
  responsavel TEXT, ok INTEGER, detalhe TEXT, segundos REAL);
CREATE INDEX IF NOT EXISTS ix_lab_resp ON laboratorio_exercicios(responsavel, id);
CREATE TABLE IF NOT EXISTS laboratorio_medidas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, area TEXT, linhas INTEGER, segundos REAL);
"""
PADRAO = {"habilitado": True, "intervalo_minutos": 10}


def _c(cfg) -> dict:
    return {**PADRAO, **((getattr(cfg, "dados", {}) or {}).get("laboratorio") or {})}


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
    return tb


# =============================================================================== gerador de casos
def _br(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar(area: str, semente: int) -> dict:
    """Base LIMPA (a verdade) + rótulos sujos do cabeçalho + o que foi plantado."""
    rng = np.random.default_rng(semente)
    n = int(rng.integers(150, 400))
    d0 = date(2026, 1, 1)
    datas = [d0 + timedelta(days=int(x)) for x in rng.integers(0, 300, n)]
    ids = rng.permutation(np.arange(10_000, 10_000 + n))  # toda base real tem identificador da linha
    if area == "educacao_nps":
        cursos = rng.choice(["Direito", "Medicina", "Engenharia", "Pedagogia"], n)
        base = {"Direito": 8.0, "Medicina": 6.0, "Engenharia": 7.0, "Pedagogia": 9.0}
        nota = np.clip(np.round([rng.normal(base[c], 2) for c in cursos]), 0, 10).astype(int)
        rotulos = {"ID": ids, "Curso": cursos, "Modalidade": rng.choice(["EAD", "Presencial"], n), "Nota NPS": nota,
                   "Data da Resposta": datas}
        return {"area": area, "n": n, "rotulos": rotulos, "segmento": "Curso", "metrica": "Nota NPS", "op": "nps", "moeda": False}
    if area == "varejo":
        regiao = rng.choice(["Norte", "Sul", "Sudeste", "Nordeste", "Centro-Oeste"], n)
        valor = np.round(rng.lognormal(6, 0.6, n), 2)
        rotulos = {"ID": ids, "Região": regiao, "Canal de Venda": rng.choice(["Loja", "App", "Site"], n), "Valor da Venda": valor,
                   "Data": datas}
        return {"area": area, "n": n, "rotulos": rotulos, "segmento": "Região", "metrica": "Valor da Venda", "op": "media", "moeda": True}
    if area == "rh":
        grupo = rng.random(n) < 0.5  # dois perfis claros: júnior e sênior
        salario = np.round(np.where(grupo, rng.normal(3500, 300, n), rng.normal(12000, 900, n)), 2)
        tempo = np.round(np.where(grupo, rng.normal(1.5, 0.5, n), rng.normal(9, 1.2, n)), 1)
        rotulos = {"ID": ids, "Departamento": rng.choice(["Vendas", "TI", "Operações"], n), "Salário": salario,
                   "Tempo de Casa (anos)": tempo}
        return {"area": area, "n": n, "rotulos": rotulos, "segmento": "Departamento", "metrica": "Salário", "op": "media",
                "moeda": True, "segmentos_esperados": 2, "colunas_segmentacao": ["Salário", "Tempo de Casa (anos)"]}
    if area == "financeiro":
        rotulos = {"ID": ids, "Centro de Custo": rng.choice(["Adm", "Comercial", "Fábrica", "Logística"], n),
                   "Conta Contábil": rng.choice(["Pessoal", "Aluguel", "Energia", "Serviços"], n),
                   "Valor Lançado": np.round(rng.normal(5000, 2500, n), 2), "Data do Lançamento": datas}
        return {"area": area, "n": n, "rotulos": rotulos, "segmento": "Centro de Custo", "metrica": "Valor Lançado",
                "op": "soma", "moeda": True}
    if area == "marketing":
        invest = np.round(rng.uniform(500, 20000, n), 2)
        cliques = np.round(invest * 0.8 + rng.normal(0, 400, n))
        ctr = np.round(rng.uniform(0.5, 5, n), 2)
        conversoes = np.round(cliques * 0.05 + rng.normal(0, 15, n))
        rotulos = {"ID": ids, "Canal": rng.choice(["Google", "Meta", "TikTok", "E-mail"], n), "Investimento": invest,
                   "Cliques": cliques, "CTR (%)": ctr, "Conversões": conversoes}
        return {"area": area, "n": n, "rotulos": rotulos, "segmento": "Canal", "metrica": "Conversões", "op": "soma",
                "moeda": False, "driver_alvo": "Conversões", "driver_esperado": "Cliques"}
    if area == "logistica":
        atraso = np.round(np.abs(rng.normal(1, 1, n)), 1)
        plantados = rng.choice(n, 3, replace=False)
        atraso[plantados] = [120.0, 150.0, 200.0]
        rotulos = {"ID": ids, "Transportadora": rng.choice(["Rápida", "Econômica", "Expressa"], n),
                   "Prazo (dias)": rng.integers(2, 10, n), "Atraso (dias)": atraso, "Data de Envio": datas}
        return {"area": area, "n": n, "rotulos": rotulos, "segmento": "Transportadora", "metrica": "Atraso (dias)",
                "op": "media", "moeda": False, "anomalia_coluna": "Atraso (dias)", "anomalias_plantadas": 3}
    raise ValueError(area)


def escrever_sujo(caso: dict, caminho: Path) -> None:
    """Planilha como chega na vida real: título, linha vazia, valores em R$, datas em texto, duplicata e Total."""
    from openpyxl import Workbook
    rot = caso["rotulos"]
    cab = list(rot)
    wb = Workbook()
    ws = wb.active
    ws.title = "Relatório"
    ws.append([f"Relatório gerado pelo laboratório — {caso['area']}"])
    ws.append([])
    ws.append([f"  {c} " if i % 2 else c.upper() if i == 0 else c for i, c in enumerate(cab)])
    linhas = []
    for i in range(caso["n"]):
        linha = []
        for c in cab:
            v = rot[c][i]
            if isinstance(v, date):
                v = v.strftime("%d/%m/%Y")
            elif c == caso["metrica"] and caso.get("moeda"):
                v = _br(float(v))
            elif isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating,)):
                v = float(v)
            elif isinstance(v, np.str_):
                v = str(v)
            linha.append(v)
        linhas.append(linha)
    for linha in linhas:
        ws.append(linha)
    ws.append(linhas[0])  # duplicata exata
    ws.append(["Total"] + [None] * (len(cab) - 1))
    wb.save(caminho)


def verdade(caso: dict) -> pd.DataFrame:
    return pd.DataFrame({normalizar_nome_coluna(c): v for c, v in caso["rotulos"].items()})


# =============================================================================== exercício
def _cfg_lab(cfg, pasta: Path):
    from robo.config import Config
    dados = copy.deepcopy(cfg.dados)
    dados["regras"] = []
    dados["pastas"] = {"entrada": str(pasta / "entrada"), "logs": str(pasta / "logs"), "agentes": str(pasta / "agentes"),
                       "habilidades": str(pasta / "habilidades")}
    (pasta / "entrada").mkdir(parents=True, exist_ok=True)
    return Config(dados, cfg.base)


def _valores_verdade(op: str, df: pd.DataFrame, col: str, por: str) -> dict:
    from robo import conferencia
    return conferencia.valores_pandas(op, df, col, [por])


def _iguais(a: dict, b: dict, tol: float = 1e-6) -> list[str]:
    erros = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if x is None or y is None or not math.isclose(x, y, rel_tol=tol, abs_tol=tol):
            erros.append(f"{k}: esperado {y}, obtido {x}")
    return erros


def exercicio(cfg, area: str | None = None, semente: int | None = None, gravar: bool = True,
              biblioteca: str | None = None) -> dict:
    """Um treino com resposta conhecida. gravar=False = reconferência (caderno de lições): refaz o MESMO caso e a
    MESMA biblioteca sem gravar nada (sem treino novo, sem acerto/erro, sem handover, sem pedido de ajuda)."""
    from robo import bibliotecas, calculos, ciencia, memoria
    from robo.pipeline import processar_arquivo
    tb = _tb(cfg)
    with tb.tx() as c:
        feitos = c.execute("SELECT COUNT(DISTINCT rodada) FROM laboratorio_exercicios").fetchone()[0]
    semente = int(semente if semente is not None else time.time_ns() % 2_000_000_000)
    area = area or AREAS[feitos % len(AREAS)]
    rodada = f"LAB-{datetime.now():%Y%m%d-%H%M%S}-{area}"
    caso = gerar(area, semente)
    certo = verdade(caso)
    seg, met = normalizar_nome_coluna(caso["segmento"]), normalizar_nome_coluna(caso["metrica"])
    pasta = Path(cfg.logs) / "laboratorio" / rodada
    resultados: list[dict] = []

    def registrar(etapa, resp, ok, detalhe, t0):
        resultados.append({"etapa": etapa, "responsavel": resp, "ok": bool(ok), "detalhe": detalhe,
                           "segundos": round(time.perf_counter() - t0, 3)})

    try:
        cfg_lab = _cfg_lab(cfg, pasta)
        arq = cfg_lab.entrada / f"lab_{area}_{semente}.xlsx"
        escrever_sujo(caso, arq)
        # ---- 1. engenharia: pipeline real em diagnóstico (e avisos de depreciação do código do robô)
        t0 = time.perf_counter()
        r, avisos = bibliotecas.capturar_depreciacoes(lambda: processar_arquivo(arq, cfg_lab, gravar=False))
        seg_pipeline = time.perf_counter() - t0
        tabs = dict(getattr(r.tratamento, "analisaveis", {}) or {}) if r.tratamento else {}
        df = next(iter(tabs.values()), None)
        faltam = [c for c in certo.columns if df is None or c not in df.columns]
        registrar("Achar o cabeçalho e os nomes das colunas", "leitura", not faltam,
                  "cabeçalho certo" if not faltam else f"colunas não encontradas: {faltam}; erros: "
                  + "; ".join(e.mensagem for e in r.relatorio.erros[:3]), t0)
        if df is not None and not faltam:
            ok_linhas = len(df) == caso["n"]
            ok_tipo = pd.api.types.is_numeric_dtype(df[met])
            soma_ok = ok_tipo and math.isclose(float(pd.to_numeric(df[met]).sum()), float(certo[met].sum()), rel_tol=1e-9, abs_tol=1e-6)
            registrar("Limpar: tirar Total e duplicata, converter R$ e números", "limpeza", ok_linhas and soma_ok,
                      f"{len(df)} linhas (esperado {caso['n']}); {met} numérica: {ok_tipo}; soma confere: {soma_ok}", t0)
        if gravar:
            with tb.tx() as c:
                c.execute("INSERT INTO laboratorio_medidas (data_hora, area, linhas, segundos) VALUES (?,?,?,?)",
                          (_agora(), area, caso["n"], round(seg_pipeline, 3)))
        for a in avisos:
            esp = bibliotecas.especialista_do_aviso(a)
            resultados.append({"etapa": "Código do robô sem aviso de depreciação", "responsavel": esp, "ok": False,
                               "detalhe": a, "segundos": 0.0})
        # ---- 2. análise: a calculadora entende o pedido e acerta o número por segmento
        if df is not None and not faltam:
            t0 = time.perf_counter()
            pergunta = {"nps": f"nps por {seg}", "media": f"média de {met} por {seg}", "soma": f"soma de {met} por {seg}"}[caso["op"]]
            resp = calculos.calcular(cfg_lab, pergunta, fontes={area: (df, arq.name)})
            calc = (resp or {}).get("calc")
            if not calc:
                registrar(f"Calcular “{pergunta}”", "analise_estatistica", False, f"não entendeu: {(resp or {}).get('texto', '')[:200]}", t0)
            else:
                obtido = _valores_verdade(calc["op"], calc["dados"], (calc["metricas"] or [None])[0], calc["por"][0] if calc["por"] else seg)
                esperado = _valores_verdade(caso["op"], certo, met, seg)
                dif = _iguais(obtido, esperado)
                registrar(f"Calcular “{pergunta}”", "analise_estatistica" if caso["op"] != "nps" else "analise_indicadores",
                          not dif and calc["op"] == caso["op"], "número certo em todos os grupos" if not dif else "; ".join(dif[:3]), t0)
        # ---- 3. ciência de dados: acha o que foi plantado
        if df is not None and not faltam:
            t0 = time.perf_counter()
            if caso.get("driver_alvo"):
                alvo, esperado = normalizar_nome_coluna(caso["driver_alvo"]), normalizar_nome_coluna(caso["driver_esperado"])
                dr = ciencia.drivers(df, alvo)
                topo = dr["drivers"][0]["atributo"] if dr.get("ok") else None
                registrar("Achar o driver plantado", "cd_senior_drivers", topo == esperado, f"1º driver: {topo} (plantado: {esperado})", t0)
            if caso.get("segmentos_esperados"):
                cols = [normalizar_nome_coluna(c) for c in caso["colunas_segmentacao"]]
                sg = ciencia.segmentar(df, cols)
                registrar("Achar os perfis plantados", "cd_pleno_segmentos", sg.get("ok") and sg["k"] == caso["segmentos_esperados"],
                          f"{sg.get('k')} grupo(s) (plantados: {caso['segmentos_esperados']}), silhueta {sg.get('silhueta', 0):.2f}", t0)
            if caso.get("anomalia_coluna"):
                col = normalizar_nome_coluna(caso["anomalia_coluna"])
                an = ciencia.anomalias(df, [col])
                achou = sum(a["quantidade"] for a in an["achados"] if a["coluna"] == col)
                registrar("Achar as anomalias plantadas", "cd_junior_anomalias", achou >= caso["anomalias_plantadas"],
                          f"{achou} achada(s) (plantadas: {caso['anomalias_plantadas']})", t0)
        # ---- 4. PostgreSQL: a mesma conta em SQL, no schema separado do laboratório
        if df is not None and not faltam and cfg.banco.get("habilitado"):
            t0 = time.perf_counter()
            try:
                obtido = _sql_no_banco(cfg, df, area, semente, caso["op"], met, seg)
                dif = _iguais(obtido, _valores_verdade(caso["op"], certo, met, seg), 1e-6)
                registrar("Mesma conta no PostgreSQL (schema laboratorio)", "dba", not dif,
                          "SQL bate com a verdade" if not dif else "; ".join(dif[:3]), t0)
            except Exception as e:
                registrar("Mesma conta no PostgreSQL (schema laboratorio)", "dba", False, f"{type(e).__name__}: {e}", t0)
        # ---- 5. guilda Python: uma biblioteca por rodada
        t0 = time.perf_counter()
        nome_lib = biblioteca if biblioteca in bibliotecas.BIBLIOTECAS else \
            list(bibliotecas.BIBLIOTECAS)[feitos % len(bibliotecas.BIBLIOTECAS)]
        rev = bibliotecas.revisar(nome_lib)
        registrar(f"Revisão da biblioteca {nome_lib} {rev['versao']}", rev["especialista"], rev["ok"],
                  "tudo como o robô espera" if rev["ok"] else "; ".join(rev["falhas"]), t0)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)

    falhas = [x for x in resultados if not x["ok"]]
    if not gravar:
        return {"rodada": rodada, "area": area, "semente": semente, "linhas": caso["n"], "etapas": len(resultados),
                "acertos": len(resultados) - len(falhas), "falhas": [f"{x['etapa']}: {x['detalhe'][:120]}" for x in falhas],
                "resultados": resultados}
    # ---- memória, handovers e pedidos de ajuda
    from robo import interacoes
    with tb.tx() as c:
        for x in resultados:
            c.execute("INSERT INTO laboratorio_exercicios (rodada, data_hora, area, semente, etapa, responsavel, ok, detalhe, segundos) "
                      "VALUES (?,?,?,?,?,?,?,?,?)", (rodada, _agora(), area, semente, x["etapa"], x["responsavel"], int(x["ok"]),
                                                     x["detalhe"][:1000], x["segundos"]))
    for x in resultados:
        memoria.experiencia(cfg, x["responsavel"], "acerto" if x["ok"] else "erro", f"Laboratório ({area}): {x['etapa']}",
                            "laboratorio", rodada, x["detalhe"], tb)
        if not x["ok"]:
            hid = memoria.handover(cfg, f"Laboratório: {x['etapa']} falhou — {x['detalhe'][:200]}", f"lab_{area}", x["responsavel"],
                                   f"semente {semente}", tb)
            interacoes.pedir_ajuda(cfg, x["responsavel"], f"{x['etapa']}: {x['detalhe'][:160]}", hid)
    return {"rodada": rodada, "area": area, "semente": semente, "linhas": caso["n"], "etapas": len(resultados),
            "acertos": len(resultados) - len(falhas), "falhas": [f"{x['etapa']}: {x['detalhe'][:120]}" for x in falhas]}


def _sql_no_banco(cfg, df: pd.DataFrame, area: str, semente: int, op: str, met: str, seg: str) -> dict:
    from psycopg import sql

    from robo import conferencia
    from robo.banco import Banco, tipo_pg
    b = Banco(cfg.banco, cfg.base)
    b.criar_banco_se_preciso()  # igual à produção: cria o banco na primeira vez
    tabela = f"lab_{area}_{semente}"
    dados = df[[seg, met]].copy()
    tipos = {c: tipo_pg(dados[c]) for c in dados.columns}
    with b.conectar() as conn:
        with conn.transaction():
            conn.execute("CREATE SCHEMA IF NOT EXISTS laboratorio")
            tipos = b._garantir_tabela(conn, "laboratorio", tabela, tipos)
            b._copiar(conn, "laboratorio", tabela, dados, tipos)
            consulta = conferencia.montar_sql(op, met, [seg], [], f'"laboratorio"."{tabela}"', None)
            linhas = conn.execute(consulta).fetchall()
            conn.execute(sql.SQL("DROP TABLE {}").format(sql.Identifier("laboratorio", tabela)))
    return {conferencia._chave(r[0]): float(r[1]) for r in linhas}


# =============================================================================== consulta e rotina
def resumo(cfg, dias: int = 7) -> dict:
    tb = _tb(cfg)
    desde = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    with tb.tx() as c:
        por = [dict(r) for r in c.execute(
            "SELECT responsavel, SUM(ok) acertos, COUNT(*) - SUM(ok) erros FROM laboratorio_exercicios WHERE data_hora>=? "
            "GROUP BY responsavel ORDER BY erros DESC", (desde,))]
        rodadas = c.execute("SELECT COUNT(DISTINCT rodada) FROM laboratorio_exercicios WHERE data_hora>=?", (desde,)).fetchone()[0]
        areas = {r["area"]: r["n"] for r in c.execute(
            "SELECT area, COUNT(DISTINCT rodada) n FROM laboratorio_exercicios WHERE data_hora>=? GROUP BY area", (desde,))}
        ultimas = [dict(r) for r in c.execute("SELECT * FROM laboratorio_exercicios ORDER BY id DESC LIMIT 30")]
    return {"rodadas": rodadas, "por_area": areas, "por_pessoa": por, "ultimas": ultimas}


def estrategia_ti(cfg) -> dict:
    """Visão estratégica da TI Python: velocidade por volume, projeção e o que ameaça a operação."""
    from robo import memoria
    tb = _tb(cfg)
    with tb.tx() as c:
        med = [dict(r) for r in c.execute("SELECT * FROM laboratorio_medidas ORDER BY id DESC LIMIT 200")]
    linhas = []
    proj = {}
    if len(med) >= 5:
        x = np.array([m["linhas"] for m in med], float)
        y = np.array([m["segundos"] for m in med], float)
        b, a = np.polyfit(x, y, 1)
        por_mil = max(b, 1e-9) * 1000
        proj = {n: a + b * n for n in (10_000, 100_000, 300_000)}
        linhas.append(f"Velocidade medida em {len(med)} rodadas: {por_mil:.2f} s a cada mil linhas (mais {a:.1f} s fixos).")
        linhas.append("Projeção (linear, sem contar o banco): " + "; ".join(f"{n:,} linhas ≈ {s / 60:.1f} min".replace(",", ".")
                                                                            for n, s in proj.items()) + ".")
        recentes, antigas = y[: len(y) // 2] / x[: len(x) // 2], y[len(y) // 2:] / x[len(x) // 2:]
        if antigas.mean() and recentes.mean() > antigas.mean() * 1.25:
            linhas.append("⚠ O tempo por linha piorou mais de 25% nas rodadas recentes: investigar antes de aumentar volume.")
    else:
        linhas.append(f"Só {len(med)} medida(s) até agora; a projeção sai com 5 ou mais rodadas do laboratório.")
    defeitos = [h for h in memoria.handovers(cfg, 5, abertos=True, limite=200)]
    linhas.append(f"Dívida técnica aberta no 5º andar: {len(defeitos)} handover(s)" +
                  (" — " + "; ".join(h["erro"][:80] for h in defeitos[:3]) if defeitos else "."))
    return {"texto": "\n".join(linhas), "projecao_segundos": proj, "medidas": len(med)}


def rotina(cfg) -> dict | None:
    c = _c(cfg)
    if not c.get("habilitado", True):
        return None
    tb = _tb(cfg)
    with tb.tx() as conn:
        u = conn.execute("SELECT data_hora FROM laboratorio_exercicios ORDER BY id DESC LIMIT 1").fetchone()
    if u and datetime.fromisoformat(u[0]) > datetime.now() - timedelta(minutes=float(c["intervalo_minutos"])):
        return None
    return exercicio(cfg)
