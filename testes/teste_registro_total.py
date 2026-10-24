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


def teste_maquina_nova_recebe_os_arquivos_byte_a_byte(cfg_factory, tmp_path):
    import shutil
    from robo.canal import Canal
    origem = cfg_factory(pastas={"entrada": str(tmp_path / "a" / "entrada"), "logs": str(tmp_path / "a" / "logs")})
    origem.criar_pastas()
    canal = Canal(origem)
    canal.postar("dba", "primeira mensagem", "banco", "alerta", ref="H-1")
    canal.postar("coord_devops", "segunda — com acento", "ti")
    (origem.logs / "ti").mkdir(exist_ok=True)
    (origem.logs / "ti" / "estado.json").write_text('{"alertas_ativos": ["x"]}', encoding="utf-8")
    (origem.logs / "rh").mkdir(exist_ok=True)
    (origem.logs / "rh" / "avaliacoes.jsonl").write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
    rt.capturar(origem)
    nova = cfg_factory(pastas={"entrada": str(tmp_path / "b" / "entrada"), "logs": str(tmp_path / "b" / "logs")})
    nova.criar_pastas()
    shutil.copy(origem.logs / "trabalho.db", nova.logs / "trabalho.db")   # só o banco viaja
    feitos = rt.restaurar_arquivos(nova)
    assert feitos["canal"] == 2 and feitos["versoes"] >= 2 and feitos["linhas"] == 1
    for rel in ("canal/mensagens.jsonl", "canal/estado.json", "ti/estado.json", "rh/avaliacoes.jsonl"):
        assert (nova.logs / rel).read_bytes() == (origem.logs / rel).read_bytes(), rel
    assert rt.capturar(nova) == {}                        # nada "novo": mesma geração, mesma posição
    Canal(nova).postar("dba", "terceira, já na máquina nova", "banco")
    rt.capturar(nova)
    assert [r[0] for r in _q(nova, "SELECT id FROM canal_mensagens ORDER BY id")] == [1, 2, 3]  # o contador continuou


def _nova_maquina(cfg, guardado):
    """Como o turno da nuvem: só o banco volta (cópia pela API de backup do SQLite, que leva o WAL junto)."""
    import shutil
    import sqlite3
    with sqlite3.connect(cfg.logs / "trabalho.db") as origem, sqlite3.connect(guardado) as copia:
        origem.backup(copia)
    shutil.rmtree(cfg.logs)
    cfg.logs.mkdir(parents=True)
    shutil.copy(guardado, cfg.logs / "trabalho.db")


def teste_historico_atravessa_turnos_sem_cortar_linhas(cfg_factory, tmp_path):
    """Achado no app do celular: na nuvem, linhas do histórico chegavam cortadas ("EINO_estoque…" no lugar da data).
    O CSV é gravado com \\r\\n; a restauração recriava com \\n (arquivo menor) e a captura seguinte continuava da posição
    antiga, cortando o começo das linhas novas. Três turnos seguidos têm de devolver o histórico intacto."""
    import shutil
    from robo import historico, registro_total

    def linha(i):
        return {"data_hora": f"2026-10-24 1{i}:00:00", "arquivo": f"TREINO_x_{i}.xlsx", "status": "sucesso",
                "linhas_entrada": 10, "linhas_saida": 9, "erros": 0, "avisos": 1, "duracao_seg": "13,2",
                "saidas": "s", "id": f"id{i}"}
    cfg = cfg_factory()
    cfg.criar_pastas()
    historico.registrar(cfg.logs, linha(1))
    registro_total.capturar(cfg)
    for turno in (2, 3, 4):  # cada turno: máquina nova (logs apagados, só o banco volta), uma linha nova, captura
        _nova_maquina(cfg, tmp_path / f"db{turno}")
        registro_total.restaurar_arquivos(cfg)
        historico.registrar(cfg.logs, linha(turno))
        registro_total.capturar(cfg)
    linhas = historico.ler(cfg.logs, incluir_sinteticos=True)
    assert [x["arquivo"] for x in linhas] == [f"TREINO_x_{i}.xlsx" for i in (4, 3, 2, 1)]
    assert all(x["data_hora"].startswith("2026-10-24") and x["id"] for x in linhas)


def teste_historico_antigo_guardado_sem_cr_se_recupera(cfg_factory, tmp_path):
    """O banco da nuvem já tem linhas guardadas sem o \\r (antes da correção). Restaurar, escrever e capturar de novo
    precisa manter tudo: a 1ª restauração vira uma geração nova capturada inteira uma vez; dali em diante é exato."""
    import shutil
    import sqlite3
    from robo import historico, registro_total

    cfg = cfg_factory()
    cfg.criar_pastas()
    registro_total.capturar(cfg)  # cria as tabelas
    cab = "﻿" + ";".join(historico.CABECALHO)
    antigas = [cab, "2026-10-23 10:00:00;TREINO_a.xlsx;sucesso;5;5;0;0;1,0;s;ida",
               "2026-10-23 11:00:00;TREINO_b.xlsx;sucesso;5;5;0;0;1,0;s;idb"]
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        for n, txt in enumerate(antigas, 1):  # como a versão antiga guardava: sem o \r
            c.execute("INSERT INTO arquivos_linhas (arquivo, geracao, n_linha, conteudo, capturado_em) VALUES (?,?,?,?,?)",
                      ("logs/historico_processamentos.csv", "legado", n, txt, "2026-10-23T12:00:00"))
    for turno in (1, 2, 3):
        _nova_maquina(cfg, tmp_path / f"db{turno}")
        registro_total.restaurar_arquivos(cfg)
        historico.registrar(cfg.logs, {"data_hora": f"2026-10-24 0{turno}:00:00", "arquivo": f"TREINO_n{turno}.xlsx",
                                       "status": "sucesso", "id": f"n{turno}"})
        registro_total.capturar(cfg)
    linhas = historico.ler(cfg.logs, incluir_sinteticos=True)
    assert [x["arquivo"] for x in linhas] == ["TREINO_n3.xlsx", "TREINO_n2.xlsx", "TREINO_n1.xlsx",
                                             "TREINO_b.xlsx", "TREINO_a.xlsx"]
    assert all(x["data_hora"][:4] == "2026" for x in linhas)


def teste_linha_cortada_do_historico_nao_conta_como_real(cfg_factory):
    """As linhas já cortadas na nuvem (colunas deslocadas) ficam guardadas no banco, mas não entram em número nenhum:
    deslocadas, o nome da planilha de treino caía fora da coluna 'arquivo' e ela passava por real."""
    from robo import central, historico
    cfg = cfg_factory()
    cfg.criar_pastas()
    historico.registrar(cfg.logs, {"data_hora": "2026-10-24 10:00:00", "arquivo": "vendas.xlsx", "status": "sucesso",
                                   "linhas_entrada": 3, "linhas_saida": 3, "erros": 0, "avisos": 0, "id": "v1"})
    with open(historico.arquivo_historico(cfg.logs), "a", encoding="utf-8") as f:  # como a nuvem deixou
        f.write("EINO_estoque_x.xlsx;sucesso;2497;2494;0;2;13,2;TREINO_estoque_x.xlsx | t;20261024_155548_TREINO\r\n")
    assert [x["arquivo"] for x in historico.ler(cfg.logs, incluir_sinteticos=True)] == ["vendas.xlsx"]
    assert central.montar(cfg, 1)["totais"]["recebidos"] in (0, 1)  # a Central não quebra mais com o '13,2'
