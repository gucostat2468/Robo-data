"""Boletim da empresa para o celular: um JSON pequeno com o que está acontecendo, publicado pelo turno da nuvem.

    python -m robo boletim             mostra o boletim deste computador (só lê)

Como chega ao celular sem o seu computador ligado:
  1. o turno da nuvem (GitHub Actions) monta o boletim a cada 5 minutos e no fim do turno;
  2. publica em estado/estado.json no ramo `painel-celular` do repositório (um commit por boletim: o histórico
     inteiro fica guardado, nada é sobrescrito sem registro);
  3. o app do celular (uma página do Claude, privada) lê esse arquivo pelo conector do GitHub e se atualiza sozinho.

Honestidade:
  - só números que estão nos registros (jobs, demandas, treino, fábrica, rotinas); nada é estimado ou inventado;
  - cada bloco diz de quando é o dado; entre um turno e outro a empresa está PARADA e o boletim diz isso;
  - nenhum segredo, nenhum endereço de banco, nenhum dado pessoal (só nomes e cargos dos funcionários virtuais).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("robo")

VERSAO = 1
RAMO = "painel-celular"
ARQUIVO = "estado/estado.json"
LEIA = "README.md"  # o GitHub abre este arquivo sozinho na página do ramo


def _q(c, sql, params=()):
    try:
        return c.execute(sql, params).fetchall()
    except sqlite3.Error:  # tabela que ainda não existe neste banco: bloco vazio, nunca inventado
        return []


def montar(cfg, agora: datetime | None = None, turno: dict | None = None) -> dict:
    from robo import organizacao
    agora = agora or datetime.now()
    hoje = agora.strftime("%Y-%m-%d")
    db = Path(cfg.logs) / "trabalho.db"
    gente = organizacao.por_id(cfg)
    nome = lambda pid: (gente.get(pid) or {}).get("nome", pid)  # noqa: E731
    andares = {a: {"andar": a, "pessoas": 0, "trabalharam_hoje": 0, "demandas": 0, "concluidas": 0, "parciais": 0,
                   "falhas": 0, "treino": 0, "acertos": 0} for a in sorted({p["andar"] for p in gente.values()})}
    for p in gente.values():
        andares[p["andar"]]["pessoas"] += 1
    saida = {"versao": VERSAO, "gerado_em": agora.isoformat(timespec="seconds"), "turno": turno or {},
             "funcionarios": len(gente), "andares": [], "agora": [], "ultimos": [], "sql": {}, "fabrica": {},
             "rotinas": [], "totais": {}, "banco": _banco(cfg)}
    if not db.exists():
        saida["andares"] = list(andares.values())
        return saida
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        ativos_hoje: dict[int, set] = {}
        for pid, andar, estado, n in _q(c, "SELECT funcionario, andar, estado, COUNT(*) FROM solicitacoes "
                                           "WHERE origem='demanda_sintetica' AND criada_em>=? GROUP BY 1,2,3", (hoje,)):
            a = andares.get(andar) or andares.get((gente.get(pid) or {}).get("andar"))
            if not a:
                continue
            a["demandas"] += n
            a["concluidas"] += n if estado == "concluida" else 0
            a["parciais"] += n if estado == "concluida_parcialmente" else 0
            a["falhas"] += n if estado == "falhou" else 0
            ativos_hoje.setdefault(a["andar"], set()).add(pid)
        for pid, andar, n, ac in _q(c, "SELECT funcionario, andar, COUNT(*), SUM(acertou) FROM treino_tentativas "
                                       "WHERE data_hora>=? GROUP BY 1,2", (hoje,)):
            a = andares.get(andar)
            if a:
                a["treino"] += n
                a["acertos"] += int(ac or 0)
                ativos_hoje.setdefault(andar, set()).add(pid)
        for a, quem in ativos_hoje.items():
            andares[a]["trabalharam_hoje"] = len(quem)
        saida["andares"] = list(andares.values())
        # quem está com trabalho aberto AGORA (job sem fim)
        saida["agora"] = [{"funcionario": nome(f), "cargo": (gente.get(f) or {}).get("papel", ""), "tipo": t,
                           "desde": i} for t, f, i in _q(c, "SELECT tipo, funcionario, inicio FROM jobs "
                                                            "WHERE fim IS NULL ORDER BY id DESC LIMIT 10")]
        # últimos trabalhos fechados, com o que foi feito
        for sid, titulo, pid, estado, quando in _q(
                c, "SELECT id, titulo, funcionario, estado, atualizada_em FROM solicitacoes "
                   "WHERE origem='demanda_sintetica' ORDER BY atualizada_em DESC LIMIT 10"):
            p = gente.get(pid) or {}
            saida["ultimos"].append({"quando": quando, "funcionario": nome(pid), "cargo": p.get("papel", ""),
                                     "andar": p.get("andar"), "trabalho": titulo, "estado": estado})
        n, ok = (_q(c, "SELECT COUNT(*), SUM(estado='concluida') FROM solicitacoes WHERE modelo='demanda:sql_treino' "
                       "AND criada_em>=?", (hoje,)) or [(0, 0)])[0]
        saida["sql"] = {"exercicios_hoje": n or 0, "concluidos_hoje": int(ok or 0)}
        n, ok = (_q(c, "SELECT COUNT(*), SUM(estado='conferido_ok') FROM fabrica_lotes WHERE data_hora>=?",
                    (hoje,)) or [(0, 0)])[0]
        saida["fabrica"] = {"lotes_hoje": n or 0, "conferidos_ok_hoje": int(ok or 0)}
        desde = (agora - timedelta(hours=24)).isoformat(timespec="seconds")
        saida["rotinas"] = [{"rotina": r, "execucoes_24h": n, "erros_24h": int(e or 0), "ultima": u}
                            for r, n, e, u in _q(c, "SELECT nome, COUNT(*), SUM(status='erro'), MAX(fim) "
                                                    "FROM rotinas_execucoes WHERE inicio>=? GROUP BY nome ORDER BY nome",
                                                 (desde,))]
        saida["pessoas"] = _pessoas(c, gente, hoje, cfg)
        try:  # projetos entre andares (robo/projetos.py): quem fez cada etapa e como terminou
            from robo import projetos
            saida["projetos"] = projetos.resumo(cfg, 3)
        except Exception as e:
            saida["projetos"] = {"erro": type(e).__name__}
        try:  # tempo MEDIDO dos últimos turnos, por natureza (robo/tempo_turno.py)
            from robo import tempo_turno
            saida["tempo_turnos"] = tempo_turno.ultimos(cfg, 6)
        except Exception as e:
            saida["tempo_turnos"] = {"erro": type(e).__name__}
        try:  # inteligência própria: só o que está no registro de modelos (nunca estimado)
            from robo import modelos_ml
            saida["modelos"] = modelos_ml.resumo(cfg)
        except Exception as e:
            saida["modelos"] = {"erro": type(e).__name__}
        # prova de que o nível é trabalho diferente e não só rótulo: acerto por nível em todo o histórico
        saida["niveis"] = [{"nivel": nv or "sem nível", "demandas": n, "concluidas": int(ok or 0), "parciais": int(pa or 0),
                            "falhas": int(fa or 0)}
                           for nv, n, ok, pa, fa in _q(c, "SELECT json_extract(plano,'$.nivel') nv, COUNT(*), "
                                                          "SUM(estado='concluida'), SUM(estado='concluida_parcialmente'), "
                                                          "SUM(estado='falhou') FROM solicitacoes WHERE origem='demanda_sintetica' "
                                                          "AND COALESCE(json_extract(plano,'$.tipo_demanda'),'') != 'treinamento' "
                                                          "GROUP BY 1 ORDER BY CASE nv WHEN 'basico' THEN 1 WHEN 'medio' THEN 2 "
                                                          "WHEN 'dificil' THEN 3 WHEN 'profissional' THEN 4 ELSE 5 END")]
        tot = lambda sql: (_q(c, sql) or [(0,)])[0][0] or 0  # noqa: E731
        saida["totais"] = {"demandas": tot("SELECT COUNT(*) FROM solicitacoes WHERE origem='demanda_sintetica'"),
                           "tentativas_treino": tot("SELECT COUNT(*) FROM treino_tentativas"),
                           "conversas": tot("SELECT COUNT(*) FROM interacoes"),
                           "trabalhos_com_prova": tot("SELECT COUNT(*) FROM jobs")}
    finally:
        c.close()
    return saida


def _pessoas(c, gente: dict, hoje: str, cfg=None) -> list[dict]:
    """Cada funcionário: o último trabalho e se é do papel dele, ou por que não trabalhou (registro do ciclo)."""
    from robo import demandas, organizacao
    ultima = {}
    for pid, titulo, modelo, estado, quando, plano in _q(
            c, "SELECT funcionario, titulo, modelo, estado, criada_em, plano FROM solicitacoes WHERE origem='demanda_sintetica' "
               "ORDER BY criada_em"):
        ultima[pid] = (titulo, modelo, estado, quando, plano)
    evento, bloqueio = {}, {}
    for pid, ev, motivo, quando in _q(c, "SELECT funcionario, evento, motivo, data_hora FROM demandas_registro ORDER BY id"):
        evento[pid] = (ev, motivo, quando)
        if ev in ("bloqueada", "sem_trabalho"):
            bloqueio[pid] = motivo
    hoje_n = {pid: n for pid, n in _q(c, "SELECT funcionario, COUNT(*) FROM solicitacoes WHERE origem='demanda_sintetica' "
                                         "AND criada_em>=? GROUP BY 1", (hoje,))}
    saida = []
    for pid, p in sorted(gente.items(), key=lambda x: (x[1]["andar"], x[1]["nome"])):
        nivel = organizacao.nivel_de(pid, p)
        item = {"nome": p["nome"], "andar": p["andar"], "cargo": p.get("papel", ""), "area": organizacao.area_de(pid) or "",
                "demandas_hoje": hoje_n.get(pid, 0), "ultimo": "", "quando": "", "estado": "", "situacao": ""}
        u, ev = ultima.get(pid), evento.get(pid)
        if u:
            titulo, modelo, estado, quando, plano = u
            ferr = (modelo or "").split(":")[-1]
            try:
                tipo = json.loads(plano or "{}").get("tipo_demanda") or "trabalho"
            except ValueError:
                tipo = "trabalho"
            item.update(ultimo=titulo or "", quando=quando or "", estado=estado or "")
            if tipo == "treinamento":
                item["situacao"] = "estudo (o trabalho do papel estava bloqueado)"
            else:
                try:
                    papel = ferr in demandas.candidatas(cfg, {"id": pid, "andar": p["andar"]})
                except Exception:
                    papel = True
                item["situacao"] = "trabalho do papel" if papel else "trabalho FORA do papel"
        if nivel == "estagiario":
            item["situacao"] = "estagiário: observa (regra do dono)" + (f" — {ev[1][:120]}" if ev and ev[0] == "observou" else "")
        elif pid in organizacao.ROTINA_PROPRIA:
            item["situacao"] = f"trabalho do papel na rotina {organizacao.ROTINA_PROPRIA[pid]}"
        elif not u:
            item["situacao"] = f"sem trabalho ainda ({ev[1][:120]})" if ev else "sem trabalho ainda"
        if item["situacao"].startswith("estudo") and bloqueio.get(pid):
            item["situacao"] = f"estudo (trabalho do papel bloqueado: {bloqueio[pid][:110]})"
        saida.append(item)
    return saida


def _banco(cfg) -> dict:
    """Cobertura das tabelas (SQLite e PostgreSQL) do último levantamento do turno (cobertura_banco, a cada salvamento).
    Só nomes de tabela, contagens e a causa de cada vazia: nenhum conteúdo, nenhum endereço de banco."""
    arq = Path(cfg.logs) / "cobertura_banco.json"
    if not arq.exists():
        return {}
    try:
        r = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    from robo.cobertura_banco import COM_DADOS
    itens = r.get("itens") or []
    onde = lambda i: i["onde"] if i["onde"] == "sqlite" else f"postgres.{i.get('schema')}"  # noqa: E731
    return {"levantamento": r.get("levantamento"), # conferido = o levantamento CONTOU tabelas no PostgreSQL (banco desligado não conta como conferido)
            "postgres_conferido": not r.get("erro_postgres") and any(i["onde"] == "postgres" for i in itens),
            "erro_postgres": (r.get("erro_postgres") or "")[:120].split(":")[0] or None,
            "tabelas": len(itens), "com_dados": sum(i["situacao"] == COM_DADOS for i in itens),
            "linhas": sum(int(i.get("linhas") or 0) for i in itens), "resumo": r.get("resumo") or {},
            "vazias": [{"onde": onde(i), "tabela": i["tabela"], "situacao": i["situacao"].replace("vazia: ", ""),
                        "causa": (i.get("causa") or "")[:160]} for i in itens if i["situacao"] != COM_DADOS]}


# =============================================================================== versão para ler no navegador
ESTADOS = {"concluida": "✅ concluída", "concluida_parcialmente": "🟡 parcial", "falhou": "🔴 falhou"}


def _hora(iso: str | None) -> str:
    """O turno roda em UTC; quem lê está em Brasília (UTC-3)."""
    if not iso:
        return ""
    try:
        return (datetime.fromisoformat(str(iso)[:19]) - timedelta(hours=3)).strftime("%d/%m %H:%M")
    except ValueError:
        return str(iso)


def markdown(d: dict) -> str:
    """O mesmo boletim em Markdown: o GitHub mostra formatado no navegador do celular, sem login e sem app."""
    t = d.get("turno") or {}
    estado = t.get("estado") or "sem turno"
    andares = d.get("andares") or []
    soma = lambda k: sum(a.get(k) or 0 for a in andares)  # noqa: E731
    dem, ok = soma("demandas"), soma("concluidas")
    taxa = f" ({100 * ok / dem:.0f}%)" if dem else ""
    l = [f"# Empresa ao vivo", "",
         f"**Boletim das {_hora(d.get('gerado_em'))}** (horário de Brasília) · {estado}", "",
         "> Atualiza a cada 5 minutos enquanto a empresa trabalha. Recarregue a página para ver o mais novo.", "",
         "## Hoje", "",
         f"- **{dem}** demandas, **{ok}** concluídas{taxa}, {soma('parciais')} parciais, {soma('falhas')} com falha",
         f"- **{soma('trabalharam_hoje')}** de {d.get('funcionarios')} funcionários já trabalharam",
         f"- SQL: {(d.get('sql') or {}).get('exercicios_hoje', 0)} exercícios, "
         f"{(d.get('sql') or {}).get('concluidos_hoje', 0)} conferidos com o gabarito",
         f"- Fábrica: {(d.get('fabrica') or {}).get('lotes_hoje', 0)} planilhas, "
         f"{(d.get('fabrica') or {}).get('conferidos_ok_hoje', 0)} conferidas sem erro", "",
         "## Trabalhando agora", ""]
    agora = d.get("agora") or []
    l += [f"- {a['funcionario']} ({a.get('cargo', '')}): {a.get('tipo')} desde {_hora(a.get('desde'))[-5:]}" for a in agora] \
        or ["- ninguém com trabalho aberto neste boletim"]
    l += ["", "## Andares", "", "| Andar | Trabalharam | Demandas | Concluídas | Parciais | Falhas |", "|---|--:|--:|--:|--:|--:|"]
    l += [f"| {a['andar']}º | {a['trabalharam_hoje']} de {a['pessoas']} | {a['demandas']} | {a['concluidas']} | "
          f"{a['parciais']} | {a['falhas']} |" for a in andares]
    l += ["", "## Últimas entregas", "", "| Hora | Quem | Trabalho | Resultado |", "|---|---|---|---|"]
    l += [f"| {_hora(u.get('quando'))[-5:]} | {u['funcionario']} ({u.get('andar')}º) | {u.get('trabalho', '')} | "
          f"{ESTADOS.get(u.get('estado'), u.get('estado'))} |" for u in d.get("ultimos") or []]
    if d.get("niveis"):
        l += ["", "## Dificuldade (todo o histórico)", "", "| Nível | Demandas | Concluídas | Parciais | Falhas | Acerto |",
              "|---|--:|--:|--:|--:|--:|"]
        l += [f"| {n['nivel']} | {n['demandas']} | {n['concluidas']} | {n['parciais']} | {n['falhas']} | "
              f"{100 * n['concluidas'] / n['demandas']:.0f}% |" for n in d["niveis"] if n["demandas"]]
    pessoas = d.get("pessoas") or []
    if pessoas:
        fora = [x for x in pessoas if "FORA" in x["situacao"] or x["situacao"].startswith(("sem trabalho", "estudo"))]
        l += ["", "## Cada funcionário", "",
              f"{len(pessoas) - len(fora)} de {len(pessoas)} no trabalho do papel, observando (estagiário) ou na rotina "
              f"própria da equipe; {len(fora)} precisam de atenção.", ""]
        for andar in sorted({x["andar"] for x in pessoas}):
            l += [f"### {andar}º andar", "", "| Quem | Cargo | Situação | Último trabalho | Hoje |", "|---|---|---|---|--:|"]
            l += [f"| {x['nome']} | {x['cargo'][:40]} | {x['situacao'][:90]} | {x['ultimo'][:60]} "
                  f"{('(' + ESTADOS.get(x['estado'], x['estado']) + ')') if x['estado'] else ''} | {x['demandas_hoje']} |"
                  for x in pessoas if x["andar"] == andar]
            l.append("")
    tt = d.get("tempo_turnos")
    if isinstance(tt, list) and tt:
        u = tt[0]
        p = u["percentual"]
        l += ["", "## Tempo do último turno (medido)", "",
              f"- {u['inicio'][11:16]}–{u['fim'][11:16]} ({u['segundos'] / 60:.0f} min, {u['voltas']} voltas; "
              f"cobertura do cronômetro {100 * u['cobertura']:.0f}%)",
              f"- **Entregas aprovadas na revisão independente: {u['entregas_aprovadas']} "
              f"({u['entregas_por_hora']:.1f} por hora)** — o indicador principal",
              "- " + " · ".join(f"{k} {p.get(k, 0):.0f}%" for k in ("operacional", "estudo", "revisao", "coordenacao",
                                                                     "manutencao", "erro", "parado", "sem_medicao")),
              f"- Bloqueios: {u['contagens'].get('bloqueios', 0)}; etapas esperando dependência: "
              f"{u['contagens'].get('etapas_esperando_dependencia', 0)}"]
        if len(tt) > 1:
            l.append("- Turnos anteriores (entregas/hora): " + ", ".join(f"{x['entregas_por_hora']:.1f}" for x in tt[1:]))
    pj = d.get("projetos")
    if isinstance(pj, list) and pj:
        l += ["", "## Projetos entre andares (várias pessoas, uma etapa depende da outra)", ""]
        for x in pj:
            l.append(f"- {x['titulo']}: **{ESTADOS.get(x['estado'], x['estado'])}** — "
                     + "; ".join(f"{e['ordem']}. {e['funcionario']} ({e['estado']})" for e in x["etapas"]))
    m = d.get("modelos") or {}
    if m and "erro" not in m:
        l += ["", "## Inteligência própria (modelo de risco das demandas)", ""]
        if not m.get("modelos"):
            l.append(f"- Ainda sem modelo: {m['rotuladas_agora']} demandas rotuladas de {m['minimo_para_treinar']} "
                     "necessárias para o 1º treino.")
        else:
            l += [f"- {x['id']}: **{x['estado']}** (treinado por {x['criado_por']})" for x in m["modelos"]]
        av = m.get("ultima_avaliacao")
        if av and av.get("candidato"):
            c, bl = av["candidato"], av.get("baseline") or {}
            l.append(f"- Última avaliação independente ({av['quem']}): {av['modelo']} "
                     f"{'aprovado' if av['resultado'] == 'avaliado_aprovado' else 'reprovado'} — log loss {c['log_loss']:.3f} "
                     f"contra baseline {bl.get('log_loss', 0):.3f}" + (f"; motivos: {'; '.join(av['motivos'])}" if av.get("motivos") else ""))
        l += [f"- Referência em sombra: {m.get('referencia') or 'nenhuma'}; {m.get('inferencias_sombra', 0)} previsões em sombra",
              f"- Uso operacional: {m.get('uso_operacional')}"]
    b = d.get("banco") or {}
    if b:
        l += ["", "## Banco de dados", "",
              f"Levantamento das {_hora(b.get('levantamento'))}: **{b['com_dados']} de {b['tabelas']}** tabelas com dados "
              f"({b['linhas']:,} linhas contadas uma a uma).".replace(",", "."),
              "" if b.get("postgres_conferido") else f"> PostgreSQL NÃO conferido neste levantamento ({b.get('erro_postgres') or 'banco desligado'}).",
              "", "| Onde | Tabelas | Com dados |", "|---|--:|--:|"]
        l += [f"| {k} | {v['tabelas']} | {v['com_dados']} |" for k, v in (b.get("resumo") or {}).items()]
        if b.get("vazias"):
            l += ["", "Vazias e por quê (nada é preenchido para parecer cheio):", "",
                  "| Onde | Tabela | Situação | Causa |", "|---|---|---|---|"]
            l += [f"| {v['onde']} | {v['tabela']} | {v['situacao']} | {v['causa'][:110]} |" for v in b["vazias"]]
    l += ["", "---", "Números tirados dos registros da empresa (dado sintético de treino, nunca de cliente)."]
    return "\n".join(l) + "\n"


# =============================================================================== publicar (turno da nuvem)
def _git(*args, cwd: Path, check: bool = True, input_: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60, check=check,
                          input=input_)


MARCA = "BOLETIM-JSON:"


def mensagem(dados: dict) -> str:
    """Primeira linha legível; depois a marca e o JSON compacto numa linha só."""
    leve = {k: v for k, v in dados.items() if k != "pessoas"}
    if leve.get("banco"):  # a lista de vazias fica só no arquivo: a mensagem leva o resumo
        leve["banco"] = {k: v for k, v in leve["banco"].items() if k != "vazias"}
    return f"boletim {dados['gerado_em']}\n\n{MARCA}{json.dumps(leve, ensure_ascii=False, separators=(',', ':'), default=str)}\n"


def ler_mensagem(texto: str) -> dict | None:
    i = texto.find(MARCA)
    if i < 0:
        return None
    try:
        return json.loads(texto[i + len(MARCA):].strip().splitlines()[0])
    except (ValueError, IndexError):
        return None


def publicar(cfg, raiz: Path, pasta: Path, turno: dict | None = None, remoto: str = "origin") -> bool:
    """Grava o boletim num commit do ramo painel-celular e envia. `raiz` é o repositório (o checkout do turno);
    `pasta`, um diretório de trabalho só do boletim (git worktree). Falha aqui nunca derruba o turno."""
    try:
        dados = montar(cfg, turno=turno)
        if not (pasta / ".git").exists():
            existe = _git("fetch", "--depth", "1", remoto, RAMO, cwd=raiz, check=False).returncode == 0
            if existe:
                _git("worktree", "add", "-f", "--detach", str(pasta), "FETCH_HEAD", cwd=raiz)
            else:  # primeira vez: ramo novo, sem o código do projeto (só o boletim)
                _git("worktree", "add", "-f", "--detach", str(pasta), cwd=raiz)
                _git("checkout", "--orphan", "boletim_local", cwd=pasta)
                _git("rm", "-rf", "--quiet", ".", cwd=pasta, check=False)
        alvo = pasta / ARQUIVO
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(json.dumps(dados, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        (pasta / LEIA).write_text(markdown(dados), encoding="utf-8")
        _git("add", ARQUIVO, LEIA, cwd=pasta)
        if _git("diff", "--cached", "--quiet", cwd=pasta, check=False).returncode == 0:
            return True  # nada mudou
        # o boletim vai também na MENSAGEM do commit: o app lê a lista de commits do ramo (JSON puro pelo conector
        # do GitHub) e ganha de graça a série dos últimos boletins para os gráficos do dia
        _git("-c", "user.name=robo-boletim", "-c", "user.email=robo-boletim@users.noreply.github.com",
             "commit", "-q", "-F", "-", cwd=pasta, input_=mensagem(dados))
        r = _git("push", "-q", remoto, f"HEAD:refs/heads/{RAMO}", cwd=pasta, check=False)
        if r.returncode != 0:  # outro turno publicou antes: traz o dele e põe o nosso por cima (sem forçar)
            _git("fetch", "-q", remoto, RAMO, cwd=pasta)
            _git("rebase", "-q", "-X", "theirs", "FETCH_HEAD", cwd=pasta, check=False)
            r = _git("push", "-q", remoto, f"HEAD:refs/heads/{RAMO}", cwd=pasta, check=False)
        if r.returncode != 0:
            log.warning("Boletim: não consegui enviar (%s)", (r.stderr or "").strip()[:200])
            return False
        return True
    except Exception as e:
        log.warning("Boletim: não publiquei (%s: %s)", type(e).__name__, str(e)[:200])
        return False


def ligado() -> bool:
    """Só publica no turno da nuvem e quando o workflow pede (ROBO_PUBLICAR_BOLETIM=1)."""
    return os.environ.get("ROBO_PUBLICAR_BOLETIM") == "1"
