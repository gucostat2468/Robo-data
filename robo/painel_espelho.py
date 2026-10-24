"""Espelho do painel para o celular: as MESMAS respostas da API do painel, geradas pelo turno da nuvem.

O painel do computador (robo/painel) é servido por um programa Python que lê o banco ao vivo. No celular não há esse
programa. Então o turno da nuvem chama as rotas de leitura do painel (as mesmas funções, sem servidor) e grava cada
resposta como um arquivo JSON no ramo `painel-espelho`. O app do Floot serve o painel ORIGINAL (mesmo HTML, JS, CSS e
escritório 3D) e troca só a origem dos dados: lê o espelho em vez do servidor. Botões que alteram algo ficam
bloqueados no celular (somente leitura).

Regras:
  - só rotas de LEITURA; as que mostram endereço do banco, caminhos do sistema ou IPs ficam de fora (EXCLUIR);
  - antes de publicar, cada arquivo é conferido contra os segredos da configuração e do ambiente: se algum aparecer,
    o arquivo NÃO é publicado e o índice diz qual foi removido (nunca vaza para tapar buraco);
  - CPF válido, e-mail e telefone saem mascarados (o repositório é público; ver mascarar_pessoais);
  - o ramo guarda só a versão atual (um commit, substituído a cada publicação): é uma cópia derivada; a fonte de
    verdade continua no SQLite e no PostgreSQL, com histórico completo.

    python -m robo espelho      gera o espelho deste computador numa pasta (não publica)
"""

from __future__ import annotations

import collections
import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("robo")

RAMO = "painel-espelho"
VERSAO = 1
# config sai numa versão limpa (_config_limpa); diagnóstico do celular: IPs da rede de casa; acesso: o app responde
EXCLUIR = {"/api/config", "/api/celular/diagnostico", "/api/acesso"}
POR_PESSOA = ("/api/funcionario", "/api/treino/pessoa")
ULTIMAS_SOLICITACOES = 40
INTERVALO_MIN_S = 9 * 60  # o turno pede a cada boletim (5 min); o espelho sai a cada ~10 min (pesa mais)
_ultimo = {"t": 0.0}


def chave(rota: str, params: dict | None = None) -> str:
    """Nome do arquivo de uma rota com parâmetros: /api/funcionario?id=x → funcionario__id=x (o app usa a mesma regra)."""
    base = rota[len("/api/"):].replace("/", "_")
    if params:
        base += "__" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return re.sub(r"[^A-Za-z0-9_=&.\-]", "_", base)


def _controle(cfg, ligado_desde: float | None = None):
    """O controle do painel sem ligar nada (sem robô, sem pastas novas): só para as rotas de leitura funcionarem.
    ligado_desde: hora (time.time) em que o turno da nuvem começou; com ela o painel mostra "ligado" (é o turno que
    trabalha); sem ela, "pausado" (entre turnos a empresa fica parada)."""
    from robo.monitor import Monitor
    from robo.painel import controle
    c = object.__new__(controle.ControleRobo)
    c.caminho_config, c.cfg, c.erro_config = None, cfg, None
    c.monitor = Monitor(cfg)
    c._thread = threading.current_thread() if ligado_desde else None  # "ligado" = há uma linha de execução viva
    c._parar, c._trava, c._trava_eventos = threading.Event(), threading.Lock(), threading.Lock()
    c.ligado_desde, c.memoria_log = ligado_desde, controle.MemoriaLog()
    c.eventos, c._seq_eventos = collections.deque(maxlen=400), 0
    return c


def gerar(cfg, ligado_desde: float | None = None) -> dict:
    """{chave: resposta} de todas as rotas de leitura, mais a ficha e o treino de cada pessoa e as últimas demandas."""
    from robo import organizacao
    from robo.painel import servidor
    api = servidor.Api(_controle(cfg, ligado_desde), 0)
    saida, falhas = {}, {}

    def chamar(rota, params=None):
        try:
            saida[chave(rota, params)] = servidor.ROTAS_GET[rota](api, {k: [v] for k, v in (params or {}).items()})
        except servidor.ErroApi:
            pass  # rota que precisa de um id que não existe aqui: o app mostra "não disponível no celular"
        except Exception as e:
            falhas[chave(rota, params)] = f"{type(e).__name__}: {str(e)[:160]}"
    for rota in servidor.ROTAS_GET:
        if rota not in EXCLUIR:
            chamar(rota)
    try:
        saida["config"] = _config_limpa(api)
    except Exception as e:
        falhas["config"] = f"{type(e).__name__}: {str(e)[:160]}"
    for p in organizacao.lista(cfg, com_contratados=True):
        for rota in POR_PESSOA:
            chamar(rota, {"id": p["id"]})
    for s in (saida.get("solicitacoes") or {}).get("itens", [])[:ULTIMAS_SOLICITACOES]:
        if isinstance(s, dict) and s.get("id"):
            chamar("/api/solicitacao", {"id": s["id"]})
    return {"dados": saida, "falhas": falhas}


def _config_limpa(api) -> dict:
    """A tela de configurações sem o que é do servidor: o banco vira só "ligado/desligado" e as pastas só o nome.
    A rota original copiaria um config.yaml de exemplo se não existir arquivo: aqui isso não acontece."""
    from unittest import mock

    from robo.painel import configuracao, servidor
    with mock.patch.object(configuracao, "garantir_arquivo", lambda caminho: Path("config.yaml")):
        c = servidor.ROTAS_GET["/api/config"](api, {})
    b = c.get("banco") or {}
    c["banco"] = {"habilitado": bool(b.get("habilitado")), "senha_definida": bool(b.get("senha_definida"))}
    c["pastas"] = {k: Path(v).name for k, v in (c.get("pastas") or {}).items()}
    c["arquivo_config"] = "turno da nuvem (sem arquivo)"
    c["somente_leitura"] = True
    return c


def segredos(cfg) -> list[str]:
    """Valores que nunca podem aparecer no espelho (senhas, tokens, endereço do banco)."""
    b = getattr(cfg, "banco", {}) or {}
    vals = [b.get("senha"), b.get("senha_leitura"), b.get("host") if b.get("host") not in ("localhost", "127.0.0.1") else None]
    for var in ("ROBO_PG_URL", "ROBO_PG_SENHA_LEITURA", "ROBO_TELEGRAM_TOKEN", "ROBO_TELEGRAM_CODIGO", "GH_TOKEN",
                "GITHUB_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        vals.append(os.environ.get(var))
    return [str(v) for v in vals if v and len(str(v)) >= 6]


def limpar(dados: dict, proibidos: list[str]) -> tuple[dict, list[str]]:
    """Tira inteiro qualquer arquivo em que um segredo aparece (não tenta mascarar: na dúvida, não publica)."""
    bons, removidos = {}, []
    for k, v in dados.items():
        texto = json.dumps(v, ensure_ascii=False, default=str)
        if any(s in texto for s in proibidos):
            removidos.append(k)
        else:
            bons[k] = texto
    return bons, removidos


_RE_CPF_TEXTO = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)|(?<![\d.])\d{11}(?![\d.])")
_RE_EMAIL_TEXTO = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_RE_TEL_TEXTO = re.compile(r"(?:\+?55\s?)?\(\d{2}\)\s?9?\d{4}-\d{4}")


def mascarar_pessoais(texto: str) -> tuple[str, int]:
    """O ramo do espelho é público (o repositório é público): CPF válido, e-mail e telefone viram máscara antes de
    publicar, mesmo os sintéticos (os casos de LGPD do treino têm exemplos com a mesma cara). Devolve (texto, quantos)."""
    from robo.quadro import cpf_valido
    n = 0

    def cpf(m):
        nonlocal n
        if not cpf_valido(m.group(0)):
            return m.group(0)  # número de pedido com 11 dígitos não é CPF
        n += 1
        return "***.***.***-**"

    def troca(rotulo):
        def f(m):
            nonlocal n
            n += 1
            return rotulo
        return f
    texto = _RE_CPF_TEXTO.sub(cpf, texto)
    texto = _RE_EMAIL_TEXTO.sub(troca("***@***"), texto)
    texto = _RE_TEL_TEXTO.sub(troca("(**) *****-****"), texto)
    return texto, n


def escrever(cfg, pasta: Path, codigo_sha: str = "", ligado_desde: float | None = None) -> dict:
    """Grava o espelho em `pasta` (api/<chave>.json + indice.json). Devolve o índice."""
    t0 = time.perf_counter()
    g = gerar(cfg, ligado_desde)
    bons, removidos = limpar(g["dados"], segredos(cfg))
    (pasta / "api").mkdir(parents=True, exist_ok=True)
    mascarados = 0
    for k, texto in bons.items():
        texto, n = mascarar_pessoais(texto)
        mascarados += n
        (pasta / "api" / f"{k}.json").write_text(texto, encoding="utf-8")
    indice = {"versao": VERSAO, "gerado_em": datetime.now().isoformat(timespec="seconds"), "codigo_sha": codigo_sha,
              "chaves": sorted(bons), "removidos_por_seguranca": removidos, "falhas": g["falhas"],
              "dados_pessoais_mascarados": mascarados,
              "segundos": round(time.perf_counter() - t0, 2)}
    (pasta / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
    return indice


def _git(*args, cwd: Path, check: bool = True):
    import subprocess
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120, check=check)


def publicar(cfg, raiz: Path, pasta: Path, remoto: str = "origin", forcar: bool = False,
             ligado_desde: float | None = None) -> bool:
    """Gera e envia o espelho como um único commit no ramo painel-espelho (substitui o anterior). Nunca derruba o turno."""
    if not forcar and time.monotonic() - _ultimo["t"] < INTERVALO_MIN_S:
        return False
    _ultimo["t"] = time.monotonic()
    try:
        sha = _git("rev-parse", "HEAD", cwd=raiz).stdout.strip()
        if not (pasta / ".git").exists():
            _git("worktree", "add", "-f", "--detach", str(pasta), cwd=raiz)
        _git("checkout", "-q", "--orphan", f"espelho_{int(time.time())}", cwd=pasta)
        _git("rm", "-rf", "--quiet", ".", cwd=pasta, check=False)
        for resto in pasta.iterdir():  # sobras não versionadas de uma volta anterior
            if resto.name != ".git" and resto.is_file():
                resto.unlink()
        indice = escrever(cfg, pasta, sha, ligado_desde)
        _git("add", "-A", ".", cwd=pasta)
        _git("-c", "user.name=robo-espelho", "-c", "user.email=robo-espelho@users.noreply.github.com", "commit", "-q",
             "-m", f"espelho do painel {indice['gerado_em']} ({len(indice['chaves'])} respostas)", cwd=pasta)
        r = _git("push", "-q", "--force", remoto, f"HEAD:refs/heads/{RAMO}", cwd=pasta, check=False)
        if r.returncode != 0:
            log.warning("Espelho do painel: não consegui enviar (%s)", (r.stderr or "").strip()[:200])
            return False
        if indice["removidos_por_seguranca"]:
            log.warning("Espelho do painel: %s resposta(s) tinham segredo e NÃO foram publicadas: %s",
                        len(indice["removidos_por_seguranca"]), ", ".join(indice["removidos_por_seguranca"][:10]))
        return True
    except Exception as e:
        log.warning("Espelho do painel: não publiquei (%s: %s)", type(e).__name__, str(e)[:200])
        return False
