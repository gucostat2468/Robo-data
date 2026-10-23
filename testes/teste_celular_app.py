"""Fase 6 — celular de verdade: diagnóstico passo a passo, app instalável (PWA), ações opcionais e tela de 375 px.

O que precisa ser verdade sempre:
  - o diagnóstico aponta o passo que falhou (desligado, sem senha, sem rede, servidor parado) e passa quando tudo está ok;
  - o app tem ícones PNG de verdade, service worker que NUNCA guarda dado (/api) e tela offline;
  - ações vêm desligadas; ligadas, exigem sessão + cabeçalho do app, são só 4 e cada uma fica em acessos_celular e jobs;
  - nenhuma tela do celular rola para o lado numa largura de 375 px (iPhone SE / mini).
"""

import http.client
import json
import socket
import sqlite3
import struct
import threading
from http.server import ThreadingHTTPServer

import pytest

from robo import diagnostico_celular as dc
from robo.diagnostico_pc import FALHA, OK
from robo.painel import celular
from robo.painel.acesso import gerar_hash

SENHA = "Celular@2026segura"


class ControleFalso:
    """Só o que as ações usam: ligado, pausar, ligar e o log em memória."""

    def __init__(self):
        self.ligado = True
        self.chamadas = []

        class _Log:
            def desde(_, seq):
                return [{"seq": 1, "hora": "23/10 10:00:00", "nivel": "INFO", "mensagem": "Robô ligado."}]
        self.memoria_log = _Log()

    def pausar(self):
        self.chamadas.append("pausar")
        self.ligado = False

    def ligar(self):
        self.chamadas.append("ligar")
        self.ligado = True
        return True


@pytest.fixture
def app(cfg_factory):
    feitos = []

    def _ligar(acoes=False, controle=None):
        cfg = cfg_factory(celular={"habilitado": True, "porta": 8766, "acoes": acoes})
        cfg.criar_pastas()
        guardado = gerar_hash(SENHA)
        cfg.painel["senha_hash"] = guardado
        s = ThreadingHTTPServer(("127.0.0.1", 0), celular.criar_manipulador(lambda: cfg, lambda: guardado, controle,
                                                                           celular.PortaoCelular()))
        threading.Thread(target=s.serve_forever, daemon=True).start()
        feitos.append(s)
        return cfg, s.server_address[1]
    yield _ligar
    for s in feitos:
        s.shutdown()
        s.server_close()


def _pedir(porta, metodo, caminho, corpo=None, cookie=None, app_cab=True):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    cab = {"Content-Type": "application/json", "User-Agent": "Android teste"}
    if app_cab:
        cab["X-Robo-Celular"] = "1"
    if cookie:
        cab["Cookie"] = cookie
    c.request(metodo, caminho, body=json.dumps(corpo).encode() if corpo is not None else None, headers=cab)
    r = c.getresponse()
    dados = r.read()
    c.close()
    return r.status, dict(r.getheaders()), dados


def _entrar(porta) -> str:
    st, cab, _ = _pedir(porta, "POST", "/entrar", {"senha": SENHA})
    assert st == 200
    return cab["Set-Cookie"].split(";")[0]


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _por_titulo(itens) -> dict:
    return {i["titulo"].split(".")[0]: i for i in itens}


# ----------------------------------------------------------------------------------------------- diagnóstico
def teste_diagnostico_aponta_cada_falha_simulada(cfg_factory):
    cfg = cfg_factory(celular={"habilitado": False, "porta": _porta_livre()})
    itens = _por_titulo(dc.rodar(cfg, ip=None))  # sem rede, desligado, sem senha, nada ouvindo
    assert itens["1"]["situacao"] == FALHA and "celular --ligar" in itens["1"]["corrigir"]
    assert itens["2"]["situacao"] == FALHA and "robo senha" in itens["2"]["corrigir"]
    assert itens["3"]["situacao"] == FALHA
    assert itens["4"]["situacao"] == FALHA and "abra o robô" in itens["4"]["corrigir"]
    assert itens["5"]["situacao"] == "nao_se_aplica"  # não testa o que depende de um passo que já falhou
    cfg2 = cfg_factory(celular={"habilitado": True, "porta": 8766})
    assert _por_titulo(dc.rodar(cfg2, ip="200.147.67.142"))["3"]["situacao"] == "atencao"  # IP público


def teste_diagnostico_passa_com_o_servidor_de_verdade(app):
    cfg, porta = app()
    cfg.dados["celular"]["porta"] = porta
    itens = _por_titulo(dc.rodar(cfg, ip="127.0.0.1"))
    for passo in ("1", "2", "3", "4", "5"):
        assert itens[passo]["situacao"] == OK, itens[passo]
    assert dc.endereco(cfg, "192.168.0.10") == f"http://192.168.0.10:{porta}/"


def teste_qr_code_do_endereco():
    pytest.importorskip("segno")
    svg = dc.qr_svg("http://192.168.0.10:8766/")
    assert svg.lstrip().startswith("<?xml") or "<svg" in svg
    assert "█" in dc.qr_terminal("http://192.168.0.10:8766/")


def teste_comando_diagnostico_celular_devolve_erro_quando_falha(tmp_path, capsys):
    import yaml
    from robo import comandos
    arq = tmp_path / "config.yaml"
    arq.write_text(yaml.safe_dump({"pastas": {"entrada": str(tmp_path / "Bases-Limpeza"), "logs": str(tmp_path / "logs")},
                                   "celular": {"habilitado": False, "porta": _porta_livre()}}), encoding="utf-8")
    assert comandos.principal(["--config", str(arq), "diagnostico-celular"]) == 1
    saida = capsys.readouterr().out
    assert "✘ 1. Ligado no config.yaml" in saida and "Resultado:" in saida


# ----------------------------------------------------------------------------------------------- PWA
def _tamanho_png(dados: bytes) -> tuple[int, int]:
    assert dados[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", dados[16:24])


def teste_app_instalavel_com_icones_e_tela_offline(app):
    _, porta = app()
    st, _, corpo = _pedir(porta, "GET", "/manifest.webmanifest")
    m = json.loads(corpo)
    assert st == 200 and m["display"] == "standalone" and m["start_url"] == "/"
    pngs = {i["sizes"]: i for i in m["icons"] if i["type"] == "image/png"}
    assert {"192x192", "512x512"} <= set(pngs) and any(i.get("purpose") == "maskable" for i in m["icons"])
    for icone in m["icons"]:
        st, cab, dados = _pedir(porta, "GET", icone["src"])
        assert st == 200, icone["src"]
        if icone["type"] == "image/png":
            assert cab["Content-Type"] == "image/png"
            assert _tamanho_png(dados) == tuple(int(x) for x in icone["sizes"].split("x"))
    st, _, dados = _pedir(porta, "GET", "/icone-180.png")
    assert st == 200 and _tamanho_png(dados) == (180, 180)  # iPhone não aceita SVG como ícone de tela inicial
    st, _, pagina = _pedir(porta, "GET", "/")
    assert b'href="/icone-180.png"' in pagina
    st, cab, sw = _pedir(porta, "GET", "/service-worker.js")
    assert st == 200 and "javascript" in cab["Content-Type"]
    assert b'startsWith("/api/")' in sw and b"/offline.html" in sw  # dado nunca vai para o cache
    st, _, off = _pedir(porta, "GET", "/offline.html")
    assert st == 200 and "diagnostico-celular".encode() in off


# ----------------------------------------------------------------------------------------------- ações
def teste_acoes_vem_desligadas(app):
    cfg, porta = app()
    cookie = _entrar(porta)
    r = json.loads(_pedir(porta, "GET", "/api/resumo", cookie=cookie)[2])
    assert r["acoes"] == {"ligadas": False}
    st, _, corpo = _pedir(porta, "POST", "/api/acao", {"acao": "pausar"}, cookie=cookie)
    assert st == 403 and "desligadas" in json.loads(corpo)["erro"]


def teste_acoes_exigem_sessao_e_cabecalho_do_app(app):
    _, porta = app(acoes=True, controle=ControleFalso())
    assert _pedir(porta, "POST", "/api/acao", {"acao": "pausar"})[0] == 401  # sem senha
    cookie = _entrar(porta)
    assert _pedir(porta, "POST", "/api/acao", {"acao": "pausar"}, cookie=cookie, app_cab=False)[0] == 403
    for proibida in ("apagar", "aprovar_regra", "sql", "config"):
        assert _pedir(porta, "POST", "/api/acao", {"acao": proibida}, cookie=cookie)[0] == 400


def teste_pausar_retomar_e_ver_log_ficam_registrados(app):
    controle = ControleFalso()
    cfg, porta = app(acoes=True, controle=controle)
    cookie = _entrar(porta)
    st, _, corpo = _pedir(porta, "POST", "/api/acao", {"acao": "pausar"}, cookie=cookie)
    assert st == 200 and json.loads(corpo)["ligado"] is False
    assert json.loads(_pedir(porta, "POST", "/api/acao", {"acao": "retomar"}, cookie=cookie)[2])["ligado"] is True
    linhas = json.loads(_pedir(porta, "POST", "/api/acao", {"acao": "ver_log"}, cookie=cookie)[2])["linhas"]
    assert controle.chamadas == ["pausar", "ligar"] and "Robô ligado." in linhas[0]
    acoes = [a["detalhe"] for a in celular.acessos(cfg) if a["evento"] == "acao"]
    assert acoes == ["ver_log → 200", "retomar → 200", "pausar → 200"]
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    jobs = c.execute("SELECT j.tipo, j.origem, j.estado, e.etapa FROM jobs j JOIN jobs_etapas e ON e.job_id=j.id "
                     "WHERE j.tipo='acao_celular' ORDER BY j.id").fetchall()
    c.close()
    assert jobs == [("acao_celular", "dono", "concluido", "pausar"), ("acao_celular", "dono", "concluido", "retomar"),
                    ("acao_celular", "dono", "concluido", "ver_log")]


def teste_reprocessar_reprovado_pelo_celular(app):
    cfg, porta = app(acoes=True)
    (cfg.erros / "20261023_101500_vendas.xlsx").write_bytes(b"x")
    (cfg.erros / "20261023_101500_vendas_ERROS.txt").write_text("coluna faltando", encoding="utf-8")
    cookie = _entrar(porta)
    r = json.loads(_pedir(porta, "GET", "/api/resumo", cookie=cookie)[2])
    assert r["acoes"] == {"ligadas": True, "reprovados": ["20261023_101500_vendas.xlsx"]}
    st, _, corpo = _pedir(porta, "POST", "/api/acao", {"acao": "reprocessar", "nome": "20261023_101500_vendas.xlsx"},
                          cookie=cookie)
    assert st == 200 and json.loads(corpo)["nome"] == "vendas.xlsx"
    assert (cfg.entrada / "vendas.xlsx").exists() and not any(cfg.erros.glob("*vendas*"))
    st, _, _ = _pedir(porta, "POST", "/api/acao", {"acao": "reprocessar", "nome": "../config.yaml"}, cookie=cookie)
    assert st == 404  # só nomes dentro de Bases-Erros
    assert [a["detalhe"] for a in celular.acessos(cfg) if a["evento"] == "acao"][0].endswith("→ 404")


# ----------------------------------------------------------------------------------------------- 375 px
def _navegador():
    pw = pytest.importorskip("playwright.sync_api")
    try:
        p = pw.sync_playwright().start()
    except Exception as e:  # pragma: no cover - depende da máquina
        pytest.skip(f"Playwright indisponível: {e}")
    # o Chromium do Playwright, ou um já instalado (ROBO_TESTE_CHROMIUM ou o caminho comum de contêiner)
    import os
    from pathlib import Path
    caminhos = [None] + [c for c in (os.environ.get("ROBO_TESTE_CHROMIUM"), "/opt/pw-browsers/chromium") if c and Path(c).exists()]
    erro = None
    for caminho in caminhos:
        try:
            return p, p.chromium.launch(executable_path=caminho)
        except Exception as e:  # pragma: no cover - depende da máquina
            erro = e
    p.stop()
    pytest.skip(f"Chromium indisponível: {str(erro)[:200]}")


def _largura_extra(pagina) -> int:
    return pagina.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")


def teste_nada_rola_para_o_lado_em_375px(app, tmp_path):
    cfg, porta = app(acoes=True, controle=ControleFalso())
    (cfg.erros / "20261023_101500_um_nome_de_arquivo_bem_comprido_de_pesquisa_nps_outubro_2026.xlsx").write_bytes(b"x")
    p, b = _navegador()
    try:
        ctx = b.new_context(viewport={"width": 375, "height": 740}, device_scale_factor=2, is_mobile=True, has_touch=True)
        pg = ctx.new_page()
        base = f"http://127.0.0.1:{porta}"
        pg.goto(base + "/")
        pg.wait_for_selector("#tela-login:not([hidden])")
        assert _largura_extra(pg) <= 0, "tela de entrada"
        pg.fill("#senha", SENHA)
        pg.click("#form-login button")
        pg.wait_for_selector("#tela-resumo:not([hidden]) .kpi")
        for aba in ("vivo", "andares", "operacao", "acoes"):
            pg.click(f'.aba[data-aba="{aba}"]')
            assert _largura_extra(pg) <= 0, f"aba {aba}"
        alvo = pg.eval_on_selector('.botoes .acao[data-acao="pausar"]', "e => e.getBoundingClientRect().height")
        assert alvo >= 44  # dedo, não mouse
        pg.goto(base + "/offline.html")
        assert _largura_extra(pg) <= 0, "tela offline"
        ctx.close()
    finally:
        b.close()
        p.stop()


def teste_painel_principal_em_375px_sem_rolar_para_o_lado(tmp_path):
    import yaml
    from robo.painel.controle import ControleRobo
    from robo.painel.servidor import Api, criar_manipulador
    entrada = tmp_path / "Bases-Limpeza"
    entrada.mkdir()
    arq = tmp_path / "config.yaml"
    arq.write_text(yaml.safe_dump({"pastas": {"entrada": str(entrada), "logs": str(tmp_path / "logs"),
                                              "agentes": str(tmp_path / "agentes"), "habilidades": str(tmp_path / "hab")},
                                   "painel": {"notificacoes": False}}), encoding="utf-8")
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), None)
    porta = servidor.server_address[1]
    servidor.RequestHandlerClass = criar_manipulador(Api(ControleRobo(arq), porta))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    p, b = _navegador()
    try:
        ctx = b.new_context(viewport={"width": 375, "height": 740}, is_mobile=True, has_touch=True)
        pg = ctx.new_page()
        for pagina in ("inicio", "historico", "fabrica", "celular"):
            pg.goto(f"http://127.0.0.1:{porta}/#{pagina}")
            pg.wait_for_selector(".pagina .cabecalho h1")
            pg.wait_for_timeout(400)
            assert _largura_extra(pg) <= 0, pagina
        assert pg.is_visible(".topo-movel")  # gaveta: o menu fica atrás do botão ☰
        ctx.close()
    finally:
        b.close()
        p.stop()
        servidor.shutdown()
