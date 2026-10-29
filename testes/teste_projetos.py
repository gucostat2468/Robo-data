"""Projetos entre andares (robo/projetos.py): várias pessoas, dependências, a mesma base e revisão independente.

O que precisa ser verdade:
  - cada etapa é de uma pessoa diferente, da área certa, e ninguém do projeto é o revisor nem o dono;
  - todas as etapas usam a mesma base; o drivers leva o driver verdadeiro da fábrica como critério;
  - etapa que depende de outra que falhou fica bloqueada (não roda sobre resultado ruim);
  - o projeto passa pela revisão independente e conta como entrega quando aprovado;
  - no máximo um projeto por intervalo; sem base com NPS e atributos, não nasce (motivo registrado).
"""

import pytest

from robo import demandas, organizacao, orquestrador, projetos
from robo.trabalho import Trabalho


def _base(cfg_factory, linhas=1500):
    from robo import fabrica, pos_processamento
    from robo.monitor import Monitor
    cfg = cfg_factory(fabrica={"linhas_min": linhas, "linhas_max": linhas})
    cfg.criar_pastas()
    fabrica.produzir_lote(cfg, regra_id="nps", linhas=linhas, semente=11)
    Monitor(cfg, ao_processar=lambda r: pos_processamento.registrar(cfg, r)).ciclo(forcar=True)
    return cfg


def teste_plano_com_pessoas_diferentes_mesma_base_e_dependencias(cfg_factory):
    cfg = _base(cfg_factory)
    p = projetos.montar(cfg)
    assert not isinstance(p, str), p
    quem = [e["funcionario"] for e in p["etapas"]]
    assert len(quem) == len(set(quem)) >= 4  # uma pessoa por etapa
    assert p["revisor"] not in quem and projetos.DONO_DO_PROJETO not in quem
    gente = organizacao.por_id(cfg)
    assert len({gente[q]["andar"] for q in quem}) >= 3  # passa por vários andares
    arquivos = {e["parametros"]["arquivo"] for e in p["etapas"] if e["ferramenta"] not in ("resumo_executivo",
                                                                                          "diagnosticar_planilha")}
    assert arquivos == {p["base"]}
    dr = next(i for i, e in enumerate(p["etapas"], 1) if e["ferramenta"] == "drivers")
    assert {"tipo": "primeiro_driver", "esperado": "nota_conteudo"} in p["criterios_por_etapa"][str(dr)]
    assert p["etapas"][-1]["ferramenta"] == "resumo_executivo" and len(p["etapas"][-1]["depende"]) >= 2


def teste_projeto_executa_revisa_e_conta_como_entrega(cfg_factory):
    cfg = _base(cfg_factory)
    r = projetos.ciclo(cfg, intervalo_horas=1, por_ciclo=1)
    assert r["projeto"], r
    s = Trabalho(cfg).solicitacao(r["projeto"])
    assert r["estado"] in ("concluida", "concluida_parcialmente", "falhou")
    assert all(e["estado"] in ("concluida", "falhou", "bloqueada") for e in s["etapas"])
    assert s["revisor"] not in {e["funcionario"] for e in s["etapas"]}
    assert s["plano"]["tipo_demanda"] == "projeto"
    assert projetos.resumo(cfg)[0]["id"] == r["projeto"]
    assert projetos.ciclo(cfg, intervalo_horas=1, por_ciclo=1) is None  # com intervalo (freio): espera


def teste_etapa_que_depende_de_falha_fica_bloqueada(cfg_factory, monkeypatch):
    cfg = _base(cfg_factory)
    from robo import ferramentas
    original = ferramentas.executar

    def falha_perfil(nome, cfg_, **kw):
        if nome == "perfil_indicadores":
            return ferramentas.resultado(False, "limitacao", "falha de teste no perfil")
        return original(nome, cfg_, **kw)
    monkeypatch.setattr(ferramentas, "executar", falha_perfil)
    sid, _ = projetos.criar(cfg)
    orquestrador.executar(cfg, sid)
    et = {e["ferramenta"]: e["estado"] for e in Trabalho(cfg).solicitacao(sid)["etapas"]}
    assert et["perfil_indicadores"] == "falhou"
    assert et["drivers"] == "bloqueada" and et["resumo_executivo"] == "bloqueada"  # não rodaram sobre resultado ruim
    assert et["dados_pessoais"] == "concluida"  # não depende do perfil


def teste_sem_base_nao_nasce_projeto(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    r = projetos.ciclo(cfg)
    assert r["projeto"] is None and "sem base" in r["motivo"]


def teste_ciclo_de_demandas_cria_o_projeto(cfg_factory):
    cfg = _base(cfg_factory)
    cfg.dados["demandas"] = {"intervalo_minutos": 0, "por_ciclo": 2, "por_dia": 500}
    r = demandas.rotina(cfg)
    assert r["projeto"] and r["projeto"]["projeto"]


def teste_ciclo_faz_dois_tipos_sem_repetir_pessoa(cfg_factory):
    """Pedido do dono: mais trabalho, sem espera entre projetos. Um ciclo faz NPS e segmentação, e ninguém está em
    dois projetos ao mesmo tempo."""
    cfg = _base(cfg_factory)
    r = projetos.ciclo(cfg, intervalo_horas=0, por_ciclo=2)
    assert {p["tipo"] for p in r["projetos"]} == {"nps", "segmentacao"}, r
    t = Trabalho(cfg)
    pessoas = [e["funcionario"] for p in r["projetos"] for e in t.solicitacao(p["projeto"])["etapas"]]
    assert len(pessoas) == len(set(pessoas))
    seg = next(p for p in r["projetos"] if p["tipo"] == "segmentacao")
    ferrs = [e["ferramenta"] for e in t.solicitacao(seg["projeto"])["etapas"]]
    assert "segmentacao" in ferrs and "anomalias" in ferrs and ferrs[-1] == "resumo_executivo"
    assert projetos.ciclo(cfg, intervalo_horas=0, por_ciclo=2)["projetos"]  # sem espera: o próximo ciclo já faz mais


def teste_projeto_aprovado_vira_pacote_de_entrega(cfg_factory):
    """A empresa usa o produto: projeto aprovado gera base tratada, indicadores e relatório, e o registro fica."""
    import sqlite3
    cfg = _base(cfg_factory)
    r = projetos.ciclo(cfg, intervalo_horas=0, por_ciclo=1)
    p = r["projetos"][0]
    if p["estado"] != "concluida":
        pytest.skip(f"projeto não aprovado neste sorteio: {p['estado']}")
    e = p["entrega"]
    assert e["ok"] and e["recomendacoes"]
    from pathlib import Path
    assert (Path(e["pasta"]) / "relatorio.html").exists()
    assert projetos.entregas(cfg)[0]["projeto"] == p["projeto"]
    with sqlite3.connect(cfg.logs / "trabalho.db") as c:
        with pytest.raises(sqlite3.DatabaseError):
            c.execute("DELETE FROM entregas")
