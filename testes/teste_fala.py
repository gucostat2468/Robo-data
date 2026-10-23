"""Fala natural: a mesma pergunta varia a frase e mantém os números; nada de vocabulário de robô; número fora dos fatos
nunca sai; IA que inventa número é descartada; disjuntor protege o robô quando o modelo cai."""

import re

import pytest

from robo import canal, ia, voz

PERGUNTAS = ["como está hoje?", "quais erros tivemos?", "o que é NPS?", "como faço um PROCX?", "quem é a equipe?",
             "sprint", "ideias", "banco", "blablabla fornecedores", "Dora, oi", "oi"]


def _cfg(cfg_factory, **extra):
    cfg = cfg_factory(**extra)
    cfg.criar_pastas()
    return cfg


def _com_dia_de_trabalho(cfg):
    from robo import historico
    from datetime import datetime
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for i, (arq, st, linhas) in enumerate([("vendas.xlsx", "sucesso", 1250), ("nps.xlsx", "sucesso", 342), ("rh.xlsx", "reprovado", 0)]):
        historico.registrar(cfg.logs, {"data_hora": agora, "arquivo": arq, "status": st, "linhas_entrada": linhas,
                                       "linhas_saida": linhas, "erros": 0, "avisos": 0, "duracao_seg": "1,0", "saidas": "", "id": f"X{i}"})


def teste_mesma_pergunta_frases_diferentes_mesmos_numeros(cfg_factory):
    cfg = _cfg(cfg_factory)
    _com_dia_de_trabalho(cfg)
    a = canal.responder("como está hoje?", cfg)[0]["texto"]
    b = canal.responder("como está hoje?", cfg)[0]["texto"]
    assert a != b
    nums = lambda t: sorted(re.findall(r"\d[\d.,]*", t))  # noqa: E731
    assert nums(a) == nums(b) and "1.592" in a       # 1250 + 342 linhas aprovadas


def teste_sem_vocabulario_de_robo_e_sem_numero_inventado(cfg_factory):
    cfg = _cfg(cfg_factory)
    _com_dia_de_trabalho(cfg)
    for q in PERGUNTAS:
        for r in canal.responder(q, cfg):
            assert not voz.tem_vocabulario_de_robo(r["texto"]), (q, r["texto"])
            assert "Posso ajudar com" not in r["texto"]
            assert ia.numeros_inventados(r["texto"], r["fatos"]) == [], (q, r["texto"])
            assert r["texto"].rstrip()[-1] in ".!?", r["texto"]


def teste_nao_entendi_e_uma_frase_e_uma_pergunta(cfg_factory):
    cfg = _cfg(cfg_factory)
    r = canal.responder("blablabla xpto fornecedores", cfg)[0]
    assert r["intencao"] == "nao_entendi" and r["texto"].count("?") == 1 and "fornecedores" in r["texto"]


def teste_formula_do_excel_nao_e_quebrada():
    assert voz.limpar("Use =PROCX(a; b; c). Depois; confira") == "Use =PROCX(a; b; c). Depois. Confira."


def teste_nenhum_paragrafo_repetido_em_24h(cfg_factory):
    cfg = _cfg(cfg_factory)
    textos = [canal.responder("como está hoje?", cfg)[0]["texto"] for _ in range(6)]
    assert len(set(textos)) == len(textos)


def teste_ia_que_inventa_numero_e_descartada(cfg_factory, monkeypatch):
    cfg = _cfg(cfg_factory, ia={"provedor": "api_compativel", "url": "https://x/v1", "modelo": "m", "chave_env": "ROBO_IA_TESTE"})
    monkeypatch.setenv("ROBO_IA_TESTE", "k")
    monkeypatch.setattr(ia, "_disjuntor", {"falhas": 0, "aberto_ate": 0.0, "motivo": ""})
    monkeypatch.setattr(ia, "_chamar", lambda *a, **k: "Hoje foram 999 planilhas aprovadas.")
    r = ia.conversar(cfg, "s", [{"role": "user", "content": "q"}], {"conteudo": "Hoje foram 3 planilhas."})
    assert not r["ok"] and "999" in r["aviso"]
    monkeypatch.setattr(ia, "_chamar", lambda *a, **k: "Hoje três planilhas chegaram, foram 3 no total.")
    r = ia.conversar(cfg, "s", [{"role": "user", "content": "q"}], {"conteudo": "Hoje foram 3 planilhas."})
    assert r["ok"] and r["natureza"] == "hipotese" and r["modelo"] == "m"
    resp = canal.responder("como está hoje?", cfg)[0]       # o "3" não está nos fatos do dia: descartado, a voz responde
    assert resp["natureza"] == "regra"
    monkeypatch.setattr(ia, "_chamar", lambda *a, **k: "Ainda não chegou nenhuma planilha hoje, a equipe está pronta.")
    resp = canal.responder("como está hoje?", cfg)[0]
    assert resp["natureza"] == "hipotese" and resp["modelo"] == "m"


def teste_disjuntor_abre_depois_de_tres_falhas(cfg_factory, monkeypatch):
    cfg = _cfg(cfg_factory, ia={"provedor": "api_compativel", "url": "https://x/v1", "modelo": "m", "chave_env": "ROBO_IA_TESTE"})
    monkeypatch.setenv("ROBO_IA_TESTE", "k")
    monkeypatch.setattr(ia, "_disjuntor", {"falhas": 0, "aberto_ate": 0.0, "motivo": ""})

    def cai(*a, **k):
        raise OSError("sem rede")
    monkeypatch.setattr(ia, "_chamar", cai)
    for _ in range(3):
        assert not ia.conversar(cfg, "s", [{"role": "user", "content": "q"}], {})["ok"]
    s = ia.status(cfg)
    assert s["situacao"] == "modelo ausente" and "3 vezes" in s["motivo"]
    assert canal.responder("como está hoje?", cfg)[0]["natureza"] == "regra"   # a voz responde, nada cai


def teste_sem_ia_por_padrao_e_status_honesto(cfg_factory):
    cfg = _cfg(cfg_factory)
    s = ia.status(cfg)
    assert s["situacao"] == "desligada" and not s["configurado"]
    cfg2 = _cfg(cfg_factory, ia={"provedor": "api_compativel", "url": "https://x/v1", "modelo": "m", "chave_env": "NAO_EXISTE_X"})
    assert "NAO_EXISTE_X" in ia.status(cfg2)["motivo"]


def teste_api_de_teste_de_conversa():
    from robo.painel.servidor import ROTAS_POST
    assert "/api/ia/testar" in ROTAS_POST
