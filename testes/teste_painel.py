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
    # recusado de um jeito ou de outro: 413 ou conexão encerrada antes de o corpo terminar de chegar
    with pytest.raises((urllib.error.HTTPError, urllib.error.URLError, ConnectionError)) as e:
        urllib.request.urlopen(req)
    if isinstance(e.value, urllib.error.HTTPError):
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


def teste_conversa_tarefa_aprovacao_e_memoria_pela_api(painel, tmp_path):
    base, entrada = painel
    _, f = chamar(base, "/api/funcionarios")
    ids = {x["id"] for x in f["funcionarios"]}
    _, esc = chamar(base, "/api/escritorio")
    assert ids == {a["id"] for a in esc["equipe"]}, "o escritório 3D e o registro único têm as mesmas pessoas"
    _, ficha = chamar(base, "/api/funcionario?id=dba")
    assert ficha["contrato"]["nome"] == "Dora" and ficha["onde_registra"]
    status, r = chamar(base, "/api/conversa/enviar", {"funcionario": "dba", "texto": "o que você faz?"})
    assert status == 200 and r["respostas"][0]["natureza"] == "conhecimento"
    _, c = chamar(base, "/api/conversa?id=" + r["conversa_id"])
    assert len(c["mensagens"]) == 2
    # anexo de fora da pasta de anexos é recusado
    status, _ = chamar(base, "/api/conversa/enviar", {"funcionario": "dba", "texto": "verifique", "arquivo": "/etc/passwd"})
    assert status == 400
    status, a = chamar(base, "/api/conversa/anexar", dados=_xlsx(tmp_path), cabecalhos={"X-Nome-Arquivo": "base.xlsx"})
    assert status == 200
    status, r = chamar(base, "/api/solicitacoes/criar", {"texto": "publique esta planilha", "funcionario": "coord_engenharia",
                                                          "arquivo": a["arquivo"]})
    assert status == 200
    import time
    for _ in range(100):
        _, lista = chamar(base, "/api/solicitacoes")
        if lista["aprovacoes"]:
            break
        time.sleep(0.1)
    assert lista["aprovacoes"] and not list(entrada.iterdir())
    status, _ = chamar(base, "/api/aprovacoes/decidir", {"id": lista["aprovacoes"][0]["id"], "aprovado": False})
    assert status == 200
    status, m = chamar(base, "/api/memoria")
    assert status == 200 and "desempenho" in m
    assert chamar(base, "/api/reuniao/gerar", {})[0] == 200


def teste_senha_do_painel(painel):
    base, _ = painel
    assert chamar(base, "/api/acesso")[1] == {"senha": False, "logado": True}
    status, r = chamar(base, "/api/senha", {"nova": "curta", "confirmacao": "curta"})
    assert status == 400 and "8 caracteres" in r["erro"]
    assert chamar(base, "/api/senha", {"nova": "segredo-forte-1", "confirmacao": "segredo-forte-1"})[0] == 200
    # agora tudo pede senha; o hash nunca sai do servidor
    assert chamar(base, "/api/estado")[0] == 401 and chamar(base, "/api/config")[0] == 401
    assert chamar(base, "/api/robo/pausar", {})[0] == 401
    assert chamar(base, "/api/conversa/anexar", dados=b"x", cabecalhos={"X-Nome-Arquivo": "a.csv"})[0] == 401
    assert chamar(base, "/api/login", {"senha": "errada"})[0] == 403
    req = urllib.request.Request(base + "/api/login", data=json.dumps({"senha": "segredo-forte-1"}).encode(),
                                 headers={"X-Robo-Painel": "1", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        cookie = r.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    sessao = {"Cookie": cookie.split(";")[0]}
    status, cfg = chamar(base, "/api/config", cabecalhos=sessao)
    assert status == 200 and cfg["senha_definida"] and "senha_hash" not in json.dumps(cfg)
    # trocar exige a senha atual; força bruta trava
    assert chamar(base, "/api/senha", {"atual": "x", "nova": "outra-senha-2", "confirmacao": "outra-senha-2"},
                  cabecalhos=sessao)[0] == 403
    for _ in range(5):
        chamar(base, "/api/login", {"senha": "errada"})
    status, r = chamar(base, "/api/login", {"senha": "segredo-forte-1"})
    assert status == 403 and "Muitas tentativas" in r["erro"]


def teste_hash_da_senha():
    from robo.painel.acesso import conferir_hash, gerar_hash
    h = gerar_hash("minha-senha-123")
    assert h.startswith("pbkdf2_sha256$200000$") and "minha-senha" not in h
    assert conferir_hash("minha-senha-123", h) and not conferir_hash("minha-senha-124", h)


def teste_conhecimento_e_erros_pelo_painel(painel):
    base, _ = painel
    s, r = chamar(base, "/api/conhecimento/rodar", {})
    assert s == 200 and r["integridade"]["integra"] and r["estudada"] > 0
    s, k = chamar(base, "/api/conhecimento")
    assert s == 200 and k["licoes"] > 0 and k["pessoas"]
    s, novo = chamar(base, "/api/conhecimento/criar", {"titulo": "NPS sempre inteiro", "conteudo": "NPS com 0 casas decimais.",
                                                       "pergunta": "casas decimais do NPS", "publico": "todos"})
    assert s == 200 and novo["id"]
    s, l = chamar(base, f"/api/conhecimento/licao?id={novo['id']}")
    assert s == 200 and len(l["pessoas"]) == k["pessoas"].__len__() and l["trilha"]
    assert chamar(base, "/api/conhecimento/versao", {"id": novo["id"], "conteudo": "x", "motivo": ""})[0] == 400
    s, v = chamar(base, "/api/conhecimento/versao", {"id": novo["id"], "conteudo": "NPS inteiro (ARRED 0).", "motivo": "fórmula"})
    assert s == 200 and v["id"].endswith(".v2")
    s, b = chamar(base, "/api/conhecimento/buscar?q=casas%20decimais%20NPS")
    assert s == 200 and b["licoes"][0]["id"] == v["id"]  # a versão antiga saiu da busca; a nova entrou
    assert chamar(base, "/api/conhecimento/caderno?id=leitura")[0] == 200
    assert chamar(base, "/api/conhecimento/caderno?id=ninguem")[0] == 404
    s, e = chamar(base, "/api/erros")
    assert s == 200 and isinstance(e["erros"], list)
    with urllib.request.urlopen(base + "/conhecimento.js") as r:
        assert b"renderConhecimento" in r.read()


def teste_scripts_do_painel_nao_repetem_nomes_globais():
    """Os .js do painel dividem o mesmo escopo global: um const/function repetido derruba o arquivo inteiro no navegador
    (aconteceu com 'duracao' na sala de reunião — a página sumiu do menu sem erro visível)."""
    import re
    from pathlib import Path
    pasta = Path(__file__).resolve().parent.parent / "robo" / "painel" / "estaticos"
    html = (pasta / "inicio.html").read_text(encoding="utf-8")
    vistos = {}
    for nome in re.findall(r'<script src="([^"/]+\.js)"', html):
        for ident in re.findall(r"(?m)^(?:const|let|var|function|async function|class)\s+([A-Za-z_$][\w$]*)",
                                (pasta / nome).read_text(encoding="utf-8")):
            assert ident not in vistos, f"'{ident}' declarado em {vistos[ident]} e em {nome}"
            vistos[ident] = nome


def teste_modo_demonstracao_isolado_e_com_erro_real(tmp_path):
    from robo import demonstracao, historico
    from robo.config import carregar_config
    from robo.pipeline import processar_arquivo
    caminho = demonstracao.preparar(tmp_path / "demo")
    cfg = carregar_config(caminho)
    assert str(cfg.entrada).startswith(str(tmp_path)) and str(cfg.logs).startswith(str(tmp_path))  # não toca a produção
    assert not demonstracao.tem_senha(caminho)
    arquivos = sorted(cfg.entrada.glob("*.xlsx"))
    assert len(arquivos) == 8
    from robo import aprendizado
    resultados = {a.stem: processar_arquivo(a, cfg) for a in arquivos}
    status = {k: r.status for k, r in resultados.items()}
    assert status.pop("pedidos_com_formula_quebrada") == "reprovado"
    assert status.pop("nps_pesquisa_professores") == "reprovado" and set(status.values()) == {"sucesso"}
    # a demonstração mostra o aprendizado real: a reprovação dos professores vira proposta de sinônimo
    [pid] = aprendizado.propor(cfg, resultados["nps_pesquisa_professores"])
    assert aprendizado.listar(cfg)[0]["valor"] == "nota_nps_professor"
    assert len(historico.ler(cfg.logs, 50)) == 8
    assert demonstracao.preparar(tmp_path / "demo") == caminho  # reabrir não recria nem duplica


# ---------------------------------------------------------------- achados da auditoria de segurança (regressão)
def _painel_com_senha(tmp_path, entrada_auto=False):
    from robo.painel.acesso import gerar_hash
    entrada = tmp_path / "OneDrive" / "Bases-Limpeza"
    entrada.mkdir(parents=True, exist_ok=True)
    cfgp = tmp_path / "config.yaml"
    cfgp.write_text(yaml.safe_dump({"pastas": {"entrada": "auto" if entrada_auto else str(entrada), "logs": str(tmp_path / "logs"),
                                               "agentes": str(tmp_path / "agentes"), "habilidades": str(tmp_path / "habilidades")},
                                    "painel": {"notificacoes": False, "senha_hash": gerar_hash("SenhaForte123")}}), encoding="utf-8")
    controle = ControleRobo(cfgp)
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), None)
    porta = servidor.server_address[1]
    servidor.RequestHandlerClass = criar_manipulador(Api(controle, porta))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor, f"http://127.0.0.1:{porta}", cfgp


def teste_senha_continua_valendo_quando_a_config_nao_carrega(tmp_path, monkeypatch):
    monkeypatch.setenv("OneDrive", str(tmp_path / "nao_existe"))
    monkeypatch.setenv("OneDriveConsumer", str(tmp_path / "nao_existe"))
    monkeypatch.setenv("OneDriveCommercial", str(tmp_path / "nao_existe"))
    servidor, base, cfgp = _painel_com_senha(tmp_path, entrada_auto=True)
    try:
        antes = cfgp.read_text(encoding="utf-8")
        assert chamar(base, "/api/acesso")[1] == {"senha": True, "logado": False}
        assert chamar(base, "/api/config")[0] == 401
        assert chamar(base, "/api/senha", {"nova": "atacante123", "confirmacao": "atacante123"})[0] == 401
        assert chamar(base, "/api/config/entrada", {"caminho": str(tmp_path)})[0] == 401
        assert cfgp.read_text(encoding="utf-8") == antes  # nada foi gravado
    finally:
        servidor.shutdown()


def teste_corpo_invalido_vira_400_e_excluir_agente_nao_sai_da_pasta(tmp_path):
    servidor, base, cfgp = _painel_com_senha(tmp_path)
    try:
        req = urllib.request.Request(base + "/api/login", data=json.dumps({"senha": "SenhaForte123"}).encode(),
                                     headers={"X-Robo-Painel": "1", "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as r:
            cookie = r.headers["Set-Cookie"].split(";")[0]
        h = {"Cookie": cookie}
        assert chamar(base, "/api/login", dados=b"[1]", cabecalhos={"Content-Type": "application/json"})[0] == 400
        assert chamar(base, "/api/robo/pausar", dados=b'{"a":"\x80"}', cabecalhos={**h, "Content-Type": "application/json"})[0] == 400
        assert chamar(base, "/api/canal/enviar", dados=b"[1]", cabecalhos={**h, "Content-Type": "application/json"})[0] == 400
        assert chamar(base, "/api/config/salvar", {"alteracoes": [1]}, h)[0] == 400
        assert chamar(base, "/api/agentes/salvar", {"agente": "x"}, h)[0] == 400
        segredo = tmp_path / "segredo.yaml"
        segredo.write_text("x: 1", encoding="utf-8")
        assert chamar(base, "/api/agentes/excluir", {"id": "../segredo"}, h)[0] == 400
        assert chamar(base, "/api/agentes/excluir", {"id": "../config"}, h)[0] == 400
        assert segredo.exists() and cfgp.exists()
    finally:
        servidor.shutdown()


def teste_tarefa_sem_etapa_nao_sai_concluida_e_registro_automatico_interrompido_falha(tmp_path, cfg_factory):
    from robo import orquestrador
    from robo.trabalho import Trabalho
    cfg = cfg_factory()
    tb = Trabalho(cfg)
    sid = tb.criar_solicitacao("tarefa", "x", "x", "automatica", "recepcao", 1, "media", modelo="pipeline", estado="na_fila")
    tb.mudar_estado(sid, "em_execucao", "robo")
    assert orquestrador.retomar_pendentes(cfg) == []
    assert tb.solicitacao(sid)["estado"] == "falhou"
