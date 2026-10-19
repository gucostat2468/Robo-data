"""Nada se perde: toda tabela de registro é protegida contra apagar (inclusive as futuras), o SQLite tem backup diário
conferido e o 1º backup de cada mês fica para sempre."""

import gzip
import json
import sqlite3

import pytest

from robo import backup
from robo.trabalho import TABELAS_DE_ESTADO, Trabalho, proteger


@pytest.fixture
def cfg(cfg_factory):
    c = cfg_factory()
    c.criar_pastas()
    return c


def _criar_todas_as_tabelas(cfg):
    """Cada módulo cria o próprio esquema na primeira vez que é usado."""
    from robo import aprendizado, auditoria, erros, ferramentas, interacoes, laboratorio, licoes, rotinas, sala
    Trabalho(cfg)
    for m in (aprendizado, auditoria, erros, interacoes, laboratorio, licoes, sala):
        m._tb(cfg)
    rotinas.estado(cfg)
    ferramentas.executar("historico", cfg, quem="canal_nina")


def teste_nenhuma_tabela_de_registro_pode_ser_apagada(cfg):
    _criar_todas_as_tabelas(cfg)
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    tabelas = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    assert {"laboratorio_exercicios", "interacoes", "uso_ferramentas", "rotinas_execucoes", "auditorias"} <= set(tabelas)
    protegidas = {r[0] for r in c.execute("SELECT tbl_name FROM sqlite_master WHERE type='trigger' "
                                          "AND upper(sql) LIKE '%BEFORE DELETE%'")}
    assert set(tabelas) - protegidas == set(TABELAS_DE_ESTADO)  # só a tabela de estado atual fica sem gatilho
    # prova com linha de verdade numa das que estavam expostas antes
    c.execute("INSERT INTO uso_ferramentas (data_hora, ferramenta, quem, ok) VALUES ('2026-10-18', 'x', 'y', 1)")
    with pytest.raises(sqlite3.DatabaseError, match="não pode ser apagado"):
        c.execute("DELETE FROM uso_ferramentas")
    c.close()


def teste_tabela_criada_no_futuro_ja_nasce_protegida(cfg):
    with Trabalho(cfg).tx() as c:
        c.execute("CREATE TABLE modulo_novo (id INTEGER PRIMARY KEY, x TEXT)")
        assert proteger(c) == ["modulo_novo"]
        assert proteger(c) == []  # idempotente
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    c.execute("INSERT INTO modulo_novo (x) VALUES ('registro')")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DELETE FROM modulo_novo")
    c.close()


def teste_backup_do_sqlite_conferido_compactado_e_registrado(cfg):
    from robo import memoria
    memoria.experiencia(cfg, "limpeza", "acerto", "teste", "pipeline", "x")
    r = backup.backup_sqlite(cfg)
    assert r["ok"] and r["integridade"] == "ok" and r["linhas"] >= 1 and len(r["sha256"]) == 64
    arq = backup.pasta_sqlite(cfg) / r["arquivo"]
    restaurado = cfg.logs / "restaurado.db"
    restaurado.write_bytes(gzip.decompress(arq.read_bytes()))
    c = sqlite3.connect(restaurado)
    assert c.execute("SELECT resumo FROM experiencias").fetchone()[0] == "teste"  # o backup restaura de verdade
    c.close()
    manifesto = json.loads((backup.pasta_sqlite(cfg) / r["arquivo"].replace(".gz", ".manifesto.json")).read_text("utf-8"))
    assert manifesto["contagens"]["experiencias"] == 1
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    assert c.execute("SELECT tipo, ok, sha256 FROM backups_registro").fetchall() == [("sqlite", 1, r["sha256"])]
    c.close()


def teste_rotina_faz_backup_do_sqlite_mesmo_sem_postgres(cfg):
    Trabalho(cfg)
    assert not cfg.banco.get("habilitado")
    backup.rotina(cfg)
    assert backup.ultimo_sqlite(cfg)["ok"]


def teste_primeiro_backup_de_cada_mes_nunca_e_apagado(cfg, monkeypatch):
    pasta = backup.pasta_sqlite(cfg)
    pasta.mkdir(parents=True)
    nomes = [f"trabalho_2026{m:02d}{d:02d}_030000.db.gz" for m in (8, 9, 10) for d in (1, 10, 20)]
    for n in nomes:
        (pasta / n).write_bytes(b"x")
    monkeypatch.setitem(cfg.dados, "backup", {"manter_sqlite": 2, "manter_sqlite_horas": 0, "manter_sqlite_dias": 0})
    backup._rodizio_sqlite(cfg)
    ficaram = sorted(p.name for p in pasta.glob("*.db.gz"))
    assert ficaram == ["trabalho_20260801_030000.db.gz", "trabalho_20260901_030000.db.gz",
                       "trabalho_20261001_030000.db.gz", "trabalho_20261010_030000.db.gz",
                       "trabalho_20261020_030000.db.gz"]


def teste_rodizio_de_hora_em_hora_guarda_48h_um_por_dia_e_o_mes(cfg, monkeypatch):
    from datetime import datetime, timedelta
    monkeypatch.setitem(cfg.dados, "backup", {"manter_sqlite": 1})  # isola as regras de 48 h, dia e mês
    pasta = backup.pasta_sqlite(cfg)
    pasta.mkdir(parents=True)
    agora = datetime.now().replace(minute=0, second=0, microsecond=0)
    horas = [agora - timedelta(hours=h) for h in range(0, 24 * 120, 6)]  # um backup a cada 6 h por 120 dias
    for t in horas:
        (pasta / f"trabalho_{t:%Y%m%d_%H%M%S}.db.gz").write_bytes(b"x")
    backup._rodizio_sqlite(cfg)
    ficaram = {p.name for p in pasta.glob("*.db.gz")}
    nome = lambda t: f"trabalho_{t:%Y%m%d_%H%M%S}.db.gz"  # noqa: E731
    assert all(nome(t) in ficaram for t in horas if agora - t <= timedelta(hours=48))       # tudo das últimas 48 h
    for dia in {t.date() for t in horas if agora - t <= timedelta(days=89)}:                  # 1 por dia em 90 dias
        assert nome(min(t for t in horas if t.date() == dia)) in ficaram
    assert not any(nome(t) in ficaram for t in horas                                         # o resto sai…
                   if timedelta(hours=49) < agora - t < timedelta(days=89) and t != min(x for x in horas if x.date() == t.date()))
    for mes in {(t.year, t.month) for t in horas}:                                           # …menos o 1º do mês
        assert nome(min(t for t in horas if (t.year, t.month) == mes)) in ficaram


def teste_copia_extra_conferida(cfg, tmp_path, monkeypatch):
    from robo import memoria
    extra = tmp_path / "hd_externo"
    monkeypatch.setitem(cfg.dados, "backup", {"copia_extra": str(extra)})
    memoria.experiencia(cfg, "dba", "acerto", "algo para copiar", "teste", "")
    r = backup.backup_sqlite(cfg)
    assert r["ok"] and r["copia_extra"] is True
    copiado = extra / "robo_planilhas" / "backups_sqlite" / r["arquivo"]
    assert copiado.read_bytes() == (backup.pasta_sqlite(cfg) / r["arquivo"]).read_bytes()


def teste_retencao_padrao_guarda_originais_para_sempre(cfg):
    assert cfg.manutencao["dias_retencao_originais"] == 0 and cfg.manutencao["dias_retencao_relatorios"] == 0
