"""Levar a memória da empresa para outro computador sem perder nada (python -m robo importar-memoria)."""

import gzip
import shutil
import sqlite3

import pytest

from robo import backup, memoria


def _com_historia(cfg_factory, tmp_path, nome):
    cfg = cfg_factory(pastas={"entrada": str(tmp_path / nome / "entrada"), "logs": str(tmp_path / nome / "logs")})
    cfg.criar_pastas()
    memoria.experiencia(cfg, "dba", "acerto", f"registro de {nome}", "teste", "")
    return cfg


def _contar(cfg, tabela="experiencias"):
    con = sqlite3.connect(cfg.logs / "trabalho.db")
    try:
        return [r[0] for r in con.execute(f"SELECT resumo FROM {tabela}")]
    finally:
        con.close()


def teste_importa_em_computador_novo_e_confere_sha(cfg_factory, tmp_path):
    origem = _com_historia(cfg_factory, tmp_path, "origem")
    b = backup.backup_sqlite(origem)
    arquivo = backup.pasta_sqlite(origem) / b["arquivo"]
    novo = cfg_factory(pastas={"entrada": str(tmp_path / "novo" / "entrada"), "logs": str(tmp_path / "novo" / "logs")})
    r = backup.restaurar_sqlite(novo, arquivo)
    assert r["ok"] and r["sha256"] == b["sha256"] and any("SHA-256 igual" in p for p in r["passos"])
    assert "registro de origem" in _contar(novo)


def teste_recusa_sobrescrever_historia_e_guarda_tudo_ao_substituir(cfg_factory, tmp_path):
    origem = _com_historia(cfg_factory, tmp_path, "origem")
    arquivo = backup.pasta_sqlite(origem) / backup.backup_sqlite(origem)["arquivo"]
    destino = _com_historia(cfg_factory, tmp_path, "destino")
    with pytest.raises(ValueError, match="já tem história"):
        backup.restaurar_sqlite(destino, arquivo)
    assert "registro de destino" in _contar(destino)            # nada mudou
    r = backup.restaurar_sqlite(destino, arquivo, substituir=True)
    assert "registro de origem" in _contar(destino)
    guardados = list(destino.logs.glob("trabalho_antes_da_restauracao_*.db"))
    assert len(guardados) == 1 and any("guardada antes da troca" in p for p in r["passos"])
    con = sqlite3.connect(guardados[0])
    assert "registro de destino" in [x[0] for x in con.execute("SELECT resumo FROM experiencias")]  # a antiga existe
    con.close()


def teste_recusa_arquivo_adulterado(cfg_factory, tmp_path):
    origem = _com_historia(cfg_factory, tmp_path, "origem")
    b = backup.backup_sqlite(origem)
    arquivo = backup.pasta_sqlite(origem) / b["arquivo"]
    adulterado = tmp_path / "x" / arquivo.name
    adulterado.parent.mkdir()
    shutil.copy(backup.pasta_sqlite(origem) / arquivo.name.replace(".db.gz", ".db.manifesto.json"),
                adulterado.parent / arquivo.name.replace(".db.gz", ".db.manifesto.json"))
    with gzip.open(arquivo, "rb") as f:
        dados = bytearray(f.read())
    dados[-10] ^= 0xFF
    with gzip.open(adulterado, "wb") as g:
        g.write(bytes(dados))
    novo = cfg_factory(pastas={"entrada": str(tmp_path / "novo" / "entrada"), "logs": str(tmp_path / "novo" / "logs")})
    with pytest.raises(ValueError, match="SHA-256"):
        backup.restaurar_sqlite(novo, adulterado)
    assert not (novo.logs / "trabalho.db").exists()
