"""Inteligência própria (robo/modelos_ml.py): modelo treinado de verdade, avaliado por outra pessoa e governado.

O que precisa ser verdade sempre:
  - modelo só é aprovado se bater o baseline no teste temporal, for reprodutível e conferir por outro caminho;
  - quem treina não avalia; quem treina ou aprova não promove; modelo adulterado não é usado;
  - atributos só com o passado (sem vazamento) e o teste é sempre o período mais novo;
  - a sombra só pontua demandas que nasceram depois do dataset do modelo; nada da empresa usa o número;
  - tudo fica em tabelas só de inclusão (nem apagar nem alterar), espelhadas no PostgreSQL pela cópia da memória.
"""

import json
import random
import sqlite3

import pytest

from robo import demandas, ferramentas
from robo import modelos_ml as ml
from robo.trabalho import Trabalho

GENTE = ["dba", "ci_pleno", "cd_senior_drivers", "head_ciencia", "eng_pleno", "bi_powerbi"]
FERRS = ["drivers", "calcular", "perfil_indicadores", "diagnosticar_planilha"]


def _cfg(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    Trabalho(cfg)
    return cfg


def _demandas(cfg, n=600, sinal=True, semente=3, dia0=1, prefixo="S"):
    """Demandas fechadas num banco de TESTE isolado. Com sinal: uma pessoa falha quase sempre (efeito que o baseline
    por ferramenta × nível não enxerga e o histórico da pessoa enxerga). Sem sinal: rótulo é moeda."""
    rng = random.Random(semente)
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        for i in range(n):
            pid, f = rng.choice(GENTE), rng.choice(FERRS)
            nv = rng.choice(["basico", "medio", "dificil", "profissional"])
            p = (0.1 + 0.25 * (nv in ("dificil", "profissional")) + 0.7 * (pid == "eng_pleno")) if sinal else 0.4
            dia, hora = dia0 + i // 40, (i % 40) // 2
            c.execute("INSERT INTO solicitacoes (id, tipo, origem, estado, funcionario, andar, modelo, plano, criada_em, "
                      "atualizada_em) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (f"{prefixo}{i:04d}", "demanda", "demanda_sintetica", "falhou" if rng.random() < p else "concluida",
                       pid, 1, f"demanda:{f}", json.dumps({"nivel": nv, "etapas": 2}),
                       f"2026-{dia // 28 + 1:02d}-{dia % 28 + 1:02d}T{hora:02d}:00:00",
                       f"2026-{dia // 28 + 1:02d}-{dia % 28 + 1:02d}T{hora:02d}:30:00"))


def teste_ciclo_completo_treina_avalia_promove_e_pontua_em_sombra(cfg_factory):
    cfg = _cfg(cfg_factory)
    _demandas(cfg)
    t = ml.treinar(cfg)
    assert t["ok"] and ml.estado_de(cfg, t["modelo"]) == "candidato"
    a = ml.avaliar(cfg)
    assert a["aprovado"], a["motivos"]
    assert a["candidato"]["log_loss"] < a["baseline"]["log_loss"] and a["reprodutivel"]
    assert a["auc_por_pares"] == pytest.approx(a["candidato"]["auc"])
    assert ml.promover(cfg)["ok"] and ml.referencia(cfg) == t["modelo"]
    assert ml.pontuar_em_sombra(cfg)["pontuadas"] == 0  # nada nasceu depois do dataset: não pontua o próprio treino
    _demandas(cfg, n=40, dia0=60, prefixo="N")  # demandas novas
    s = ml.pontuar_em_sombra(cfg)
    assert s["pontuadas"] == 40
    mo = ml.monitorar(cfg)
    assert mo["fechadas"] == 40 and mo["situacao"] in ("estavel", "degradou") and "real" in mo
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        assert c.execute("SELECT COUNT(*) FROM ml_inferencias WHERE modo='sombra'").fetchone()[0] == 40
    assert "dono" in ml.resumo(cfg)["uso_operacional"]  # nenhuma decisão usa o modelo sem o dono


def teste_modelo_sem_sinal_e_reprovado_e_nao_promove(cfg_factory):
    cfg = _cfg(cfg_factory)
    _demandas(cfg, sinal=False)
    t = ml.treinar(cfg)
    a = ml.avaliar(cfg)
    assert not a["aprovado"] and a["motivos"]
    assert ml.estado_de(cfg, t["modelo"]) == "reprovado"
    assert ml.promover(cfg) == {"ok": False, "motivo": "nenhum modelo aprovado esperando promoção"}
    with pytest.raises(ml.ErroGovernanca, match="só modelo aprovado"):
        ml.promover(cfg, t["modelo"])
    assert ml.referencia(cfg) is None


def teste_ninguem_aprova_o_proprio_trabalho(cfg_factory):
    cfg = _cfg(cfg_factory)
    _demandas(cfg)
    t = ml.treinar(cfg, quem="ml_engenheiro")
    with pytest.raises(ml.ErroGovernanca, match="quem treina não avalia"):
        ml.avaliar(cfg, t["modelo"], quem="ml_engenheiro")
    ml.avaliar(cfg, t["modelo"], quem="ml_avaliador")
    with pytest.raises(ml.ErroGovernanca, match="a promoção é de outra pessoa"):
        ml.promover(cfg, t["modelo"], quem="ml_avaliador")
    with pytest.raises(ml.ErroGovernanca, match="a promoção é de outra pessoa"):
        ml.promover(cfg, t["modelo"], quem="ml_engenheiro")
    assert ml.promover(cfg, t["modelo"], quem="ml_mlops")["ok"]
    # e a demanda de avaliar nunca é montada para quem treinou
    assert isinstance(demandas._ml_para_avaliar(cfg, {"id": "ml_engenheiro"}), str)


def teste_artefato_ou_dataset_adulterado_nao_e_usado(cfg_factory):
    cfg = _cfg(cfg_factory)
    _demandas(cfg)
    t = ml.treinar(cfg)
    arq = cfg.logs / "ml" / "modelos" / f"{t['modelo']}.json"
    arq.write_text(arq.read_text(encoding="utf-8").replace('"vies":', '"vies": 0, "x":'), encoding="utf-8")
    with pytest.raises(ml.ErroGovernanca, match="checksum"):
        ml.carregar(cfg, t["modelo"])
    assert ml.conferir_artefatos(cfg)["problemas"]
    ds = cfg.logs / "ml" / "datasets" / f"{t['dataset']['id']}.json"
    d = json.loads(ds.read_text(encoding="utf-8"))
    d["linhas"][0][-1] = 1 - d["linhas"][0][-1]  # inverte um rótulo
    ds.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ml.ErroGovernanca, match="checksum"):
        ml.ler_dataset(cfg, t["dataset"]["id"])


def teste_sem_vazamento_e_corte_temporal(cfg_factory):
    cfg = _cfg(cfg_factory)
    _demandas(cfg, n=120)
    linhas = ml._linhas_rotuladas(cfg)
    primeira = linhas[0]
    assert primeira["hist_pessoa_n"] == 0 and primeira["hist_pessoa_taxa"] == 0.5  # sem passado = neutro
    # o rótulo de uma demanda nunca entra no próprio histórico (só o que FECHOU antes de ela nascer)
    for l in linhas[:40]:
        anteriores = [x for x in linhas if x["funcionario"] == l["funcionario"] and x["criada_em"] < l["criada_em"]]
        assert l["hist_pessoa_n"] <= len(anteriores)
    p = ml.dividir(linhas)
    assert max(x["criada_em"] for x in p["treino"]) <= min(x["criada_em"] for x in p["teste"])


def teste_dataset_versionado_e_idempotente(cfg_factory):
    cfg = _cfg(cfg_factory)
    _demandas(cfg)
    t1 = ml.treinar(cfg)
    t2 = ml.treinar(cfg)
    assert t2["repetido"] and t2["modelo"] == t1["modelo"]  # mesmos dados = mesmo dataset, sem candidato repetido
    assert isinstance(demandas._ml_para_treinar(cfg, {"id": "ml_engenheiro"}), str)  # e não vira demanda à toa


def teste_poucos_dados_nao_treina(cfg_factory):
    cfg = _cfg(cfg_factory)
    _demandas(cfg, n=20)
    t = ml.treinar(cfg)
    assert not t["ok"] and "exige" in t["motivo"]
    r = ferramentas.executar("ml_treinar", cfg, quem="ml_engenheiro")
    assert not r["ok"] and r["natureza"] == "limitacao"


def teste_rollback_volta_para_a_referencia_anterior(cfg_factory, monkeypatch):
    """Mecânica do rollback (o critério "bater a referência" tem teste próprio e aqui fica desligado)."""
    monkeypatch.setitem(ml.CRITERIOS, "precisa_bater_referencia", False)
    cfg = _cfg(cfg_factory)
    _demandas(cfg)
    v1 = ml.treinar(cfg)["modelo"]
    ml.avaliar(cfg)
    ml.promover(cfg)
    assert ml.rollback(cfg, "teste")["ok"] is False  # a 1ª referência não tem anterior
    _demandas(cfg, n=200, semente=9, dia0=20, prefixo="T")
    v2 = ml.treinar(cfg)["modelo"]
    assert ml.avaliar(cfg)["aprovado"]
    ml.promover(cfg)
    assert ml.referencia(cfg) == v2 and ml.estado_de(cfg, v1) == "substituido"
    r = ml.rollback(cfg, "degradou em sombra")
    assert r == {"ok": True, "saiu": v2, "voltou": v1} and ml.referencia(cfg) == v1


def teste_registros_de_ml_sao_permanentes(cfg_factory):
    cfg = _cfg(cfg_factory)
    _demandas(cfg)
    t = ml.treinar(cfg)
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        with pytest.raises(sqlite3.DatabaseError):
            c.execute("UPDATE ml_modelos SET checksum='x' WHERE id=?", (t["modelo"],))
        with pytest.raises(sqlite3.DatabaseError):
            c.execute("DELETE FROM ml_modelos_eventos")


def teste_ferramentas_da_equipe_rodam_com_contrato(cfg_factory):
    from robo import organizacao
    cfg = _cfg(cfg_factory)
    _demandas(cfg)
    for pid, f in (("ml_lider", "ml_portfolio"), ("ml_engenheiro", "ml_treinar"), ("ml_avaliador", "ml_avaliar"),
                   ("ml_mlops", "ml_registro")):
        assert organizacao.pode_usar(pid, f, cfg)
        r = ferramentas.executar(f, cfg, quem=pid)
        assert r["ok"] and r["evidencia"], (f, r["texto"])
    assert ml.referencia(cfg)  # treinado, avaliado e promovido por três pessoas diferentes
    quem = {e["evento"]: e["quem"] for e in ml.eventos(cfg)}
    assert len({quem["candidato"], quem["avaliado_aprovado"], quem["promovido"]}) == 3


def teste_candidato_que_nao_bate_a_referencia_e_reprovado(cfg_factory, monkeypatch):
    """Um candidato pior que a referência atual (aqui: pesos zerados, sempre 50%) nunca a substitui."""
    cfg = _cfg(cfg_factory)
    _demandas(cfg)
    v1 = ml.treinar(cfg)["modelo"]
    ml.avaliar(cfg)
    ml.promover(cfg)
    _demandas(cfg, n=100, semente=5, dia0=20, prefixo="R")
    original = ml.logistica_treinar

    def fraco(treino, lam):
        m = original(treino, lam)
        return {**m, "pesos": [0.0] * len(m["pesos"]), "vies": 0.0}
    monkeypatch.setattr(ml, "logistica_treinar", fraco)
    v2 = ml.treinar(cfg)["modelo"]
    a = ml.avaliar(cfg)
    assert not a["aprovado"] and any("referência atual" in m for m in a["motivos"])
    assert ml.referencia(cfg) == v1 and ml.estado_de(cfg, v2) == "reprovado"
