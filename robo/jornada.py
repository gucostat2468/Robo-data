"""Jornada ponta a ponta (equipe de Airflow: Caetano, Bianca e Gael): a esteira inteira, de hora em hora, com resposta
conhecida.

Num computador de teste ISOLADO (pasta temporária, banco desligado, sem regras de produção — nada toca as pastas nem as
tabelas de produção), a Bianca:
  1. coloca uma planilha sintética SUJA (laboratório: título acima do cabeçalho, R$, data em texto, linha duplicada e
     linha de Total) na Bases-Limpeza do computador de teste;
  2. roda o MESMO processamento do monitor (pipeline.processar_arquivo, gravando);
  3. confere cada etapa com a verdade (a planilha nasceu limpa, então o resultado certo é conhecido):
       entrada     o arquivo saiu da Bases-Limpeza;
       leitura     o cabeçalho certo foi achado (todas as colunas da verdade na saída);
       limpeza     linhas certas (sem Total e sem duplicata) e métrica numérica com a soma certa;
       validacao   a execução terminou aprovada;
       saida       o arquivo tratado existe em Bases-Tratadas;
       historico   a execução foi registrada (historico + JSON da execução);
       analise     o 2º andar gerou a análise (logs/analises/<id>.json);
     e mede o tempo de cada etapa (pelos sinais do próprio pipeline).
Cada rodada fica registrada para sempre em jornada_execucoes. Etapa com falha vira alerta no canal #ti com o nome
da etapa.
"""

from __future__ import annotations

import copy
import json
import math
import tempfile
import time
from pathlib import Path

import pandas as pd

from robo.trabalho import Trabalho, _agora

RESPONSAVEL = "airflow_pleno"
ETAPAS = ["entrada", "leitura", "limpeza", "validacao", "saida", "historico", "analise"]
NOME_ETAPA = {"entrada": "Entrada (arquivo saiu da Bases-Limpeza)", "leitura": "Leitura (cabeçalho certo)",
              "limpeza": "Limpeza (linhas e números certos)", "validacao": "Validação (aprovada)",
              "saida": "Saída (arquivo em Bases-Tratadas)", "historico": "Histórico (execução registrada)",
              "analise": "Análise (2º andar gerou o relatório)"}

ESQUEMA = """CREATE TABLE IF NOT EXISTS jornada_execucoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, area TEXT, semente INTEGER, linhas_esperadas INTEGER,
  linhas_saida INTEGER, ok INTEGER, etapa_falhou TEXT, etapas TEXT, tempos TEXT, segundos REAL, versao_codigo TEXT);
CREATE TRIGGER IF NOT EXISTS jornada_execucoes_sem_alterar BEFORE UPDATE ON jornada_execucoes
BEGIN SELECT RAISE(ABORT, 'registro permanente: jornada_execucoes não pode ser alterado'); END;"""


def _tb(cfg) -> Trabalho:
    from robo.trabalho import proteger
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        proteger(c)
    return tb


def _cfg_sandbox(cfg, pasta: Path):
    from robo.config import Config
    dados = copy.deepcopy(cfg.dados)
    dados["regras"] = []
    entrada = pasta / "Bases-Limpeza"
    dados["pastas"] = {"entrada": str(entrada), "saida": "auto", "erros": "auto", "originais": "auto", "relatorios": "auto",
                       "logs": str(pasta / "logs"), "agentes": str(pasta / "agentes"), "habilidades": str(pasta / "habilidades")}
    dados["banco"] = {**(dados.get("banco") or {}), "habilitado": False}   # nunca toca o banco de produção
    entrada.mkdir(parents=True, exist_ok=True)
    c = Config(dados, cfg.base)
    c.criar_pastas()
    return c


def percorrer(cfg, area: str | None = None, semente: int | None = None) -> dict:
    """Uma volta completa na esteira. Não grava nada na produção (quem registra é `rotina`)."""
    from robo import historico, laboratorio
    from robo.limpeza import normalizar_nome_coluna
    from robo.pipeline import processar_arquivo
    semente = int(semente if semente is not None else time.time_ns() % 2_000_000_000)
    area = area or laboratorio.AREAS[semente % len(laboratorio.AREAS)]
    caso = laboratorio.aplicar_nivel(laboratorio.gerar(area, semente), 1, semente)
    certo = laboratorio.verdade(caso)
    met = normalizar_nome_coluna(caso["metrica"])
    etapas = {e: {"ok": False, "detalhe": "não chegou nesta etapa"} for e in ETAPAS}
    tempos: dict[str, float] = {}
    marcas: list[tuple[str, float]] = []
    inicio = time.perf_counter()
    linhas_saida = None
    with tempfile.TemporaryDirectory(prefix="jornada_") as d:
        sb = _cfg_sandbox(cfg, Path(d))
        arq = sb.entrada / f"jornada_{area}_{semente}.xlsx"
        laboratorio.escrever_sujo(caso, arq)
        try:
            r = processar_arquivo(arq, sb, gravar=True,
                                  ao_etapa=lambda etapa, arquivo, **_: marcas.append((etapa, time.perf_counter())))
        except Exception as e:
            etapas["entrada"] = {"ok": False, "detalhe": f"o processamento quebrou: {type(e).__name__}: {e}"}
            r = None
        fim = time.perf_counter()
        for i, (etapa, t) in enumerate(marcas):
            prox = marcas[i + 1][1] if i + 1 < len(marcas) else fim
            tempos[etapa] = round(tempos.get(etapa, 0.0) + (prox - t), 3)
        if r is not None:
            etapas["entrada"] = {"ok": not arq.exists(), "detalhe": "o arquivo saiu da Bases-Limpeza" if not arq.exists()
                                 else "o arquivo continua na Bases-Limpeza (não foi processado)"}
            tabs = {n: df for n, df in (r.tabelas or {}).items() if not n.startswith("dim_")}
            df = next(iter(tabs.values()), None)
            faltam = [c for c in certo.columns if df is None or c not in df.columns]
            etapas["leitura"] = {"ok": df is not None and not faltam,
                                 "detalhe": "cabeçalho certo (todas as colunas)" if df is not None and not faltam
                                 else f"colunas não encontradas: {faltam[:5]}"}
            if df is not None and not faltam:
                linhas_saida = len(df)
                numerica = pd.api.types.is_numeric_dtype(df[met])
                soma_ok = numerica and math.isclose(float(pd.to_numeric(df[met]).sum()), float(certo[met].sum()),
                                                    rel_tol=1e-9, abs_tol=1e-6)
                id_col = normalizar_nome_coluna("ID")
                duplicadas = int(df.duplicated(subset=[id_col]).sum()) if id_col in df.columns else int(df.duplicated().sum())
                total_txt = any(df[c].astype(str).str.strip().str.lower().eq("total").any()
                                for c in df.columns if df[c].dtype == object)
                ok = len(df) == caso["n"] and soma_ok and not duplicadas and not total_txt
                etapas["limpeza"] = {"ok": ok, "detalhe": f"{len(df)} linhas (esperado {caso['n']}); duplicadas: {duplicadas}; "
                                                          f"linha de Total: {'sim' if total_txt else 'não'}; soma de {met} "
                                                          f"{'confere' if soma_ok else 'NÃO confere'}"}
            etapas["validacao"] = {"ok": r.status == "sucesso", "detalhe": f"status final: {r.status}"
                                   + ("" if r.status == "sucesso" else " — " + "; ".join(e.mensagem for e in r.relatorio.erros[:2]))}
            saidas = [Path(p) for p in r.saidas]
            etapas["saida"] = {"ok": bool(saidas) and all(p.exists() and sb.tratadas in p.parents for p in saidas),
                               "detalhe": ", ".join(p.name for p in saidas) or "nenhum arquivo em Bases-Tratadas"}
            exe = historico.ler_execucao(sb.logs, r.id) if r.id else None
            etapas["historico"] = {"ok": bool(exe) and exe.get("status") == r.status,
                                   "detalhe": f"execução {r.id} registrada" if exe else "execução não encontrada no histórico"}
            analise = Path(sb.logs) / "analises" / f"{r.id}.json"
            etapas["analise"] = {"ok": analise.exists(), "detalhe": "relatório de análise gerado" if analise.exists()
                                 else "a análise não foi gerada"}
    falhou = next((e for e in ETAPAS if not etapas[e]["ok"]), None)
    return {"area": area, "semente": semente, "linhas_esperadas": caso["n"], "linhas_saida": linhas_saida, "ok": falhou is None,
            "etapa_falhou": falhou, "etapas": etapas, "tempos": tempos, "segundos": round(time.perf_counter() - inicio, 3)}


def rotina(cfg) -> dict:
    """De hora em hora: uma volta completa, registrada; falha vira alerta no #ti com a etapa."""
    from robo.treino import versao_codigo
    tb = _tb(cfg)
    j = percorrer(cfg)
    with tb.tx() as c:
        jid = c.execute("INSERT INTO jornada_execucoes (data_hora, area, semente, linhas_esperadas, linhas_saida, ok, etapa_falhou, "
                        "etapas, tempos, segundos, versao_codigo) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (_agora(), j["area"], j["semente"], j["linhas_esperadas"], j["linhas_saida"], int(j["ok"]),
                         j["etapa_falhou"], json.dumps(j["etapas"], ensure_ascii=False), json.dumps(j["tempos"]), j["segundos"],
                         versao_codigo())).lastrowid
    if not j["ok"]:
        try:
            from robo.canal import Canal
            e = j["etapa_falhou"]
            Canal(cfg).postar(RESPONSAVEL, f"Jornada ponta a ponta J{jid} parou em {NOME_ETAPA[e]}: {j['etapas'][e]['detalhe']} "
                              f"(planilha sintética de {j['area']}, semente {j['semente']}).", "ti", "alerta")
        except Exception:
            pass
    return {"id": jid, "ok": j["ok"], "etapa_falhou": j["etapa_falhou"], "segundos": j["segundos"]}


def ultimas(cfg, limite: int = 10) -> list[dict]:
    with _tb(cfg).tx() as c:
        linhas = [dict(r) for r in c.execute("SELECT * FROM jornada_execucoes ORDER BY id DESC LIMIT ?", (limite,))]
    for x in linhas:
        x["etapas"] = json.loads(x["etapas"] or "{}")
        x["tempos"] = json.loads(x["tempos"] or "{}")
    return linhas
