"""Conversas entre funcionários: só com fato e necessidade, com evidência em cada fala e compromisso verificado depois."""

import json
import sqlite3
from datetime import datetime

from robo import aprendizados, dialogo, fatos, rotinas


def _cfg(cfg_factory):
    cfg = cfg_factory(dialogo={"intervalo_minutos": 0})
    cfg.criar_pastas()
    return cfg


def teste_sem_fato_ninguem_fala_e_o_silencio_e_contado(cfg_factory):
    cfg = _cfg(cfg_factory)
    assert dialogo.rotina(cfg) is None
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    assert c.execute("SELECT sem_assunto, conversas FROM dialogo_ciclos").fetchone() == (1, 0)
    assert c.execute("SELECT name FROM sqlite_master WHERE name='interacoes'").fetchone() is None or \
        c.execute("SELECT COUNT(*) FROM interacoes").fetchone()[0] == 0
    c.close()


def teste_rotina_com_erro_vira_cobranca_do_gestor_com_evidencia(cfg_factory):
    cfg = _cfg(cfg_factory)
    rotinas.executar(cfg, "backup", lambda: (_ for _ in ()).throw(OSError("disco cheio")))
    f = [x for x in fatos.fatos_do_dia(cfg) if x["tipo"] == "rotina_erro"]
    assert f and f[0]["responsavel"] == "dba"
    r = dialogo.rotina(cfg)
    assert r and r["conversas"][0]["para"] == "dba"
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    falas = c.execute("SELECT de, para, texto, dados FROM interacoes ORDER BY id").fetchall()
    assert c.execute("SELECT COUNT(*) FROM interacoes WHERE dados IS NULL").fetchone()[0] == 0
    c.close()
    assert len(falas) >= 2 and "disco cheio" in falas[0][2] and json.loads(falas[0][3])["fonte"].startswith("rotinas_execucoes")
    assert dialogo.rotina(cfg) is None                                    # o mesmo fato não vira conversa duas vezes
    rotinas.executar(cfg, "backup", lambda: {"ok": 1})                   # a rotina voltou: o compromisso fica cumprido
    assert dialogo.verificar_compromissos(cfg) == 1
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    assert c.execute("SELECT situacao FROM dialogo_conversas").fetchone()[0] == "cumprido"
    c.close()


def teste_erro_repetido_no_treino_pede_ajuda_a_quem_acertou(cfg_factory):
    cfg = _cfg(cfg_factory)
    for _ in range(2):
        aprendizados.registrar(cfg, "recepcao", "treino:sql", "erro", causa="numero_diferente: soma sem filtro", origem="treino")
    aprendizados.registrar(cfg, "dba", "treino:sql", "acerto", origem="treino")
    aprendizados.registrar(cfg, None, "treino:sql", "erro", causa="numero_diferente", correcao="aplicar o filtro do pedido",
                           contexto={"tipo_erro": "numero_diferente"}, origem="semente")
    r = dialogo.rotina(cfg)
    conv = r["conversas"][0]
    assert conv["de"] == "recepcao" and conv["para"] == "dba" and conv["turnos"] == 4
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    textos = [x[0] for x in c.execute("SELECT texto FROM interacoes ORDER BY id")]
    origem = c.execute("SELECT origem, resultado FROM aprendizados WHERE origem='dialogo'").fetchone()
    c.close()
    assert "aplicar o filtro do pedido" in textos[1] and origem == ("dialogo", "quase")
    assert all(t.rstrip()[-1] in ".!?" and "|" not in t for t in textos)
