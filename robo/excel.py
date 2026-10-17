"""3º ANDAR — Sala Excel (Trade Marketing e Pesquisa de Mercado).

Para cada base aprovada, a equipe de especialistas monta uma entrega em Excel com FÓRMULAS
(nada de número colado), pronta para quem trabalha no Excel:

  Ricardo · Supervisor da Sala Excel (ex-Microsoft)  monta a Conferência e assina a entrega
  Pedro   · Pesquisa de Mercado                        plano tabular (frequências e NPS por segmento)
  Lúcia   · Fórmulas e Power Query                     indicadores (NPS, CSAT) com margem de erro em fórmula
  Tânia   · Trade Marketing                             vendas, share e preço médio por loja/canal/SKU
  Gabriel · Tabelas Dinâmicas e Dashboards              organização, formatos e o Resumo da entrega

Garantia de qualidade: cada número da entrega é recalculado de forma independente em Python e
comparado, dentro do próprio arquivo, com a fórmula (aba Conferência). A célula de status no Resumo
mostra "✔ Todas as conferências OK" ou "✖ Há divergências — não use". O Excel recalcula ao abrir.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from robo.limpeza import sem_acento

log = logging.getLogger("robo")

EQUIPE_EXCEL = [
    {"id": "excel_supervisor", "nome": "Ricardo", "papel": "Gerente da Sala Excel", "cor": "#107C41",
     "descricao": "Veio da Microsoft e conhece o Excel de ponta a ponta. Gerencia a sala, responde dúvidas de Excel no "
                  "canal e só assina a entrega quando a aba Conferência fecha 100%."},
    {"id": "excel_pesquisa", "nome": "Pedro", "papel": "Especialista em Pesquisa de Mercado", "cor": "#0E7490",
     "descricao": "Monta o plano tabular: frequência e percentual de cada segmento e, quando há nota, o NPS por segmento, "
                  "tudo em CONT.SES (COUNTIFS) — auditável célula a célula."},
    {"id": "excel_formulas", "nome": "Lúcia", "papel": "Especialista em Fórmulas e Power Query", "cor": "#7C3AED",
     "descricao": "Escreve os indicadores em fórmula: NPS, CSAT top-2-box e a margem de erro de 95%."},
    {"id": "excel_trade", "nome": "Tânia", "papel": "Especialista em Trade Marketing", "cor": "#DB2777",
     "descricao": "Quando a base tem vendas, monta SOMASES (SUMIFS) por loja, canal, região e SKU, com share e preço médio."},
    {"id": "excel_dinamicas", "nome": "Gabriel", "papel": "Especialista em Tabelas Dinâmicas e Dashboards", "cor": "#CA8A04",
     "descricao": "Organiza a entrega: Resumo com status, formatos de número, painéis congelados e guia de uso."},
]

PADRAO_EXCEL = {"habilitado": True, "max_linhas": 300_000, "max_categorias": 30, "max_segmentos": 6, "top_trade": 50}

RE_MEDIDA = re.compile(r"(^|_)(valor|venda|vendas|receita|faturamento|sell_?out|sell_?in|preco|quantidade|qtd|qtde|volume|unidades|gmv)(_|$)")
RE_DIMENSAO = re.compile(r"(^|_)(loja|pdv|canal|regiao|uf|estado|cidade|categoria|marca|sku|produto|rede|cliente|vendedor|bandeira|fornecedor)(_|$)")

AZUL = PatternFill("solid", fgColor="1F3864")
VERDE_CLARO = PatternFill("solid", fgColor="E8F5E9")
CINZA = PatternFill("solid", fgColor="F3F4F6")
BRANCO_NEGRITO = Font(bold=True, color="FFFFFF")
NEGRITO = Font(bold=True)
FINA = Side(style="thin", color="D1D5DB")
BORDA = Border(top=FINA, bottom=FINA, left=FINA, right=FINA)


def _criterio(valor) -> str:
    """Critério de CONT.SES que casa EXATAMENTE com o valor (escapa * ? ~ e operadores no início)."""
    texto = str(valor).replace("~", "~~").replace("*", "~*").replace("?", "~?")
    if texto[:1] in "<>=":
        texto = "=" + texto
    return '"' + texto.replace('"', '""') + '"'


def _igual_excel(serie: pd.Series, valor) -> pd.Series:
    """Mesma regra do CONT.SES: texto compara sem diferenciar maiúsculas."""
    alvo = str(valor).strip().lower()
    return serie.map(lambda v: v is not None and not (not isinstance(v, str) and pd.isna(v)) and str(v).strip().lower() == alvo)


class Entrega:
    def __init__(self, df: pd.DataFrame, base: str, arquivo: str, papeis: dict, indicadores: dict, cfg: dict):
        self.df = df.reset_index(drop=True)
        self.base, self.arquivo, self.papeis, self.indicadores = base, arquivo, papeis, indicadores
        self.c = {**PADRAO_EXCEL, **(cfg or {})}
        self.wb = Workbook()
        self.wb.calculation = CalcProperties(fullCalcOnLoad=True)
        self.conferencias: list[tuple] = []   # (descrição, referência da célula, valor esperado)
        self.n = len(self.df)
        self.coluna_letra: dict[str, str] = {}
        self.etapas: list[str] = []

    # --------------------------------------------------------------- utilidades
    def _faixa(self, coluna: str) -> str:
        letra = self.coluna_letra[coluna]
        return f"Dados!${letra}$2:${letra}${self.n + 1}"

    def _conferir(self, descricao: str, aba: str, celula: str, esperado: float):
        self.conferencias.append((descricao, f"'{aba}'!{celula}", float(esperado)))

    @staticmethod
    def _cabecalho(ws, linha: int, titulos: list[str], coluna: int = 1):
        for i, t in enumerate(titulos):
            c = ws.cell(row=linha, column=coluna + i, value=t)
            c.font, c.fill, c.alignment, c.border = BRANCO_NEGRITO, AZUL, Alignment(horizontal="center", vertical="center", wrap_text=True), BORDA

    @staticmethod
    def _larguras(ws, larguras: dict):
        for col, w in larguras.items():
            ws.column_dimensions[col].width = w

    # --------------------------------------------------------------- Dados
    def aba_dados(self):
        ws = self.wb.active
        ws.title = "Dados"
        colunas = list(self.df.columns)
        for i, col in enumerate(colunas, 1):
            self.coluna_letra[col] = get_column_letter(i)
        self._cabecalho(ws, 1, colunas)
        for linha in self.df.astype(object).itertuples(index=False, name=None):
            ws.append([None if (v is None or (not isinstance(v, str) and pd.isna(v))) else
                       (v.to_pydatetime() if isinstance(v, pd.Timestamp) else v) for v in linha])
        # segurança: texto de origem que começa com "=" fica como TEXTO (não vira fórmula ativa)
        for linha in ws.iter_rows(min_row=2):
            for cel in linha:
                if cel.data_type == "f":
                    cel.data_type = "s"
        for i, col in enumerate(colunas, 1):
            letra = get_column_letter(i)
            ws.column_dimensions[letra].width = max(10, min(40, len(col) + 4))
            if pd.api.types.is_datetime64_any_dtype(self.df[col]):
                for (cel,) in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                    cel.number_format = "dd/mm/yyyy"
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    # --------------------------------------------------------------- Pedro · plano tabular
    def segmentos(self) -> list[str]:
        candidatos = [c for c, p in self.papeis.items() if p == "categoria" and c in self.df.columns
                      and 2 <= self.df[c].nunique() <= int(self.c["max_categorias"])
                      and self.df[c].dropna().astype(str).str.len().max() < 200]
        return candidatos[: int(self.c["max_segmentos"])]

    def aba_plano_tabular(self):
        segs = self.segmentos()
        if not segs:
            return
        ws = self.wb.create_sheet("Plano tabular")
        ws["A1"] = f"Plano tabular — {self.base}"; ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = "Frequências por segmento. Fórmulas CONT.SES sobre a aba Dados (clique numa célula para ver)."
        nps = self.indicadores.get("nps")
        linha = 4
        for seg in segs:
            titulos = ["Categoria", "Base (n)", "% da base"] + (["Promotores", "Detratores", "NPS", "Base pequena?"] if nps else [])
            ws.cell(row=linha, column=1, value=seg).font = Font(bold=True, size=12, color="1F3864")
            linha += 1
            self._cabecalho(ws, linha, titulos)
            inicio = linha + 1
            valores = sorted(self.df[seg].dropna().astype(str).str.strip().unique(), key=str.lower)
            vistos = set()
            for v in valores:
                if v.lower() in vistos:
                    continue
                vistos.add(v.lower())
                linha += 1
                mascara = _igual_excel(self.df[seg], v)
                n_esp = int(mascara.sum())
                ws.cell(row=linha, column=1, value=v).border = BORDA
                c = ws.cell(row=linha, column=2, value=f"=COUNTIFS({self._faixa(seg)},{_criterio(v)})")
                c.number_format, c.border = "#,##0", BORDA
                self._conferir(f"[{seg}] base de {v}", "Plano tabular", f"B{linha}", n_esp)
                c = ws.cell(row=linha, column=3, value=f"=IF($B${{TOTAL}}=0,0,B{linha}/$B${{TOTAL}})")
                c.number_format, c.border = "0.0%", BORDA
                if nps:
                    notas = self.df.loc[mascara, nps].dropna().astype(float)
                    p, d = int((notas >= 9).sum()), int((notas <= 6).sum())
                    c = ws.cell(row=linha, column=4, value=f'=COUNTIFS({self._faixa(seg)},{_criterio(v)},{self._faixa(nps)},">=9")')
                    c.number_format, c.border = "#,##0", BORDA
                    c = ws.cell(row=linha, column=5, value=f'=COUNTIFS({self._faixa(seg)},{_criterio(v)},{self._faixa(nps)},"<=6")')
                    c.number_format, c.border = "#,##0", BORDA
                    n_resp = f'COUNTIFS({self._faixa(seg)},{_criterio(v)},{self._faixa(nps)},">=0")'
                    c = ws.cell(row=linha, column=6, value=f"=IF({n_resp}=0,\"\",(D{linha}-E{linha})/{n_resp}*100)")
                    c.number_format, c.border = "0", BORDA  # NPS sem casas decimais (padrão da casa)
                    ws.cell(row=linha, column=7, value=f'=IF({n_resp}<30,"sim","não")').border = BORDA
                    self._conferir(f"[{seg}] promotores de {v}", "Plano tabular", f"D{linha}", p)
                    self._conferir(f"[{seg}] detratores de {v}", "Plano tabular", f"E{linha}", d)
                    if len(notas):
                        self._conferir(f"[{seg}] NPS de {v}", "Plano tabular", f"F{linha}", 100 * (p - d) / len(notas))
            linha += 1
            total = linha
            ws.cell(row=total, column=1, value="Total").font = NEGRITO
            c = ws.cell(row=total, column=2, value=f"=SUM(B{inicio}:B{total - 1})"); c.font, c.number_format = NEGRITO, "#,##0"
            c = ws.cell(row=total, column=3, value=f"=SUM(C{inicio}:C{total - 1})"); c.font, c.number_format = NEGRITO, "0.0%"
            for r in range(inicio, total):
                cel = ws.cell(row=r, column=3)
                cel.value = cel.value.replace("{TOTAL}", str(total))
            self._conferir(f"[{seg}] total preenchido", "Plano tabular", f"B{total}", int(self.df[seg].notna().sum()))
            linha = total + 3
        self._larguras(ws, {"A": 34, "B": 12, "C": 12, "D": 12, "E": 12, "F": 10, "G": 14})
        ws.freeze_panes = "A4"
        self.etapas.append("excel_pesquisa")

    # --------------------------------------------------------------- Lúcia · indicadores
    def aba_indicadores(self):
        if not self.indicadores:
            return
        ws = self.wb.create_sheet("Indicadores")
        ws["A1"] = f"Indicadores — {self.base}"; ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = "Tudo em fórmula sobre a aba Dados. Margem de erro com 95% de confiança."
        self._cabecalho(ws, 4, ["Indicador", "Valor", "Fórmula / leitura"])
        linha = 4
        if "nps" in self.indicadores:
            col = self.indicadores["nps"]
            notas = self.df[col].dropna().astype(float)
            n, p, d = len(notas), int((notas >= 9).sum()), int((notas <= 6).sum())
            faixa = self._faixa(col)
            itens = [("Respostas (n)", f"=COUNT({faixa})", "#,##0", n),
                     ("Promotores (9-10)", f'=COUNTIF({faixa},">=9")', "#,##0", p),
                     ("Detratores (0-6)", f'=COUNTIF({faixa},"<=6")', "#,##0", d),
                     ("% Promotores", "=IF(B5=0,0,B6/B5)", "0.0%", p / n if n else 0),
                     ("% Detratores", "=IF(B5=0,0,B7/B5)", "0.0%", d / n if n else 0),
                     ("NPS", "=(B8-B9)*100", "0", 100 * (p - d) / n if n else 0),
                     ("Margem de erro (± pts, 95%)", "=IF(B5=0,0,1.96*SQRT((B8+B9-(B8-B9)^2)/B5)*100)", "0.0",
                      100 * 1.96 * math.sqrt(((p + d) / n - ((p - d) / n) ** 2) / n) if n else 0)]
            leituras = ["Notas preenchidas", "Notas 9 e 10", "Notas de 0 a 6", "", "", "%Promotores − %Detratores",
                        "O NPS real está entre NPS − margem e NPS + margem"]
            for (nome, formula, formato, esperado), leitura in zip(itens, leituras):
                linha += 1
                ws.cell(row=linha, column=1, value=nome).border = BORDA
                c = ws.cell(row=linha, column=2, value=formula); c.number_format, c.border = formato, BORDA
                ws.cell(row=linha, column=3, value=leitura).border = BORDA
                self._conferir(f"Indicador: {nome}", "Indicadores", f"B{linha}", esperado)
            ws.cell(row=10, column=2).font = Font(bold=True, size=13, color="1F3864")
        if "csat" in self.indicadores:
            col = self.indicadores["csat"]
            notas = self.df[col].dropna().astype(float)
            escala = 5 if notas.max() <= 5 else 7 if notas.max() <= 7 else 10
            corte = escala - 1
            n, sat = len(notas), int((notas >= corte).sum())
            faixa = self._faixa(col)
            linha += 2
            base = linha + 1
            for nome, formula, formato, esperado in (
                    ("CSAT — respostas (n)", f"=COUNT({faixa})", "#,##0", n),
                    (f"CSAT — satisfeitos (≥ {corte})", f'=COUNTIF({faixa},">={corte}")', "#,##0", sat),
                    ("CSAT (top-2-box)", f"=IF(B{base}=0,0,B{base + 1}/B{base})", "0.0%", sat / n if n else 0)):
                linha += 1
                ws.cell(row=linha, column=1, value=nome).border = BORDA
                c = ws.cell(row=linha, column=2, value=formula); c.number_format, c.border = formato, BORDA
                self._conferir(f"Indicador: {nome}", "Indicadores", f"B{linha}", esperado)
        self._larguras(ws, {"A": 34, "B": 14, "C": 52})
        self.etapas.append("excel_formulas")

    # --------------------------------------------------------------- Tânia · trade marketing
    def colunas_trade(self) -> tuple[list[str], list[str]]:
        medidas = [c for c in self.df.columns if self.papeis.get(c) == "numero" and RE_MEDIDA.search(sem_acento(c))]
        dims = [c for c in self.df.columns if self.papeis.get(c) in ("categoria", "texto") and RE_DIMENSAO.search(sem_acento(c))
                and self.df[c].dropna().astype(str).str.len().max() < 200]
        return medidas, dims

    def aba_trade(self):
        medidas, dims = self.colunas_trade()
        if not medidas or not dims:
            return
        ws = self.wb.create_sheet("Trade")
        ws["A1"] = f"Trade marketing — {self.base}"; ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = "SOMASES (SUMIFS) sobre a aba Dados. Share = participação no total da coluna."
        valor = next((m for m in medidas if re.search(r"valor|venda|receita|faturamento|sell|gmv", m)), medidas[0])
        qtd = next((m for m in medidas if re.search(r"quantidade|qtd|qtde|volume|unidades", m) and m != valor), None)
        linha = 4
        top = int(self.c["top_trade"])
        for dim in dims[:3]:
            ws.cell(row=linha, column=1, value=f"{dim} × {valor}").font = Font(bold=True, size=12, color="1F3864")
            linha += 1
            titulos = [dim, f"Soma de {valor}", "Share %"] + ([f"Soma de {qtd}", "Preço médio"] if qtd else [])
            self._cabecalho(ws, linha, titulos)
            agrupado = (self.df.assign(_k=self.df[dim].astype(str).str.strip().str.lower())
                        .groupby("_k").agg(rotulo=(dim, "first"), soma=(valor, "sum")).sort_values("soma", ascending=False))
            total_geral = float(self.df[valor].sum())
            inicio = linha + 1
            for _, g in agrupado.head(top).iterrows():
                linha += 1
                rot = str(g["rotulo"]).strip()
                mascara = _igual_excel(self.df[dim], rot)
                ws.cell(row=linha, column=1, value=rot).border = BORDA
                c = ws.cell(row=linha, column=2, value=f"=SUMIFS({self._faixa(valor)},{self._faixa(dim)},{_criterio(rot)})")
                c.number_format, c.border = "#,##0.00", BORDA
                soma = float(self.df.loc[mascara, valor].sum())
                self._conferir(f"[{dim}] {valor} de {rot}", "Trade", f"B{linha}", soma)
                c = ws.cell(row=linha, column=3, value=f"=IF(SUM({self._faixa(valor)})=0,0,B{linha}/SUM({self._faixa(valor)}))")
                c.number_format, c.border = "0.0%", BORDA
                if total_geral:
                    self._conferir(f"[{dim}] share de {rot}", "Trade", f"C{linha}", soma / total_geral)
                if qtd:
                    c = ws.cell(row=linha, column=4, value=f"=SUMIFS({self._faixa(qtd)},{self._faixa(dim)},{_criterio(rot)})")
                    c.number_format, c.border = "#,##0", BORDA
                    q = float(self.df.loc[mascara, qtd].sum())
                    self._conferir(f"[{dim}] {qtd} de {rot}", "Trade", f"D{linha}", q)
                    c = ws.cell(row=linha, column=5, value=f'=IF(D{linha}=0,"",B{linha}/D{linha})')
                    c.number_format, c.border = "#,##0.00", BORDA
            if len(agrupado) > top:
                linha += 1
                ws.cell(row=linha, column=1, value=f"(mostrando os {top} maiores de {len(agrupado)})").font = Font(italic=True, color="6B7280")
            linha += 3
        self._larguras(ws, {"A": 34, "B": 18, "C": 10, "D": 16, "E": 14})
        self.etapas.append("excel_trade")

    # --------------------------------------------------------------- Ricardo · conferência / Gabriel · resumo
    def aba_conferencia(self):
        ws = self.wb.create_sheet("Conferência")
        ws["A1"] = "Conferência independente"; ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = "Cada fórmula da entrega comparada com o valor recalculado em Python. Qualquer ERRO invalida a entrega."
        self._cabecalho(ws, 4, ["#", "O que é conferido", "Valor da fórmula", "Valor esperado", "Status"])
        for i, (descricao, ref, esperado) in enumerate(self.conferencias, 1):
            r = 4 + i
            ws.cell(row=r, column=1, value=i)
            ws.cell(row=r, column=2, value=descricao)
            ws.cell(row=r, column=3, value=f"=IFERROR({ref},\"#ERRO\")").number_format = "#,##0.0000"
            ws.cell(row=r, column=4, value=round(esperado, 10)).number_format = "#,##0.0000"
            ws.cell(row=r, column=5, value=f'=IF(ISNUMBER(C{r}),IF(ABS(C{r}-D{r})<=0.0001*MAX(1,ABS(D{r})),"OK","ERRO"),"ERRO")')
        self._larguras(ws, {"A": 6, "B": 60, "C": 18, "D": 18, "E": 10})
        ws.freeze_panes = "A5"
        self.etapas.append("excel_supervisor")

    def aba_resumo(self):
        ws = self.wb.create_sheet("Resumo", 0)
        ultima = 4 + len(self.conferencias)
        ws["A1"] = f"Entrega Excel — {self.base}"; ws["A1"].font = Font(bold=True, size=16, color="1F3864")
        ws["A3"] = "Status da conferência"; ws["A3"].font = NEGRITO
        if not self.conferencias:
            ws["B3"] = "Sem números para conferir nesta base (nenhum segmento, indicador ou valor de trade reconhecido)"
        else:
            ws["B3"] = (f"=IF(COUNTIF('Conferência'!E5:E{ultima},\"OK\")={len(self.conferencias)},"
                        f"\"✔ Todas as {len(self.conferencias)} conferências OK\",\"✖ Há divergências — não use, avise o supervisor\")")
        ws["B3"].font = Font(bold=True, size=13, color="107C41")
        ws["B3"].fill = VERDE_CLARO
        linhas = [("Arquivo de origem", self.arquivo), ("Registros", self.n), ("Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M")),
                  ("Supervisor", "Ricardo — Sala Excel")]
        for i, (k, v) in enumerate(linhas, 5):
            ws.cell(row=i, column=1, value=k).font = NEGRITO
            ws.cell(row=i, column=2, value=v)
        ws["A10"] = "Abas desta entrega"; ws["A10"].font = Font(bold=True, size=12)
        guia = {"Plano tabular": "Frequências, % e NPS por segmento (pesquisa de mercado).",
                "Indicadores": "NPS e CSAT com margem de erro, tudo em fórmula.",
                "Trade": "Vendas, share e preço médio por loja, canal, região ou SKU.",
                "Conferência": "Cada número recalculado e comparado. Precisa estar 100% OK.",
                "Dados": "A base tratada usada por todas as fórmulas."}
        r = 11
        for aba, texto in guia.items():
            if aba in self.wb.sheetnames:
                ws.cell(row=r, column=1, value=aba).font = NEGRITO
                ws.cell(row=r, column=2, value=texto)
                r += 1
        ws.cell(row=r + 1, column=1, value="Dica").font = NEGRITO
        ws.cell(row=r + 1, column=2, value="Clique em qualquer número e veja a fórmula na barra de fórmulas: nada aqui é valor colado.")
        self._larguras(ws, {"A": 26, "B": 90})
        self.etapas.append("excel_dinamicas")

    def gerar(self, destino: Path) -> dict:
        self.aba_dados()
        self.aba_plano_tabular()
        self.aba_indicadores()
        self.aba_trade()
        self.aba_conferencia()
        self.aba_resumo()
        temporario = destino.with_name(f"~robo_tmp_{destino.name}")
        self.wb.save(temporario)
        temporario.replace(destino)
        return {"arquivo": str(destino), "conferencias": len(self.conferencias), "abas": self.wb.sheetnames, "etapas": self.etapas}


def gerar_entrega(tabelas: dict, arquivo: str, base: str, cfg, papeis: dict | None, indicadores: dict | None, ao_etapa=None) -> dict | None:
    """Ponto de entrada usado pelo pipeline. Nunca levanta exceção: falha vira log."""
    c = {**PADRAO_EXCEL, **(cfg.dados.get("excel") or {})}
    if not c.get("habilitado", True) or not tabelas:
        return None
    nome, df = next(iter(tabelas.items()))
    if df.empty or len(df) > int(c["max_linhas"]):
        return None
    try:
        from robo.analise import converter_escalas, detectar_indicadores, papel_coluna
        df, escalas, _origem = converter_escalas(df)
        if papeis is None:
            papeis = {col: papel_coluna(df[col], col, int(c["max_categorias"]), cfg.limpeza.get("padroes_identificador", []))
                      for col in df.columns}
        if indicadores is None:
            indicadores = detectar_indicadores(df, papeis, {})
            for tipo, col in escalas.items():
                indicadores.setdefault(tipo, col)
        for col in df.columns:
            papeis.setdefault(col, "numero" if col in escalas.values() else "texto")
        entrega = Entrega(df, base, arquivo, papeis, indicadores or {}, c)
        for etapa in ("excel_pesquisa", "excel_formulas", "excel_trade", "excel_dinamicas", "excel_supervisor"):
            if ao_etapa:
                try:
                    ao_etapa(etapa, arquivo)
                except Exception:
                    pass
        cfg.relatorios.mkdir(parents=True, exist_ok=True)
        return entrega.gerar(cfg.relatorios / f"{base}_excel.xlsx")
    except PermissionError:
        log.warning("Entrega Excel de %s não foi atualizada: o arquivo está aberto no Excel.", base)
    except Exception:
        log.exception("Sala Excel não conseguiu montar a entrega de %s", arquivo)
    return None
