"""Espelho do painel (robo/painel_espelho.py): as mesmas respostas da API do painel, sem segredo, num ramo próprio.

O app do celular serve o painel original e lê estes arquivos no lugar do servidor do computador.
"""

import json
import subprocess

from robo import jobs
from robo import painel_espelho as pe


def _git(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout


def teste_chave_igual_a_do_app():
    assert pe.chave("/api/escritorio") == "escritorio"
    assert pe.chave("/api/reuniao/ao-vivo") == "reuniao_ao-vivo"
    assert pe.chave("/api/funcionario", {"id": "cd_senior_drivers"}) == "funcionario__id=cd_senior_drivers"
    assert pe.chave("/api/x", {"b": "2", "a": "1 2"}) == "x__a=1_2&b=2"  # ordem fixa e caracteres seguros


def teste_espelho_tem_as_rotas_de_leitura_e_nada_sensivel(cfg_factory, tmp_path):
    cfg = cfg_factory()
    cfg.criar_pastas()
    jobs.fechar(cfg, jobs.abrir(cfg, "demanda", "sintetico", None, "dba"), "concluido", {})
    i = pe.escrever(cfg, tmp_path / "esp", "abc123")
    assert i["codigo_sha"] == "abc123" and not i["falhas"]
    for k in ("escritorio", "estado", "funcionarios", "central", "estrategia", "agentes", "canal", "gestao"):
        assert k in i["chaves"], k
    assert "funcionario__id=dba" in i["chaves"]  # a ficha de cada pessoa
    assert not {"config", "log", "celular_diagnostico", "acesso"} & set(i["chaves"])  # pastas, caminhos e IPs: fora
    esc = json.loads((tmp_path / "esp" / "api" / "escritorio.json").read_text(encoding="utf-8"))
    assert esc  # a mesma resposta que o escritório 3D recebe do servidor


def teste_segredo_nunca_vai_para_o_espelho(cfg_factory, tmp_path, monkeypatch):
    monkeypatch.setenv("ROBO_TELEGRAM_TOKEN", "123456789:AA" + "s" * 33)
    cfg = cfg_factory()
    bons, removidos = pe.limpar({"ok": {"a": 1}, "vaza": {"t": "token 123456789:AA" + "s" * 33}}, pe.segredos(cfg))
    assert list(bons) == ["ok"] and removidos == ["vaza"]


def teste_publica_um_commit_so_e_substitui(cfg_factory, tmp_path):
    cfg = cfg_factory()
    cfg.criar_pastas()
    origem = tmp_path / "github.git"
    _git("init", "-q", "--bare", str(origem), cwd=tmp_path)
    repo = tmp_path / "checkout"
    _git("clone", "-q", str(origem), str(repo), cwd=tmp_path)
    (repo / "x.txt").write_text("código\n")
    _git("add", ".", cwd=repo)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c", cwd=repo)
    _git("push", "-q", "origin", "HEAD:refs/heads/principal", cwd=repo)
    sha = _git("rev-parse", "HEAD", cwd=repo).strip()
    pasta = tmp_path / "espelho_git"
    assert pe.publicar(cfg, repo, pasta, forcar=True)
    assert pe.publicar(cfg, repo, pasta) is False  # dentro do intervalo: não publica de novo
    assert pe.publicar(cfg, repo, pasta, forcar=True)
    # o ramo é derivado: um commit só (o anterior é substituído), sem o código do projeto
    assert len(_git("log", "--oneline", pe.RAMO, cwd=origem).splitlines()) == 1
    arquivos = _git("ls-tree", "-r", "--name-only", pe.RAMO, cwd=origem).split()
    assert "indice.json" in arquivos and "api/escritorio.json" in arquivos and "x.txt" not in arquivos
    indice = json.loads(_git("show", f"{pe.RAMO}:indice.json", cwd=origem))
    assert indice["codigo_sha"] == sha  # o app carrega o painel exatamente desta versão do código
    assert "principal" in _git("branch", cwd=origem)
