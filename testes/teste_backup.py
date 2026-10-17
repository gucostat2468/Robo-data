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
    Banco(cfg.banco, cfg.base).criar_banco_se_preciso()
    if not com_pg_dump:
        monkeypatch.setattr(backup, "localizar_pg_dump", lambda: None)
    elif not backup.localizar_pg_dump():
        pytest.skip("pg_dump não instalado")
    for _ in range(3):
        r = backup.fazer_backup(cfg)
        assert r["ok"], r
    assert r["metodo"] == ("pg_dump" if com_pg_dump else "csv")
    assert len([d for d in backup.pasta(cfg).iterdir() if d.is_dir()]) <= 2, "guarda só os últimos N"
