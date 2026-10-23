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
    assert boletim.ler_mensagem(msg) == dados
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
