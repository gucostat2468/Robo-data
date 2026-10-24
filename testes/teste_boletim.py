"""Boletim do celular (robo/boletim.py): só números dos registros, publicado num ramo próprio, sem segredo.

Usa um repositório git local no papel do GitHub: o turno publica, o app lê o arquivo do ramo painel-celular.
"""

import json
import subprocess

from robo import boletim, jobs


def _git(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


def teste_boletim_vazio_nao_inventa(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    b = boletim.montar(cfg)
    assert b["funcionarios"] >= 100 and b["ultimos"] == [] and b["agora"] == []
    assert all(a["demandas"] == 0 and a["treino"] == 0 for a in b["andares"])


def teste_boletim_conta_o_que_aconteceu(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    jid = jobs.abrir(cfg, "demanda", "sintetico", None, "dba")  # trabalho aberto agora
    b = boletim.montar(cfg)
    assert [x["tipo"] for x in b["agora"]] == ["demanda"] and b["totais"]["trabalhos_com_prova"] == 1
    jobs.fechar(cfg, jid, "concluido", {})
    assert boletim.montar(cfg)["agora"] == []


def teste_publica_no_ramo_proprio_com_historico(cfg_factory, tmp_path):
    cfg = cfg_factory()
    cfg.criar_pastas()
    origem = tmp_path / "github.git"
    _git("init", "-q", "--bare", str(origem), cwd=tmp_path)
    repo = tmp_path / "checkout"
    _git("clone", "-q", str(origem), str(repo), cwd=tmp_path)
    (repo / "x.txt").write_text("código do projeto\n")
    _git("add", ".", cwd=repo)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c", cwd=repo)
    _git("push", "-q", "origin", "HEAD:refs/heads/principal", cwd=repo)
    pasta = tmp_path / "boletim_git"
    assert boletim.publicar(cfg, repo, pasta, {"estado": "trabalhando"})
    jobs.abrir(cfg, "demanda", "sintetico", None, "dba")
    assert boletim.publicar(cfg, repo, pasta, {"estado": "trabalhando"})
    # o ramo tem só o boletim (nada do código) e guarda cada versão
    arquivos = _git("ls-tree", "-r", "--name-only", "painel-celular", cwd=origem).split()
    assert arquivos == ["README.md", "estado/estado.json"]
    assert len(_git("log", "--oneline", "painel-celular", cwd=origem).splitlines()) == 2
    dados = json.loads(_git("show", "painel-celular:estado/estado.json", cwd=origem))
    assert dados["turno"]["estado"] == "trabalhando" and len(dados["agora"]) == 1
    # a mensagem do commit carrega o mesmo boletim (é o que o app lê pelo conector)
    msg = _git("log", "-1", "--format=%B", "painel-celular", cwd=origem)
    assert boletim.ler_mensagem(msg) == {k: v for k, v in dados.items() if k != "pessoas"}  # a lista de pessoas fica só no arquivo
    assert len(dados["pessoas"]) >= 100 and all(x["situacao"] for x in dados["pessoas"])
    assert "principal" in _git("branch", cwd=origem)  # o ramo do código não foi tocado
    # um novo turno (pasta nova) continua o mesmo ramo, sem forçar
    assert boletim.publicar(cfg, repo, tmp_path / "outro_turno", {"estado": "pausa"})
    assert len(_git("log", "--oneline", "painel-celular", cwd=origem).splitlines()) == 3


def teste_boletim_sem_segredo(cfg_factory, monkeypatch):
    monkeypatch.setenv("ROBO_TELEGRAM_TOKEN", "123456789:AA" + "z" * 33)
    cfg = cfg_factory(banco={"habilitado": True, "senha": "naoPodeAparecer9"})
    cfg.criar_pastas()
    texto = json.dumps(boletim.montar(cfg))
    assert "naoPodeAparecer9" not in texto and "zzzz" not in texto


def teste_so_publica_quando_o_workflow_pede(monkeypatch):
    monkeypatch.delenv("ROBO_PUBLICAR_BOLETIM", raising=False)
    assert not boletim.ligado()
    monkeypatch.setenv("ROBO_PUBLICAR_BOLETIM", "1")
    assert boletim.ligado()


def teste_versao_para_navegador(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    jobs.abrir(cfg, "demanda", "sintetico", None, "dba")
    md = boletim.markdown(boletim.montar(cfg))
    assert md.startswith("# Empresa ao vivo") and "| Andar |" in md and "Trabalhando agora" in md
    assert boletim._hora("2026-10-23T23:19:41") == "23/10 20:19"  # UTC → Brasília


def teste_boletim_mostra_a_cobertura_real_das_tabelas(cfg_factory):
    """O dono (e a auditoria) vê no celular quais tabelas têm dados e a causa de cada vazia, do levantamento do turno."""
    from robo import cobertura_banco as cb
    cfg = cfg_factory()
    cfg.criar_pastas()
    assert boletim.montar(cfg)["banco"] == {}  # sem levantamento: não inventa cobertura
    jobs.fechar(cfg, jobs.abrir(cfg, "demanda", "sintetico", None, "dba"), "concluido", {})  # um trabalho real gravado
    cb.salvar_relatorio(cfg, cb.levantar(cfg))
    b = boletim.montar(cfg)["banco"]
    assert b["tabelas"] > 30 and 0 < b["com_dados"] < b["tabelas"]
    assert not b["postgres_conferido"]  # banco desligado neste teste: nunca dito como conferido
    vazia = {v["tabela"]: v for v in b["vazias"]}["solicitacoes"]
    assert vazia["onde"] == "sqlite" and vazia["situacao"] == "funcionalidade não acionada" and vazia["causa"]
    md = boletim.markdown(boletim.montar(cfg))
    assert "## Banco de dados" in md and "| sqlite | solicitacoes |" in md and "PostgreSQL NÃO conferido" in md
    leve = boletim.ler_mensagem(boletim.mensagem(boletim.montar(cfg)))
    assert "vazias" not in leve["banco"] and leve["banco"]["tabelas"] == b["tabelas"]  # a mensagem leva só o resumo


def teste_boletim_mede_acerto_por_nivel(cfg_factory):
    """Os níveis precisam ser trabalho diferente: o boletim mostra o acerto de cada nível, tirado das demandas reais."""
    import sqlite3
    cfg = cfg_factory()
    cfg.criar_pastas()
    boletim.montar(cfg)
    from robo.trabalho import Trabalho
    Trabalho(cfg)
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        for i, (nv, est) in enumerate([("basico", "concluida"), ("basico", "concluida"), ("dificil", "falhou"),
                                       ("dificil", "concluida"), ("medio", "concluida")]):
            c.execute("INSERT INTO solicitacoes (id, tipo, origem, estado, funcionario, andar, plano, criada_em) "
                      "VALUES (?,?,?,?,?,?,?,?)", (f"s{i}", "demanda", "demanda_sintetica", est, "dba", 1,
                                                   json.dumps({"nivel": nv}), "2026-10-24T10:00:00"))
        c.execute("INSERT INTO solicitacoes (id, tipo, origem, estado, funcionario, andar, plano, criada_em) VALUES "
                  "('t1','demanda','demanda_sintetica','concluida','dba',1,?, '2026-10-24T10:00:00')",
                  (json.dumps({"nivel": "basico", "tipo_demanda": "treinamento"}),))  # estudo não conta como nível
    n = {x["nivel"]: x for x in boletim.montar(cfg)["niveis"]}
    assert list(n) == ["basico", "medio", "dificil"]
    assert n["basico"]["demandas"] == 2 and n["dificil"]["falhas"] == 1 and n["dificil"]["concluidas"] == 1
    assert "| dificil | 2 | 1 | 0 | 1 | 50% |" in boletim.markdown(boletim.montar(cfg))
