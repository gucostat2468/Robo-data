import json
import math

import numpy as np
import pandas as pd
import pytest
from openpyxl import Workbook

from robo.analise import Analise, analisar, calcular_indicador, chave_base, holm
from robo.pipeline import SUCESSO, processar_arquivo


def base_nps(n=600, semente=7, medicina_ruim=True):
    rng = np.random.default_rng(semente)
    cursos = rng.choice(["Direito", "Psicologia", "Administração", "Medicina"], n)
    notas = rng.choice(range(11), n, p=[.02, .02, .02, .03, .03, .05, .08, .1, .15, .2, .3])
    if medicina_ruim:  # Medicina tem NPS realmente pior
        ruins = (cursos == "Medicina") & (rng.random(n) < .5)
        notas = np.where(ruins, rng.choice(range(0, 6), n), notas)
    atendimento = np.clip(notas * 0.5 + rng.normal(0, 1, n), 0, 5).round(1)  # atributo correlacionado (driver)
    return pd.DataFrame({
        "id_resposta": [str(i) for i in range(n)],
        "data_resposta": pd.to_datetime("2026-09-01") + pd.to_timedelta(rng.integers(0, 30, n), unit="D"),
        "nota_nps": pd.array(notas, dtype="Int64"),
        "curso": cursos,
        "uf": rng.choice(["SP", "RJ", "MG", "AC"], n, p=[.45, .3, .23, .02]),
        "nota_atendimento": atendimento,
        "comentario": ["texto livre de exemplo bem longo para o teste número " + str(i) for i in range(n)],
    })


def nova_analise(df, **cfg):
    return Analise(df, "dados", "nps_setembro.xlsx", "nps", cfg, ["id", "id_*", "*_id"])


def teste_papeis_e_deteccao_de_indicador():
    a = nova_analise(base_nps())
    assert a.papeis["id_resposta"] == "id" and a.papeis["data_resposta"] == "data"
    assert a.papeis["curso"] == "categoria" and a.papeis["comentario"] == "texto_livre"
    assert a.indicadores_cols == {"nps": "nota_nps"}
    assert set(a.segmentos) == {"curso", "uf"}


def teste_nps_e_margem_de_erro_conferem_com_a_formula():
    r = calcular_indicador("nps", pd.Series([10, 10, 9, 8, 7, 6, 0, 10]), 1.96)
    p, d = 4 / 8, 2 / 8
    assert r["valor"] == pytest.approx(25.0)
    assert r["margem"] == pytest.approx(100 * 1.96 * math.sqrt((p + d - (p - d) ** 2) / 8))
    csat = calcular_indicador("csat", pd.Series([5, 4, 3, 2, 5]), 1.96)
    assert csat["valor"] == pytest.approx(60.0)


def teste_estatistica_acha_o_efeito_real_e_nao_inventa_diferencas():
    a = nova_analise(base_nps())
    a.fazer_indicadores(); a.fazer_estatistica()
    sig = a.destaques[a.destaques["significativo"]]
    assert ("curso", "Medicina") in set(zip(sig["segmento_coluna"], sig["segmento"]))
    assert (sig.loc[sig["segmento"] == "Medicina", "diferenca"] < 0).all()
    # UF não tem efeito nos dados: nenhuma UF pode aparecer como diferença real
    assert not (sig["segmento_coluna"] == "uf").any()
    # AC tem base pequena: não entra nos testes e aparece sinalizada nos indicadores
    assert "AC" not in set(a.destaques["segmento"])
    assert a.indicadores.loc[a.indicadores["segmento"] == "AC", "base_pequena"].all()
    # driver: nota de atendimento correlacionada com o NPS
    assert ((a.relacoes["variavel_a"] == "nota_nps") | (a.relacoes["variavel_b"] == "nota_nps")).any()


def teste_sem_efeito_nenhum_destaque_falso():
    a = nova_analise(base_nps(medicina_ruim=False, semente=11))
    a.fazer_indicadores(); a.fazer_estatistica()
    assert not a.destaques["significativo"].any()


def teste_holm():
    assert holm([0.001, 0.04, 0.03], 0.05) == [True, False, False]
    assert holm([0.01, 0.02, 0.03], 0.05) == [True, True, True]


def teste_monitoramento_compara_com_cargas_anteriores():
    ant = nova_analise(base_nps(semente=1))
    foto = ant.tirar_foto()
    nova = base_nps(n=250, semente=2).drop(columns=["nota_atendimento"])
    nova.loc[:9, "curso"] = "Medicna"  # erro de digitação = categoria inédita
    a = nova_analise(nova)
    a.fazer_monitoramento([foto])
    tipos = set(a.alertas["tipo"])
    assert {"volume", "coluna sumiu", "categoria inédita", "indicador"} <= tipos
    assert any("Medicna" in m for m in a.alertas["mensagem"])


def teste_chave_base_agrupa_ondas():
    assert chave_base("nps_outubro.xlsx", {}) == chave_base("NPS Setembro 2026.xlsx", {}) == "nps"
    assert chave_base("vendas_2026_09.csv", {}) == "vendas"
    assert chave_base("pesquisa_csat_outubro.xlsx", {"padrao": "pesquisa_csat_*"}) == "pesquisa_csat"
    # a mesma regra não junta pesquisas diferentes (achado da auditoria: alunos e professores viravam 'nps')
    assert chave_base("nps_pesquisa_alunos.xlsx", {"padrao": "nps_*"}) != chave_base("nps_pesquisa_professores.xlsx", {"padrao": "nps_*"})


def _salvar_xlsx(df, caminho):
    wb = Workbook()
    ws = wb.active
    ws.append(list(df.columns))
    for linha in df.astype(object).itertuples(index=False):
        ws.append([v.to_pydatetime() if isinstance(v, pd.Timestamp) else (None if pd.isna(v) else v) for v in linha])
    wb.save(caminho)


def teste_pipeline_gera_analise_e_nunca_reprova(pastas, cfg_factory, monkeypatch):
    cfg = cfg_factory()
    arq = pastas / "Bases-Limpeza" / "nps_setembro.xlsx"
    _salvar_xlsx(base_nps(), arq)
    etapas = []
    r = processar_arquivo(arq, cfg, ao_etapa=lambda e, a, **k: etapas.append(e))
    assert r.status == SUCESSO
    assert (cfg.relatorios / "nps_analise.xlsx").exists()
    abas = pd.read_excel(cfg.relatorios / "nps_analise.xlsx", sheet_name=None)
    assert {"resumo", "perfil", "indicadores", "destaques"} <= set(abas)
    assert any("NPS:" in l for l in abas["resumo"]["resumo_executivo"])
    assert [e for e in etapas if e.startswith("analise:")] == [
        "analise:perfil", "analise:indicadores", "analise:estatistica", "analise:monitoramento", "analise:relator"]
    assert json.loads((cfg.logs / "analises" / f"{r.id}.json").read_text(encoding="utf-8"))["indicadores_detectados"]

    # um analista quebrado não afeta a publicação
    import robo.analise as mod
    monkeypatch.setattr(mod.Analise, "fazer_estatistica", lambda self: 1 / 0)
    arq2 = pastas / "Bases-Limpeza" / "nps_outubro.xlsx"
    _salvar_xlsx(base_nps(semente=3), arq2)
    r2 = processar_arquivo(arq2, cfg)
    assert r2.status == SUCESSO
    assert any("não conseguiu concluir" in l for l in r2.analise["resumo"])
    # e a segunda onda já é comparada com a primeira
    alertas = pd.read_excel(cfg.relatorios / "nps_analise.xlsx", sheet_name="alertas")
    assert (alertas["tipo"] == "indicador").any()


def teste_analise_pode_ser_desligada(pastas, cfg_factory):
    cfg = cfg_factory(analise={"habilitado": False})
    arq = pastas / "Bases-Limpeza" / "nps_x.xlsx"
    _salvar_xlsx(base_nps(n=50), arq)
    r = processar_arquivo(arq, cfg)
    assert r.status == SUCESSO and r.analise is None
