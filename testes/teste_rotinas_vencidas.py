"""Cadência das rotinas dentro do turno (rotinas.vencidas + laço de nuvem.turno).

Antes, o laço do turno repetia só canal, registro, treino, laboratório, fábrica, demandas e telegram; o resto rodava
uma vez no começo do turno. Na nuvem real, o diálogo (intervalo de 20 min) foi verificado às 21:58 e às 22:25 ainda
não tinha sido de novo. O que precisa ser verdade:
  - rotina vence quando o intervalo de ROTINAS passa desde a última verificação (relógio controlado);
  - o laço chama a vencida, uma vez, depois de fábrica → esteira → demandas;
  - rotina que falhou não é repetida a cada volta (espera o intervalo dela);
  - as rotinas do laço fixo nunca entram de novo pela lista de vencidas (sem execução duplicada na mesma volta).
"""

import threading
from datetime import datetime, timedelta

from robo import nuvem, rotinas
from robo.trabalho import Trabalho


def _cfg(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    Trabalho(cfg)
    return cfg


def teste_vence_pelo_intervalo_da_rotina_com_relogio_controlado(cfg_factory):
    cfg = _cfg(cfg_factory)
    rotinas.executar(cfg, "dialogo", lambda: None)   # 20 min
    rotinas.executar(cfg, "licoes", lambda: None)    # 60 min
    agora = datetime.now()
    assert "dialogo" not in rotinas.vencidas(cfg, agora + timedelta(minutes=19))
    assert "dialogo" in rotinas.vencidas(cfg, agora + timedelta(minutes=21))
    assert "licoes" not in rotinas.vencidas(cfg, agora + timedelta(minutes=59))
    assert "licoes" in rotinas.vencidas(cfg, agora + timedelta(minutes=61))
    assert "reuniao" in rotinas.vencidas(cfg, agora)  # nunca rodou: vence (a própria rotina decide se faz)
    e = {r["nome"]: r for r in rotinas.estado(cfg)}["dialogo"]
    assert e["proxima_verificacao"] and datetime.fromisoformat(e["proxima_verificacao"]) > agora


def teste_falha_fica_registrada_e_nao_repete_a_cada_volta(cfg_factory):
    cfg = _cfg(cfg_factory)

    def quebra():
        raise RuntimeError("falha de teste")
    rotinas.executar(cfg, "dialogo", quebra)
    assert rotinas.execucoes(cfg, "dialogo")[0]["status"] == "erro"
    assert "dialogo" not in rotinas.vencidas(cfg, datetime.now() + timedelta(minutes=5))


def teste_vencidas_nao_duplicam_o_laco_fixo(cfg_factory):
    cfg = _cfg(cfg_factory)
    v = rotinas.vencidas(cfg, excluir=nuvem.FORA_DAS_VENCIDAS)
    assert not set(v) & nuvem.FORA_DAS_VENCIDAS and len(v) == len(set(v))


def teste_turno_chama_a_rotina_vencida_dentro_do_laco(tmp_path, monkeypatch):
    """Relógio controlado: depois da 1ª volta o relógio das rotinas pula 21 min; na 2ª volta o diálogo vence e roda
    (uma vez, depois das demandas); a ronda de TI (30 min) ainda não."""
    desvio = {"min": 0}

    class Relogio(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(minutes=desvio["min"])
    monkeypatch.setattr(rotinas, "datetime", Relogio)
    ordem, voltas = [], {"n": 0}
    executar = rotinas.executar
    monkeypatch.setattr(rotinas, "executar", lambda cfg, nome, f: ordem.append(nome) or executar(cfg, nome, f))
    monkeypatch.setattr(rotinas, "funcao", lambda cfg, nome: (lambda: None))
    monkeypatch.setattr(nuvem, "restaurar", lambda cfg: {"origem": "teste"})
    monkeypatch.setattr(nuvem, "garantir_leitura", lambda cfg: True)
    monkeypatch.setattr(nuvem, "salvar", lambda cfg: {"ok": True})
    monkeypatch.setattr(nuvem, "tamanho_mb", lambda cfg: 1.0)
    monkeypatch.setattr(nuvem, "_esteira", lambda m: ordem.append("ESTEIRA") or 0)
    monkeypatch.setattr(nuvem, "garantir_base", lambda cfg, m: 0)
    monkeypatch.setattr(rotinas, "abrir_sessao", lambda cfg: {"sessao": 1})
    parar = threading.Event()

    def batimento(*a, **k):
        voltas["n"] += 1
        ordem.append(f"FIM_VOLTA_{voltas['n']}")
        desvio["min"] = 21
        if voltas["n"] == 2:
            parar.set()
    monkeypatch.setattr(rotinas, "batimento", batimento)
    cfg = nuvem.config_da_nuvem(tmp_path, "postgresql://u:p@127.0.0.1:1/x")
    nuvem.turno(cfg, minutos=5, pausa_s=0, parar=parar)
    v1 = ordem[ordem.index("canal"):ordem.index("FIM_VOLTA_1")]
    v2 = ordem[ordem.index("FIM_VOLTA_1") + 1:ordem.index("FIM_VOLTA_2")]
    assert "dialogo" not in v1  # acabou de rodar no começo do turno
    assert v2.count("dialogo") == 1 and "ronda_ti" not in v2
    assert v2.index("fabrica") < v2.index("ESTEIRA") < v2.index("demandas") < v2.index("dialogo")
    assert all(v2.count(n) == 1 for n in v2)  # nenhuma rotina duas vezes na mesma volta
