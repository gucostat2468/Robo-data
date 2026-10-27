"""Tempo do turno por natureza (robo/tempo_turno.py): medido, nunca estimado.

O que precisa ser verdade:
  - cada segundo cronometrado vai para UMA natureza; o que o cronômetro não cobriu fica em "sem_medicao";
  - o tempo da rotina demandas é repartido pelas demandas que ela executou (trabalho → operacional, estudo → estudo,
    falha → erro) e o resto é revisão/coordenação do ciclo; nunca passa do tempo da própria rotina;
  - rotina que terminou em erro conta como erro;
  - entrega aprovada = demanda de trabalho 'concluida' (passou na revisão independente); estudo não conta;
  - o registro do turno é permanente (nem alterar nem apagar).
"""

import json
import sqlite3
import time
from datetime import datetime, timedelta

import pytest

from robo import jobs, rotinas, tempo_turno
from robo.trabalho import Trabalho


def _cfg(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    Trabalho(cfg)
    return cfg


def _demanda(cfg, sid, tipo, estado_job, segundos, estado_sol="concluida"):
    agora = datetime.now()
    ini = (agora - timedelta(seconds=segundos)).isoformat(timespec="seconds")
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        c.execute("INSERT INTO solicitacoes (id, tipo, origem, estado, funcionario, plano, criada_em, atualizada_em) "
                  "VALUES (?,?,?,?,?,?,?,?)", (sid, "tarefa", "demanda_sintetica", estado_sol, "dba",
                                                json.dumps({"tipo_demanda": tipo}), ini, agora.isoformat(timespec="seconds")))
    jid = jobs.abrir(cfg, "demanda", "sintetico", None, "dba")
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        c.execute("UPDATE jobs SET inicio=? WHERE id=?", (ini, jid))
    jobs.fechar(cfg, jid, estado_job, {"solicitacao": sid})


def teste_reparte_o_tempo_e_mede_a_cobertura(cfg_factory):
    cfg = _cfg(cfg_factory)
    cr = tempo_turno.Cronometro()
    cr.inicio_txt = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
    cr.por_chamada = {"esteira": 30.0, "treino": 20.0, "backup": 10.0, "pausa": 60.0, "dialogo": 5.0, "demandas": 40.0}
    _demanda(cfg, "D1", "trabalho", "concluido", 10)
    _demanda(cfg, "D2", "treinamento", "concluido", 5)
    _demanda(cfg, "D3", "trabalho", "falhou", 5, "falhou")
    r = tempo_turno.calcular(cfg, cr, total_s=200.0)
    n = r["por_natureza"]
    assert n["operacional"] == pytest.approx(30 + 10, abs=1.5)
    assert n["estudo"] == pytest.approx(20 + 5, abs=1.5)
    assert n["erro"] == pytest.approx(5, abs=1.5)
    assert n["revisao"] == pytest.approx(40 - 20, abs=3)
    assert n["manutencao"] == 10 and n["parado"] == 60 and n["coordenacao"] == 5
    assert n["sem_medicao"] == pytest.approx(200 - 165)
    assert sum(n.values()) == pytest.approx(200, abs=0.5)  # nada some, nada é inventado
    assert r["cobertura"] == pytest.approx(165 / 200, abs=0.001)
    assert r["entregas_aprovadas"] == 1  # só o trabalho concluído; estudo e falha não contam
    assert r["entregas_por_hora"] == pytest.approx(1 / (200 / 3600), abs=0.01)


def teste_demandas_nunca_passam_do_tempo_da_rotina(cfg_factory):
    cfg = _cfg(cfg_factory)
    cr = tempo_turno.Cronometro()
    cr.inicio_txt = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
    cr.por_chamada = {"demandas": 4.0}
    _demanda(cfg, "D1", "trabalho", "concluido", 10)  # 10 s com resolução de segundo > 4 s medidos na rotina
    n = tempo_turno.calcular(cfg, cr, total_s=4.0)["por_natureza"]
    assert n["operacional"] == pytest.approx(4.0) and n["revisao"] == 0


def teste_rotina_com_erro_conta_como_erro(cfg_factory):
    cfg = _cfg(cfg_factory)
    cr = tempo_turno.Cronometro()

    def quebra():
        time.sleep(0.05)  # só para o tempo do erro aparecer no arredondamento
        raise RuntimeError("x")
    cr.rotina(cfg, "dialogo", rotinas.executar, quebra)
    cr.rotina(cfg, "pdca", rotinas.executar, lambda: None)
    n = tempo_turno.calcular(cfg, cr)["por_natureza"]
    assert n["erro"] > 0 and n["erro"] == pytest.approx(cr.por_chamada["dialogo"], abs=0.05)


def teste_registro_do_turno_e_permanente(cfg_factory):
    cfg = _cfg(cfg_factory)
    cr = tempo_turno.Cronometro()
    with cr.medir("pausa"):
        pass
    tempo_turno.fechar(cfg, cr, voltas=3)
    u = tempo_turno.ultimos(cfg)[0]
    assert u["voltas"] == 3 and set(u["por_natureza"]) == set(tempo_turno.NATUREZAS)
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        with pytest.raises(sqlite3.DatabaseError):
            c.execute("UPDATE tempo_turnos SET segundos=0")
        with pytest.raises(sqlite3.DatabaseError):
            c.execute("DELETE FROM tempo_turnos")


def teste_turno_grava_o_tempo_e_o_boletim_mostra(tmp_path, monkeypatch):
    import threading

    from robo import boletim, nuvem
    monkeypatch.setattr(nuvem, "restaurar", lambda cfg: {"origem": "teste"})
    monkeypatch.setattr(nuvem, "garantir_leitura", lambda cfg: True)
    monkeypatch.setattr(nuvem, "salvar", lambda cfg, **k: {"ok": True})
    monkeypatch.setattr(nuvem, "tamanho_mb", lambda cfg: 1.0)
    monkeypatch.setattr(nuvem, "_esteira", lambda m: 0)
    monkeypatch.setattr(nuvem, "garantir_base", lambda cfg, m: 0)
    monkeypatch.setattr(rotinas, "funcao", lambda cfg, nome: (lambda: None))
    monkeypatch.setattr(rotinas, "abrir_sessao", lambda cfg: {"sessao": 1})
    parar = threading.Event()
    monkeypatch.setattr(rotinas, "batimento", lambda *a, **k: parar.set())
    cfg = nuvem.config_da_nuvem(tmp_path, "postgresql://u:p@127.0.0.1:1/x")
    r = nuvem.turno(cfg, minutos=5, pausa_s=0, parar=parar)
    t = r["tempo"]
    assert t and 0 < t["cobertura"] <= 1
    assert sum(t["por_natureza"].values()) == pytest.approx(t["segundos"], abs=0.5)  # o resto é "sem_medicao"
    assert "dialogo" in t["por_chamada"] and "esteira" in t["por_chamada"]
    md = boletim.markdown(boletim.montar(cfg))
    assert "Tempo do último turno (medido)" in md and "indicador principal" in md


def teste_tempo_e_gravado_antes_do_salvamento_final(tmp_path, monkeypatch):
    """1º turno real: o tempo era gravado DEPOIS do salvamento final e ficava só na máquina descartada."""
    import threading

    from robo import nuvem
    vistos = []
    monkeypatch.setattr(nuvem, "restaurar", lambda cfg: {"origem": "teste"})
    monkeypatch.setattr(nuvem, "garantir_leitura", lambda cfg: True)
    monkeypatch.setattr(nuvem, "salvar", lambda cfg, **k: vistos.append(len(tempo_turno.ultimos(cfg))) or {"ok": True})
    monkeypatch.setattr(nuvem, "tamanho_mb", lambda cfg: 1.0)
    monkeypatch.setattr(nuvem, "_esteira", lambda m: 0)
    monkeypatch.setattr(nuvem, "garantir_base", lambda cfg, m: 0)
    monkeypatch.setattr(rotinas, "funcao", lambda cfg, nome: (lambda: None))
    monkeypatch.setattr(rotinas, "abrir_sessao", lambda cfg: {"sessao": 1})
    parar = threading.Event()
    monkeypatch.setattr(rotinas, "batimento", lambda *a, **k: parar.set())
    cfg = nuvem.config_da_nuvem(tmp_path, "postgresql://u:p@127.0.0.1:1/x")
    nuvem.turno(cfg, minutos=5, pausa_s=0, parar=parar)
    assert vistos[-1] == 1  # o salvamento final já leva a linha do tempo deste turno
