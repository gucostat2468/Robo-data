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
NIVEIS = {1: "básico (título, R$, data em texto, duplicata, Total)",
          2: "escritório (título em várias linhas, nulos como '-' e 'N/A', subtotal no meio, espaços sobrando)",
          3: "exportação de sistema (número americano, datas misturadas com número de série, coluna vazia, rodapé)",
          4: "formatos difíceis de número (menos no fim como no SAP, sinal − copiado de PDF, '1,2 mil')",
          5: "sistema antigo (cabeçalho em duas linhas, cabeçalho repetido a cada página, linhas vazias no meio, "
             "negativo contábil entre parênteses, milhar separado por espaço)"}
_prontos: set[str] = set()


def _c(cfg) -> dict:
    return {**PADRAO, **((getattr(cfg, "dados", {}) or {}).get("laboratorio") or {})}


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    if str(tb.arquivo) not in _prontos or not tb.arquivo.exists():
        with tb.tx() as c:
            c.executescript(ESQUEMA)
            from robo.trabalho import proteger
            proteger(c)
            if "nivel" not in {r[1] for r in c.execute("PRAGMA table_info(laboratorio_exercicios)")}:
                c.execute("ALTER TABLE laboratorio_exercicios ADD COLUMN nivel INTEGER DEFAULT 1")
        _prontos.add(str(tb.arquivo))
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


def _etapa_base_lab(etapa: str) -> str:
    """'Revisão da biblioteca numpy 2.5.3' → 'Revisão da biblioteca numpy' (a versão muda; o assunto não)."""
    import re
    return re.sub(r"\s+\d+(\.\d+)+\S*$", "", str(etapa).strip())


def aplicar_nivel(caso: dict, nivel: int, semente: int) -> dict:
    """Planta a sujeira do nível e ajusta a VERDADE (ex.: célula com '-' vira vazio na resposta certa)."""
    caso = {**caso, "nivel": nivel, "rotulos": {k: np.array(v, dtype=object) if k == caso["metrica"] else v
                                                for k, v in caso["rotulos"].items()}}
    rng = np.random.default_rng(semente + 7 * nivel)
    if nivel >= 2:
        nulos = sorted(int(i) for i in rng.choice(caso["n"], max(3, caso["n"] // 30), replace=False))
        caso["nulos"] = nulos
        met = caso["rotulos"][caso["metrica"]]
        for i in nulos:
            met[i] = None
        caso["subtotal_em"] = int(caso["n"] // 2)
    if nivel >= 4 and caso.get("moeda"):
        met = caso["rotulos"][caso["metrica"]]
        formatos = {}
        for i in range(caso["n"]):
            if met[i] is None:
                continue
            if i % 7 == 3:  # valor grande escrito "1,2 mil": a VERDADE passa a ser o valor arredondado que foi escrito
                met[i] = round(float(met[i]) / 100) * 100.0 or 100.0
                formatos[i] = "mil"
            elif caso["area"] == "financeiro" and i % 5 == 1:  # estornos negativos em formatos de sistema
                met[i] = -abs(float(met[i]))
                formatos[i] = ["sap", "unicode"][i % 2]
        caso["formatos"] = formatos
    if nivel >= 5:  # sistema antigo: formatos de número que planilha de verdade traz e que confundem conversão
        met = caso["rotulos"][caso["metrica"]]
        formatos = caso.setdefault("formatos", {})
        for i in range(caso["n"]):
            if met[i] is None or i in formatos:
                continue
            if caso.get("moeda") and i % 9 == 4:  # estorno contábil: (1.234,56) é NEGATIVO
                met[i] = -abs(float(met[i]))
                formatos[i] = "parenteses"
            elif i % 11 == 6 and abs(float(met[i])) >= 1000:  # 12 345,67 com espaço fino (exportação francesa/ERP)
                formatos[i] = "espaco"
    return caso


def escrever_sujo(caso: dict, caminho: Path) -> None:
    """Planilha como chega na vida real, com a sujeira do nível do caso (1 a 5)."""
    from openpyxl import Workbook
    nivel = caso.get("nivel", 1)
    rot = caso["rotulos"]
    cab = list(rot)
    met = caso["metrica"]
    rng = np.random.default_rng(caso["n"] * 31 + nivel)
    wb = Workbook()
    ws = wb.active
    ws.title = "Relatório"
    ws.append([f"Relatório gerado pelo laboratório — {caso['area']}"])
    if nivel >= 2:
        ws.append(["Fonte: ERP corporativo"])
        ws.append(["Período: jan a out/2026"])
    ws.append([])
    cab_escrito = [f"  {c} " if i % 2 else c.upper() if i == 0 else c for i, c in enumerate(cab)]
    if nivel >= 3:  # coluna vazia no meio (sem cabeçalho e sem dados)
        meio = len(cab) // 2
        cab_escrito = cab_escrito[:meio] + [None] + cab_escrito[meio:]
    if nivel >= 5:  # cabeçalho em duas linhas: um "grupo" por cima, como relatório de sistema antigo
        ws.append(["Identificação"] + [None] * (len(cab_escrito) // 2 - 1) + ["Dados do registro"]
                  + [None] * (len(cab_escrito) - len(cab_escrito) // 2 - 1))
    ws.append(cab_escrito)

    def celula(c, v, i):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ["-", "N/A", ""][i % 3]
        if isinstance(v, date):
            if nivel >= 3 and i % 3 == 1:   # número de série do Excel (célula sem formato de data)
                return (v - date(1899, 12, 30)).days
            if nivel >= 3 and i % 3 == 2:
                return v.isoformat()
            return v.strftime("%d/%m/%Y")
        if c == met:
            v = float(v)
            fmt = caso.get("formatos", {}).get(i)
            if fmt == "mil":
                return f"R$ {v / 1000:.1f} mil".replace(".", ",")
            if fmt == "sap":
                return _br(abs(v)).replace("R$ ", "") + "-"          # 1.234,56-  (menos no fim)
            if fmt == "unicode":
                return "\u2212" + _br(abs(v)).replace("R$ ", "")      # −1.234,56  (sinal copiado de PDF)
            if fmt == "parenteses":
                return "(" + _br(abs(v)).replace("R$ ", "") + ")"     # (1.234,56)  negativo contábil
            if fmt == "espaco":
                return f"{v:,.2f}".replace(",", "\u202f").replace(".", ",")  # 12 345,67 (espaço fino)
            if nivel == 3:
                return f"{v:,.2f}"           # padrão americano: 1,234.56
            if caso.get("moeda"):
                return _br(v)
            if nivel >= 4:
                return f"{v:,.2f}"           # nível 4 mantém o padrão americano para as métricas sem moeda
            return int(v) if float(v).is_integer() else v
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, (str, np.str_)):
            return f" {v}  " if nivel >= 2 and i % 4 == 0 else str(v)   # espaços sobrando
        return v

    linhas = []
    for i in range(caso["n"]):
        linha = [celula(c, rot[c][i], i) for c in cab]
        if nivel >= 3:
            linha = linha[:meio] + [None] + linha[meio:]
        linhas.append(linha)
    for i, linha in enumerate(linhas):
        if nivel >= 5 and i and i % 60 == 0:  # quebra de página do relatório: o cabeçalho se repete no meio dos dados
            ws.append(cab_escrito)
        if nivel >= 5 and i and i % 37 == 0:  # linha totalmente vazia no meio da tabela
            ws.append([])
        ws.append(linha)
        if nivel >= 2 and i == caso.get("subtotal_em"):  # subtotal no meio da tabela
            ws.append([f"Subtotal {str(rot[cab[1]][i])}"] + [None] * (len(linha) - 1))
    ws.append(linhas[0])  # duplicata exata (com o mesmo ID)
    ws.append(["Total"] + [None] * (len(linhas[0]) - 1))
    if nivel >= 3:
        ws.append([])
        ws.append([f"Gerado em {date(2026, 10, 18):%d/%m/%Y} às 08:00 por sistema_erp (usuário: relatorios)"])
    wb.save(caminho)


def verdade(caso: dict) -> pd.DataFrame:
    df = pd.DataFrame({normalizar_nome_coluna(c): v for c, v in caso["rotulos"].items()})
    met = normalizar_nome_coluna(caso["metrica"])
    df[met] = pd.to_numeric(df[met], errors="coerce")
    return df


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
              biblioteca: str | None = None, nivel: int | None = None) -> dict:
    """Um treino com resposta conhecida. gravar=False = reconferência (caderno de lições): refaz o MESMO caso e a
    MESMA biblioteca sem gravar nada (sem treino novo, sem acerto/erro, sem handover, sem pedido de ajuda)."""
    from robo import bibliotecas, calculos, ciencia, memoria
    from robo.pipeline import processar_arquivo
    tb = _tb(cfg)
    with tb.tx() as c:
        feitos = c.execute("SELECT COUNT(DISTINCT rodada) FROM laboratorio_exercicios").fetchone()[0]
    semente = int(semente if semente is not None else time.time_ns() % 2_000_000_000)
    area = area or AREAS[feitos % len(AREAS)]
    # dificuldade crescente: percorre as 6 áreas no nível 1, depois no 2, depois no 3 — e recomeça
    nivel = int(nivel or 1 + (feitos // len(AREAS)) % len(NIVEIS))
    # número sequencial no fim: duas rodadas no mesmo segundo não se misturam (nem a pasta, nem o termômetro)
    rodada = f"LAB-{datetime.now():%Y%m%d-%H%M%S}-{area}-n{nivel}-{feitos + 1}"
    inicio_job = _agora()
    caso = aplicar_nivel(gerar(area, semente), nivel, semente)
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
            col_data = next((normalizar_nome_coluna(c) for c, v in caso["rotulos"].items()
                             if len(v) and isinstance(v[0], date)), None)
            if col_data and col_data in df.columns and ok_linhas:
                t0 = time.perf_counter()
                obtidas = df[col_data].dt.date.tolist() if pd.api.types.is_datetime64_any_dtype(df[col_data]) else []
                esperadas = sorted(certo[col_data].tolist())
                ok_datas = pd.api.types.is_datetime64_any_dtype(df[col_data]) and sorted(
                    d for d in obtidas if d is not None and not pd.isna(d)) == esperadas
                registrar("Converter as datas (texto, ISO e número de série)", "limpeza", ok_datas,
                          "todas as datas certas" if ok_datas else
                          f"{col_data}: ficou como {df[col_data].dtype} (não virou data)" if not obtidas else
                          f"{col_data}: {sum(1 for d in obtidas if d is None or pd.isna(d))} data(s) vazia(s) ou diferente(s)", t0)
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
            resp = calculos.calcular(cfg_lab, pergunta, fontes={area: (df, arq.name)}, apelidos=False)
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
        return {"rodada": rodada, "area": area, "semente": semente, "nivel": nivel, "linhas": caso["n"], "etapas": len(resultados),
                "acertos": len(resultados) - len(falhas), "falhas": [f"{x['etapa']}: {x['detalhe'][:120]}" for x in falhas],
                "resultados": resultados}
    # ---- memória, handovers e pedidos de ajuda
    from robo import interacoes
    with tb.tx() as c:
        for x in resultados:
            c.execute("INSERT INTO laboratorio_exercicios (rodada, data_hora, area, semente, etapa, responsavel, ok, detalhe, "
                      "segundos, nivel) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (rodada, _agora(), area, semente, x["etapa"], x["responsavel"], int(x["ok"]), x["detalhe"][:1000],
                       x["segundos"], nivel))
    try:  # prova de trabalho: o exercício inteiro vira um job fechado, uma etapa por responsável
        from robo import jobs
        jobs.registrar_concluido(cfg, "laboratorio", "sintetico", None, inicio_job,
                                 [{"etapa": x["etapa"], "funcionario": x["responsavel"], "ok": x["ok"], "detalhe": x["detalhe"],
                                   "evidencia": {"segundos": x["segundos"]}} for x in resultados],
                                 "concluido" if all(x["ok"] for x in resultados) else "falhou", rodada,
                                 {"area": area, "nivel": nivel, "semente": semente})
    except Exception:
        pass
    try:
        from robo import aprendizados
        for x in resultados:
            aprendizados.registrar(cfg, x["responsavel"], f"laboratorio:{_etapa_base_lab(x['etapa'])}",
                                   "acerto" if x["ok"] else "erro", acao=f"{area} nível {nivel}",
                                   causa="" if x["ok"] else x["detalhe"][:500], nivel=nivel, evidencia_id=rodada,
                                   origem="laboratorio", contexto={"area": area, "semente": semente})
    except Exception:
        pass
    for x in resultados:
        memoria.experiencia(cfg, x["responsavel"], "acerto" if x["ok"] else "erro", f"Laboratório ({area}): {x['etapa']}",
                            "laboratorio", rodada, x["detalhe"], tb)
        if not x["ok"]:
            hid = memoria.handover(cfg, f"Laboratório: {x['etapa']} falhou — {x['detalhe'][:200]}", f"lab_{area}", x["responsavel"],
                                   f"semente {semente}", tb)
            interacoes.pedir_ajuda(cfg, x["responsavel"], f"{x['etapa']}: {x['detalhe'][:160]}", hid)
    return {"rodada": rodada, "area": area, "semente": semente, "nivel": nivel, "linhas": caso["n"], "etapas": len(resultados),
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
    return {"rodadas": rodadas, "por_area": areas, "por_pessoa": por, "ultimas": ultimas, "por_nivel": por_nivel(cfg)}


def por_nivel(cfg, ultimas_rodadas: int = 20) -> list[dict]:
    """O termômetro: taxa de acerto de cada nível de dificuldade e a linha do tempo das últimas rodadas do nível.
    Quando o código melhora, a linha sobe (ex.: nível 4 de 3/6 para 6/6 depois de ensinar 'R$ 1,2 mil')."""
    with _tb(cfg).tx() as c:
        linhas = [dict(r) for r in c.execute(
            "SELECT COALESCE(nivel, 1) nivel, rodada, MIN(data_hora) data_hora, area, SUM(ok) ok, COUNT(*) total "
            "FROM laboratorio_exercicios GROUP BY rodada ORDER BY MIN(id)")]
    saida = []
    for n, descricao in NIVEIS.items():
        rs = [r for r in linhas if r["nivel"] == n]
        ok, total = sum(r["ok"] for r in rs), sum(r["total"] for r in rs)
        saida.append({"nivel": n, "descricao": descricao, "rodadas": len(rs), "acertos": ok, "etapas": total,
                      "taxa": round(100 * ok / total, 1) if total else None,
                      "linha_do_tempo": [{"data_hora": r["data_hora"], "area": r["area"],
                                          "taxa": round(100 * r["ok"] / r["total"], 1)} for r in rs[-ultimas_rodadas:]]})
    return saida


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
