"""Canal offline: entende o dono, responde com dados reais, admite quando não sabe e faz sprint de 15 dias."""

from datetime import date, timedelta

from conftest import REGRA_NPS
from robo.canal import Canal, responder
from robo.pipeline import processar_arquivo


def teste_pergunta_de_excel_vai_para_o_especialista(cfg_factory):
    r = responder("Como faço uma tabela dinâmica?", cfg_factory())[0]
    assert r["autor"] == "excel_dinamicas" and "Inserir" in r["texto"]


def teste_status_usa_dados_reais(planilha_baguncada, cfg_factory):
    cfg = cfg_factory([REGRA_NPS])
    processar_arquivo(planilha_baguncada, cfg)
    r = responder("como está hoje?", cfg)[0]
    assert "1 arquivo(s) recebido(s), 1 aprovado(s)" in r["texto"]


def teste_nao_inventa(cfg_factory):
    assert responder("blorp fizz wazzle", cfg_factory())[0]["intencao"] == "nao_entendi"


def teste_calculo_amostral_exato(cfg_factory):
    assert "385" in responder("tamanho de amostra para margem de 5%", cfg_factory())[0]["texto"]
    assert "±4,9" in responder("qual a margem de erro com 400 respostas?", cfg_factory())[0]["texto"].replace(".", ",")


def teste_conversa_fica_registrada_e_filtra(cfg_factory):
    cfg = cfg_factory()
    c = Canal(cfg)
    c.perguntar("Ricardo, como faço PROCX?", "excel")
    assert len(c.listar(canal="excel")) == 2
    assert c.listar(autor="excel_supervisor")[0]["tipo"] == "resposta"
    assert c.listar(busca="procx") and not c.listar(canal="banco")


def teste_acontecimentos_e_sprint(planilha_baguncada, cfg_factory):
    cfg = cfg_factory([REGRA_NPS])
    processar_arquivo(planilha_baguncada, cfg)
    c = Canal(cfg)
    assert c.sincronizar() == 1
    assert c.sincronizar() == 0, "não posta o mesmo acontecimento duas vezes"
    assert any(m["autor"] == "publicacao" and "Publiquei" in m["texto"] for m in c.listar(canal="engenharia"))
    falas = c.publicar_sprint()
    autores = {m["autor"] for m in falas}
    assert {"recepcao", "validacao", "supervisor", "canal_iara", "canal_helena"} <= autores
    assert all(m["texto"].startswith("Sprint 1") for m in falas)


def teste_sprint_fechada_e_publicada_sozinha(planilha_baguncada, cfg_factory):
    cfg = cfg_factory([REGRA_NPS])
    c = Canal(cfg)
    e = c.estado()
    e["inicio_sprints"] = (date.today() - timedelta(days=16)).isoformat()
    c.salvar_estado(e)
    c.sincronizar()
    assert any(m["tipo"] == "sprint" and m["texto"].startswith("Sprint 1 (") and "parcial" not in m["texto"]
               for m in c.listar())


def teste_responde_pelo_manual_md(cfg_factory):
    cfg = cfg_factory()
    cfg.agentes.mkdir(parents=True, exist_ok=True)
    (cfg.agentes / "limpeza.md").write_text("# Manual da Lia\n\n## Remoção de linhas de total\nLinhas com Total na "
                                            "primeira coluna saem da base porque somariam duas vezes.\n", encoding="utf-8")
    r = responder("por que a remoção de linhas de total acontece?", cfg)[0]
    assert r["autor"] == "limpeza" and r["intencao"] == "manual"
