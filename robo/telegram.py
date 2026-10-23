"""Grupo no Telegram com os funcionários: o dono conversa com a empresa pelo celular, de qualquer lugar.

    python -m robo telegram --testar            confere o token e o grupo (não manda nada sem você pedir)
    python -m robo telegram --descobrir          mostra o id do grupo e o SEU id (depois de você escrever no grupo)
    python -m robo telegram --configurar <grupo> <seu_id>
    python -m robo telegram --apresentar         manda o cartão de cada funcionário (foto, nome, cargo, área, andar)

Como funciona (honesto):
  - é UM robô do Telegram (criado por você no @BotFather) que fala por todos: cada mensagem sai assinada pelo
    funcionário que respondeu ("Davi · Estatística · 2º andar"). O Telegram não deixa um robô trocar de foto a cada
    mensagem; por isso cada funcionário ganha um cartão com foto (iniciais na cor dele) na apresentação;
  - quem responde é o mesmo canal da empresa (robo/canal.py): os fatos vêm dos registros, nunca inventados;
  - só o DONO manda na empresa pelo grupo: mensagem de outra pessoa é registrada e ignorada;
  - o token fica na variável de ambiente ROBO_TELEGRAM_TOKEN (nunca em arquivo, nunca no log);
  - toda mensagem que entra e sai fica em telegram_mensagens (só de inclusão) e vai para o PostgreSQL.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from robo.trabalho import Trabalho, _agora

log = logging.getLogger("robo")

API = "https://api.telegram.org"
PADRAO = {"habilitado": False, "chat_id": "", "dono_id": "", "token_env": "ROBO_TELEGRAM_TOKEN", "resumo_minutos": 120,
          "max_respostas": 3}
ESQUEMA = """
CREATE TABLE IF NOT EXISTS telegram_mensagens (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT NOT NULL, direcao TEXT NOT NULL, chat_id TEXT, update_id INTEGER,
  autor TEXT, funcionario TEXT, texto TEXT, ok INTEGER, erro TEXT);
CREATE INDEX IF NOT EXISTS ix_tg_update ON telegram_mensagens(update_id);
CREATE TRIGGER IF NOT EXISTS telegram_mensagens_imutavel BEFORE UPDATE ON telegram_mensagens
BEGIN SELECT RAISE(ABORT, 'mensagem do Telegram é permanente: não se altera'); END;
"""


class ErroTelegram(RuntimeError):
    pass


def _c(cfg) -> dict:
    return {**PADRAO, **((getattr(cfg, "dados", {}) or {}).get("telegram") or {})}


def _tb(cfg) -> Trabalho:
    tb = Trabalho(cfg)
    with tb.tx() as c:
        c.executescript(ESQUEMA)
        from robo.trabalho import proteger
        proteger(c)
    return tb


def token(cfg) -> str:
    return os.environ.get(_c(cfg)["token_env"], "").strip()


# =============================================================================== chamada à API (troca-se nos testes)
def _chamar(tok: str, metodo: str, dados: dict | None = None, arquivos: dict | None = None, timeout: float = 30) -> dict:
    url = f"{API}/bot{tok}/{metodo}"
    if arquivos:
        limite = uuid.uuid4().hex
        partes = []
        for k, v in (dados or {}).items():
            partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        for k, (nome, conteudo) in arquivos.items():
            partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{nome}\"\r\n"
                          f"Content-Type: image/png\r\n\r\n".encode() + conteudo + b"\r\n")
        corpo = b"".join(partes) + f"--{limite}--\r\n".encode()
        req = urllib.request.Request(url, data=corpo, headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
    else:
        req = urllib.request.Request(url, data=json.dumps(dados or {}).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            resp = json.loads(e.read())
        except ValueError:
            raise ErroTelegram(f"HTTP {e.code}") from None
    except (urllib.error.URLError, OSError) as e:  # sem internet: não derruba o robô
        raise ErroTelegram(f"sem conexão com o Telegram ({type(e).__name__})") from None
    if not resp.get("ok"):
        raise ErroTelegram(resp.get("description") or "o Telegram recusou o pedido")
    return resp.get("result")


def _api(cfg, metodo: str, dados: dict | None = None, arquivos: dict | None = None):
    tok = token(cfg)
    if not tok:
        raise ErroTelegram(f"falta o token: defina a variável de ambiente {_c(cfg)['token_env']}")
    return _chamar(tok, metodo, dados, arquivos)


def _registrar(cfg, direcao: str, texto: str, ok: bool = True, erro: str = "", chat_id="", update_id=None, autor="",
               funcionario="") -> None:
    with _tb(cfg).tx() as c:
        c.execute("INSERT INTO telegram_mensagens (data_hora, direcao, chat_id, update_id, autor, funcionario, texto, ok, erro) "
                  "VALUES (?,?,?,?,?,?,?,?,?)", (_agora(), direcao, str(chat_id), update_id, autor, funcionario,
                                                 (texto or "")[:4000], int(ok), erro[:300]))


# =============================================================================== enviar
def _assinatura(cfg, pid: str | None) -> str:
    if not pid:
        return ""
    from robo import organizacao
    p = organizacao.por_id(cfg).get(pid) or {}
    return f"<b>{_html(p.get('nome', pid))}</b> · {_html(p.get('papel', ''))} · {p.get('andar', '?')}º andar\n"


def _html(t) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def enviar(cfg, texto: str, funcionario: str | None = None, chat_id: str | None = None) -> bool:
    """Manda uma mensagem assinada pelo funcionário. Registra o envio (ou a falha). Nunca levanta exceção."""
    chat = chat_id or _c(cfg)["chat_id"]
    corpo = _assinatura(cfg, funcionario) + _html(texto)
    try:
        _api(cfg, "sendMessage", {"chat_id": chat, "text": corpo[:4096], "parse_mode": "HTML",
                                  "disable_web_page_preview": True})
        _registrar(cfg, "saida", texto, True, chat_id=chat, autor="robo", funcionario=funcionario or "")
        return True
    except ErroTelegram as e:
        _registrar(cfg, "saida", texto, False, str(e), chat_id=chat, autor="robo", funcionario=funcionario or "")
        log.warning("Telegram: não enviei a mensagem (%s)", e)
        return False


# =============================================================================== receber e responder
def _ultimo_update(cfg) -> int:
    with _tb(cfg).tx() as c:
        return int(c.execute("SELECT COALESCE(MAX(update_id), 0) FROM telegram_mensagens").fetchone()[0])


def buscar(cfg) -> list[dict]:
    """Mensagens novas do grupo desde a última lida (cada uma é lida uma vez só)."""
    novas = _api(cfg, "getUpdates", {"offset": _ultimo_update(cfg) + 1, "timeout": 0,
                                     "allowed_updates": ["message"]}) or []
    saida = []
    for u in novas:
        m = u.get("message") or {}
        de = m.get("from") or {}
        saida.append({"update_id": u["update_id"], "chat_id": str((m.get("chat") or {}).get("id", "")),
                      "autor_id": str(de.get("id", "")), "autor": de.get("first_name") or de.get("username") or "",
                      "texto": m.get("text") or ""})
    return saida


def atender(cfg) -> dict:
    """Lê o grupo e responde ao dono pelo canal da empresa. Mensagem de outra pessoa ou de outro chat: registra e ignora."""
    c = _c(cfg)
    lidas = respondidas = ignoradas = 0
    for m in buscar(cfg):
        lidas += 1
        do_dono = bool(c["dono_id"]) and m["autor_id"] == str(c["dono_id"]) and m["chat_id"] == str(c["chat_id"])
        _registrar(cfg, "entrada", m["texto"], True, "" if do_dono else "ignorada: não é o dono neste grupo",
                   m["chat_id"], m["update_id"], m["autor"] or m["autor_id"])
        if not do_dono or not m["texto"].strip():
            ignoradas += 1
            continue
        from robo import canal
        try:
            respostas = canal.responder(m["texto"], cfg)[: int(c["max_respostas"])]
        except Exception as e:
            log.exception("Telegram: o canal não conseguiu responder")
            respostas = [{"autor": "canal_nina", "texto": f"Tive um problema para responder agora ({type(e).__name__}). "
                                                          "Registrei o erro; tente de novo em instantes."}]
        for r in respostas:
            if enviar(cfg, r.get("texto") or "", r.get("autor")):
                respondidas += 1
    return {"lidas": lidas, "respondidas": respondidas, "ignoradas": ignoradas}


def resumo_do_periodo(cfg) -> str | None:
    """O que aconteceu desde o último resumo, só com números dos registros. None = nada novo."""
    import sqlite3
    with _tb(cfg).tx() as c:
        ultimo = c.execute("SELECT MAX(data_hora) FROM telegram_mensagens WHERE direcao='saida' AND autor='resumo'").fetchone()[0]
        desde = ultimo or "0000"
        try:
            dem = c.execute("SELECT COUNT(*), SUM(estado='concluida'), SUM(estado='concluida_parcialmente'), "
                            "SUM(estado='falhou') FROM solicitacoes WHERE origem='demanda_sintetica' AND criada_em>?",
                            (desde,)).fetchone()
            treino = c.execute("SELECT COUNT(*), SUM(acertou) FROM treino_tentativas WHERE data_hora>?", (desde,)).fetchone()
            lotes = c.execute("SELECT COUNT(*) FROM fabrica_lotes WHERE data_hora>?", (desde,)).fetchone()[0]
        except sqlite3.OperationalError:
            return None
    if not (dem[0] or treino[0] or lotes):
        return None
    partes = []
    if dem[0]:
        partes.append(f"{dem[0]} demanda(s): {dem[1] or 0} concluída(s), {dem[2] or 0} parcial(is), {dem[3] or 0} com falha")
    if treino[0]:
        partes.append(f"{treino[0]} tentativa(s) de treino, {treino[1] or 0} certa(s)")
    if lotes:
        partes.append(f"{lotes} planilha(s) sintética(s) da fábrica")
    return "Resumo desde " + (desde[:16].replace("T", " ") if ultimo else "o início") + ": " + "; ".join(partes) + "."


def rotina(cfg) -> dict | None:
    """A cada minuto (com o robô aberto ou no turno da nuvem): responde o dono e, de tempos em tempos, manda o resumo.
    Desligado ou sem token: None (não é trabalho)."""
    c = _c(cfg)
    if not c["habilitado"] or not token(cfg) or not c["chat_id"]:
        return None
    r = atender(cfg)
    with _tb(cfg).tx() as conn:
        ultimo = conn.execute("SELECT MAX(data_hora) FROM telegram_mensagens WHERE autor='resumo'").fetchone()[0]
    from datetime import datetime, timedelta
    if not ultimo or datetime.fromisoformat(ultimo) < datetime.now() - timedelta(minutes=float(c["resumo_minutos"])):
        texto = resumo_do_periodo(cfg)
        if texto:
            chat = c["chat_id"]
            try:
                _api(cfg, "sendMessage", {"chat_id": chat, "text": _assinatura(cfg, "dem_coordenador") + _html(texto),
                                          "parse_mode": "HTML"})
                _registrar(cfg, "saida", texto, True, chat_id=chat, autor="resumo", funcionario="dem_coordenador")
                r["resumo"] = True
            except ErroTelegram as e:
                _registrar(cfg, "saida", texto, False, str(e), chat_id=chat, autor="resumo", funcionario="dem_coordenador")
    return r if (r["lidas"] or r.get("resumo")) else None


# =============================================================================== apresentação com foto
def avatar(pessoa: dict, pasta: Path) -> Path:
    """Cartão 512x512: iniciais na cor do funcionário (a mesma do escritório 3D)."""
    from PIL import Image, ImageDraw, ImageFont
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{pessoa['id']}.png"
    if destino.exists():
        return destino
    cor = pessoa.get("cor") or "#1D4ED8"
    img = Image.new("RGB", (512, 512), cor)
    d = ImageDraw.Draw(img)
    iniciais = "".join(x[0] for x in str(pessoa.get("nome", "?")).split()[:2]).upper()
    try:
        fonte = ImageFont.truetype("DejaVuSans-Bold.ttf", 200)
    except OSError:
        fonte = ImageFont.load_default()
    caixa = d.textbbox((0, 0), iniciais, font=fonte)
    d.text(((512 - (caixa[2] - caixa[0])) / 2 - caixa[0], (512 - (caixa[3] - caixa[1])) / 2 - caixa[1]), iniciais,
           fill="white", font=fonte)
    img.save(destino)
    return destino


def apresentar(cfg, limite: int | None = None) -> dict:
    """Manda o cartão de cada funcionário (foto + nome, cargo, área e andar), em lotes de 10 (álbum do Telegram)."""
    from robo import organizacao
    gente = sorted(organizacao.lista(cfg), key=lambda p: (p["andar"], p["nome"]))[:limite]
    pasta = Path(cfg.logs) / "telegram" / "avatares"
    chat, enviados = _c(cfg)["chat_id"], 0
    for i in range(0, len(gente), 10):
        grupo = gente[i:i + 10]
        midia, arquivos = [], {}
        for p in grupo:
            nome_arq = f"a{p['id']}"
            arquivos[nome_arq] = (f"{p['id']}.png", avatar(p, pasta).read_bytes())
            legenda = (f"{p['nome']} — {p['papel']}\n{organizacao.area_de(p['id']) or 'sem área'} · {p['andar']}º andar\n"
                       f"Nível: {organizacao.nivel_de(p['id'], p)}")
            midia.append({"type": "photo", "media": f"attach://{nome_arq}", "caption": legenda})
        try:
            _api(cfg, "sendMediaGroup", {"chat_id": chat, "media": json.dumps(midia, ensure_ascii=False)}, arquivos)
            enviados += len(grupo)
            _registrar(cfg, "saida", f"apresentação: {', '.join(p['id'] for p in grupo)}", True, chat_id=chat, autor="robo")
        except ErroTelegram as e:
            _registrar(cfg, "saida", f"apresentação de {len(grupo)}", False, str(e), chat_id=chat, autor="robo")
            return {"enviados": enviados, "erro": str(e)}
        time.sleep(1)  # o Telegram limita envios por segundo num grupo
    return {"enviados": enviados}
