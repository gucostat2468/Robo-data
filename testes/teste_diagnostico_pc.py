"""python -m robo diagnostico: confere o computador sem alterar nada e aponta como corrigir."""

from robo import diagnostico_pc
from robo.comandos import principal


def teste_diagnostico_aponta_painel_sem_senha_e_testa_a_trava(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    itens = {i["titulo"]: i for i in diagnostico_pc.rodar(cfg)}
    assert len(itens) == len(diagnostico_pc.VERIFICACOES)
    assert itens["Senha do painel"]["situacao"] == "falha" and "python -m robo senha" in itens["Senha do painel"]["corrigir"]
    assert itens["Trava entre programas"]["situacao"] == "ok"           # trava real entre dois processos
    assert itens["PostgreSQL"]["situacao"] == "nao_se_aplica"           # banco desligado: não inventa falha
    assert all(i["situacao"] in ("ok", "atencao", "falha", "nao_se_aplica") for i in itens.values())


def teste_comando_devolve_1_quando_ha_falha(cfg_factory, tmp_path, capsys):
    import yaml
    cfg = cfg_factory()
    cfg.criar_pastas()
    caminho = tmp_path / "config.yaml"
    caminho.write_text(yaml.safe_dump(cfg.dados, allow_unicode=True), encoding="utf-8")
    assert principal(["--config", str(caminho), "diagnostico"]) == 1
    assert "✘ Senha do painel" in capsys.readouterr().out
