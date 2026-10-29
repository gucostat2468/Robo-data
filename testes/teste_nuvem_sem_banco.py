"""Turno que não depende do banco (robo/nuvem.py): a memória também vai num arquivo criptografado do GitHub Actions.

27/10: o Neon grátis estourou a cota, recusou as conexões e o turno nem começava (a empresa parou). O que precisa
ser verdade agora:
  - o arquivo é criptografado (o repositório é público) e conferido pelo SHA-256 ao voltar; chave errada = ignorado;
  - sem chave nenhuma, o arquivo não é gravado (nunca em claro);
  - o turno restaura a cópia MAIS NOVA entre o banco e o arquivo; banco fora do ar não impede o turno;
  - sem banco, o turno trabalha, salva no arquivo e diz no resultado que está sem banco.
"""

import gzip
import hashlib
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from robo import nuvem, rotinas

URL_FORA = "postgresql://u:p@127.0.0.1:1/x"  # porta 1: o banco não responde (como o Neon com a cota estourada)


@pytest.fixture
def pastas(tmp_path, monkeypatch):
    ent, sai = tmp_path / "entrada", tmp_path / "saida"
    monkeypatch.setenv("ROBO_MEMORIA_ENTRADA", str(ent))
    monkeypatch.setenv("ROBO_MEMORIA_SAIDA", str(sai))
    monkeypatch.setenv("ROBO_MEMORIA_CHAVE", "chave-de-teste-123")
    monkeypatch.setattr(nuvem, "_sem_banco", {"motivo": None})
    return ent, sai


def _db_gz(tmp_path, marca: str) -> tuple[bytes, str]:
    db = tmp_path / f"{marca}.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE marca (v TEXT)")
        c.execute("INSERT INTO marca VALUES (?)", (marca,))
    bruto = db.read_bytes()
    return gzip.compress(bruto), hashlib.sha256(bruto).hexdigest()


def teste_arquivo_criptografado_volta_igual_e_chave_errada_e_ignorada(pastas, tmp_path, monkeypatch):
    ent, sai = pastas
    dados, sha = _db_gz(tmp_path, "a")
    arq = nuvem.guardar_arquivo(dados, sha, 1)
    assert arq.read_bytes()[:8] == b"Salted__" and dados not in arq.read_bytes()  # criptografado, nada em claro
    sai.rename(ent)
    lido = nuvem.ler_arquivo()
    assert lido["sha256"] == sha and lido["dados"] == dados
    monkeypatch.setenv("ROBO_MEMORIA_CHAVE", "outra-chave")
    assert nuvem.ler_arquivo() is None  # chave errada: não usa (e não quebra o turno)


def teste_sem_chave_nao_grava_arquivo(pastas, tmp_path, monkeypatch):
    monkeypatch.delenv("ROBO_MEMORIA_CHAVE")
    monkeypatch.delenv("ROBO_PG_URL", raising=False)
    dados, sha = _db_gz(tmp_path, "a")
    assert nuvem.guardar_arquivo(dados, sha, 1) is None
    monkeypatch.setenv("ROBO_PG_URL", URL_FORA)  # sem chave própria, deriva do segredo do banco
    assert nuvem.guardar_arquivo(dados, sha, 1)


def teste_restaura_do_arquivo_quando_o_banco_esta_fora(pastas, tmp_path):
    ent, sai = pastas
    dados, sha = _db_gz(tmp_path, "do_arquivo")
    nuvem.guardar_arquivo(dados, sha, 1)
    sai.rename(ent)
    cfg = nuvem.config_da_nuvem(tmp_path / "turno", URL_FORA)
    cfg.criar_pastas()
    r = nuvem.restaurar(cfg)
    assert r["origem"] == "arquivo do GitHub" and r["banco"] is False and r["sem_banco"]
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        assert c.execute("SELECT v FROM marca").fetchone()[0] == "do_arquivo"


def teste_restaura_a_copia_mais_nova(pastas, tmp_path, monkeypatch):
    """Banco com a cópia de ontem, arquivo com a de agora (o turno trabalhou sem banco): usa o arquivo; e o contrário."""
    ent, sai = pastas
    novo, sha_novo = _db_gz(tmp_path, "novo")
    nuvem.guardar_arquivo(novo, sha_novo, 1)
    sai.rename(ent)
    velho, sha_velho = _db_gz(tmp_path, "velho")

    class Conn:
        def __init__(self, quando):
            self.quando = quando

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, *a):
            return self

        def fetchone(self):
            return (7, sha_velho, velho, self.quando)
    for quando, esperado in ((datetime.now(timezone.utc) - timedelta(days=1), "novo"),
                             (datetime.now(timezone.utc) + timedelta(days=1), "velho")):
        cfg = nuvem.config_da_nuvem(tmp_path / f"turno_{esperado}", URL_FORA)
        cfg.criar_pastas()
        monkeypatch.setattr(nuvem, "_conectar", lambda cfg, q=quando: Conn(q))
        nuvem.restaurar(cfg)
        with sqlite3.connect(cfg.logs / "trabalho.db") as c:
            assert c.execute("SELECT v FROM marca").fetchone()[0] == esperado


def teste_turno_trabalha_sem_banco_e_guarda_a_memoria(pastas, tmp_path, monkeypatch):
    ent, sai = pastas
    monkeypatch.setattr(nuvem, "_esteira", lambda m: 0)
    monkeypatch.setattr(nuvem, "garantir_base", lambda cfg, m: 0)
    monkeypatch.setattr(rotinas, "funcao", lambda cfg, nome: (lambda: None))
    parar = threading.Event()
    monkeypatch.setattr(rotinas, "batimento", lambda *a, **k: parar.set())
    dados, sha = _db_gz(tmp_path, "turno_anterior")  # o turno anterior deixou a memória no arquivo
    nuvem.guardar_arquivo(dados, sha, 1)
    sai.rename(ent)
    cfg = nuvem.config_da_nuvem(tmp_path / "turno", URL_FORA)
    r = nuvem.turno(cfg, minutos=5, pausa_s=0, parar=parar)
    assert r["origem"] == "arquivo do GitHub"
    assert r["banco"] is False and r["sem_banco"] and r["banco_mb"] is None
    assert r["memoria"]["arquivo_github"] is True and (sai / nuvem.ARQ_MEMORIA).exists()
    # o próximo turno começa dessa memória (a deste turno, não a anterior)
    import shutil
    shutil.rmtree(ent)
    sai.rename(ent)
    cfg2 = nuvem.config_da_nuvem(tmp_path / "turno2", URL_FORA)
    cfg2.criar_pastas()
    assert nuvem.restaurar(cfg2)["origem"] == "arquivo do GitHub"


def teste_banco_fora_e_sem_arquivo_nao_comeca_de_memoria_antiga(pastas, tmp_path):
    """A memória mais nova está presa no banco: começar da inicial criaria duas histórias com os mesmos números."""
    cfg = nuvem.config_da_nuvem(tmp_path / "turno", URL_FORA)
    cfg.criar_pastas()
    with pytest.raises(RuntimeError, match="não começa de uma memória antiga"):
        nuvem.restaurar(cfg)
    assert not (cfg.logs / "trabalho.db").exists()
