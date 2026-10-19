"""Quem faz o quê: todo mundo do organograma aparece, com o último trabalho REGISTRADO — nada inventado."""

from datetime import datetime, timedelta

from robo import atividade_equipe, organizacao
from robo.trabalho import Trabalho


def _semear(cfg, agora):
    from robo import interacoes, rotinas, treino
    treino._tb(cfg)
    interacoes._tb(cfg)
    rotinas._tb(cfg)
    h = lambda horas: (agora - timedelta(hours=horas)).isoformat(timespec="seconds")  # noqa: E731
    with Trabalho(cfg).tx() as c:
        c.execute("INSERT INTO treino_tentativas (data_hora, funcionario, competencia, nivel, acertou) VALUES (?,?,?,?,?)",
                  (h(30), "recepcao", "sql", 2, 1))
        c.execute("INSERT INTO treino_tentativas (data_hora, funcionario, competencia, nivel, acertou) VALUES (?,?,?,?,?)",
                  (h(0.5), "recepcao", "sql", 3, 0))
        c.execute("INSERT INTO interacoes (data_hora, de, para, tipo, texto) VALUES (?,?,?,?,?)",
                  (h(5), "dba", "recepcao", "mentoria", "Vamos rever a consulta juntas"))
        c.execute("INSERT INTO treino_tentativas (data_hora, funcionario, competencia, nivel, acertou) VALUES (?,?,?,?,?)",
                  (h(40), "limpeza", "sql", 1, 1))
        c.execute("INSERT INTO rotinas_execucoes (nome, inicio, fim, segundos, status, detalhe) VALUES (?,?,?,?,?,?)",
                  ("backup", h(1), h(1), 2.0, "fez", ""))


def teste_todos_aparecem_e_ultimo_trabalho_e_o_mais_recente(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    agora = datetime.now()
    _semear(cfg, agora)
    q = atividade_equipe.quadro(cfg, agora)
    pessoas = {p["id"]: p for p in q["pessoas"]}
    assert set(pessoas) == {p["id"] for p in organizacao.lista(cfg)}
    rec = pessoas["recepcao"]
    assert rec["situacao"] == "trabalhando" and "errou" in rec["ultimo"]["o_que"] and rec["em_24h"] == 1
    # o backup é responsabilidade da DBA: a rotina (1 h atrás) é mais nova que a conversa dela (5 h atrás)
    assert pessoas["dba"]["ultimo"]["fonte"] == "rotinas_execucoes" and pessoas["dba"]["situacao"] == "trabalhando"
    assert pessoas["limpeza"]["situacao"] == "ocioso"
    parados = {p["id"] for p in q["parados"]}
    assert "limpeza" in parados and "recepcao" not in parados
    assert sum(a["pessoas"] for a in q["andares"]) == len(pessoas)
    assert all(p["escopo"] for p in q["pessoas"] if p["id"] in ("recepcao", "bi_powerbi", "airflow_pleno"))


def teste_banco_vazio_ninguem_tem_trabalho_inventado(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    q = atividade_equipe.quadro(cfg)
    assert q["pessoas"] and all(p["ultimo"] is None and p["situacao"] == "sem_registro" and p["em_24h"] == 0
                                for p in q["pessoas"])
    assert len(q["parados"]) == len(q["pessoas"])


def teste_ronda_de_ti_conta_como_trabalho_do_5o_andar(cfg_factory):
    from robo import ti
    cfg = cfg_factory()
    cfg.criar_pastas()
    ti._salvar_estado(cfg, {"ultima_ronda": {"data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "itens": [
        {"id": "infra_pleno", "ok": False, "achados": ["Disco com 1 GB livre"]}]}})
    p = {x["id"]: x for x in atividade_equipe.quadro(cfg)["pessoas"]}["infra_pleno"]
    assert p["situacao"] == "trabalhando" and "Ronda de TI" in p["ultimo"]["o_que"] and "Disco com 1 GB" in p["ultimo"]["o_que"]


def teste_api(cfg_factory):
    from robo.painel.servidor import ROTAS_GET
    assert "/api/quem-faz-o-que" in ROTAS_GET
