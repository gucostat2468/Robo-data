"""Backup do PostgreSQL: pg_dump quando existe; senão, exportação em CSV compactado com manifesto."""

import os

import pytest

from robo import backup

PG = os.environ.get("ROBO_TESTE_PG")


def teste_sem_banco_nao_finge_backup(cfg_factory):
    r = backup.fazer_backup(cfg_factory())
    assert not r["ok"] and "desligado" in r["motivo"]


@pytest.mark.skipif(not PG, reason="defina ROBO_TESTE_PG para testar com PostgreSQL")
@pytest.mark.parametrize("com_pg_dump", [True, False])
def teste_backup_real_e_rodizio(cfg_factory, monkeypatch, com_pg_dump):
    import uuid
    partes = dict(p.split("=", 1) for p in PG.split())
    cfg = cfg_factory(banco={"habilitado": True, "host": partes.get("host"), "porta": int(partes.get("port", 5432)),
                             "usuario": partes.get("user", "postgres"), "senha": partes.get("password", ""),
                             "banco": f"robo_bkp_{uuid.uuid4().hex[:8]}"}, backup={"manter": 2})
    from robo.banco import Banco
    b = Banco(cfg.banco, cfg.base)
    b.criar_banco_se_preciso()
    try:
        if not com_pg_dump:
            monkeypatch.setattr(backup, "localizar_pg_dump", lambda: None)
        elif not backup.localizar_pg_dump():
            pytest.skip("pg_dump não instalado")
        for _ in range(3):
            r = backup.fazer_backup(cfg)
            assert r["ok"], r
        assert r["metodo"] == ("pg_dump" if com_pg_dump else "csv")
        dirs = sorted(d.name for d in backup.pasta(cfg).iterdir() if d.is_dir())
        assert len(dirs) <= 2 + 1, "guarda os últimos N + o 1º do mês"
        assert backup._mensais(dirs) <= set(dirs)  # o 1º do mês nunca sai
    finally:  # o banco do teste não fica esquecido no servidor
        with b.conectar("postgres") as conn:
            conn.autocommit = True
            conn.execute(f'DROP DATABASE IF EXISTS "{cfg.banco["banco"]}" WITH (FORCE)')
