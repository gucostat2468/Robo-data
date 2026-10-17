"""Modelo de linguagem (IA) OPCIONAL — desligado por padrão.

Regras da casa:
  - sem configuração, o robô diz "nenhum modelo configurado" e trabalha só com regras e código (como hoje);
  - nunca finge que um modelo foi consultado: toda resposta de IA vem marcada como tal;
  - só aceita modelo LOCAL (no próprio computador, ex.: Ollama em 127.0.0.1) — nada sai da máquina;
  - IA só redige texto; número, cálculo, SQL e decisão continuam determinísticos e conferidos.

Configuração (config.yaml):
  ia:
    provedor: ollama            # "nenhum" (padrão) ou "ollama"
    modelo: llama3.1:8b
    url: http://127.0.0.1:11434
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

LOCAIS = {"127.0.0.1", "localhost", "::1"}


def _c(cfg) -> dict:
    return dict((getattr(cfg, "dados", {}) or {}).get("ia") or {})


def status(cfg) -> dict:
    c = _c(cfg)
    prov = str(c.get("provedor") or "nenhum").lower()
    if prov in ("", "nenhum", "none"):
        return {"configurado": False, "provedor": "nenhum",
                "motivo": "Nenhum modelo de IA configurado: as respostas vêm de regras, cálculos e código do robô."}
    if prov != "ollama":
        return {"configurado": False, "provedor": prov, "motivo": f"Provedor '{prov}' não suportado (só 'ollama', local)."}
    url = str(c.get("url") or "http://127.0.0.1:11434")
    if urlparse(url).hostname not in LOCAIS:
        return {"configurado": False, "provedor": prov, "motivo": "Por segurança, só aceito modelo no próprio computador (127.0.0.1)."}
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=2) as r:
            modelos = [m.get("name") for m in json.loads(r.read()).get("models", [])]
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"configurado": False, "provedor": prov, "motivo": f"Ollama não respondeu em {url} ({e}). Sigo sem IA."}
    modelo = c.get("modelo")
    if modelo not in modelos:
        return {"configurado": False, "provedor": prov, "motivo": f"Modelo '{modelo}' não está instalado no Ollama ({', '.join(modelos) or 'nenhum'})."}
    return {"configurado": True, "provedor": prov, "modelo": modelo, "url": url}


def redigir(cfg, instrucao: str, fatos: str) -> dict:
    """Pede ao modelo local para REDIGIR um texto só com os fatos dados. Sem modelo: {ok: False, motivo}."""
    s = status(cfg)
    if not s["configurado"]:
        return {"ok": False, "motivo": s["motivo"]}
    corpo = json.dumps({"model": s["modelo"], "stream": False,
                        "prompt": f"{instrucao}\nUse SOMENTE estes fatos, sem inventar números:\n{fatos}"}).encode()
    req = urllib.request.Request(s["url"].rstrip("/") + "/api/generate", data=corpo, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            texto = json.loads(r.read()).get("response", "").strip()
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "motivo": f"O modelo não respondeu ({e})."}
    return {"ok": bool(texto), "texto": texto, "natureza": "hipotese", "modelo": s["modelo"],
            "aviso": "Texto redigido por IA local a partir dos fatos; números conferidos pelo robô."}
