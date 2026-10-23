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
             "rotinas": [], "totais": {}}
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
        tot = lambda sql: (_q(c, sql) or [(0,)])[0][0] or 0  # noqa: E731
        saida["totais"] = {"demandas": tot("SELECT COUNT(*) FROM solicitacoes WHERE origem='demanda_sintetica'"),
                           "tentativas_treino": tot("SELECT COUNT(*) FROM treino_tentativas"),
                           "conversas": tot("SELECT COUNT(*) FROM interacoes"),
                           "trabalhos_com_prova": tot("SELECT COUNT(*) FROM jobs")}
    finally:
        c.close()
    return saida


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
    l += ["", "---", "Números tirados dos registros da empresa (dado sintético de treino, nunca de cliente)."]
    return "\n".join(l) + "\n"


# =============================================================================== publicar (turno da nuvem)
def _git(*args, cwd: Path, check: bool = True, input_: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60, check=check,
                          input=input_)


MARCA = "BOLETIM-JSON:"


def mensagem(dados: dict) -> str:
    """Primeira linha legível; depois a marca e o JSON compacto numa linha só."""
    return f"boletim {dados['gerado_em']}\n\n{MARCA}{json.dumps(dados, ensure_ascii=False, separators=(',', ':'), default=str)}\n"


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
