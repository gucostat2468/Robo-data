"""5º andar com trabalho de nuvem real (robo/ti_nuvem.py), modo servidor (robo/servico.py) e conexão por variáveis.

O que precisa ser verdade sempre:
  - backup que não volta é problema; computador novo (menos de um dia) não é;
  - o caçador de segredos acha token e senha plantados e não acusa os moldes da documentação;
  - a conexão do Google Cloud vai pelo Unix socket /cloudsql/<instância> e sem SSL; sem variável, nada;
  - a saúde do serviço só lê: GET responde, POST é recusado, nenhum segredo aparece.
"""

import gzip
import json
import shutil
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import pytest

from robo import nuvem, servico, ti_nuvem


def _banco_vivo(cfg, dias_atras: float):
    db = cfg.logs / "trabalho.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE IF NOT EXISTS sessoes (id INTEGER PRIMARY KEY, aberto_em TEXT)")
        c.execute("INSERT INTO sessoes (aberto_em) VALUES (?)",
                  ((datetime.now() - timedelta(days=dias_atras)).isoformat(timespec="seconds"),))
    return db


def teste_backup_restaura_ou_acusa(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    assert ti_nuvem.detalhe_restauracao(cfg)["ok"]                         # sem banco: nada a cobrar
    db = _banco_vivo(cfg, 0.1)
    assert ti_nuvem.chk_restauracao_backup(cfg) == []                      # banco de hoje: backup ainda não venceu
    db.unlink()
    db = _banco_vivo(cfg, 3)
    assert ti_nuvem.chk_restauracao_backup(cfg)                            # 3 dias sem backup: problema
    pasta = cfg.logs / "backups_sqlite"
    pasta.mkdir()
    with open(db, "rb") as o, gzip.open(pasta / "trabalho_x.db.gz", "wb") as d:
        shutil.copyfileobj(o, d)
    r = ti_nuvem.detalhe_restauracao(cfg)
    assert r["ok"] and r["integridade"] == "ok" and r["linhas"] == 1
    (pasta / "trabalho_y.db.gz").write_bytes(gzip.compress(b"isto nao e um banco" * 100))
    import os
    os.utime(pasta / "trabalho_y.db.gz", (datetime.now().timestamp() + 60,) * 2)  # o mais novo é o quebrado
    with pytest.raises(sqlite3.DatabaseError):
        ti_nuvem.detalhe_restauracao(cfg)


def teste_cacador_de_segredos(tmp_path):
    (tmp_path / "a.py").write_text('URL = "postgresql://robo:' + 'S3nhaForte@host/db"\n', encoding="utf-8")  # montado em 2 partes: este arquivo não pode ter o segredo inteiro
    (tmp_path / "b.md").write_text("Use postgresql://usuario:senha@host/banco no exemplo\n", encoding="utf-8")
    (tmp_path / "c.yaml").write_text("token: 123456789:AA" + "b" * 33 + "\n", encoding="utf-8")
    achados = ti_nuvem.detalhe_segredos(None, tmp_path)["achados"]
    assert {(a["arquivo"], a["tipo"]) for a in achados} == {("a.py", "URL de banco com senha"),
                                                            ("c.yaml", "token do Telegram")}


def teste_o_repositorio_esta_pronto_e_limpo():
    assert ti_nuvem.detalhe_prontidao(None)["problemas"] == []
    assert ti_nuvem.detalhe_segredos(None)["problemas"] == []


def teste_url_do_ambiente():
    assert nuvem.url_do_ambiente({}) == ""
    assert nuvem.url_do_ambiente({"ROBO_PG_URL": "postgresql://a:b@h/d"}) == "postgresql://a:b@h/d"
    from psycopg.conninfo import conninfo_to_dict
    c = conninfo_to_dict(nuvem.url_do_ambiente({"DB_USER": "app", "DB_PASS": "x y'z", "DB_NAME": "flexible",
                                               "INSTANCE_CONNECTION_NAME": "proj:us-central1:flexible-db"}))
    assert c["host"] == "/cloudsql/proj:us-central1:flexible-db" and c["password"] == "x y'z" and "port" not in c
    c = conninfo_to_dict(nuvem.url_do_ambiente({"DB_USER": "app", "DB_NAME": "d", "DB_HOST": "10.0.0.5"}))
    assert c["host"] == "10.0.0.5" and c["port"] == "5432"


def teste_socket_do_cloud_sql_sem_ssl(tmp_path):
    url = nuvem.url_do_ambiente({"DB_USER": "app", "DB_PASS": "p", "DB_NAME": "d",
                                 "INSTANCE_CONNECTION_NAME": "proj:reg:inst"})
    cfg = nuvem.config_da_nuvem(tmp_path, url)
    assert cfg.banco["host"] == "/cloudsql/proj:reg:inst" and cfg.banco["sslmode"] == ""
    cfg = nuvem.config_da_nuvem(tmp_path, "postgresql://a:b@ep-x.neon.tech/neondb")
    assert cfg.banco["sslmode"] == "require"


def teste_saude_so_le_e_nao_mostra_segredo():
    srv = servico.iniciar_saude(0)  # porta livre qualquer
    porta = srv.server_address[1]
    try:
        servico._atualizar(estado="entre_turnos", turnos=3)
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/saude", timeout=5) as r:
            corpo = json.loads(r.read())
        assert corpo["estado"] == "entre_turnos" and corpo["turnos"] == 3
        assert not any(k in json.dumps(corpo).lower() for k in ("senha", "password", "postgresql://"))
        req = urllib.request.Request(f"http://127.0.0.1:{porta}/saude", data=b"x", method="POST")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        assert e.value.code == 405
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/painel", timeout=5)
        assert e.value.code == 404
    finally:
        srv.shutdown()


def teste_servico_sem_banco_nao_sobe(monkeypatch, tmp_path):
    for v in ("ROBO_PG_URL", "DB_USER", "DB_PASS", "DB_NAME", "INSTANCE_CONNECTION_NAME"):
        monkeypatch.delenv(v, raising=False)
    assert servico.principal(str(tmp_path), voltas=1) == 1


# ----------------------------------------------------------------------------------------------- operação 24 h
def _get(porta, rota):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}{rota}", timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def teste_healthz_diz_503_com_banco_fora_e_nao_vaza_endereco(tmp_path, monkeypatch):
    cfg = nuvem.config_da_nuvem(tmp_path, "postgresql://u:" + "segredo123@127.0.0.1:1/x")  # porta 1: ninguém escuta (montado em 2 partes)
    monkeypatch.setitem(servico._BANCO, "cfg", cfg)
    monkeypatch.setitem(servico._BANCO, "quando", 0.0)
    srv = servico.iniciar_saude(0)
    try:
        codigo, corpo = _get(srv.server_address[1], "/healthz")
        assert codigo == 503 and corpo["banco"]["ok"] is False and corpo["processo"] == "vivo"
        assert "segredo123" not in json.dumps(corpo) and "127.0.0.1" not in json.dumps(corpo)
    finally:
        srv.shutdown()


DSN = __import__("os").environ.get("ROBO_TESTE_PG")


@pytest.mark.skipif(not DSN, reason="defina ROBO_TESTE_PG para testar com PostgreSQL")
def teste_healthz_200_com_banco_no_ar(tmp_path, monkeypatch):
    d = dict(p.split("=", 1) for p in DSN.split())
    cfg = nuvem.config_da_nuvem(tmp_path, f"postgresql://{d.get('user', 'postgres')}@{d.get('host')}:{d.get('port')}/postgres")
    monkeypatch.setitem(servico._BANCO, "cfg", cfg)
    monkeypatch.setitem(servico._BANCO, "quando", 0.0)
    srv = servico.iniciar_saude(0)
    try:
        codigo, corpo = _get(srv.server_address[1], "/healthz")
        assert codigo == 200 and corpo["banco"]["ok"] is True
    finally:
        srv.shutdown()


def teste_sinal_de_parada_encerra_o_turno_salvando(tmp_path, monkeypatch):
    """SIGTERM liga PARAR: o turno sai do laço logo e ainda passa por salvar() (nada do que foi feito se perde)."""
    import threading
    import time as _t
    from robo import rotinas
    chamadas = []
    monkeypatch.setattr(nuvem, "restaurar", lambda cfg: {"origem": "teste"})
    monkeypatch.setattr(nuvem, "garantir_leitura", lambda cfg: True)
    monkeypatch.setattr(nuvem, "salvar", lambda cfg: chamadas.append("salvar") or {"ok": True})
    monkeypatch.setattr(nuvem, "tamanho_mb", lambda cfg: 1.0)
    monkeypatch.setattr(nuvem, "_esteira", lambda m: 0)
    monkeypatch.setattr(rotinas, "executar", lambda *a, **k: None)
    monkeypatch.setattr(rotinas, "funcao", lambda *a, **k: None)
    monkeypatch.setattr(rotinas, "abrir_sessao", lambda cfg: {"sessao": 1})
    monkeypatch.setattr(rotinas, "batimento", lambda *a, **k: None)
    cfg = nuvem.config_da_nuvem(tmp_path, "postgresql://u:p@127.0.0.1:1/x")
    parar = threading.Event()
    threading.Timer(0.5, parar.set).start()
    inicio = _t.monotonic()
    r = nuvem.turno(cfg, minutos=10, pausa_s=60, parar=parar)
    assert _t.monotonic() - inicio < 10   # não esperou os 10 minutos
    assert chamadas == ["salvar"] and r["voltas"] >= 1


def teste_turno_trata_a_planilha_antes_de_distribuir_trabalho(tmp_path, monkeypatch):
    """Cada turno começa numa máquina nova: a demanda que precisa de planilha só pode ser distribuída depois que a
    fábrica gerou e a esteira tratou a planilha do turno (antes virava estudo por bloqueio)."""
    import threading
    from robo import rotinas
    ordem = []
    monkeypatch.setattr(nuvem, "restaurar", lambda cfg: {"origem": "teste"})
    monkeypatch.setattr(nuvem, "garantir_leitura", lambda cfg: True)
    monkeypatch.setattr(nuvem, "salvar", lambda cfg: {"ok": True})
    monkeypatch.setattr(nuvem, "tamanho_mb", lambda cfg: 1.0)
    monkeypatch.setattr(nuvem, "_esteira", lambda m: ordem.append("ESTEIRA") or 0)
    monkeypatch.setattr(rotinas, "executar", lambda cfg, nome, f: ordem.append(nome))
    monkeypatch.setattr(rotinas, "funcao", lambda *a, **k: None)
    monkeypatch.setattr(rotinas, "abrir_sessao", lambda cfg: {"sessao": 1})
    monkeypatch.setattr(rotinas, "batimento", lambda *a, **k: None)
    cfg = nuvem.config_da_nuvem(tmp_path, "postgresql://u:p@127.0.0.1:1/x")
    parar = threading.Event()
    threading.Timer(0.3, parar.set).start()
    nuvem.turno(cfg, minutos=5, pausa_s=60, parar=parar)
    assert ordem.index("fabrica") < ordem.index("ESTEIRA") < ordem.index("demandas")
    # e em cada volta do laço também: fábrica → esteira → demandas
    volta = ordem[ordem.index("canal"):]
    assert volta.index("fabrica") < volta.index("ESTEIRA") < volta.index("demandas")


def teste_maquina_nova_ganha_planilha_antes_da_distribuicao(cfg_factory):
    """Máquina nova do turno não tem planilha: sem ela quase todo trabalho das áreas de dados ficava bloqueado."""
    from robo import demandas, pos_processamento
    from robo.monitor import Monitor
    cfg = cfg_factory(fabrica={"linhas_min": 200, "linhas_max": 300})
    cfg.criar_pastas()
    assert not demandas.base_tratada(cfg)
    monitor = Monitor(cfg, ao_processar=lambda r: pos_processamento.registrar(cfg, r))
    assert nuvem.garantir_base(cfg, monitor) == 1
    assert demandas.base_tratada(cfg) and demandas.base_original(cfg)
    assert nuvem.garantir_base(cfg, monitor) == 0  # já tem: não produz outra
