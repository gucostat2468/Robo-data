"""Pacote de entrega (robo/entrega.py): a planilha vira base tratada, indicadores.xlsx e relatorio.html.

O que precisa ser verdade:
  - o arquivo original nunca muda e a entrega tem os três arquivos;
  - recomendação só sai do que os números sustentam (driver importante, grupo significativamente abaixo,
    transportadora significativamente pior); notas empatadas não viram "desempenho abaixo";
  - média de algo sem sentido conhecido (ex.: dias de atraso) não vira recomendação nem ganha cor de bom/ruim;
  - logística: % no prazo confere com a conta feita por outro caminho;
  - texto da base nunca vira HTML (nada de script no relatório).
"""

import hashlib
from pathlib import Path

import pandas as pd

from robo import entrega, fabrica


def _cfg(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    return cfg


def _lote(cfg, regra):
    lote = fabrica.produzir_lote(cfg, regra, 1500, 2, semente=7, injetar=False)
    return Path(cfg.logs) / "fabrica" / lote["arquivo"]


def teste_pesquisa_nps_vira_entrega_completa(cfg_factory, tmp_path):
    cfg = _cfg(cfg_factory)
    arq = _lote(cfg, "nps")
    antes = hashlib.sha256(arq.read_bytes()).hexdigest()
    r = entrega.entregar(cfg, arq, tmp_path / "saida")
    assert r["ok"] and set(r["arquivos"]) == {"base_tratada.xlsx", "indicadores.xlsx", "relatorio.html",
                                         "manifesto.json"}
    assert all(c["ok"] for c in r["conferencias"]), r["conferencias"]  # o certificado bate
    assert hashlib.sha256(arq.read_bytes()).hexdigest() == antes  # o original não muda
    pasta = Path(r["pasta"])
    h = (pasta / "relatorio.html").read_text(encoding="utf-8")
    assert "Recomendações" in h and "O que mais pesa na nota" in h and ">NPS<" in h and "nan" not in h.lower()
    abas = pd.ExcelFile(pasta / "indicadores.xlsx").sheet_names
    assert {"indicadores", "drivers", "qualidade"} <= set(abas)
    # o driver verdadeiro da fábrica (nota_conteudo) é a 1ª recomendação
    assert "nota_conteudo" in r["recomendacoes"][0]


def teste_prioridade_por_importancia_e_desempenho():
    df = pd.DataFrame({"a": [9, 9, 8, 9] * 10, "b": [3, 4, 3, 4] * 10, "c": [7, 8, 7, 8] * 10})
    drv = {"ok": True, "drivers": [{"atributo": "b", "correlacao": 0.6, "peso_pct": 50},
                                   {"atributo": "a", "correlacao": 0.5, "peso_pct": 40},
                                   {"atributo": "c", "correlacao": 0.1, "peso_pct": 10}]}
    p = {x["atributo"]: x["quadrante"] for x in entrega.prioridades(drv, df)}
    assert p["b"] == "Melhorar primeiro" and p["a"] == "Manter (é força)"
    # notas praticamente iguais: não inventa "desempenho abaixo"; só a importância conta
    iguais = pd.DataFrame({"a": [7.4] * 40, "b": [7.41] * 40})
    q = entrega.prioridades({"ok": True, "drivers": [{"atributo": "a", "correlacao": 0.5, "peso_pct": 60},
                                                      {"atributo": "b", "correlacao": 0.1, "peso_pct": 40}]}, iguais)
    assert {x["quadrante"] for x in q} == {"Mais importante", "Menor peso"}


def teste_logistica_confere_e_aponta_transportadora_pior(cfg_factory, tmp_path):
    cfg = _cfg(cfg_factory)
    r = entrega.entregar(cfg, _lote(cfg, "logistica"), tmp_path / "saida")
    assert r["ok"]
    base = pd.read_excel(Path(r["pasta"]) / "base_tratada.xlsx")
    col = next(c for c in base.columns if "atraso" in c)
    logi = entrega.logistica(base)
    validos = base[col].dropna()  # atraso vazio não conta nem como no prazo nem como atrasado
    assert logi["geral"]["n"] == len(validos)
    assert abs(logi["geral"]["pct_no_prazo"] - 100 * (validos <= 0).mean()) < 1e-9  # outro caminho, mesmo número
    assert any("Econômica" in x and "SLA" in x for x in r["recomendacoes"])  # a fábrica atrasa mais a Econômica
    # "média de atraso" menor NÃO vira "investigar" (menos atraso é melhor; o sentido não é o de um indicador)
    assert not any(x.startswith("Investigar") and "atraso" in x for x in r["recomendacoes"])


def teste_texto_da_base_nao_vira_html(cfg_factory, tmp_path):
    cfg = _cfg(cfg_factory)
    arq = tmp_path / "pesquisa.xlsx"
    pd.DataFrame({"id_resposta": range(80), "canal": ["<script>alert(1)</script>", "Loja"] * 40,
                  "nota_nps": [10, 9, 3, 8] * 20}).to_excel(arq, index=False)
    r = entrega.entregar(cfg, arq, tmp_path / "saida")
    h = (Path(r["pasta"]) / "relatorio.html").read_text(encoding="utf-8")
    assert "<script>" not in h and "&lt;script&gt;" in h


def teste_arquivo_ruim_gera_relatorio_que_explica(cfg_factory, tmp_path):
    cfg = _cfg(cfg_factory)
    r = entrega.entregar(cfg, tmp_path / "nao_existe.xlsx", tmp_path / "saida")
    assert not r["ok"] and r["erros"] and r["arquivos"] == ["relatorio.html", "manifesto.json"]
    assert "Corrigir a origem dos dados" in r["recomendacoes"][0]


def teste_numero_no_padrao_brasileiro():
    assert entrega._n(1234.5) == "1.234,5" and entrega._n(-0.04) == "0,0" and entrega._n(7.38, 0) == "7"


def teste_qualquer_planilha_da_fabrica_vira_entrega(cfg_factory, tmp_path):
    """As 15 regras da fábrica (vendas, financeiro, folha, estoque, churn...): limpeza, análise e relatório completos."""
    from robo import regras_negocio
    cfg = _cfg(cfg_factory)
    for regra in regras_negocio.catalogo(cfg):
        r = entrega.entregar(cfg, _lote(cfg, regra.id), tmp_path / "saida")
        assert r["ok"] and r["linhas"] > 1000 and r["recomendacoes"], regra.id
        h = (Path(r["pasta"]) / "relatorio.html").read_text(encoding="utf-8")
        assert "Visão geral da base" in h and "Limpeza e padronização feitas" in h, regra.id
        assert ">nan<" not in h.lower(), regra.id


def teste_vendas_usa_valor_como_metrica_principal_e_ignora_mes_incompleto(cfg_factory, tmp_path):
    import numpy as np
    cfg = _cfg(cfg_factory)
    rng = np.random.default_rng(1)
    datas = list(pd.date_range("2026-01-01", "2026-06-30", freq="D")) * 6 + list(pd.date_range("2026-07-01", "2026-07-03"))
    n = len(datas)
    arq = tmp_path / "vendas.xlsx"
    pd.DataFrame({"pedido": range(n), "regiao": rng.choice(["Sul", "Norte", "Sudeste"], n), "quantidade": rng.integers(1, 9, n),
                  "valor_da_venda": rng.uniform(100, 900, n).round(2), "data_da_venda": datas}).to_excel(arq, index=False)
    r = entrega.entregar(cfg, arq, tmp_path / "saida")
    h = (Path(r["pasta"]) / "relatorio.html").read_text(encoding="utf-8")
    assert "Total de valor_da_venda por regiao" in h
    assert "2026-07 parece incompleto" in h  # 3 dias de julho não viram "queda de 95%"
    assert not any("Queda no último mês (2026-07)" in x for x in r["recomendacoes"])
