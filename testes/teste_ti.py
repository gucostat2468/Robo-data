"""5º andar: a ronda de TI verifica a máquina e o programa de verdade."""

from robo import ti
from robo.canal import Canal


def teste_ronda_em_ambiente_saudavel(cfg_factory):
    cfg = cfg_factory(painel={"senha_hash": "pbkdf2_sha256$1$00$00"})  # saudável inclui painel com senha
    ti.ronda(cfg)  # 1ª ronda registra o código conhecido
    r = ti.ronda(cfg)
    assert r["saudavel"], r["itens"]
    assert {i["id"] for i in r["itens"]} == {p["id"] for p in ti.EQUIPE_TI if p["funcao"]}


def teste_painel_sem_senha_e_alerta_de_seguranca(cfg_factory):
    cfg = cfg_factory()
    assert any("painel está sem senha" in a for a in ti.chk_seguranca(cfg))


def teste_alerta_vai_para_o_canal_uma_vez(cfg_factory):
    cfg = cfg_factory(ti={"disco_minimo_gb": 10 ** 9, "disco_critico_gb": 10 ** 8})
    cfg.criar_pastas()
    assert not ti.ronda(cfg)["saudavel"]
    ti.ronda(cfg)
    alertas = [m for m in Canal(cfg).listar(canal="ti") if "CRÍTICO" in m["texto"]]
    assert len(alertas) == 1 and alertas[0]["autor"] == "infra_pleno"


def teste_codigo_novo_de_habilidade_e_vigiado(cfg_factory):
    cfg = cfg_factory()
    ti.ronda(cfg)
    cfg.habilidades.mkdir(parents=True, exist_ok=True)
    (cfg.habilidades / "estranha.py").write_text("x = 1\n", encoding="utf-8")
    r = ti.ronda(cfg)
    seg = next(i for i in r["itens"] if i["id"] == "sec_senior")
    assert any("estranha.py" in a for a in seg["achados"])
