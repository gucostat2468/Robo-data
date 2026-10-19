"""Acompanhamento pelo celular (somente leitura) e liberação do PostgreSQL para o app do celular.

O que precisa ser verdade sempre:
  - o servidor do celular não tem NENHUMA ação: só a página, o resumo e entrar/sair;
  - só responde a rede privada; exige a senha do painel; sem senha no painel, não liga;
  - 5 senhas erradas do mesmo aparelho → bloqueado (mesmo acertando depois);
  - toda tentativa de entrar fica registrada para sempre;
  - o pg_hba.conf só ganha UMA linha (idempotente), com cópia de antes, e só para rede privada.
"""

import http.client
import json
import sqlite3
import threading
from http.server import ThreadingHTTPServer

import pytest

from robo.painel import celular
from robo.painel.acesso import gerar_hash

SENHA = "Celular@2026segura"


@pytest.fixture
def servidor(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    guardado = gerar_hash(SENHA)
    feitos = []

    def _ligar(ip_cliente=None):
        Manip = celular.criar_manipulador(lambda: cfg, lambda: guardado, None, celular.PortaoCelular())
        if ip_cliente:
            Manip = type("Fora", (Manip,), {"_ip": lambda self: ip_cliente})
        s = ThreadingHTTPServer(("127.0.0.1", 0), Manip)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        feitos.append(s)
        return s.server_address[1]
    yield cfg, _ligar
    for s in feitos:
        s.shutdown()
        s.server_close()


def _pedir(porta, metodo, caminho, corpo=None, cookie=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    cab = {"Content-Type": "application/json", "User-Agent": "iPhone teste"}
    if cookie:
        cab["Cookie"] = cookie
    c.request(metodo, caminho, body=json.dumps(corpo).encode() if corpo is not None else None, headers=cab)
    r = c.getresponse()
    dados = r.read()
    c.close()
    return r.status, dict(r.getheaders()), dados


def teste_so_rede_privada():
    for ip in ("127.0.0.1", "192.168.0.23", "10.1.2.3", "172.20.0.5", "100.101.102.103", "::1", "fe80::1%eth0",
               "::ffff:192.168.1.10"):
        assert celular.ip_privado(ip), ip
    for ip in ("8.8.8.8", "200.147.67.142", "172.32.0.1", "::ffff:8.8.8.8", "2804:14c::1", "", "lixo"):
        assert not celular.ip_privado(ip), ip


def teste_nao_liga_sem_senha_nem_desligado(cfg_factory):
    cfg = cfg_factory()
    assert celular.configuracao(cfg) == {"habilitado": False, "porta": 8766}  # desligado por padrão
    s, motivo = celular.iniciar(lambda: cfg, lambda: None)
    assert s is None and "desligado" in motivo
    cfg.dados["celular"] = {"habilitado": True, "porta": 8766}
    s, motivo = celular.iniciar(lambda: cfg, lambda: None)
    assert s is None and "sem senha" in motivo


def teste_fluxo_completo_somente_leitura(servidor):
    cfg, ligar = servidor
    porta = ligar()
    st, cab, corpo = _pedir(porta, "GET", "/")
    assert st == 200 and b"apple-mobile-web-app-capable" in corpo
    assert "default-src 'self'" in cab["Content-Security-Policy"] and cab["X-Frame-Options"] == "DENY"
    assert cab["Cache-Control"] == "no-store"
    for arq in ("/celular.js", "/celular.css", "/robo.svg", "/manifest.webmanifest"):
        assert _pedir(porta, "GET", arq)[0] == 200, arq
    st, _, corpo = _pedir(porta, "GET", "/api/resumo")
    assert st == 200 and json.loads(corpo) == {"erro": "Entre com a senha do painel.", "login": True}  # sem dado nenhum
    # nenhuma rota do painel principal existe aqui (nem para ler, nem para mudar)
    for metodo, rota in (("GET", "/api/historico"), ("POST", "/api/robo/pausar"), ("POST", "/api/consultas/executar"),
                         ("GET", "/../config.yaml"), ("GET", "/inicio.html"), ("POST", "/api/login")):
        assert _pedir(porta, metodo, rota, {})[0] == 404, rota
    st, _, corpo = _pedir(porta, "POST", "/entrar", {"senha": "errada123"})
    assert st == 403 and "incorreta" in json.loads(corpo)["erro"]
    st, cab, _ = _pedir(porta, "POST", "/entrar", {"senha": SENHA})
    assert st == 200 and "HttpOnly" in cab["Set-Cookie"] and "SameSite=Strict" in cab["Set-Cookie"]
    cookie = cab["Set-Cookie"].split(";")[0]
    st, _, corpo = _pedir(porta, "GET", "/api/resumo", cookie=cookie)
    r = json.loads(corpo)
    assert st == 200 and {"robo", "rotinas", "treino", "planilhas", "ti", "decisoes", "backup", "ao_vivo", "andares",
                          "gente"} <= set(r)
    assert isinstance(r["ao_vivo"], list) and isinstance(r["andares"], list) and "conversas" in r["gente"]
    assert r["robo"] == {"ligado": None, "fila": None} and isinstance(r["rotinas"]["atrasadas"], list)
    assert "tentativas_24h" in r["treino"] and r["decisoes"]["abertas"] == 0
    assert _pedir(porta, "POST", "/sair", cookie=cookie)[0] == 200
    assert json.loads(_pedir(porta, "GET", "/api/resumo", cookie=cookie)[2]).get("login") is True  # saiu = sessão morta
    eventos = [a["evento"] for a in celular.acessos(cfg)]
    assert eventos == ["entrou", "senha_errada"] and celular.acessos(cfg)[0]["navegador"] == "iPhone teste"


def teste_forca_bruta_bloqueia_o_aparelho(servidor):
    cfg, ligar = servidor
    porta = ligar()
    for _ in range(4):
        assert _pedir(porta, "POST", "/entrar", {"senha": "x" * 9})[0] == 403
    assert _pedir(porta, "POST", "/entrar", {"senha": "x" * 9})[0] == 429
    st, _, corpo = _pedir(porta, "POST", "/entrar", {"senha": SENHA})  # nem a senha certa entra durante o bloqueio
    assert st == 429 and "Tente de novo" in json.loads(corpo)["erro"]
    assert [a["evento"] for a in celular.acessos(cfg)][:2] == ["bloqueado", "bloqueado"]


def teste_fora_da_rede_de_casa_recusa_tudo(servidor):
    _, ligar = servidor
    porta = ligar(ip_cliente="200.147.67.142")
    assert _pedir(porta, "GET", "/")[0] == 403
    assert _pedir(porta, "POST", "/entrar", {"senha": SENHA})[0] == 403


def teste_registro_de_acesso_e_permanente(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    celular.registrar_acesso(cfg, "192.168.0.9", "entrou")
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("UPDATE acessos_celular SET evento='x'")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DELETE FROM acessos_celular")
    c.close()


def teste_seguranca_aponta_celular_sem_senha(cfg_factory):
    from robo.ti import chk_seguranca
    cfg = cfg_factory()
    cfg.criar_pastas()
    cfg.dados["celular"] = {"habilitado": True}
    assert any("celular" in p for p in chk_seguranca(cfg))
    cfg.painel["senha_hash"] = gerar_hash(SENHA)
    assert not any("celular" in p for p in chk_seguranca(cfg))


def teste_comando_celular_liga_e_desliga(tmp_path, cfg_factory):
    import yaml
    from robo.comandos import principal
    base = cfg_factory()
    base.criar_pastas()
    dados = dict(base.dados)
    dados["painel"] = {**dados["painel"], "senha_hash": gerar_hash(SENHA)}
    arq = tmp_path / "config.yaml"
    arq.write_text(yaml.safe_dump(dados, allow_unicode=True), encoding="utf-8")
    assert principal(["--config", str(arq), "celular", "--ligar"]) == 0
    assert yaml.safe_load(arq.read_text(encoding="utf-8"))["celular"]["habilitado"] is True
    assert principal(["--config", str(arq), "celular", "--desligar"]) == 0
    assert yaml.safe_load(arq.read_text(encoding="utf-8"))["celular"]["habilitado"] is False


# ------------------------------------------------------------------------------------- PostgreSQL para o app do celular
def teste_rede_da_casa():
    from robo import acesso_rede_banco as a
    assert a.rede_de("192.168.0.23") == "192.168.0.0/24"
    assert a.rede_de("10.0.5.77") == "10.0.5.0/24"
    assert a.validar_rede("100.64.0.0/10") == "100.64.0.0/10"  # Tailscale
    for ruim in ("0.0.0.0/0", "8.8.8.0/24", "10.0.0.0/8", "200.147.67.0/24"):
        with pytest.raises(ValueError):
            a.validar_rede(ruim)
    with pytest.raises(ValueError):
        a.rede_de("200.147.67.142")
    assert a.listen_inclui("*", "192.168.0.2") and a.listen_inclui("localhost, 192.168.0.2", "192.168.0.2")
    assert not a.listen_inclui("localhost", "192.168.0.2")


def teste_pg_hba_so_ganha_uma_linha_com_copia(tmp_path):
    from robo import acesso_rede_banco as a
    hba = tmp_path / "pg_hba.conf"
    original = "# TYPE DATABASE USER ADDRESS METHOD\nlocal all postgres peer\nhost all all 127.0.0.1/32 scram-sha-256"
    hba.write_text(original, encoding="utf-8")
    r1 = a.incluir_no_hba(hba, "robo_dados", "robo_leitura", "192.168.0.0/24")
    assert r1["alterado"] and (tmp_path / r1["copia"].split("/")[-1]).read_text(encoding="utf-8") == original
    texto = hba.read_text(encoding="utf-8")
    assert texto.startswith(original + "\n")  # nada do que existia mudou
    assert texto.rstrip("\n").splitlines()[-1].split()[:5] == ["host", "robo_dados", "robo_leitura", "192.168.0.0/24", "scram-sha-256"]
    r2 = a.incluir_no_hba(hba, "robo_dados", "robo_leitura", "192.168.0.0/24")
    assert not r2["alterado"] and hba.read_text(encoding="utf-8") == texto  # rodar de novo não duplica
    assert len(list(tmp_path.glob("pg_hba.conf.antes_robo_*"))) == 1
