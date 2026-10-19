"""Vigia: se o robô cair, ele volta sozinho — e cada queda fica registrada."""

import sqlite3

import pytest

from robo import vigia
from robo.monitor import TravaInstancia


def teste_religa_quando_parado_e_registra(cfg_factory, monkeypatch):
    cfg = cfg_factory()
    cfg.criar_pastas()
    chamadas = []
    monkeypatch.setattr(vigia, "ligar_robo", lambda caminho=None: chamadas.append(caminho) or 4242)
    assert not vigia.robo_rodando(cfg)
    r = vigia.checar(cfg, "meu_config.yaml")
    assert r == {"situacao": "religou", "pid": 4242} and chamadas == ["meu_config.yaml"]
    assert vigia.eventos(cfg)[0]["evento"] == "religou"


def teste_rodando_sem_painel_registra_sem_matar_e_ok_nao_registra(cfg_factory, monkeypatch):
    cfg = cfg_factory()
    cfg.criar_pastas()
    monkeypatch.setattr(vigia, "ligar_robo", lambda caminho=None: pytest.fail("não pode ligar outro robô"))
    with TravaInstancia(cfg.logs):  # um robô rodando
        assert vigia.robo_rodando(cfg)
        monkeypatch.setattr("robo.painel.servidor.ja_rodando", lambda porta: False)
        assert vigia.checar(cfg)["situacao"] == "sem_resposta"
        monkeypatch.setattr("robo.painel.servidor.ja_rodando", lambda porta: True)
        assert vigia.checar(cfg)["situacao"] == "ok"
    assert [e["evento"] for e in vigia.eventos(cfg)] == ["sem_resposta"]  # o "ok" não enche o banco
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("UPDATE vigia_eventos SET evento='x'")
    c.close()


def teste_comando_do_app_usa_o_config_e_sem_janela():
    cmd = vigia._comando_app("c:/x/config.yaml")
    assert cmd[1:] == ["-m", "robo", "--config", "c:/x/config.yaml", "app", "--sem-janela"]


def teste_preparar_pc_ordem_dos_passos_e_para_no_obrigatorio(monkeypatch, tmp_path):
    from robo import preparar_pc
    lista = preparar_pc.passos("mem.db.gz", tem_senha_painel=False, windows=True)
    assert [a[0] for _, a, _ in lista] == ["instalar-banco", "importar-memoria", "senha", "celular",
                                           "liberar-banco-celular", "inicializacao", "vigia", "diagnostico"]
    monkeypatch.setenv("ROBO_PG_SUPER_SENHA", "x")
    chamados = []
    def principal(args):
        chamados.append(args[2] if args[0] == "--config" else args[0])
        return 1 if "celular" in args else 0      # o app do celular falha (obrigatório): para ali
    cfg = tmp_path / "config.yaml"
    cfg.write_text("painel:\n  senha_hash: x\n", encoding="utf-8")
    assert preparar_pc.preparar(principal, str(cfg), None) == 1
    assert chamados == ["instalar-banco", "celular"]   # com senha no painel não pede de novo; parou no que falhou
