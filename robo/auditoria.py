"""Auditoria por amostragem dos heads: é assim que se confia no resultado sem refazer tudo.

Toda semana cada head escolhe até 3 entregas recentes da área e REFAZ por outro caminho:
  Eduardo (Engenharia)  — relê a base publicada e confere as linhas com o histórico e com o PostgreSQL;
  Natália (Ciência)     — recalcula o NPS geral da base publicada e compara com o que a análise publicou;
  Felipe (BI e Excel)   — reabre a entrega Excel: fórmulas vivas, nenhum erro (#REF!), aba Conferência íntegra;
  Simone (Governança)   — procura e-mail, CPF e telefone nas bases publicadas;
  André (Infra)         — backup em dia, ronda de TI saudável, nenhuma rotina com erro sem registro;
  Juliana (Gente)       — todos aprovados nas provas e rodada de estudo em dia.
A amostra é sorteada com semente da semana: a mesma semana audita sempre as mesmas entregas (dá para refazer e
conferir a auditoria). Achado vira handover para a área; tudo fica em logs/trabalho.db → auditorias.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from robo.trabalho import Trabalho, _agora

ESQUEMA = """CREATE TABLE IF NOT EXISTS auditorias (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, head TEXT, area TEXT, amostra TEXT, aprovada INTEGER,
  achados TEXT, conferidos INTEGER);"""
AMOSTRA = 3


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
    return tb


def _execucoes(cfg, dias: int = 7) -> list[dict]:
    from robo import historico
    limite = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
    hist = [h for h in historico.ler(cfg.logs, 3000) if h.get("status") == "sucesso"]
    recentes = [h for h in hist if str(h.get("data_hora", "")) >= limite] or hist[:20]
    saida = []
    for h in recentes:
        exe = historico.ler_execucao(cfg.logs, h.get("id") or "")
        if exe:
            saida.append(exe)
    return saida


def _mais_recentes(execucoes: list[dict], caminho) -> list[dict]:
    """Os arquivos publicados (base, análise, Excel) têm nome fixo e são sobrescritos a cada carga: só a execução
    MAIS RECENTE de cada caminho corresponde ao que está no disco. Auditar as antigas daria falso alarme."""
    vistos, saida = set(), []
    for e in sorted(execucoes, key=lambda x: str(x.get("data_hora", "")), reverse=True):
        c = caminho(e)
        if c and c not in vistos:
            vistos.add(c)
            saida.append(e)
    return saida


def _saida(e: dict) -> str | None:
    s = [x for x in e.get("saidas") or [] if str(x).lower().endswith((".xlsx", ".csv"))]
    return str(s[0]) if s else None


def _amostra(itens: list, semente: str) -> list:
    rng = random.Random(f"{datetime.now():%G-%V}-{semente}")  # mesma semana ISO = mesma amostra
    return rng.sample(itens, min(AMOSTRA, len(itens)))


def _ler_principal(caminho: str):
    import pandas as pd
    p = Path(caminho)
    if p.suffix.lower() == ".csv":
        return None, pd.read_csv(p, sep=None, engine="python", encoding="utf-8-sig", dtype=str)
    abas = pd.read_excel(p, sheet_name=None, dtype=str)
    nome = next((n for n in abas if not n.startswith("dim_") and n not in ("dicionario_dados", "log_qualidade")), next(iter(abas)))
    return nome, abas[nome]


# --------------------------------------------------------------------------- comparadores (testados nas provas)
def conferir_linhas(esperado: int, no_arquivo: int, no_banco: int | None = None) -> list[str]:
    achados = []
    if no_arquivo != esperado:
        achados.append(f"arquivo publicado tem {no_arquivo} linha(s), o histórico registrou {esperado}")
    if no_banco is not None and no_banco != esperado:
        achados.append(f"PostgreSQL tem {no_banco} linha(s) deste arquivo, o histórico registrou {esperado}")
    return achados


def conferir_indicador(publicado: float, recalculado: float, tolerancia: float = 0.1) -> list[str]:
    if abs(publicado - recalculado) > tolerancia:
        return [f"análise publicou {publicado:.1f}, o recálculo deu {recalculado:.1f}"]
    return []


def backup_atrasado(ultimo: dict | None, agora: datetime | None = None, horas: float = 36) -> bool:
    agora = agora or datetime.now()
    if not ultimo or not ultimo.get("ok") or not ultimo.get("data_hora"):
        return True
    return agora - datetime.strptime(ultimo["data_hora"], "%Y-%m-%d %H:%M:%S") > timedelta(hours=horas)


# --------------------------------------------------------------------------- auditorias de cada head
def _engenharia(cfg) -> tuple[list, list]:
    amostra, achados = [], []
    for exe in _amostra(_mais_recentes(_execucoes(cfg), _saida), "engenharia"):
        saidas = [s for s in exe.get("saidas") or [] if str(s).lower().endswith((".xlsx", ".csv")) and Path(s).exists()]
        if not saidas:
            continue
        nome, df = _ler_principal(saidas[0])
        tab = next((t for t in exe.get("tabelas") or [] if t["nome"] == nome), None) if nome else None
        esperado = tab["linhas"] if tab else exe.get("linhas_saida")
        no_banco = None
        fatos = [t for t in exe.get("tabelas_banco") or [] if str(t).startswith("tratado.") and not str(t).split(".")[1].startswith("dim_")]
        if cfg.banco.get("habilitado") and fatos:
            try:
                from robo.banco import Banco
                schema, tabela = fatos[0].split(".", 1)
                with Banco(cfg.banco, cfg.base).conectar() as conn:
                    no_banco = conn.execute(f'SELECT COUNT(*) FROM "{schema}"."{tabela}" WHERE "_arquivo_origem" = %s',
                                            (exe["arquivo"],)).fetchone()[0]
            except Exception as e:
                achados.append(f"{exe['arquivo']}: não consegui contar no banco ({type(e).__name__})")
        amostra.append(exe["arquivo"])
        achados += [f"{exe['arquivo']}: {a}" for a in conferir_linhas(int(esperado or 0), len(df), no_banco)]
    return amostra, achados


def _ciencia(cfg) -> tuple[list, list]:
    import pandas as pd
    from robo import conferencia
    amostra, achados = [], []
    candidatos = [e for e in _execucoes(cfg) if (e.get("analise") or {}).get("relatorio") and Path(e["analise"]["relatorio"]).exists()]
    candidatos = _mais_recentes(candidatos, lambda e: e["analise"]["relatorio"])
    for exe in _amostra(candidatos, "ciencia"):
        abas = pd.read_excel(exe["analise"]["relatorio"], sheet_name=None)
        ind = abas.get("indicadores")
        if ind is None or ind.empty or "indicador" not in ind.columns:
            continue  # base sem NPS (ex.: cadastro de clientes): nada para recalcular
        linha = ind[(ind["indicador"] == "NPS") & (ind["segmento"] == "Total")]
        saidas = [s for s in exe.get("saidas") or [] if Path(s).exists()]
        if linha.empty or not saidas:
            continue
        col = linha.iloc[0]["coluna"]
        _, df = _ler_principal(saidas[0])
        if col not in df.columns:
            continue
        recalc = conferencia.valores_pandas("nps", df.assign(**{col: pd.to_numeric(df[col], errors="coerce")}), col, [])["(total)"]
        amostra.append(exe["arquivo"])
        achados += [f"{exe['arquivo']}: {a}" for a in conferir_indicador(float(linha.iloc[0]["valor"]), recalc)]
    return amostra, achados


def _bi(cfg) -> tuple[list, list]:
    from robo import quadro
    amostra, achados = [], []
    candidatos = [e for e in _execucoes(cfg) if (e.get("excel") or {}).get("arquivo") and Path(e["excel"]["arquivo"]).exists()]
    candidatos = _mais_recentes(candidatos, lambda e: e["excel"]["arquivo"])
    for exe in _amostra(candidatos, "bi"):
        ctx = quadro.Contexto(arquivo=exe["arquivo"], cfg=cfg, excel={"arquivo": exe["excel"]["arquivo"]})
        amostra.append(Path(exe["excel"]["arquivo"]).name)
        achados += [f"{Path(exe['excel']['arquivo']).name}: {a}" for a in
                    quadro.conf_integridade_excel(ctx) + quadro.conf_formulas_vivas(ctx)]
    return amostra, achados


def _governanca(cfg) -> tuple[list, list]:
    from robo import quadro
    amostra, achados = [], []
    for exe in _amostra(_mais_recentes(_execucoes(cfg), _saida), "governanca"):
        saidas = [s for s in exe.get("saidas") or [] if str(s).lower().endswith((".xlsx", ".csv")) and Path(s).exists()]
        if not saidas:
            continue
        _, df = _ler_principal(saidas[0])
        amostra.append(exe["arquivo"])
        achados += [f"{exe['arquivo']}: {a}" for a in quadro.conf_dados_pessoais(quadro.Contexto(arquivo=exe["arquivo"],
                                                                                                    analisaveis={"base": df}))]
    return amostra, achados


def _infra(cfg) -> tuple[list, list]:
    from robo import backup, rotinas, ti
    achados = []
    r = ti.ultima_ronda(cfg)
    if r and not r.get("saudavel"):
        achados.append("a última ronda de TI não está saudável")
    if cfg.banco.get("habilitado") and backup_atrasado(backup.ultimo(cfg)):
        achados.append("backup do PostgreSQL atrasado ou com falha")
    erros = [e for e in rotinas.execucoes(cfg, limite=200) if e["status"] == "erro"
             and e["inicio"] >= (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")]
    achados += [f"rotina {e['nome']} falhou em {e['inicio'][:16]}: {e['detalhe'][:120]}" for e in erros[:5]]
    return ["ronda de TI", "backup", "rotinas"], achados


def _gente(cfg) -> tuple[list, list]:
    from robo import desenvolvimento, organizacao, rh
    achados = []
    for p in organizacao.lista(cfg):
        try:
            if not rh.ficha(p.get("_agente") or {"id": p["id"], "habilidades": []})["provas"]["aprovado"]:
                achados.append(f"{p['nome']} ({p['id']}) está reprovado na prova técnica")
        except Exception as e:
            achados.append(f"{p['nome']}: prova não rodou ({type(e).__name__})")
    u = desenvolvimento.ultima_rodada(cfg)
    if not u or datetime.fromisoformat(u["criada_em"]) < datetime.now() - timedelta(days=4):
        achados.append("a rodada de estudo está atrasada (deveria acontecer 2x por semana)")
    return ["provas técnicas de todos", "rodada de estudo"], achados


HEADS = {
    "head_engenharia": ("Engenharia de Dados", _engenharia),
    "head_ciencia": ("Ciência de Dados", _ciencia),
    "head_bi": ("BI e Excel", _bi),
    "head_governanca": ("Governança e LGPD", _governanca),
    "head_ti": ("Infraestrutura e Segurança", _infra),
    "head_rh": ("Gente e Gestão", _gente),
}


def auditar(cfg, head: str) -> dict:
    from robo import memoria
    area, funcao = HEADS[head]
    try:
        amostra, achados = funcao(cfg)
    except Exception as e:
        amostra, achados = [], [f"a auditoria não conseguiu terminar ({type(e).__name__}: {e})"]
    aprovada = not achados
    tb = _tb(cfg)
    with tb.tx() as c:
        c.execute("INSERT INTO auditorias (data_hora, head, area, amostra, aprovada, achados, conferidos) VALUES (?,?,?,?,?,?,?)",
                  (_agora(), head, area, json.dumps(amostra, ensure_ascii=False), int(aprovada),
                   json.dumps(achados, ensure_ascii=False), len(amostra)))
    if amostra or achados:
        if achados:
            memoria.experiencia(cfg, head, "acerto", f"Auditoria de {area} achou {len(achados)} problema(s)", "auditoria", "",
                                "\n".join(achados[:10]), tb)
            for a in achados[:10]:
                memoria.handover(cfg, f"Auditoria {area}: {a}", "auditoria", head, tb=tb)
        else:
            memoria.experiencia(cfg, head, "acerto", f"Auditoria de {area}: {len(amostra)} entrega(s) conferida(s), tudo certo",
                                "auditoria", "", ", ".join(map(str, amostra)), tb)
    return {"head": head, "area": area, "amostra": amostra, "achados": achados, "aprovada": aprovada,
            "sem_amostra": not amostra}


def auditar_todos(cfg) -> list[dict]:
    return [auditar(cfg, h) for h in HEADS]


def listar(cfg, limite: int = 50) -> list[dict]:
    tb = _tb(cfg)
    with tb.tx() as c:
        linhas = [dict(r) for r in c.execute("SELECT * FROM auditorias ORDER BY id DESC LIMIT ?", (limite,))]
    for l in linhas:
        l["amostra"], l["achados"], l["aprovada"] = json.loads(l["amostra"]), json.loads(l["achados"]), bool(l["aprovada"])
    return linhas


def rotina(cfg) -> list[dict] | None:
    u = listar(cfg, 1)
    if u and datetime.fromisoformat(u[0]["data_hora"]) > datetime.now() - timedelta(days=7):
        return None
    return auditar_todos(cfg)


def texto(resultado: dict) -> str:
    if resultado["achados"]:
        return (f"Auditoria de {resultado['area']}: conferi {len(resultado['amostra'])} item(ns) e achei "
                f"{len(resultado['achados'])} problema(s):\n" + "\n".join(f"• {a}" for a in resultado["achados"][:10]))
    if resultado["sem_amostra"]:
        return f"Auditoria de {resultado['area']}: não havia entrega recente para sortear na amostra."
    return (f"Auditoria de {resultado['area']}: conferi {len(resultado['amostra'])} item(ns) por outro caminho "
            f"({', '.join(map(str, resultado['amostra']))}) e está tudo certo.")


# --------------------------------------------------------------------------- provas técnicas dos heads
def provas() -> dict:
    import tempfile

    import pandas as pd

    from robo import quadro
    from robo.excel import Entrega
    limpa = pd.DataFrame({"id": [1, 2, 3], "nota": [10, 7, 2], "curso": ["A", "B", "A"]})
    com_email = limpa.assign(contato=["a@b.com", "c@d.com.br", "e@f.org"])
    gov = lambda df: quadro.conf_dados_pessoais(quadro.Contexto(arquivo="p.xlsx", analisaveis={"base": df}))  # noqa: E731
    agora = datetime(2026, 1, 2, 12, 0)
    with tempfile.TemporaryDirectory() as d:
        from openpyxl import load_workbook
        boa = Path(d) / "boa.xlsx"
        Entrega(limpa, "p", "p.xlsx", {"id": "id", "nota": "numero", "curso": "categoria"}, {"nps": "nota"}, {}).gerar(boa)
        wb = load_workbook(boa)
        wb["Indicadores"]["B5"] = "=#REF!+1"
        ruim = Path(d) / "ruim.xlsx"
        wb.save(ruim)
        bi = lambda p: quadro.conf_integridade_excel(quadro.Contexto(arquivo="p.xlsx", excel={"arquivo": str(p)}))  # noqa: E731
        bi_ok, bi_ruim = not bi(boa), bool(bi(ruim))
    antigas = [{"data_hora": "2026-01-01", "saidas": ["a.xlsx"], "id": 1}, {"data_hora": "2026-02-01", "saidas": ["a.xlsx"], "id": 2}]
    return {
        "head_engenharia": [("Aceita contagens iguais", not conferir_linhas(10, 10, 10)),
                            ("Só audita a execução que corresponde ao arquivo no disco",
                             [e["id"] for e in _mais_recentes(antigas, _saida)] == [2]),
                            ("Pega linha faltando no arquivo", bool(conferir_linhas(10, 9))),
                            ("Pega linha faltando no banco", bool(conferir_linhas(10, 10, 8)))],
        "head_ciencia": [("Aceita NPS igual ao recálculo", not conferir_indicador(14.8, 14.83)),
                         ("Pega NPS adulterado", bool(conferir_indicador(20.0, 14.8)))],
        "head_bi": [("Aprova entrega íntegra", bi_ok), ("Pega fórmula quebrada (#REF!)", bi_ruim),
                    ("Amostra reproduzível na mesma semana", _amostra(list(range(10)), "x") == _amostra(list(range(10)), "x"))],
        "head_governanca": [("Não acusa base sem dado pessoal", not gov(limpa)), ("Pega coluna de e-mail publicada", bool(gov(com_email)))],
        "head_ti": [("Backup de 2 h atrás está em dia", not backup_atrasado({"ok": True, "data_hora": "2026-01-02 10:00:00"}, agora)),
                    ("Backup de 3 dias atrás está atrasado", backup_atrasado({"ok": True, "data_hora": "2025-12-30 10:00:00"}, agora)),
                    ("Backup com falha conta como atrasado", backup_atrasado({"ok": False, "data_hora": "2026-01-02 11:00:00"}, agora))],
        "head_rh": [("Amostra da semana é estável", _amostra(list("abcdef"), "rh") == _amostra(list("abcdef"), "rh"))],
    }
