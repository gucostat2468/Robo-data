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


def teste_todos_aparecem_e_so_trabalho_real_conta(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    agora = datetime.now()
    _semear(cfg, agora)
    q = atividade_equipe.quadro(cfg, agora)
    pessoas = {p["id"]: p for p in q["pessoas"]}
    assert set(pessoas) == {p["id"] for p in organizacao.lista(cfg)}
    rec = pessoas["recepcao"]
    # treino há 30 min: trabalho real de hoje, mas sem job aberto agora NÃO é "trabalhando"
    assert rec["situacao"] == "ativo_hoje" and "errou" in rec["ultimo"]["o_que"] and rec["real_24h"] == 1
    # a rotina do backup (1 h atrás) é plantão: o último trabalho REAL da DBA é a conversa de 5 h atrás
    dba = pessoas["dba"]
    assert dba["ultimo"]["fonte"] == "interacoes" and dba["situacao"] == "ativo_hoje"
    assert dba["ultimo_plantao"]["fonte"] == "rotinas_execucoes"
    assert pessoas["limpeza"]["situacao"] == "ocioso"
    parados = {p["id"] for p in q["parados"]}
    assert "limpeza" in parados and "recepcao" not in parados
    assert sum(a["pessoas"] for a in q["andares"]) == len(pessoas)
    assert q["trabalho_real_agora"] == 0
    assert all(p["escopo"] for p in q["pessoas"] if p["id"] in ("recepcao", "bi_powerbi", "airflow_pleno"))


def teste_banco_vazio_ninguem_tem_trabalho_inventado(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    q = atividade_equipe.quadro(cfg)
    assert q["pessoas"] and all(p["ultimo"] is None and p["situacao"] == "sem_registro" and p["em_24h"] == 0
                                for p in q["pessoas"])
    assert len(q["parados"]) == len(q["pessoas"])


def teste_ronda_de_ti_e_plantao_nao_trabalho(cfg_factory):
    from robo import ti
    cfg = cfg_factory()
    cfg.criar_pastas()
    ti._salvar_estado(cfg, {"ultima_ronda": {"data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "itens": [
        {"id": "infra_pleno", "ok": False, "achados": ["Disco com 1 GB livre"]}]}})
    p = {x["id"]: x for x in atividade_equipe.quadro(cfg)["pessoas"]}["infra_pleno"]
    assert p["situacao"] == "plantao" and p["ultimo"] is None
    assert "Ronda de TI" in p["ultimo_plantao"]["o_que"]


def teste_forjar_trabalho_sem_job_nao_funciona(cfg_factory):
    """Registro automático recente (rotina, canal) não pode virar "trabalhando": só etapa de job aberta vale."""
    from robo import rotinas
    cfg = cfg_factory()
    cfg.criar_pastas()
    rotinas._tb(cfg)
    agora = datetime.now()
    with Trabalho(cfg).tx() as c:
        c.execute("INSERT INTO rotinas_execucoes (nome, inicio, fim, segundos, status, detalhe) VALUES (?,?,?,?,?,?)",
                  ("backup", agora.isoformat(timespec="seconds"), agora.isoformat(timespec="seconds"), 1.0, "fez", ""))
    q = atividade_equipe.quadro(cfg, agora)
    assert not [p for p in q["pessoas"] if p["situacao"] in ("trabalhando", "ativo_hoje")]


def teste_job_aberto_e_o_unico_trabalhando(cfg_factory):
    from robo import jobs
    cfg = cfg_factory()
    cfg.criar_pastas()
    jid = jobs.abrir(cfg, "planilha", "real", "vendas.xlsx", "recepcao")
    jobs.etapa(cfg, jid, "limpeza", "limpeza")
    q = {p["id"]: p for p in atividade_equipe.quadro(cfg)["pessoas"]}
    assert q["limpeza"]["situacao"] == "trabalhando" and q["limpeza"]["agora"]["arquivo"] == "vendas.xlsx"
    assert [p for p in q.values() if p["situacao"] == "trabalhando"] == [q["limpeza"]]
    jobs.fechar(cfg, jid, "concluido", {"linhas_saida": 10})
    q = {p["id"]: p for p in atividade_equipe.quadro(cfg)["pessoas"]}
    assert q["limpeza"]["situacao"] == "ativo_hoje" and q["limpeza"]["ultimo"]["fonte"] == "jobs_etapas"


def teste_api(cfg_factory):
    from robo.painel.servidor import ROTAS_GET
    assert "/api/quem-faz-o-que" in ROTAS_GET
