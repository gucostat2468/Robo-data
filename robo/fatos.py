"""Fatos do dia: a FONTE DE VERDADE ÚNICA do que aconteceu, para quem conversa, resume ou mostra números.

Cada fato: {id, tipo, valor, fonte, quando, responsavel, detalhe}. O id é estável (o mesmo fato tem o mesmo id), para
ninguém conversar duas vezes sobre a mesma coisa. Só entra o que está registrado; sintético (TREINO_) fica fora dos
fatos de produção e aparece só como fato da fábrica.

Tipos: arquivo_aprovado, arquivo_reprovado, linhas_processadas, erro_recorrente (esteira), erro_repetido_treino,
rotina_erro, licao_nova, pendencia_dono, alerta_ti, backup, fila_travada, fabrica_divergencia.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from robo.trabalho import Trabalho


def _tabelas(c) -> set[str]:
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def fatos_do_dia(cfg, agora: datetime | None = None) -> list[dict]:
    from robo.rotinas import ROTINAS
    agora = agora or datetime.now()
    dia = agora.strftime("%Y-%m-%d")
    fatos: list[dict] = []

    def add(fid, tipo, valor, fonte, quando, responsavel, detalhe=""):
        fatos.append({"id": f"{dia}:{fid}", "tipo": tipo, "valor": valor, "fonte": fonte, "quando": quando,
                      "responsavel": responsavel, "detalhe": detalhe})

    with Trabalho(cfg).tx() as c:
        tem = _tabelas(c)
        if "jobs" in tem:
            linhas = 0
            for j in c.execute("SELECT id, arquivo, estado, fim, evidencia FROM jobs WHERE tipo='planilha' AND origem='real' "
                               "AND fim LIKE ?", (dia + "%",)):
                ev = json.loads(j["evidencia"] or "{}")
                if j["estado"] == "concluido":
                    linhas += int(ev.get("linhas_saida") or 0)
                    add(f"job{j['id']}", "arquivo_aprovado", j["arquivo"], f"jobs#{j['id']}", j["fim"], "validacao",
                        f"{ev.get('linhas_saida')} linhas publicadas")
                elif j["estado"] == "falhou":
                    add(f"job{j['id']}", "arquivo_reprovado", j["arquivo"], f"jobs#{j['id']}", j["fim"], "validacao",
                        f"{ev.get('erros')} erro(s)")
            if linhas:
                add("linhas", "linhas_processadas", linhas, "jobs", dia, "coord_engenharia")
        if "aprendizados" in tem:
            for r in c.execute("SELECT competencia, causa, COUNT(*) n, MAX(id) ultimo, MAX(funcionario) quem FROM aprendizados "
                               "WHERE resultado='erro' AND origem='pipeline' AND data_hora LIKE ? GROUP BY competencia, causa "
                               "HAVING n >= 2", (dia + "%",)):
                add(f"aprend{r['ultimo']}", "erro_recorrente", r["n"], f"aprendizados#{r['ultimo']}", dia, r["quem"],
                    f"{r['causa'][:200]}")
            for r in c.execute("SELECT funcionario, competencia, COUNT(*) n, MAX(id) ultimo, MAX(causa) causa FROM aprendizados "
                               "WHERE resultado='erro' AND origem='treino' AND data_hora LIKE ? GROUP BY funcionario, competencia "
                               "HAVING n >= 2", (dia + "%",)):
                add(f"treino{r['ultimo']}", "erro_repetido_treino", r["n"], f"aprendizados#{r['ultimo']}", dia,
                    r["funcionario"], f"{r['competencia']}|{(r['causa'] or '')[:200]}")
        if "rotinas_execucoes" in tem:
            for r in c.execute("SELECT id, nome, fim, detalhe FROM rotinas_execucoes WHERE status='erro' AND fim LIKE ?",
                               (dia + "%",)):
                add(f"rot{r['id']}", "rotina_erro", r["nome"], f"rotinas_execucoes#{r['id']}", r["fim"],
                    (ROTINAS.get(r["nome"]) or (None,))[0], (r["detalhe"] or "")[:300])
        if "licoes" in tem:
            n = c.execute("SELECT COUNT(*) FROM licoes WHERE criada_em LIKE ?", (dia + "%",)).fetchone()[0] \
                if "criada_em" in {x[1] for x in c.execute("PRAGMA table_info(licoes)")} else 0
            if n:
                add("licoes", "licao_nova", n, "licoes", dia, "rh_td")
        if "backups_registro" in tem:
            r = c.execute("SELECT COUNT(*), MAX(id) FROM backups_registro WHERE data_hora LIKE ?", (dia + "%",)).fetchone()
            if r[0]:
                add(f"backup{r[1]}", "backup", r[0], f"backups_registro#{r[1]}", dia, "dba")
        if "fabrica_lotes" in tem:
            for r in c.execute("SELECT id, arquivo, resultado, regra FROM fabrica_lotes WHERE estado='conferido_divergente' "
                               "AND conferido_em LIKE ?", (dia + "%",)):
                prob = "; ".join(json.loads(r["resultado"] or "{}").get("problemas") or [])
                add(f"fab{r['id']}", "fabrica_divergencia", r["arquivo"], f"fabrica_lotes#{r['id']}", dia, "fab_coordenador",
                    f"{r['regra']}: {prob[:250]}")
    try:
        from robo import caixa_dono
        n = caixa_dono.resumo(cfg)["novas"]
        if n:
            add(f"caixa:{n}", "pendencia_dono", n, "caixa_dono", dia, "ger_operacoes")
    except Exception:
        pass
    try:
        from robo import ti
        ronda = ti.ultima_ronda(cfg) or {}
        for i in ronda.get("itens") or []:
            if i.get("achados"):
                add(f"ti:{i['id']}:{len(i['achados'])}", "alerta_ti", i["achados"][0], "ronda_ti", ronda.get("data_hora"),
                    i["id"], "; ".join(i["achados"])[:300])
    except Exception:
        pass
    try:
        from robo.monitor import eh_candidato
        velhos = [p for p in Path(cfg.entrada).iterdir() if eh_candidato(p)
                  and datetime.fromtimestamp(p.stat().st_mtime) < agora - timedelta(minutes=30)]
        if velhos:
            add(f"fila:{len(velhos)}", "fila_travada", len(velhos), "Bases-Limpeza", dia, "recepcao",
                ", ".join(p.name for p in velhos[:5]))
    except Exception:
        pass
    return fatos
