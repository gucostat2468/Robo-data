"""Registro total: tudo o que vira arquivo também vai para o banco — sem duplicar, sem perder, sem segredo."""

import json
import os
import sqlite3
import time

import pytest

from robo import registro_total as rt


def _q(cfg, sql, *args):
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


def _velho(p):
    t = time.time() - 60
    os.utime(p, (t, t))


def teste_log_com_traceback_giro_e_registro_pela_metade(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    log = cfg.logs / "robo.log"
    log.write_text("19/10/2026 10:00:00 | INFO    | começou\n"
                   "19/10/2026 10:00:01 | ERROR   | quebrou\nTraceback (most recent call last):\n  File x\nValueError: y\n"
                   "19/10/2026 10:00:02 | WARNING | ainda escrevendo\n", encoding="utf-8")
    rt.capturar(cfg)  # arquivo recém-escrito: o último registro espera (pode estar pela metade)
    assert [r[0] for r in _q(cfg, "SELECT nivel FROM logs_sistema ORDER BY id")] == ["INFO", "ERROR"]
    erro = _q(cfg, "SELECT mensagem FROM logs_sistema WHERE nivel='ERROR'")[0][0]
    assert erro.startswith("quebrou\nTraceback") and erro.endswith("ValueError: y")
    _velho(log)
    rt.capturar(cfg)
    assert [r[0] for r in _q(cfg, "SELECT nivel FROM logs_sistema ORDER BY id")] == ["INFO", "ERROR", "WARNING"]
    # meia-noite: o robo.log é girado (renomeado) depois de ganhar mais uma linha; um robo.log novo começa
    with open(log, "a", encoding="utf-8") as f:
        f.write("19/10/2026 23:59:59 | INFO    | última do dia\n")
    log.rename(cfg.logs / "robo.log.2026-10-19")
    (cfg.logs / "robo.log").write_text("20/10/2026 00:00:01 | INFO    | primeira do dia\n", encoding="utf-8")
    for p in cfg.logs.glob("robo.log*"):
        _velho(p)
    rt.capturar(cfg)
    rt.capturar(cfg)
    msgs = [r[0] for r in _q(cfg, "SELECT mensagem FROM logs_sistema ORDER BY data_hora, id")]
    assert msgs == ["começou", erro, "ainda escrevendo", "última do dia", "primeira do dia"]  # nada duplicado, nada perdido
    assert _q(cfg, "SELECT data_hora FROM logs_sistema WHERE mensagem='primeira do dia'")[0][0] == "2026-10-20T00:00:01"


def teste_canal_linhas_versoes_e_segredos(cfg_factory, tmp_path):
    base = tmp_path / "projeto"
    base.mkdir()
    (base / "config.yaml").write_text("banco:\n  senha: segredo123\npainel:\n  senha_hash: pbkdf2$abc\n  porta: 8765\n",
                                      encoding="utf-8")
    cfg = cfg_factory()
    cfg.base = base
    cfg.criar_pastas()
    (cfg.logs / "canal").mkdir()
    (cfg.logs / "canal" / "mensagens.jsonl").write_text(
        json.dumps({"id": 1, "data_hora": "2026-10-19 10:00:00", "canal": "ti", "autor": "dba", "nome": "Dora", "papel": "",
                    "tipo": "alerta", "texto": "oi", "ref": "H-1"}, ensure_ascii=False) + "\n", encoding="utf-8")
    (cfg.logs / "rh").mkdir()
    (cfg.logs / "rh" / "avaliacoes.jsonl").write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
    ata = cfg.logs / "reunioes"
    ata.mkdir()
    (ata / "REU-1.md").write_text("# Ata v1\n", encoding="utf-8")
    r1 = rt.capturar(cfg)
    assert r1 == {"canal_mensagens": 1, "arquivos_linhas": 2, "arquivos_versoes": 2}
    assert _q(cfg, "SELECT autor, texto, extra FROM canal_mensagens")[0] == ("dba", "oi", '{"ref": "H-1"}')
    config = _q(cfg, "SELECT conteudo FROM arquivos_versoes WHERE arquivo='config.yaml'")[0][0]
    assert "segredo123" not in config and "pbkdf2" not in config and "senha: ***" in config and "porta: 8765" in config
    assert rt.capturar(cfg) == {}                                    # sem novidade: nada gravado
    (ata / "REU-1.md").write_text("# Ata v2 (corrigida)\n", encoding="utf-8")
    with open(cfg.logs / "rh" / "avaliacoes.jsonl", "a", encoding="utf-8") as f:
        f.write('{"a": 3}\n')
    assert rt.capturar(cfg) == {"arquivos_linhas": 1, "arquivos_versoes": 1}
    versoes = [r[0] for r in _q(cfg, "SELECT conteudo FROM arquivos_versoes WHERE arquivo='logs/reunioes/REU-1.md' ORDER BY id")]
    assert versoes == ["# Ata v1\n", "# Ata v2 (corrigida)\n"]    # a versão antiga continua lá


def teste_registros_sao_imutaveis_e_cobertura_aponta_o_que_falta(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    (cfg.logs / "robo.log").write_text("19/10/2026 10:00:00 | INFO    | x\n", encoding="utf-8")
    _velho(cfg.logs / "robo.log")
    rt.capturar(cfg)
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    for sql in ("UPDATE logs_sistema SET mensagem='adulterado'", "DELETE FROM logs_sistema"):
        with pytest.raises(sqlite3.DatabaseError):
            c.execute(sql)
    c.close()
    assert rt.cobertura(cfg) == []
    (cfg.logs / "formato_novo.xyz").write_text("?", encoding="utf-8")
    assert rt.cobertura(cfg) == ["formato_novo.xyz"]               # arquivo de tipo desconhecido não passa calado
