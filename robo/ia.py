"""Modelo de linguagem (IA) OPCIONAL — desligado por padrão. A IA só REDIGE; nunca calcula, conta nem decide.

Regras da casa:
  - sem configuração, o robô trabalha com regras, cálculos e a voz determinística (robo/voz.py);
  - nunca finge que um modelo foi consultado: toda frase de IA vem marcada (natureza="hipotese", modelo=...);
  - todo número que aparece no texto da IA precisa existir nos FATOS da mensagem — se não existir, o texto é
    descartado e quem fala é a voz determinística (o número nunca é inventado);
  - chave de API só em VARIÁVEL DE AMBIENTE, nunca em arquivo.

Provedores (config.yaml → ia: provedor):
  nenhum           (padrão) sem IA;
  ollama           modelo LOCAL (127.0.0.1) — nada sai da máquina. ia: {modelo: llama3.1:8b, url: http://127.0.0.1:11434}
  api_compativel   API no formato OpenAI (chat/completions). ia: {url: https://…/v1, modelo: …, chave_env: ROBO_IA_CHAVE}
  anthropic        Claude pela API da Anthropic (pacote `anthropic`, opcional). ia: {modelo: claude-opus-5-5}
                   chave na variável ANTHROPIC_API_KEY.

Resiliência: tempo limite curto, 1 nova tentativa, e disjuntor — 3 falhas seguidas = 10 min sem tentar.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

LOCAIS = {"127.0.0.1", "localhost", "::1"}
PROVEDORES = ("nenhum", "ollama", "api_compativel", "anthropic")
FALHAS_PARA_ABRIR = 3
PAUSA_DISJUNTOR_S = 600

_disjuntor = {"falhas": 0, "aberto_ate": 0.0, "motivo": ""}
_trava = threading.Lock()


def _c(cfg) -> dict:
    return dict((getattr(cfg, "dados", {}) or {}).get("ia") or {})


def _provedor(cfg) -> str:
    p = str(_c(cfg).get("provedor") or "nenhum").lower().strip()
    return "nenhum" if p in ("", "none") else p


def status(cfg) -> dict:
    """{configurado, provedor, modelo, situacao: 'desligada'|'modelo ativo'|'modelo ausente', motivo}. Não chama a rede
    para os provedores remotos (só o Ollama, que é local e rápido)."""
    c, prov = _c(cfg), _provedor(cfg)
    base = {"provedor": prov, "modelo": c.get("modelo")}
    if prov == "nenhum":
        return {**base, "configurado": False, "situacao": "desligada",
                "motivo": "IA desligada: as respostas vêm de regras, cálculos e da voz de cada funcionário."}
    if prov not in PROVEDORES:
        return {**base, "configurado": False, "situacao": "modelo ausente",
                "motivo": f"Provedor '{prov}' não existe. Use um destes: {', '.join(PROVEDORES)}."}
    if time.time() < _disjuntor["aberto_ate"]:
        falta = round((_disjuntor["aberto_ate"] - time.time()) / 60)
        return {**base, "configurado": False, "situacao": "modelo ausente",
                "motivo": f"O modelo falhou {FALHAS_PARA_ABRIR} vezes seguidas ({_disjuntor['motivo']}). "
                          f"Tento de novo em {falta} min; até lá, a voz determinística responde."}
    if prov == "ollama":
        url = str(c.get("url") or "http://127.0.0.1:11434")
        if urlparse(url).hostname not in LOCAIS:
            return {**base, "configurado": False, "situacao": "modelo ausente",
                    "motivo": "Por segurança, o Ollama só é aceito no próprio computador (127.0.0.1)."}
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=2) as r:
                modelos = [m.get("name") for m in json.loads(r.read()).get("models", [])]
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {**base, "configurado": False, "situacao": "modelo ausente", "motivo": f"Ollama não respondeu em {url} ({e})."}
        if c.get("modelo") not in modelos:
            return {**base, "configurado": False, "situacao": "modelo ausente",
                    "motivo": f"Modelo '{c.get('modelo')}' não está instalado no Ollama ({', '.join(modelos) or 'nenhum'})."}
        return {**base, "configurado": True, "situacao": "modelo ativo", "url": url, "motivo": "Ollama local respondendo."}
    if prov == "api_compativel":
        env = str(c.get("chave_env") or "ROBO_IA_CHAVE")
        if not c.get("url") or not c.get("modelo"):
            return {**base, "configurado": False, "situacao": "modelo ausente", "motivo": "Falta ia.url ou ia.modelo no config.yaml."}
        if not os.environ.get(env):
            return {**base, "configurado": False, "situacao": "modelo ausente",
                    "motivo": f"A chave da API não está na variável de ambiente {env}."}
        return {**base, "configurado": True, "situacao": "modelo ativo", "url": c.get("url"),
                "motivo": "API configurada (chave na variável de ambiente)."}
    # anthropic
    try:
        import anthropic  # noqa: F401  — opcional: só é preciso com este provedor
    except ImportError:
        return {**base, "configurado": False, "situacao": "modelo ausente",
                "motivo": "O pacote 'anthropic' não está instalado (pip install anthropic)."}
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {**base, "configurado": False, "situacao": "modelo ausente",
                "motivo": "A chave da Anthropic não está na variável de ambiente ANTHROPIC_API_KEY."}
    return {**base, "modelo": c.get("modelo") or "claude-opus-5-5", "configurado": True, "situacao": "modelo ativo",
            "motivo": "Claude configurado (chave na variável de ambiente)."}


# ------------------------------------------------------------------------------------------------ números e fatos
_NUM = re.compile(r"\d[\d.]*(?:,\d+)?|\d+(?:\.\d+)?")


def numeros_do_texto(texto: str) -> set[str]:
    """Números normalizados (1.234,5 → 1234.5; 98,6 → 98.6; 2026-10-23 vira 2026, 10, 23)."""
    saida = set()
    for bruto in _NUM.findall(str(texto or "")):
        b = bruto.rstrip(".,")
        if not b:
            continue
        if "," in b:
            b = b.replace(".", "").replace(",", ".")
        elif b.count(".") > 1 or re.fullmatch(r"\d{1,3}(\.\d{3})+", b):
            b = b.replace(".", "")
        try:
            v = float(b)
        except ValueError:
            continue
        saida.add(f"{v:g}")
        for parte in re.split(r"\D+", bruto):  # datas e horas: cada pedaço também vale
            if parte:
                saida.add(f"{float(parte):g}")
    return saida


def numeros_dos_fatos(fatos) -> set[str]:
    texto = json.dumps(fatos, ensure_ascii=False, default=str) if not isinstance(fatos, str) else fatos
    return numeros_do_texto(texto)


def numeros_inventados(texto: str, fatos) -> list[str]:
    """Números do texto que NÃO estão nos fatos (0, 1 e 2 contam como palavras comuns: 'um', 'dois')."""
    permitidos = numeros_dos_fatos(fatos) | {"0", "1", "2"}
    return sorted(n for n in numeros_do_texto(texto) if n not in permitidos)


# ------------------------------------------------------------------------------------------------ conversa
def _falhou(motivo: str) -> None:
    with _trava:
        _disjuntor["falhas"] += 1
        _disjuntor["motivo"] = motivo[:160]
        if _disjuntor["falhas"] >= FALHAS_PARA_ABRIR:
            _disjuntor["aberto_ate"] = time.time() + PAUSA_DISJUNTOR_S


def _deu_certo() -> None:
    with _trava:
        _disjuntor.update({"falhas": 0, "aberto_ate": 0.0, "motivo": ""})


def _chamar(s: dict, cfg, sistema: str, mensagens: list[dict], timeout: float) -> str:
    c = _c(cfg)
    if s["provedor"] == "ollama":
        corpo = json.dumps({"model": s["modelo"], "stream": False,
                            "messages": [{"role": "system", "content": sistema}] + mensagens}).encode()
        req = urllib.request.Request(s["url"].rstrip("/") + "/api/chat", data=corpo, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (json.loads(r.read()).get("message") or {}).get("content", "").strip()
    if s["provedor"] == "api_compativel":
        chave = os.environ.get(str(c.get("chave_env") or "ROBO_IA_CHAVE"), "")
        corpo = json.dumps({"model": s["modelo"], "messages": [{"role": "system", "content": sistema}] + mensagens,
                            "temperature": 0.7}).encode()
        req = urllib.request.Request(str(c["url"]).rstrip("/") + "/chat/completions", data=corpo,
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {chave}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    import anthropic
    cliente = anthropic.Anthropic(timeout=timeout, max_retries=0)
    resp = cliente.messages.create(model=s["modelo"], max_tokens=1200, system=sistema, messages=mensagens)
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()


def conversar(cfg, sistema: str, mensagens: list[dict], fatos, timeout: float = 60) -> dict:
    """Pede ao modelo para REDIGIR com base nos fatos. Nunca levanta exceção. Devolve
    {ok, texto, modelo, natureza, aviso}. Texto com número fora dos fatos é descartado (ok=False)."""
    s = status(cfg)
    if not s.get("configurado"):
        return {"ok": False, "texto": "", "modelo": None, "natureza": None, "aviso": s["motivo"]}
    regra = ("\n\nRegras: escreva em português do Brasil, como uma pessoa fala, com frases completas e sem listas, "
             "sem marcadores, sem #, sem *. Use SOMENTE os fatos abaixo. Não invente números, nomes nem datas. "
             "Se faltar um fato, diga que não tem esse dado.\nFATOS:\n"
             + (fatos if isinstance(fatos, str) else json.dumps(fatos, ensure_ascii=False, default=str)))
    ultimo_erro = ""
    for tentativa in (1, 2):  # 1 nova tentativa
        try:
            texto = _chamar(s, cfg, sistema + regra, mensagens, min(float(timeout), 60.0))
        except Exception as e:  # rede, chave, cota, formato: nada disso derruba o robô
            ultimo_erro = f"{type(e).__name__}: {e}"
            continue
        if not texto:
            ultimo_erro = "o modelo devolveu texto vazio"
            continue
        inventados = numeros_inventados(texto, fatos)
        if inventados:
            _deu_certo()  # o modelo respondeu; o problema é o conteúdo, não a conexão
            return {"ok": False, "texto": "", "modelo": s["modelo"], "natureza": "hipotese",
                    "aviso": f"Descartei o texto do modelo: citou número(s) que não estão nos fatos ({', '.join(inventados[:5])})."}
        _deu_certo()
        return {"ok": True, "texto": texto, "modelo": s["modelo"], "natureza": "hipotese",
                "aviso": "Texto redigido por IA a partir dos fatos; os números foram conferidos pelo robô."}
    _falhou(ultimo_erro)
    return {"ok": False, "texto": "", "modelo": s.get("modelo"), "natureza": None,
            "aviso": f"O modelo não respondeu ({ultimo_erro}); quem responde é a voz determinística."}


def redigir(cfg, instrucao: str, fatos: str) -> dict:
    """Compatibilidade: redige um texto só com os fatos. Sem modelo: {ok: False, motivo}."""
    r = conversar(cfg, instrucao, [{"role": "user", "content": instrucao}], fatos, timeout=120)
    if not r["ok"]:
        return {"ok": False, "motivo": r["aviso"]}
    return {"ok": True, "texto": r["texto"], "natureza": r["natureza"], "modelo": r["modelo"], "aviso": r["aviso"]}
