"""Contratação automática e manual: só contrata com demanda comprovada, sempre em observação, e o prédio cresce."""

import pandas as pd
from openpyxl import Workbook

from robo import contratacao
from robo.canal import Canal
from robo.pipeline import SUCESSO, obter_equipe, processar_arquivo


def _planilha(pasta, nome, emails):
    wb = Workbook()
    ws = wb.active
    ws.append(["id_cliente", "nome", "email"])
    for i, e in enumerate(emails, 1):
        ws.append([i, f"Cliente {i}", e])
    caminho = pasta / nome
    wb.save(caminho)
    return caminho


def teste_contrata_estagiario_quando_ha_email_fora_do_padrao(pastas, cfg_factory):
    cfg = cfg_factory()
    sujos = ["Ana@Empresa.COM", "bruno@empresa.com", "carla.empresa.com", "Dani@Empresa.com", "edu@empresa.com", "fe@empresa.com"]
    r = processar_arquivo(_planilha(pastas / "Bases-Limpeza", "clientes_jan.xlsx", sujos), cfg)
    assert r.status == SUCESSO
    contratados = [a for a in obter_equipe(cfg).personalizados if a.get("contratado_por") == "automatico"]
    assert len(contratados) == 1
    a = contratados[0]
    assert a["nivel"] == "estagiario" and a["habilidades"][0]["habilidade"] == "validar_email"
    assert (cfg.agentes / f"{a['id']}.md").exists(), "todo contratado ganha manual"
    assert any(m["autor"] == "coord_engenharia" and "Contratei" in m["texto"] for m in Canal(cfg).listar(canal="rh"))
    # o dado publicado NÃO mudou (estagiário só observa)
    df = pd.read_excel(cfg.tratadas / "clientes_jan.xlsx")
    assert "Ana@Empresa.COM" in df["email"].tolist()


def teste_nao_contrata_sem_trabalho(pastas, cfg_factory):
    cfg = cfg_factory()
    limpos = [f"pessoa{i}@empresa.com" for i in range(8)]
    processar_arquivo(_planilha(pastas / "Bases-Limpeza", "clientes_fev.xlsx", limpos), cfg)
    assert not [a for a in obter_equipe(cfg).personalizados if a.get("contratado_por") == "automatico"]


def teste_lider_contrata_e_avalia_experiencia_de_3_meses(pastas, cfg_factory):
    from datetime import date, timedelta
    cfg = cfg_factory(contratacao_automatica={"observacoes_minimas": 2})
    sujos = ["Ana@Empresa.COM", "b@x.com", "c@x.com", "d@x.com", "e@x.com"]
    for mes in ("mar", "abr", "mai"):
        processar_arquivo(_planilha(pastas / "Bases-Limpeza", f"clientes_{mes}.xlsx", sujos), cfg)
    auto = [a for a in obter_equipe(cfg).personalizados if a.get("contratado_por") == "automatico"]
    assert len(auto) == 1, "não contrata duas vezes para a mesma necessidade"
    a = auto[0]
    assert a["contratante"] == "coord_engenharia"
    assert date.fromisoformat(a["fim_experiencia"]) - date.fromisoformat(a["contratado_em"]) == timedelta(days=90)
    assert contratacao.resumo(cfg)["observacoes"][a["id"]] == 2  # contratado no 1º arquivo, observou o 2º e o 3º
    assert contratacao.avaliar_experiencias(cfg) == [], "antes de 3 meses ninguém é avaliado"
    decisoes = contratacao.avaliar_experiencias(cfg, hoje=date.today() + timedelta(days=91))
    assert decisoes[0]["decisao"] == "efetivar"
    assert any(m["autor"] == "coord_engenharia" and "Recomendo efetivar" in m["texto"] for m in Canal(cfg).listar(canal="rh"))


def teste_estagiario_sem_trabalho_e_desligado_no_fim_da_experiencia(pastas, cfg_factory):
    from datetime import date, timedelta
    cfg = cfg_factory()
    processar_arquivo(_planilha(pastas / "Bases-Limpeza", "clientes_jun.xlsx", ["Ana@Empresa.COM", "b@x.com", "c@x.com",
                                                                                    "d@x.com", "e@x.com"]), cfg)
    decisoes = contratacao.avaliar_experiencias(cfg, hoje=date.today() + timedelta(days=91))
    assert decisoes[0]["decisao"] == "desligar"
    assert not [a for a in obter_equipe(cfg).personalizados if a.get("contratado_por") == "automatico"]


def teste_contratacao_manual_em_andar_novo(cfg_factory):
    cfg = cfg_factory()
    a = contratacao.contratar_manual(cfg, {"id": "carlos_cep", "nome": "Carlos", "papel": "CEP", "nivel": "junior",
                                           "andar": 5, "posicao": "limpeza", "cor": "#123456",
                                           "habilidades": [{"habilidade": "normalizar_cep", "parametros": {"colunas": ["cep"]},
                                                            "opcional": True}],
                                           "manual": "# Carlos\nCuida dos CEPs."})
    assert a["andar"] == 5
    equipe = obter_equipe(cfg)
    assert equipe.manual("carlos_cep").startswith("# Carlos")
    assert any("5º andar" in m["texto"] for m in Canal(cfg).listar(canal="rh"))
