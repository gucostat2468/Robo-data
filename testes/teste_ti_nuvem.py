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
