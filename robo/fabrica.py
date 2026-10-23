"""Fábrica de Planilhas: dados SINTÉTICOS de várias regras de negócio, para a empresa inteira treinar — sem parar.

Célula de produção (4º andar, ao lado da Sala de Casos — prioridade da empresa: sem planilha não há treino):
  - Joana (júnior)        GERA a planilha: regra de negócio do catálogo (robo/regras_negocio.py), semente
                          reproduzível, milhares de linhas, e planta a sujeira do mundo real (robo/laboratorio.py);
  - Ruan (pleno)          CONFERE: recalcula o gabarito por OUTRO caminho (numpy, a partir da versão limpa) e compara;
  - Celina (sênior)       REVISA e assina o lote: arquivo íntegro, linhas esperadas, gabarito completo;
  - Teodoro (coordenador) responde pela rotina "fabrica" e confere o resultado da esteira contra o gabarito.

Injeção na esteira (o que faltava): a planilha aprovada entra em Bases-Limpeza/sintetico com o prefixo TREINO_ e um
arquivo ao lado, TREINO_x.gabarito.json. A esteira processa IGUAL a um arquivo real (mesma leitura, limpeza, validação,
conferências), mas publica em Bases-Tratadas/_treino, não carrega no PostgreSQL de produção, e o histórico esconde o
sintético por padrão (robo/historico.py). Nenhum número inventado aparece em painel real.

Regras de segurança:
  - PRIORIDADE DO REAL: com arquivo real na raiz de Bases-Limpeza, a fábrica não gera (e o monitor só lê a subpasta
    sintetico com a raiz vazia);
  - um lote por vez na esteira; teto por dia; 3 falhas seguidas desligam a fábrica até alguém olhar;
  - tudo vira registro: job (prova de trabalho) e fabrica_lotes (do gerado à conferência final).
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from robo import jobs
from robo.trabalho import Trabalho, _agora

log = logging.getLogger("robo")

EQUIPE_FABRICA = [
    {"id": "fab_coordenador", "nome": "Teodoro", "cargo": "Coordenador da Fábrica de Planilhas", "nivel": "coordenador",
     "andar": 4, "cor": "#4D7C0F", "area": "Engenharia de Dados",
     "escopo": ["Responde pela rotina da fábrica: quando gerar, quanto gerar e quando parar",
                "Garante a prioridade da produção real (com arquivo real na fila, a fábrica espera)",
                "Confere o resultado da esteira contra o gabarito de cada lote e registra acerto ou erro"],
     "criterios": ["Nenhum lote sem gabarito", "Nenhum número sintético em painel real", "Teto diário respeitado"],
     "metodologias": ["Dados sintéticos com resposta conhecida", "Gestão de fila com prioridade"]},
    {"id": "fab_gerador", "nome": "Joana", "cargo": "Analista Júnior de Dados Sintéticos", "nivel": "junior", "andar": 4,
     "cor": "#65A30D", "area": "Engenharia de Dados",
     "escopo": ["Gera planilhas de 14 regras de negócio (vendas, marketing, pesquisa, RH, financeiro, operações, educação)",
                "Usa semente reproduzível e planta a sujeira do mundo real conforme o nível"],
     "criterios": ["Mesma semente gera a mesma planilha", "Quantidade de linhas dentro da faixa configurada"],
     "metodologias": ["Geração com semente", "Sujeira controlada (níveis 1 a 4 do laboratório)"]},
    {"id": "fab_conferente", "nome": "Ruan", "cargo": "Analista Pleno de Qualidade de Dados Sintéticos", "nivel": "pleno",
     "andar": 4, "cor": "#3F6212", "area": "Qualidade de Dados",
     "escopo": ["Recalcula o gabarito de cada lote por outro caminho e compara com o do gerador"],
     "criterios": ["Linhas, soma da métrica e contagem por segmento batem"],
     "metodologias": ["Dupla contagem independente"]},
    {"id": "fab_revisor", "nome": "Celina", "cargo": "Especialista Sênior em Dados de Treino", "nivel": "senior", "andar": 4,
     "cor": "#1A2E05", "area": "Qualidade de Dados",
     "escopo": ["Revisa e assina cada lote antes de ele entrar na esteira", "Barra lote com gabarito incompleto ou arquivo íntegro errado"],
     "criterios": ["Arquivo abre", "Gabarito completo", "Prefixo TREINO_ e marcação de origem"],
     "metodologias": ["Revisão por checklist com evidência"]},
]
POR_ID = {p["id"]: p for p in EQUIPE_FABRICA}
GESTORES = {"fab_coordenador": "head_casos", "fab_gerador": "fab_coordenador", "fab_conferente": "fab_coordenador",
            "fab_revisor": "fab_coordenador"}

PADRAO = {"habilitada": True, "intervalo_minutos": 30, "teto_por_dia": 24, "linhas_min": 2000, "linhas_max": 20000,
          "fila_vazia_minutos": 10, "prefixo": "TREINO_", "subpasta": "sintetico", "regras_extra": None}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS fabrica_lotes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, regra TEXT, semente INTEGER, linhas INTEGER, nivel INTEGER,
  arquivo TEXT, gerador TEXT, conferente TEXT, revisor TEXT, estado TEXT, gabarito TEXT, conferencia TEXT,
  resultado TEXT, job_fabrica INTEGER, conferido_em TEXT);
CREATE INDEX IF NOT EXISTS ix_fabrica_estado ON fabrica_lotes(estado, data_hora);
"""
# estados: reprovado_na_conferencia | na_esteira | conferido_ok | conferido_divergente | esteira_reprovou | perdido
_prontos: set[str] = set()


def _c(cfg) -> dict:
    return {**PADRAO, **((getattr(cfg, "dados", {}) or {}).get("fabrica") or {})}


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    chave = str(Path(cfg.logs).resolve())
    if chave not in _prontos:
        from robo.trabalho import proteger
        with tb.tx() as c:
            c.executescript(ESQUEMA)
            proteger(c)
        _prontos.add(chave)
    return tb


def pasta_destino(cfg) -> Path:
    return Path(cfg.entrada) / _c(cfg)["subpasta"]


def _fila_real(cfg) -> list[Path]:
    from robo.monitor import eh_candidato
    try:
        return [p for p in Path(cfg.entrada).iterdir() if eh_candidato(p)]
    except FileNotFoundError:
        return []


# ------------------------------------------------------------------------------------------------ produção de um lote
def produzir_lote(cfg, regra_id: str | None = None, linhas: int | None = None, nivel: int | None = None,
                  semente: int | None = None, injetar: bool = True) -> dict:
    """Joana gera, Ruan confere, Celina revisa. Aprovado + injetar=True: entra em Bases-Limpeza/sintetico."""
    from robo import laboratorio, regras_negocio
    c = _c(cfg)
    tb = _tb(cfg)
    with tb.tx() as conn:
        feitos = conn.execute("SELECT COUNT(*) FROM fabrica_lotes").fetchone()[0]
    regras = regras_negocio.catalogo(cfg)
    regra = regras_negocio.POR_ID.get(regra_id) if regra_id else regras[feitos % len(regras)]
    if regra is None:
        regra = next((r for r in regras if r.id == regra_id), regras[0])
    semente = int(semente if semente is not None else datetime.now().timestamp() * 1000) % 2_000_000_000
    rng = np.random.default_rng(semente)
    linhas = int(linhas or rng.integers(int(c["linhas_min"]), int(c["linhas_max"]) + 1))
    nivel = int(nivel or 1 + (feitos // len(regras)) % 4)
    nome = f"{c['prefixo']}{regra.id}_{datetime.now():%Y%m%d_%H%M%S}_{semente % 100000:05d}.xlsx"
    inicio = _agora()
    etapas = []
    # 1) Joana gera (limpa + sujeira do nível) e calcula o gabarito
    caso = laboratorio.aplicar_nivel(regras_negocio.caso(regra, linhas, semente), nivel, semente)
    limpo = laboratorio.verdade(caso)
    gab = regras_negocio.gabarito(regra, limpo)
    trabalho = Path(cfg.logs) / "fabrica" / nome
    trabalho.parent.mkdir(parents=True, exist_ok=True)
    laboratorio.escrever_sujo(caso, trabalho)
    etapas.append({"etapa": "gerar", "funcionario": "fab_gerador", "ok": trabalho.exists(),
                   "detalhe": f"{regra.nome}: {linhas} linhas, nível {nivel}, semente {semente}"})
    # 2) Ruan confere por outro caminho: numpy sobre os valores crus (não usa pandas nem o gabarito da Joana)
    met = np.array([np.nan if v is None else float(v) for v in caso["rotulos"][regra.metrica]], dtype=float)
    seg = caso["rotulos"][regra.segmento]
    valores, contagens = np.unique(np.array([str(x) for x in seg]), return_counts=True)
    refeito = {"linhas": len(met), "soma_metrica": round(float(np.nansum(met)), 4),
               "por_segmento": {str(v): int(n) for v, n in zip(valores, contagens)}}
    divergencias = [k for k in refeito if refeito[k] != gab[k] and not (k == "soma_metrica" and abs(refeito[k] - gab[k]) <= 0.01)]
    conferencia = {"refeito": refeito, "divergencias": divergencias}
    etapas.append({"etapa": "conferir_gabarito", "funcionario": "fab_conferente", "ok": not divergencias,
                   "detalhe": "gabarito bate por outro caminho" if not divergencias else f"divergiu em {', '.join(divergencias)}"})
    # 3) Celina revisa e assina
    problemas = []
    if not trabalho.exists() or trabalho.stat().st_size == 0:
        problemas.append("arquivo não foi gravado")
    if not nome.startswith(c["prefixo"]):
        problemas.append("sem o prefixo de sintético")
    if divergencias:
        problemas.append("gabarito não confere")
    if gab["linhas"] != linhas:
        problemas.append("quantidade de linhas diferente da pedida")
    etapas.append({"etapa": "revisar_lote", "funcionario": "fab_revisor", "ok": not problemas,
                   "detalhe": "lote aprovado e assinado" if not problemas else "; ".join(problemas)})
    aprovado = not problemas
    estado = "na_esteira" if aprovado and injetar else ("gerado" if aprovado else "reprovado_na_conferencia")
    destino = None
    if aprovado and injetar:
        pasta = pasta_destino(cfg)
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / nome
        (pasta / nome.replace(".xlsx", ".gabarito.json")).write_text(json.dumps(
            {"arquivo": nome, "regra": regra.id, "regra_nome": regra.nome, "area": regra.area, "indicador": regra.indicador,
             "semente": semente, "linhas": linhas, "nivel": nivel, "autor": "fab_gerador", "revisor": "fab_revisor",
             "gabarito": gab, "erros_plantados": laboratorio.NIVEIS.get(nivel), "erros_plausiveis": regra.erros_plausiveis},
            ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        shutil.copy2(trabalho, destino)
    jid = jobs.registrar_concluido(cfg, "fabrica", "sintetico", "fab_coordenador", inicio, etapas,
                                   "concluido" if aprovado else "falhou", nome,
                                   {"regra": regra.id, "linhas": linhas, "nivel": nivel, "destino": str(destino) if destino else None})
    with tb.tx() as conn:
        lote = conn.execute(
            "INSERT INTO fabrica_lotes (data_hora, regra, semente, linhas, nivel, arquivo, gerador, conferente, revisor, estado, "
            "gabarito, conferencia, job_fabrica) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_agora(), regra.id, semente, linhas, nivel, nome, "fab_gerador", "fab_conferente", "fab_revisor", estado,
             json.dumps(gab, ensure_ascii=False, default=str), json.dumps(conferencia, ensure_ascii=False), jid)).lastrowid
    return {"lote": lote, "arquivo": nome, "regra": regra.id, "linhas": linhas, "nivel": nivel, "estado": estado,
            "problemas": problemas, "destino": str(destino) if destino else None}


# ------------------------------------------------------------------------------------------------ conferência final
def _saida_com_metrica(saidas: list[str], metrica: str) -> pd.DataFrame | None:
    for s in saidas:
        p = Path(s)
        try:
            df = pd.read_csv(p, sep=None, engine="python") if p.suffix.lower() == ".csv" else pd.read_excel(p, sheet_name=0)
        except Exception:
            continue
        if metrica in df.columns:
            return df
    return None


def conferir_pendentes(cfg) -> list[dict]:
    """Teodoro: para cada lote na esteira cujo job da planilha já fechou, compara a saída com o gabarito."""
    tb = _tb(cfg)
    with tb.tx() as c:
        lotes = [dict(r) for r in c.execute("SELECT * FROM fabrica_lotes WHERE estado='na_esteira' ORDER BY id")]
    feitos = []
    for lote in lotes:
        with jobs._tb(cfg).tx() as c:
            j = c.execute("SELECT * FROM jobs WHERE tipo='planilha' AND arquivo=? AND fim IS NOT NULL ORDER BY id DESC LIMIT 1",
                          (lote["arquivo"],)).fetchone()
        if not j:
            continue
        gab = json.loads(lote["gabarito"] or "{}")
        ev = json.loads(j["evidencia"] or "{}")
        problemas = []
        if j["estado"] != "concluido":
            estado = "esteira_reprovou"
            problemas.append(f"a esteira terminou como '{j['estado']}' ({ev.get('erros')} erro(s))")
        else:
            if int(ev.get("linhas_saida") or 0) != gab.get("linhas"):
                problemas.append(f"saíram {ev.get('linhas_saida')} linhas; o gabarito diz {gab.get('linhas')}")
            df = _saida_com_metrica(ev.get("saidas") or [], gab.get("metrica"))
            if df is None:
                problemas.append("a coluna da métrica não apareceu na saída")
            else:
                soma = float(pd.to_numeric(df[gab["metrica"]], errors="coerce").sum())
                if abs(soma - float(gab.get("soma_metrica") or 0)) > max(0.05, 1e-6 * abs(soma)):
                    problemas.append(f"soma de {gab['metrica']} deu {soma:.2f}; o gabarito diz {gab['soma_metrica']:.2f}")
            estado = "conferido_divergente" if problemas else "conferido_ok"
        resultado = {"job": j["id"], "estado_job": j["estado"], "problemas": problemas, "linhas_saida": ev.get("linhas_saida")}
        with tb.tx() as c:
            c.execute("UPDATE fabrica_lotes SET estado=?, resultado=?, conferido_em=? WHERE id=? AND estado='na_esteira'",
                      (estado, json.dumps(resultado, ensure_ascii=False), _agora(), lote["id"]))
        jobs.registrar_concluido(cfg, "fabrica", "sintetico", "fab_coordenador", _agora(),
                                 [{"etapa": "conferir_resultado_da_esteira", "funcionario": "fab_coordenador",
                                   "ok": not problemas, "detalhe": "; ".join(problemas) or "a esteira acertou tudo"}],
                                 "concluido", lote["arquivo"], resultado)
        _aprender(cfg, lote, j, problemas)
        feitos.append({"lote": lote["id"], "arquivo": lote["arquivo"], "estado": estado, "problemas": problemas})
    return feitos


def _aprender(cfg, lote: dict, job: dict, problemas: list[str]) -> None:
    """Erro em planilha sintética vira lição de quem trabalhou nela (memória de cada um), acerto também."""
    try:
        from robo import memoria
        with jobs._tb(cfg).tx() as c:
            pessoas = {r[0] for r in c.execute("SELECT DISTINCT funcionario FROM jobs_etapas WHERE job_id=? "
                                                "AND funcionario IS NOT NULL", (job["id"],))}
        for pid in pessoas:
            memoria.experiencia(cfg, pid, "erro" if problemas else "acerto",
                                f"Planilha sintética {lote['regra']} ({lote['linhas']} linhas, nível {lote['nivel']})",
                                "fabrica", lote["arquivo"], "; ".join(problemas) or "resultado igual ao gabarito")
    except Exception:
        log.debug("Fábrica: aprendizado não registrado", exc_info=True)


# ------------------------------------------------------------------------------------------------ rotina
def rotina(cfg) -> dict | None:
    """Rotina 'fabrica' (Teodoro). Confere o que voltou da esteira e, se a fila real estiver vazia, produz um lote."""
    c = _c(cfg)
    if not c["habilitada"]:
        return None
    tb = _tb(cfg)
    conferidos = conferir_pendentes(cfg)
    hoje = datetime.now().strftime("%Y-%m-%d")
    with tb.tx() as conn:
        do_dia = conn.execute("SELECT COUNT(*) FROM fabrica_lotes WHERE data_hora LIKE ?", (hoje + "%",)).fetchone()[0]
        na_esteira = conn.execute("SELECT COUNT(*) FROM fabrica_lotes WHERE estado='na_esteira'").fetchone()[0]
        ultimos = [r[0] for r in conn.execute("SELECT estado FROM fabrica_lotes ORDER BY id DESC LIMIT 3")]
    saida = {"conferidos": conferidos} if conferidos else {}
    if len(ultimos) == 3 and all(e in ("reprovado_na_conferencia", "esteira_reprovou") for e in ultimos):
        return {**saida, "parada": "3 falhas seguidas: a fábrica parou até alguém olhar (Teodoro avisou no canal)"}
    if _fila_real(cfg):
        return {**saida, "aguardando_real": True} if saida else None   # produção real primeiro
    if na_esteira or do_dia >= int(c["teto_por_dia"]):
        return saida or None
    agora = datetime.now()
    with tb.tx() as conn:
        ultimo_lote = conn.execute("SELECT MAX(data_hora) FROM fabrica_lotes").fetchone()[0]
    with jobs._tb(cfg).tx() as conn:
        ultimo_real = conn.execute("SELECT MAX(fim) FROM jobs WHERE tipo='planilha' AND origem='real'").fetchone()[0]
    if ultimo_lote and (agora - datetime.fromisoformat(ultimo_lote)).total_seconds() < 60 * float(c["intervalo_minutos"]):
        return saida or None
    if ultimo_real and (agora - datetime.fromisoformat(ultimo_real)).total_seconds() < 60 * float(c["fila_vazia_minutos"]):
        return saida or None  # a fila real acabou de esvaziar: espera um pouco antes de assumir
    lote = produzir_lote(cfg)
    return {**saida, "lote": lote}


def resumo(cfg) -> dict:
    tb = _tb(cfg)
    with tb.tx() as c:
        por_estado = {r[0]: r[1] for r in c.execute("SELECT estado, COUNT(*) FROM fabrica_lotes GROUP BY estado")}
        ultimos = [dict(r) for r in c.execute("SELECT id, data_hora, regra, linhas, nivel, arquivo, estado, resultado "
                                              "FROM fabrica_lotes ORDER BY id DESC LIMIT 15")]
        linhas = c.execute("SELECT COALESCE(SUM(linhas), 0) FROM fabrica_lotes").fetchone()[0]
    return {"config": {k: v for k, v in _c(cfg).items() if k != "regras_extra"}, "por_estado": por_estado,
            "linhas_geradas": linhas, "ultimos": ultimos, "equipe": EQUIPE_FABRICA}


# ------------------------------------------------------------------------------------------------ provas do RH
def provas() -> dict:
    import tempfile
    from robo.config import Config
    with tempfile.TemporaryDirectory() as d:
        cfg = Config({"pastas": {"entrada": str(Path(d) / "entrada"), "logs": str(Path(d) / "logs"),
                                 "agentes": str(Path(d) / "agentes"), "habilidades": str(Path(d) / "hab")},
                      "banco": {"habilitado": False}}, Path(d))
        cfg.criar_pastas()
        a = produzir_lote(cfg, "vendas", 300, 1, semente=42, injetar=False)
        b = produzir_lote(cfg, "vendas", 300, 1, semente=42, injetar=False)
        with _tb(cfg).tx() as c:
            gabs = [json.loads(r[0]) for r in c.execute("SELECT gabarito FROM fabrica_lotes ORDER BY id")]
    return {
        "fab_gerador": [("Gera as linhas pedidas", a["linhas"] == 300), ("Mesma semente, mesmo gabarito", gabs[0] == gabs[1])],
        "fab_conferente": [("Gabarito confere por outro caminho", a["estado"] == "gerado")],
        "fab_revisor": [("Assina lote íntegro", not a["problemas"])],
        "fab_coordenador": [("Prefixo de sintético no nome", a["arquivo"].startswith("TREINO_"))],
    }
