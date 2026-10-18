"""Gestão do projeto: cada página, cada andar, cada função e cada módulo — com números tirados dos registros.

Nada aqui é escrito à mão como "está tudo bem": o inventário vem do código (rotas, ferramentas, módulos, testes) e o
estado vem do banco (usos, acertos, erros, handovers, lições, erros de sistema).

Evolução real de cada funcionário = taxa de acerto registrada (experiências 'acerto' x 'erro'), semana a semana.
Só dizemos "evoluindo" ou "piorando" com amostra mínima nas duas janelas comparadas; sem amostra, "dados insuficientes".
"""

from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta
from pathlib import Path

from robo import organizacao
from robo.trabalho import Trabalho

RAIZ = Path(__file__).resolve().parent.parent

# Páginas do painel: para que servem e o que carregam (as rotas são conferidas ao vivo pela API de gestão)
PAGINAS = [
    {"id": "inicio", "titulo": "Visão geral", "para_que": "Saber em 5 segundos se o robô está trabalhando e o que entrou hoje",
     "andar": 4, "apis": ["/api/estado", "/api/historico"]},
    {"id": "central", "titulo": "Central de dados", "para_que": "Acompanhar volume, qualidade e fila em tempo real", "andar": 4,
     "apis": ["/api/central"]},
    {"id": "estrategia", "titulo": "Estratégia", "para_que": "Backlog da sprint, avaliações técnicas e boas práticas", "andar": 4,
     "apis": ["/api/estrategia", "/api/boas-praticas"]},
    {"id": "escritorio", "titulo": "Escritório 3D", "para_que": "Ver quem está fazendo o quê, andar por andar", "andar": 4,
     "apis": ["/api/escritorio"]},
    {"id": "reuniao", "titulo": "Sala de reunião", "para_que": "Reunir a liderança de um andar (estilo Teams) e decidir", "andar": 4,
     "apis": ["/api/reuniao/salas"]},
    {"id": "raio", "titulo": "Raio-X da empresa", "para_que": "Como a empresa está agora e onde tudo fica registrado", "andar": 4,
     "apis": ["/api/raio-x"]},
    {"id": "gestao", "titulo": "Gestão do projeto", "para_que": "Saúde de cada página, andar, função e módulo; evolução real",
     "andar": 4, "apis": ["/api/gestao"]},
    {"id": "chat", "titulo": "Chat da empresa", "para_que": "Conversar com qualquer funcionário, com filtros", "andar": 4,
     "apis": ["/api/funcionarios"]},
    {"id": "registros", "titulo": "Banco da empresa", "para_que": "Cada tabela da memória: linhas, proteção, backups e cópia no PostgreSQL",
     "andar": 5, "apis": ["/api/banco/registros"]},
    {"id": "treino", "titulo": "Treino contínuo", "para_que": "Todos treinando em casos com gabarito, no nível de cada um",
     "andar": 4, "apis": ["/api/treino"]},
    {"id": "solicitacoes", "titulo": "Solicitações", "para_que": "Pedidos, planos, aprovações e entregas", "andar": 4,
     "apis": ["/api/solicitacoes"]},
    {"id": "conhecimento", "titulo": "Conhecimento", "para_que": "Caderno de lições de cada um e erros de sistema", "andar": 4,
     "apis": ["/api/conhecimento", "/api/erros"]},
    {"id": "memoria", "titulo": "Memória e reuniões", "para_que": "Acertos, erros, handovers, PDCA e reunião semanal", "andar": 4,
     "apis": ["/api/memoria"]},
    {"id": "canal", "titulo": "Canal da equipe", "para_que": "O que a equipe postou e as sprints de 15 dias", "andar": 4,
     "apis": ["/api/canal"]},
    {"id": "agentes", "titulo": "Equipe e contratações", "para_que": "Fichas, provas, contratação e manuais", "andar": 4,
     "apis": ["/api/agentes"]},
    {"id": "ti", "titulo": "TI e segurança", "para_que": "Rondas de saúde, segurança e alertas", "andar": 5, "apis": ["/api/ti"]},
    {"id": "reprovados", "titulo": "Reprovados", "para_que": "Planilhas barradas e o motivo, para corrigir e reenviar", "andar": 1,
     "apis": ["/api/reprovados"]},
    {"id": "historico", "titulo": "Histórico", "para_que": "Toda planilha processada, com a ficha completa", "andar": 1,
     "apis": ["/api/historico"]},
    {"id": "testar", "titulo": "Testar planilha", "para_que": "Diagnosticar um arquivo sem gravar nada", "andar": 1, "apis": []},
    {"id": "banco", "titulo": "Banco de dados", "para_que": "Tabelas do PostgreSQL (bruto → tratado → analítico)", "andar": 1,
     "apis": ["/api/banco/resumo"]},
    {"id": "consultas", "titulo": "Consultas SQL", "para_que": "Consultas prontas por problema de negócio", "andar": 2,
     "apis": ["/api/consultas"]},
    {"id": "atividade", "titulo": "Atividade", "para_que": "Log do robô ao vivo", "andar": 5, "apis": ["/api/log"]},
    {"id": "configuracoes", "titulo": "Configurações", "para_que": "Pastas, banco, senha e preferências", "andar": 5,
     "apis": ["/api/config"]},
]

MIN_EVENTOS = 5          # amostra mínima por janela para afirmar tendência
LIMIAR_PP = 5.0          # diferença mínima (pontos percentuais) para dizer que mudou


def _tb(cfg) -> Trabalho:
    return Trabalho(cfg)


def _existe(c, tabela: str) -> bool:
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabela,)).fetchone())


# =============================================================================== evolução real
def evolucao(cfg, semanas: int = 8, agora: datetime | None = None) -> list[dict]:
    """Taxa de acerto por semana de cada funcionário e a tendência (últimas 2 semanas x as anteriores)."""
    agora = agora or datetime.now()
    inicio = agora - timedelta(weeks=semanas)
    with _tb(cfg).tx() as c:
        linhas = c.execute("SELECT funcionario, data_hora, tipo FROM experiencias WHERE tipo IN ('acerto','erro') AND data_hora>=?",
                           (inicio.isoformat(timespec="seconds"),)).fetchall()
    por: dict[str, list[list[int]]] = {}
    for r in linhas:
        try:
            d = datetime.fromisoformat(str(r["data_hora"]).replace(" ", "T")[:19])
        except ValueError:
            continue
        semana = min(int((agora - d).days // 7), semanas - 1)  # 0 = semana atual
        serie = por.setdefault(r["funcionario"], [[0, 0] for _ in range(semanas)])
        serie[semana][0 if r["tipo"] == "acerto" else 1] += 1
    gente = organizacao.por_id(cfg)
    saida = []
    for p in organizacao.lista(cfg):
        serie = por.get(p["id"], [[0, 0] for _ in range(semanas)])
        taxas = [round(100 * a / (a + e), 1) if a + e else None for a, e in reversed(serie)]  # da mais antiga à atual
        rec, ant = serie[:2], serie[2:]
        ra, re_ = sum(x[0] for x in rec), sum(x[1] for x in rec)
        aa, ae = sum(x[0] for x in ant), sum(x[1] for x in ant)
        if ra + re_ >= MIN_EVENTOS and aa + ae >= MIN_EVENTOS:
            agora_t, antes_t = 100 * ra / (ra + re_), 100 * aa / (aa + ae)
            delta = round(agora_t - antes_t, 1)
            tendencia = "evoluindo" if delta >= LIMIAR_PP else "piorando" if delta <= -LIMIAR_PP else "estavel"
        else:
            delta, tendencia = None, "dados_insuficientes"
        saida.append({"id": p["id"], "nome": p["nome"], "andar": p["andar"], "papel": gente.get(p["id"], p).get("papel", ""),
                      "taxas_semana": taxas, "eventos": sum(a + e for a, e in serie), "delta_pp": delta, "tendencia": tendencia})
    return saida


# =============================================================================== funções (ferramentas)
def _texto_dos_testes() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in (RAIZ / "testes").glob("teste_*.py"))


def funcoes(cfg, dias: int = 30) -> list[dict]:
    from robo import ferramentas
    desde = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    usos: dict[str, dict] = {}
    with _tb(cfg).tx() as c:
        if _existe(c, "uso_ferramentas"):
            for r in c.execute("SELECT ferramenta, COUNT(*) n, SUM(ok) ok, SUM(excecao IS NOT NULL) exc, MAX(data_hora) ult, "
                               "AVG(segundos) seg FROM uso_ferramentas WHERE data_hora>=? GROUP BY ferramenta", (desde,)):
                usos[r["ferramenta"]] = dict(r)
    testes = _texto_dos_testes()
    saida = []
    for fid, f in ferramentas.REGISTRO.items():
        u = usos.get(fid, {})
        n = u.get("n") or 0
        autorizados = [p["id"] for p in organizacao.lista(cfg, com_contratados=False) if organizacao.pode_usar(p["id"], fid, cfg)]
        saida.append({"id": fid, "nome": f.nome, "descricao": f.descricao, "risco": f.risco, "altera_dados": f.altera_dados,
                      "autorizados": len(autorizados), "responsavel": organizacao.quem_usa(fid, cfg),
                      "usos": n, "pct_ok": round(100 * (u.get("ok") or 0) / n) if n else None,
                      "excecoes": u.get("exc") or 0, "ultimo_uso": u.get("ult"),
                      "segundos_medio": round(u["seg"], 3) if u.get("seg") is not None else None,
                      "citada_em_testes": len(re.findall(rf"['\"]{re.escape(fid)}['\"]", testes))})
    return saida


# =============================================================================== módulos (código)
def modulos(cfg) -> list[dict]:
    erros: dict[str, int] = {}
    with _tb(cfg).tx() as c:
        if _existe(c, "erros_sistema"):
            for r in c.execute("SELECT modulo, SUM(ocorrencias) n FROM erros_sistema WHERE estado <> 'resolvido' GROUP BY modulo"):
                erros[r["modulo"]] = r["n"]
    testes = {p.name: p.read_text(encoding="utf-8") for p in (RAIZ / "testes").glob("teste_*.py")}
    saida = []
    for arq in sorted((RAIZ / "robo").rglob("*.py")):
        if "__pycache__" in arq.parts or arq.name == "__init__.py":
            continue
        texto = arq.read_text(encoding="utf-8")
        try:
            doc = (ast.get_docstring(ast.parse(texto)) or "").strip().split("\n")[0]
        except SyntaxError:
            doc = "(não compila)"
        mod = ".".join(arq.relative_to(RAIZ).with_suffix("").parts)
        curto = arq.stem
        cobertos = [n for n, t in testes.items() if re.search(rf"\b(from robo(\.\w+)* import [^\n]*\b{curto}\b|{re.escape(mod)}\b)", t)]
        saida.append({"modulo": mod, "linhas": texto.count("\n") + 1, "para_que": doc,
                      "funcoes": len(re.findall(r"(?m)^\s*def ", texto)), "testes": cobertos,
                      "erros_abertos": erros.get(curto, 0)})
    return saida


# =============================================================================== andares
def andares(cfg, evol: list[dict] | None = None) -> list[dict]:
    from robo import lideranca, licoes, memoria
    evol = evol if evol is not None else evolucao(cfg)
    desemp = {d["id"]: d for d in memoria.desempenho(cfg, 30)}
    lic = {p["funcionario"]: p for p in licoes.painel(cfg)["pessoas"]}
    gente = organizacao.lista(cfg)
    saida = []
    for andar, nome in organizacao.NOME_ANDAR.items():
        ps = [p for p in gente if p["andar"] == andar]
        ids = {p["id"] for p in ps}
        ac = sum((desemp.get(i) or {}).get("acertos", 0) for i in ids)
        er = sum((desemp.get(i) or {}).get("erros", 0) for i in ids)
        lt = sum((lic.get(i) or {}).get("total", 0) for i in ids)
        la = sum((lic.get(i) or {}).get("aplicadas") or 0 for i in ids)
        tend = {}
        for e in evol:
            if e["id"] in ids:
                tend[e["tendencia"]] = tend.get(e["tendencia"], 0) + 1
        diretor = lideranca.DIRETOR_DO_ANDAR.get(andar)
        try:
            sc = lideranca.scorecard(cfg, diretor) if diretor else None
            farol = "vermelho" if sc and any(i["farol"] == "vermelho" for i in sc["indicadores"]) else \
                "amarelo" if sc and any(i["farol"] == "amarelo" for i in sc["indicadores"]) else "verde" if sc else "cinza"
        except Exception:
            farol = "cinza"
        abertos = memoria.handovers(cfg, andar, abertos=True, limite=1000)
        saida.append({
            "andar": andar, "nome": nome, "pessoas": len(ps),
            "diretor": diretor, "head": lideranca.HEAD_DO_ANDAR.get(andar), "farol": farol,
            "acertos_30d": ac, "erros_30d": er, "taxa_30d": round(100 * ac / (ac + er), 1) if ac + er else None,
            "handovers_abertos": len(abertos), "handovers_recorrentes": sum(1 for h in abertos if h["recorrencias"] >= 3),
            "licoes_atribuidas": lt, "pct_licoes_aplicadas": round(100 * la / lt) if lt else None,
            "tendencias": tend,
            "insuficientes": [(desemp.get(i) or {}).get("nome", i) for i in ids if (desemp.get(i) or {}).get("situacao") == "insuficiente"],
        })
    return saida


# =============================================================================== visão consolidada
def visao(cfg) -> dict:
    evol = evolucao(cfg)
    fs = funcoes(cfg)
    ms = modulos(cfg)
    contagem = {}
    for e in evol:
        contagem[e["tendencia"]] = contagem.get(e["tendencia"], 0) + 1
    from robo import aprendizado, laboratorio, licoes
    lp = licoes.painel(cfg)
    at = lp["atribuicoes"]
    total = sum(at.values()) or 1
    return {
        "aprendizado": {**aprendizado.resumo(cfg), "licoes_comprovadas_pct": round(100 * at.get("aplicada", 0) / total),
                        "integridade": lp["integridade"]["integra"]},
        "laboratorio": laboratorio.por_nivel(cfg),
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "paginas": PAGINAS,
        "andares": andares(cfg, evol),
        "funcoes": fs,
        "modulos": ms,
        "evolucao": evol,
        "resumo": {
            "funcionarios": len(evol), "tendencias": contagem,
            "funcoes_sem_uso_30d": [f["id"] for f in fs if not f["usos"]],
            "funcoes_sem_teste": [f["id"] for f in fs if not f["citada_em_testes"]],
            "modulos_sem_teste": [m["modulo"] for m in ms if not m["testes"]],
            "modulos_com_erro_aberto": [m["modulo"] for m in ms if m["erros_abertos"]],
        },
    }
