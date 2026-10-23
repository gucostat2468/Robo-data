"""Fábrica de Planilhas: lote sintético com gabarito entra na esteira, sai separado do real e é conferido."""

import json
import sqlite3

import pandas as pd
import pytest

from robo import fabrica, historico, leitura_bi, regras_negocio
from robo.monitor import Monitor


def _cfg(cfg_factory, **fab):
    cfg = cfg_factory(fabrica={"linhas_min": 300, "linhas_max": 400, "intervalo_minutos": 0, "fila_vazia_minutos": 0, **fab})
    cfg.criar_pastas()
    return cfg


def teste_catalogo_tem_regras_de_todas_as_areas():
    areas = {r.area for r in regras_negocio.REGRAS}
    assert len(regras_negocio.REGRAS) >= 12
    assert {"comercial", "marketing", "pesquisa", "rh", "financeiro", "operacoes", "educacao"} <= areas
    for r in regras_negocio.REGRAS:
        c = regras_negocio.caso(r, 50, 1)
        assert r.chave in c["rotulos"] and r.segmento in c["rotulos"] and r.metrica in c["rotulos"], r.id


def teste_lote_vai_para_a_subpasta_com_gabarito_e_prova_de_trabalho(cfg_factory):
    cfg = _cfg(cfg_factory)
    lote = fabrica.produzir_lote(cfg, "vendas", 300, 2, semente=3)
    destino = cfg.entrada / "sintetico" / lote["arquivo"]
    gab = json.loads((cfg.entrada / "sintetico" / lote["arquivo"].replace(".xlsx", ".gabarito.json")).read_text(encoding="utf-8"))
    assert lote["estado"] == "na_esteira" and destino.exists() and lote["arquivo"].startswith("TREINO_")
    assert gab["gabarito"]["linhas"] == 300 and gab["autor"] == "fab_gerador" and gab["revisor"] == "fab_revisor"
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    etapas = c.execute("SELECT etapa, funcionario, ok FROM jobs_etapas ORDER BY id").fetchall()
    c.close()
    assert etapas == [("gerar", "fab_gerador", 1), ("conferir_gabarito", "fab_conferente", 1), ("revisar_lote", "fab_revisor", 1)]


def teste_ponta_a_ponta_separado_do_real(cfg_factory):
    cfg = _cfg(cfg_factory)
    lote = fabrica.produzir_lote(cfg, "financeiro", 300, 3, semente=9)
    r = Monitor(cfg).ciclo(forcar=True)
    assert [x.status for x in r] == ["sucesso"]
    conf = fabrica.conferir_pendentes(cfg)
    assert conf[0]["estado"] == "conferido_ok", conf
    saida = list((cfg.tratadas / "_treino").glob("TREINO_financeiro*"))
    assert saida and not [p for p in cfg.tratadas.glob("*.xlsx")]            # nada na pasta real
    assert historico.ler(cfg.logs) == [] and len(historico.ler(cfg.logs, incluir_sinteticos=True)) == 1
    assert leitura_bi.planilhas_reais(cfg) == []                               # a Bárbara não trata como real
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    assert c.execute("SELECT origem FROM jobs WHERE tipo='planilha'").fetchone()[0] == "sintetico"
    c.close()
    assert lote["arquivo"] in saida[0].name or saida[0].name.startswith("TREINO_financeiro")


def teste_real_tem_prioridade(cfg_factory):
    cfg = _cfg(cfg_factory)
    pd.DataFrame({"id": range(1, 31), "regiao": ["Sul", "Norte"] * 15, "valor": range(30)}).to_excel(cfg.entrada / "real.xlsx", index=False)
    assert fabrica.rotina(cfg) is None                                         # fila real: a fábrica não gera
    assert not (cfg.entrada / "sintetico").exists() or not list((cfg.entrada / "sintetico").glob("*.xlsx"))
    fabrica.produzir_lote(cfg, "nps", 300, 1, semente=1)                       # mesmo com lote pronto na subpasta…
    r = Monitor(cfg).ciclo(forcar=True)
    assert [x.arquivo.name for x in r] == ["real.xlsx"]                        # …o real passa primeiro


def teste_um_lote_por_vez_e_teto_diario(cfg_factory):
    cfg = _cfg(cfg_factory, teto_por_dia=1)
    assert fabrica.rotina(cfg)["lote"]["estado"] == "na_esteira"
    assert fabrica.rotina(cfg) is None                                         # já tem lote na esteira
    Monitor(cfg).ciclo(forcar=True)
    r = fabrica.rotina(cfg)                                                     # confere, mas não passa do teto
    assert r and r["conferidos"] and "lote" not in r


def teste_tres_falhas_seguidas_param_a_fabrica(cfg_factory):
    cfg = _cfg(cfg_factory)
    with fabrica._tb(cfg).tx() as c:
        for _ in range(3):
            c.execute("INSERT INTO fabrica_lotes (data_hora, regra, estado) VALUES ('2026-01-01T00:00:00', 'x', 'esteira_reprovou')")
    assert "parada" in fabrica.rotina(cfg)


def teste_copia_exata_com_chave_de_negocio_e_removida(cfg_factory):
    """Achado da fábrica: 'Nota Fiscal' não era reconhecida como identificador e a cópia exata ficava na saída."""
    from robo.limpeza import _eh_identificador
    cfg = cfg_factory()
    padroes = cfg.dados["limpeza"]["padroes_identificador"]
    assert all(_eh_identificador(c, padroes) for c in ("nota_fiscal", "pedido", "titulo", "protocolo", "sku"))


def teste_sintetico_vai_so_para_os_schemas_de_treino():
    """Regra mudada em 23/10/2026 (cobertura do banco): a planilha sintética vai ao PostgreSQL, mas SÓ para laboratorio e
    treino. Nenhum schema de produção (bruto, tratado, analitico, analise, robo) pode aparecer no destino."""
    from robo.pipeline import cfg_de_treino

    class C:
        dados = {"banco": {"habilitado": True}}
        tratadas = erros = originais = relatorios = "/x"
    t = cfg_de_treino(C())
    b = t.dados["banco"]
    assert b["sintetico"] is True and str(t.tratadas).endswith("_treino")
    assert set(b["schemas"].values()) == {"laboratorio", "treino"}
    assert not set(b["schemas"].values()) & {"bruto", "tratado", "analitico", "analise", "robo"}


def teste_desligada_nao_faz_nada(cfg_factory):
    cfg = _cfg(cfg_factory, habilitada=False)
    assert fabrica.rotina(cfg) is None
