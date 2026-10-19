"""Treino contínuo: todos trabalham em casos com gabarito, no próprio nível; nada se perde; a Sala de Casos tem governança."""

import sqlite3

import pandas as pd
import pytest

from robo import licoes, memoria, organizacao, treino
from robo.treino_casos import CATALOGO


@pytest.fixture
def cfg(cfg_factory):
    c = cfg_factory()
    c.criar_pastas()
    licoes.colher(c)  # o caderno da empresa (manuais) — base da competência de conhecimento
    return c


def _banco(cfg):
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    c.row_factory = sqlite3.Row
    return c


def teste_todo_funcionario_de_todo_andar_tem_o_que_treinar(cfg):
    eleg = treino.elegiveis(cfg)
    assert len(eleg) >= 84 and treino.EQUIPE_SALA <= {p["id"] for p in eleg}  # a Sala também treina (revisão de casos)
    assert {p["andar"] for p in eleg} == {1, 2, 3, 4, 5}
    sem = [p["id"] for p in eleg if not treino.competencias_de(p["id"], cfg)]
    assert sem == []
    assert "sql" not in treino.competencias_de("dba", cfg)  # sem PostgreSQL ligado, nada de caso de SQL


@pytest.mark.parametrize("comp", [c for c in CATALOGO if c != "sql"])
def teste_cada_competencia_cada_nivel_caso_valido_e_robo_acerta(cfg, comp):
    """Os 5 níveis de cada competência: a revisora aprova o caso e o robô acerta. Inclui as 5 lacunas reais que o
    próprio treino achou e que foram corrigidas (LGPD +55, CPF falso, e-mail no texto, 'dias_entrega', NPS com 99)."""
    quem = next(p["id"] for p in treino.elegiveis(cfg) if comp in treino.competencias_de(p["id"], cfg))
    for nivel in range(1, 6):
        caso = treino.criar_caso(cfg, comp, nivel, semente=1000 + nivel)
        assert caso["estado"] == "validado", (nivel, caso["revisao"]["problemas"])
        r = treino.tentar(cfg, quem, comp, caso, "TESTE")
        assert r["acertou"], (nivel, r["detalhe"])


def teste_nivel_sobe_com_4_de_5_e_desce_com_2_de_5_sempre_com_prova(cfg, monkeypatch):
    pid = "eng_estagiario"  # estagiário começa no nível 1
    assert treino.nivel_atual(cfg, pid, "historico") == 1
    for i in range(5):
        treino.tentar(cfg, pid, "historico", treino.criar_caso(cfg, "historico", 1, semente=50 + i), "T")
    assert treino.nivel_atual(cfg, pid, "historico") == 2
    monkeypatch.setattr(CATALOGO["historico"], "corrigir", lambda caso, r: (False, 0.0, "erro_de_teste", "forçado"))
    for i in range(5):
        treino.tentar(cfg, pid, "historico", treino.criar_caso(cfg, "historico", 2, semente=80 + i), "T")
    assert treino.nivel_atual(cfg, pid, "historico") == 1
    c = _banco(cfg)
    ev = [dict(r) for r in c.execute("SELECT de, para, evidencia FROM treino_niveis_eventos WHERE funcionario=? ORDER BY id", (pid,))]
    assert [(e["de"], e["para"]) for e in ev] == [(None, 1), (1, 2), (2, 1)]
    assert all(e["evidencia"].count("T") == 5 for e in ev[1:])  # cada mudança cita as 5 tentativas
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("UPDATE treino_tentativas SET acertou=1")  # tentativa não muda depois de gravada
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DELETE FROM treino_tentativas")
    c.close()


def teste_erro_vira_licao_da_pessoa_e_so_conta_quando_ela_acerta_depois(cfg, monkeypatch):
    pid = "ana_junior_faixas"
    original = CATALOGO["calculo"].corrigir
    monkeypatch.setattr(CATALOGO["calculo"], "corrigir", lambda caso, r: (False, 0.0, "numero_errado", "forçado"))
    treino.tentar(cfg, pid, "calculo", treino.criar_caso(cfg, "calculo", 1, semente=7), "T")
    c = _banco(cfg)
    lic = c.execute("SELECT l.id FROM licoes l WHERE l.origem_tipo='treino' AND l.origem_ref='calculo:1:numero_errado'").fetchone()
    donos = [r[0] for r in c.execute("SELECT funcionario FROM licoes_funcionario WHERE licao_id=?", (lic["id"],))]
    assert donos == [pid]  # a lição do erro é de quem errou
    licoes.rodada(cfg)
    estado = lambda: c.execute("SELECT estado FROM licoes_funcionario WHERE licao_id=?", (lic["id"],)).fetchone()[0]  # noqa: E731
    assert estado() != "aplicada"
    monkeypatch.setattr(CATALOGO["calculo"], "corrigir", original)
    assert treino.tentar(cfg, pid, "calculo", treino.criar_caso(cfg, "calculo", 1, semente=8), "T")["acertou"]
    licoes.rodada(cfg)
    assert estado() == "aplicada"
    c.close()


def teste_erro_que_se_repete_vira_handover_para_a_area_dona(cfg, monkeypatch):
    monkeypatch.setattr(CATALOGO["lgpd"], "corrigir", lambda caso, r: (False, 0.0, "deixou_dado_pessoal_passar", "forçado"))
    for i, pid in enumerate(["canal_iara", "gov_pleno_lgpd", "rh_rs"]):
        treino.tentar(cfg, pid, "lgpd", treino.criar_caso(cfg, "lgpd", 2, semente=30 + i), "T")
    h = [x for x in memoria.handovers(cfg) if "Treino: Achar dado pessoal" in x["erro"]]
    assert len(h) == 1 and h[0]["responsavel"] == organizacao.ENCAMINHAR["dados_pessoais"]  # um por tipo de erro
    assert h[0]["detectado_por"] == "casos_planejamento" and h[0]["andar"] == 4


def teste_revisora_barra_caso_ruim_e_reprovacao_suspende_o_designer(cfg, monkeypatch):
    with pytest.raises(PermissionError):
        treino.certificar(cfg, "casos_analytics", "lgpd")  # só o designer da competência faz o exame dela
    assert treino.certificar(cfg, "casos_engenharia", "historico")["ok"]
    assert treino.certificado(cfg, "casos_engenharia", "historico")
    monkeypatch.setattr(CATALOGO["historico"], "conferir", lambda caso, cfg: ["gabarito sabotado"])
    for i in range(2):
        assert treino.criar_caso(cfg, "historico", 1, semente=60 + i)["estado"] == "reprovado"
    assert not treino.certificado(cfg, "casos_engenharia", "historico")  # 2 reprovações: refaz o exame
    c = _banco(cfg)
    assert c.execute("SELECT COUNT(*) FROM treino_tentativas").fetchone()[0] == 0  # caso reprovado não vai para ninguém
    c.close()


def teste_rodada_justa_isolada_da_producao_e_sem_corrida(cfg):
    from robo import historico
    r = treino.rodada(cfg, 8)
    assert r["ok"] and r["tentativas"] == 8 and not r["sem_caso"]
    feitos = {d["funcionario"] for d in r["detalhe"]}
    r2 = treino.rodada(cfg, 8)
    assert not feitos & {d["funcionario"] for d in r2["detalhe"]}  # quem treinou agora vai para o fim da fila
    assert historico.ler(cfg.logs) == [] and not list(cfg.tratadas.glob("*"))  # nada vazou para a produção
    assert treino._rodando.acquire(blocking=False)
    try:
        assert treino.rodada(cfg, 1)["ok"] is False  # uma rodada por vez
    finally:
        treino._rodando.release()
    exps = [e for e in memoria.experiencias(cfg, limite=100) if e["origem"] == "treino"]
    assert len(exps) >= 16  # acerto/erro na memória de cada um


# ----------------------------------------------------------------------------- lacunas reais achadas pelo treino
def teste_ciencia_nao_ignora_dias_e_anos_que_sao_medida():
    from robo.ciencia import _numericas
    df = pd.DataFrame({"dias_entrega": range(10), "anos_de_casa": range(10), "ano": range(10), "mes": range(10),
                       "dia_semana": range(10), "id": range(10), "cod_loja": range(10), "valor": range(10)})
    assert _numericas(df) == ["dias_entrega", "anos_de_casa", "valor"]


def teste_lgpd_mais55_cpf_falso_e_email_no_texto():
    from robo import quadro
    df = pd.DataFrame({"fone": ["+55 (11) 98765-4321"] * 10, "pedido": ["123.456.789-00"] * 10,  # DV inválido
                       "cpf": ["529.982.247-25"] * 10, "obs": ["retornar em ana@x.com.br"] * 10})
    achados = " ".join(quadro.conf_dados_pessoais(quadro.Contexto(arquivo="x", analisaveis={"t": df})))
    assert "[t.fone]" in achados and "[t.cpf]" in achados and "[t.obs]" in achados and "[t.pedido]" not in achados


def teste_analise_reconhece_nps_com_codigo_99():
    from robo.analise import detectar_indicadores
    df = pd.DataFrame({"nota_nps": [10, 9, 8, 7, 6, 5, 99, 10, 9, 3, 10, 8]})
    assert detectar_indicadores(df, {"nota_nps": "numero"}, {}) == {"nps": "nota_nps"}
