"""Sobe o servidor do painel numa porta livre e exercita a API como a interface faz."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
import yaml
from openpyxl import Workbook

from robo.painel.controle import ControleRobo
from robo.painel.servidor import Api, criar_manipulador


@pytest.fixture
def painel(tmp_path):
    entrada = tmp_path / "OneDrive" / "Bases-Limpeza"
    entrada.mkdir(parents=True)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"pastas": {"entrada": str(entrada), "logs": str(tmp_path / "logs"),
                                              "agentes": str(tmp_path / "agentes"), "habilidades": str(tmp_path / "habilidades")},
                                   "painel": {"notificacoes": False}}), encoding="utf-8")
    controle = ControleRobo(cfg)
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), None)
    porta = servidor.server_address[1]
    servidor.RequestHandlerClass = criar_manipulador(Api(controle, porta))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{porta}", entrada
    servidor.shutdown()


def chamar(base, caminho, corpo=None, cabecalhos=None, dados=None):
    h = {"X-Robo-Painel": "1"} if (corpo is not None or dados is not None) else {}
    h.update(cabecalhos or {})
    if corpo is not None:
        dados = json.dumps(corpo).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(base + caminho, data=dados, headers=h, method="POST" if dados is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _xlsx(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["ID", "Nota"])
    ws.append(["1", 10])
    ws.append(["2", "#REF!"])
    caminho = tmp_path / "base.xlsx"
    wb.save(caminho)
    return caminho.read_bytes()


def teste_estado_e_paginas(painel):
    base, _ = painel
    status, d = chamar(base, "/api/estado")
    assert status == 200 and d["erro_config"] is None and "kpis" in d
    for rota in ("/api/historico", "/api/reprovados", "/api/config", "/api/agentes", "/api/consultas", "/api/escritorio"):
        assert chamar(base, rota)[0] == 200, rota
    _, esc = chamar(base, "/api/escritorio")
    assert [a["id"] for a in esc["equipe"]][:3] == ["recepcao", "leitura", "limpeza"]
    assert {a["andar"] for a in esc["equipe"] if a["id"].startswith("excel_")} == {3}
    assert all(a["ativo"] for a in esc["equipe"]), "ninguém dorme: quem está sem trabalho fica de prontidão"
    assert "excel_hoje" in esc
    with urllib.request.urlopen(base + "/escritorio.js") as r:
        assert r.headers["Content-Type"].startswith("text/javascript")


def teste_seguranca_das_acoes(painel):
    base, _ = painel
    req = urllib.request.Request(base + "/api/robo/pausar", data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 403  # sem o cabeçalho do painel
    assert chamar(base, "/api/robo/pausar", {}, {"Origin": "http://site-malicioso.com"})[0] == 403
    assert chamar(base, "/api/abrir", {"alvo": "arquivo", "caminho": "C:/Windows/system32/calc.exe"})[0] == 404


def teste_testar_enviar_e_agentes(painel, tmp_path):
    base, entrada = painel
    conteudo = _xlsx(tmp_path)
    status, r = chamar(base, "/api/testar", dados=conteudo, cabecalhos={"X-Nome-Arquivo": "base.xlsx"})
    assert status == 200 and r["aprovado"] is False
    assert any(o["nivel"] == "ERRO" for o in r["ocorrencias"])
    assert chamar(base, "/api/testar", dados=b"x", cabecalhos={"X-Nome-Arquivo": "virus.exe"})[0] == 415
    status, r = chamar(base, "/api/enviar", dados=conteudo, cabecalhos={"X-Nome-Arquivo": "base.xlsx"})
    assert status == 200 and (entrada / "base.xlsx").exists()

    novo = {"id": "tina", "nome": "Tina", "papel": "Contatos", "cor": "#F97316", "posicao": "limpeza",
            "habilidades": [{"habilidade": "padronizar_texto", "parametros": {"colunas": ["id"], "modo": "maiusculo"}}]}
    assert chamar(base, "/api/agentes/salvar", {"agente": novo})[0] == 200
    _, ag = chamar(base, "/api/agentes")
    assert "tina" in [a["id"] for a in ag["agentes"]]
    status, r = chamar(base, "/api/agentes/salvar", {"agente": {**novo, "habilidades": [{"habilidade": "nao_existe"}]}})
    assert status == 400 and "não existe" in r["erro"]
    assert chamar(base, "/api/agentes/excluir", {"id": "limpeza"})[0] == 400


def teste_cabecalhos_de_seguranca_e_limite_de_corpo(painel):
    base, _ = painel
    with urllib.request.urlopen(base + "/") as r:
        assert r.headers["X-Frame-Options"] == "DENY" and "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    req = urllib.request.Request(base + "/api/canal/enviar", data=b"{" + b" " * (3 * 1024 * 1024) + b"}", method="POST",
                                 headers={"X-Robo-Painel": "1", "Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 413


def teste_canal_e_ti_pela_api(painel):
    base, _ = painel
    req = urllib.request.Request(base + "/api/canal/enviar", data=json.dumps({"texto": "como está hoje?"}).encode(),
                                 method="POST", headers={"X-Robo-Painel": "1", "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        msgs = json.loads(r.read())["mensagens"]
    assert msgs[0]["autor"] == "dono" and msgs[1]["tipo"] == "resposta"
    status, d = chamar(base, "/api/canal?busca=hoje")
    assert status == 200 and d["mensagens"]
