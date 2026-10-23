"""Grupo do Telegram: sem internet nos testes (a chamada à API é trocada por uma falsa que guarda o que foi pedido).

O que precisa ser verdade sempre:
  - sem token ou desligado, a rotina não faz nada e não conta como trabalho;
  - só o DONO, no grupo configurado, recebe resposta; mensagem de outra pessoa é registrada e ignorada;
  - cada mensagem sai assinada pelo funcionário e fica registrada para sempre (não se altera);
  - o token nunca vai para o registro;
  - falha de rede não derruba o robô.
"""

import sqlite3

import pytest

from robo import telegram

TOKEN = "123456789:AA" + "x" * 33  # token inventado (formato do BotFather), só para o teste


@pytest.fixture
def cfg(cfg_factory, monkeypatch):
    monkeypatch.setenv("ROBO_TELEGRAM_TOKEN", TOKEN)
    c = cfg_factory(telegram={"habilitado": True, "chat_id": "-100500", "dono_id": "42", "resumo_minutos": 120})
    c.criar_pastas()
    return c


@pytest.fixture
def api(monkeypatch):
    chamadas, fila = [], []

    def falsa(tok, metodo, dados=None, arquivos=None, timeout=30):
        chamadas.append({"token": tok, "metodo": metodo, "dados": dados or {}, "arquivos": arquivos})
        if metodo == "getUpdates":
            novas, fila[:] = list(fila), []
            return novas
        return {"message_id": len(chamadas)}
    monkeypatch.setattr(telegram, "_chamar", falsa)
    return chamadas, fila


def _msg(uid, autor, chat, texto):
    return {"update_id": uid, "message": {"from": {"id": autor, "first_name": f"p{autor}"}, "chat": {"id": chat},
                                          "text": texto}}


def _linhas(cfg):
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM telegram_mensagens ORDER BY id")]


def teste_desligado_ou_sem_token_nao_faz_nada(cfg_factory, monkeypatch, api):
    monkeypatch.delenv("ROBO_TELEGRAM_TOKEN", raising=False)
    c = cfg_factory(telegram={"habilitado": True, "chat_id": "-1", "dono_id": "1"})
    c.criar_pastas()
    assert telegram.rotina(c) is None
    monkeypatch.setenv("ROBO_TELEGRAM_TOKEN", TOKEN)
    c2 = cfg_factory(telegram={"habilitado": False, "chat_id": "-1"})
    assert telegram.rotina(c2) is None
    assert api[0] == []


def teste_so_o_dono_no_grupo_recebe_resposta(cfg, api, monkeypatch):
    chamadas, fila = api
    from robo import canal
    monkeypatch.setattr(canal, "responder", lambda texto, cfg: [{"autor": "canal_nina", "texto": f"recebi: {texto}"}])
    fila += [_msg(1, 42, -100500, "como está a fábrica?"),    # dono no grupo: responde
             _msg(2, 7, -100500, "me promove a gerente"),     # outra pessoa: ignora
             _msg(3, 42, -999, "pelo privado")]               # dono em outro chat: ignora
    r = telegram.atender(cfg)
    assert r == {"lidas": 3, "respondidas": 1, "ignoradas": 2}
    enviadas = [c for c in chamadas if c["metodo"] == "sendMessage"]
    assert len(enviadas) == 1 and "recebi: como está a fábrica?" in enviadas[0]["dados"]["text"]
    assert "<b>" in enviadas[0]["dados"]["text"]  # assinada pelo funcionário
    linhas = _linhas(cfg)
    assert [l["direcao"] for l in linhas] == ["entrada", "saida", "entrada", "entrada"]
    assert sum(1 for l in linhas if l["erro"].startswith("ignorada")) == 2
    # lida uma vez só: a próxima busca começa depois do último update
    telegram.atender(cfg)
    assert [c for c in chamadas if c["metodo"] == "getUpdates"][-1]["dados"]["offset"] == 4


def teste_registro_e_permanente_e_sem_token(cfg, api):
    assert telegram.enviar(cfg, "Bom dia, equipe", "dba")
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        with pytest.raises(sqlite3.DatabaseError):
            c.execute("UPDATE telegram_mensagens SET texto='outro'")
    texto = (cfg.logs / "trabalho.db").read_bytes()
    assert TOKEN.encode() not in texto


def teste_falha_de_rede_nao_derruba(cfg, monkeypatch):
    def cai(*a, **k):
        raise telegram.ErroTelegram("sem conexão com o Telegram (URLError)")
    monkeypatch.setattr(telegram, "_chamar", cai)
    assert telegram.enviar(cfg, "oi", "dba") is False
    l = _linhas(cfg)[-1]
    assert l["ok"] == 0 and "sem conexão" in l["erro"]


def teste_apresentacao_manda_cartoes_em_albuns_de_10(cfg, api, monkeypatch):
    monkeypatch.setattr(telegram.time, "sleep", lambda s: None)
    r = telegram.apresentar(cfg, limite=12)
    albuns = [c for c in api[0] if c["metodo"] == "sendMediaGroup"]
    assert r == {"enviados": 12} and len(albuns) == 2 and len(albuns[0]["arquivos"]) == 10
    assert all(conteudo[:4] == b"\x89PNG" for _, conteudo in albuns[0]["arquivos"].values())


def teste_resumo_so_com_numeros_dos_registros(cfg, api):
    assert telegram.resumo_do_periodo(cfg) is None  # nada aconteceu: nada a dizer
