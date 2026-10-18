"""Laboratório contínuo, guilda Python, interação entre funcionários, balões no 3D e sala de reunião."""

import pytest

from conftest import REGRA_NPS
from robo import bibliotecas, interacoes, laboratorio, lideranca, memoria, orquestrador, organizacao, sala
from robo.pipeline import processar_arquivo


@pytest.fixture
def cfg(planilha_baguncada, cfg_factory):
    return cfg_factory(regras=[REGRA_NPS])


@pytest.fixture
def baloes():
    capturados = []
    anterior = orquestrador.AO_EVENTO
    orquestrador.AO_EVENTO = lambda etapa, rotulo, **extra: capturados.append({"etapa": etapa, **extra})
    yield capturados
    orquestrador.AO_EVENTO = anterior


@pytest.mark.parametrize("area", laboratorio.AREAS)
def teste_laboratorio_cada_area_com_resposta_conhecida(cfg, area):
    r = laboratorio.exercicio(cfg, area, 11)
    assert r["falhas"] == [] and r["acertos"] >= 4, r
    # nada vai para a produção: nem histórico, nem Bases-Tratadas
    from robo import historico
    assert historico.ler(cfg.logs, 10) == [] and not list((cfg.entrada.parent / "Bases-Tratadas").glob("lab_*"))
    assert any(e["origem"] == "laboratorio" for e in memoria.experiencias(cfg, "limpeza"))


def teste_laboratorio_pega_erro_plantado_e_pede_ajuda(cfg, baloes, monkeypatch):
    from robo import ciencia
    monkeypatch.setattr(ciencia, "drivers", lambda df, alvo: {"ok": True, "drivers": [{"atributo": "ctr"}]})
    r = laboratorio.exercicio(cfg, "marketing", 3)
    assert any("driver" in f for f in r["falhas"])
    assert any("Laboratório: Achar o driver plantado" in h["erro"] for h in memoria.handovers(cfg))
    conversa = interacoes.recentes(cfg)
    assert [c["tipo"] for c in conversa[:2]] == ["resposta", "pedido"] and conversa[1]["de"] == "cd_senior_drivers"
    assert any(b.get("fala") and b["etapa"] == "cd_senior_drivers" for b in baloes)


def teste_rotina_do_laboratorio_respeita_intervalo(cfg):
    assert laboratorio.rotina(cfg)["etapas"] >= 4
    assert laboratorio.rotina(cfg) is None


def teste_guilda_python_e_a_mais_cobrada(cfg):
    for pid in lideranca.GUILDA_PYTHON:
        c = organizacao.contrato(pid, cfg)
        assert "revisao_biblioteca" in c["ferramentas"] and lideranca.EXIGENCIA[pid] == 90.0
    for _ in range(4):
        memoria.experiencia(cfg, "esp_pandas", "acerto", "ok", "teste")
        memoria.experiencia(cfg, "analise_perfil", "acerto", "ok", "teste")
    memoria.experiencia(cfg, "esp_pandas", "erro", "x", "teste")
    memoria.experiencia(cfg, "analise_perfil", "erro", "x", "teste")
    d = {x["id"]: x for x in memoria.desempenho(cfg)}
    assert d["esp_pandas"]["situacao"] == "insuficiente"  # 80% < 90% exigido da guilda
    assert d["analise_perfil"]["situacao"] == "atencao"   # 80% é atenção para o resto da empresa
    for nome in bibliotecas.BIBLIOTECAS:
        assert bibliotecas.revisar(nome)["ok"], nome


def teste_troca_de_experiencias_entre_colegas(cfg, baloes):
    memoria.experiencia(cfg, "leitura", "acerto", "Laboratório (varejo): Achar o cabeçalho", "laboratorio")
    memoria.experiencia(cfg, "limpeza", "erro", "Laboratório (varejo): Limpar o Total", "laboratorio")
    trocas = interacoes.trocar_experiencias(cfg)
    assert trocas and trocas[0]["aprendiz"] == "limpeza" and organizacao.por_id(cfg)[trocas[0]["mentor"]]["andar"] == 1
    assert any(e["tipo"] == "aprendizado" for e in memoria.experiencias(cfg, "limpeza"))


def teste_pedido_do_dono_vira_balao(cfg, baloes):
    from robo import atendimento
    atendimento.conversar(cfg, "dba", "o que você faz?")
    assert baloes[0]["etapa"] == "dba" and "Pedido do dono" in baloes[0]["fala"]
    assert baloes[-1]["etapa"] == "dba" and baloes[-1]["fala"].startswith("Sou Dora")


def teste_sala_de_reuniao_com_varias_pessoas(planilha_baguncada, cfg):
    memoria.registrar_execucao(cfg, processar_arquivo(planilha_baguncada, cfg))
    r = sala.abrir(cfg, 1)
    assert r["participantes"] == ["dir_dados", "head_engenharia", "ger_engenharia", "coord_engenharia"]
    d = sala.detalhes(cfg, r["conversa_id"])
    autores = {m["autor"] for m in d["mensagens"]}
    assert {"dono", "dir_dados", "head_engenharia", "coord_engenharia"} <= autores
    # citou o nome → quem responde é a pessoa citada; sem nome → a coordenação
    x = sala.falar(cfg, r["conversa_id"], "Beatriz, qual o scorecard da área?")
    assert x["respostas"][-1]["autor"] == "dir_dados"
    x = sala.falar(cfg, r["conversa_id"], "o que você faz?")
    assert x["respostas"][-1]["autor"] == "coord_engenharia"
    x = sala.falar(cfg, r["conversa_id"], "o que você faz?", para="head_engenharia")
    assert x["respostas"][-1]["autor"] == "head_engenharia"


def teste_nps_numa_formula_so():
    from robo import conferencia
    passos = conferencia.montar_excel("nps", "nota", [], [], None)
    formulas = [l for l in passos.split("\n") if l.startswith("=")]
    assert len(formulas) == 1 and formulas[0].count("CONT.SES") == 3 and formulas[0].startswith("=ARRED((")


def teste_sala_teams_completa(planilha_baguncada, cfg):
    import sqlite3
    from robo.trabalho import Trabalho
    memoria.registrar_execucao(cfg, processar_arquivo(planilha_baguncada, cfg))
    memoria.handover(cfg, "Coluna de data com texto misturado", "nps_outubro", "limpeza", "teste")
    r = sala.abrir(cfg, 1)
    cid = r["conversa_id"]
    # coordenação levanta a mão porque há handover aberto no andar (motivo real, com o id)
    mao = next(m for m in r["maos"] if m["id"] == "coord_engenharia")
    assert "handover" in mao["motivo"]
    sala.dar_palavra(cfg, cid, "coord_engenharia")
    d = sala.detalhes(cfg, cid)
    ult = d["mensagens"][-1]
    assert ult["autor"] == "coord_engenharia" and "Coluna de data com texto misturado" in ult["texto"] and "→" in ult["texto"]
    assert all(m["id"] != "coord_engenharia" for m in d["contexto"]["maos"])
    with pytest.raises(ValueError):
        sala.dar_palavra(cfg, cid, "coord_engenharia")  # já falou: mão abaixada
    # reação, convite, remoção, palco, pauta, notas, tarefa
    sala.reagir(cfg, cid, d["mensagens"][-1]["id"], "aplausos")
    with pytest.raises(ValueError):
        sala.reagir(cfg, cid, d["mensagens"][-1]["id"], "bomba")
    sala.convidar(cfg, cid, "dba")
    with pytest.raises(ValueError):
        sala.remover(cfg, cid, "coord_engenharia")  # quem conduz não sai
    sala.remover(cfg, cid, "dba")
    assert sala.compartilhar(cfg, cid, "raio_x")["palco"]["texto"].startswith("Temos")
    sala.pauta(cfg, cid, ["Erros abertos", "Próximos passos"])
    sala.pauta(cfg, cid, marcar=0)
    sala.anotar(cfg, cid, "Decidido: padronizar datas.")
    with pytest.raises(ValueError, match="prazo e de critério"):
        sala.criar_tarefa(cfg, cid, "padronizar a coluna de data da base nps_outubro", "limpeza")  # nada vago
    from datetime import date, timedelta
    t = sala.criar_tarefa(cfg, cid, "padronizar a coluna de data da base nps_outubro", "limpeza",
                          (date.today() + timedelta(days=7)).isoformat(), "duas cargas seguidas sem aviso de data em texto")
    assert Trabalho(cfg).solicitacao(t["id"]) and t["decisao"].startswith("DEC-")
    d = sala.detalhes(cfg, cid)
    assert d["mensagens"][-1]["texto"].startswith("📌 Decisão")
    assert any(m["reacoes"] for m in d["mensagens"]) and d["contexto"]["palco"]["tipo"] == "raio_x"
    # encerrar: recap salvo, reunião fecha, registro não se apaga
    fim = sala.encerrar(cfg, cid)
    rc = fim["recap"]
    assert rc["tarefas"] and rc["pauta"][0].startswith("[x]") and "👏" in rc["reacoes"] and "Raio-X da empresa" in rc["compartilhado"]
    assert "## Transcrição" in open(fim["arquivo"], encoding="utf-8").read()
    with pytest.raises(ValueError):
        sala.falar(cfg, cid, "ainda aí?")
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DELETE FROM sala_eventos")
    c.rollback()
    assert c.execute("SELECT COUNT(*) FROM salas_encerradas").fetchone()[0] == 1
    # a ata da sala NÃO entra em reunioes (é da reunião semanal; misturar fazia a rotina semanal achar que já tinha rodado)
    assert c.execute("SELECT COUNT(*) FROM reunioes").fetchone()[0] == 0
    c.close()
    from robo import reuniao
    assert all("andares" in r["ata"] for r in reuniao.listar(cfg))
    tipos = [e["tipo"] for e in sala.eventos(cfg, cid)]
    for t in ("abrir", "mao_levantada", "palavra", "reacao", "convite", "remocao", "compartilhar", "pauta", "notas", "decisao", "encerrar"):
        assert t in tipos, t


# ---------------- níveis de dificuldade (termômetro): cada nível planta sujeira real e a resposta certa é conhecida
@pytest.mark.parametrize("valor,esperado", [
    ("1.234,56-", -1234.56),     # SAP: menos no fim
    ("−1.234,56", -1234.56),     # sinal − tipográfico (copiado de PDF)
    ("R$ 1,2 mil", 1200.0),
    ("R$ 3,5 mi", 3_500_000.0),
    ("2k", 2000.0),
    ("-", None),                 # traço sozinho é nulo, não zero
    ("N/A", None),
])
def teste_formatos_dificeis_de_numero(valor, esperado):
    from robo.limpeza import numero_de
    r = numero_de(valor, ",")
    assert r == pytest.approx(esperado) if esperado is not None else r is None


def teste_rodape_de_relatorio_nao_vira_linha_de_dado():
    import pandas as pd
    from robo.config import PADROES
    from robo.limpeza import limpar_tabela
    from robo.relatorio import Relatorio
    df = pd.DataFrame({"loja": ["A", "B", "C", "Gerado em 10/10/2026 por ERP"], "valor": [10, 20, 30, None]})
    df.index = range(2, 6)
    rel = Relatorio("t.xlsx")
    out = limpar_tabela(df, "dados", PADROES["limpeza"], {}, rel)
    assert len(out) == 3 and not out["loja"].astype(str).str.contains("Gerado").any()


@pytest.mark.parametrize("nivel", [1, 2, 3, 4])
@pytest.mark.parametrize("area", ["varejo", "rh", "financeiro"])
def teste_cada_nivel_passa_com_resposta_certa(cfg, area, nivel):
    r = laboratorio.exercicio(cfg, area, 21, gravar=False, nivel=nivel)
    assert r["falhas"] == [], r


def teste_nivel_fica_gravado_e_termometro_mostra_a_linha_do_tempo(cfg):
    for n in (1, 4, 4):
        laboratorio.exercicio(cfg, "varejo", 30 + n, nivel=n)
    termo = {t["nivel"]: t for t in laboratorio.por_nivel(cfg)}
    assert termo[1]["rodadas"] == 1 and termo[4]["rodadas"] == 2 and len(termo[4]["linha_do_tempo"]) == 2
    assert termo[2]["taxa"] is None and termo[4]["taxa"] is not None
    assert "por_nivel" in laboratorio.resumo(cfg)


def teste_quem_piorou_5_pontos_levanta_a_mao_na_reuniao(cfg):
    """Alerta de regressão: 10/10 acertos há 3–4 semanas e 5/10 nas 2 últimas → a mão sobe sozinha, com os números.
    Quem está estável não entra no alerta."""
    import sqlite3
    from datetime import datetime, timedelta
    from robo.trabalho import Trabalho
    Trabalho(cfg)  # cria o banco
    agora = datetime.now()
    linhas = [("limpeza", (agora - timedelta(days=24)).isoformat(timespec="seconds"), "acerto")] * 10 + \
             [("limpeza", (agora - timedelta(days=3)).isoformat(timespec="seconds"), t) for t in ["acerto", "erro"] * 5] + \
             [("validacao", (agora - timedelta(days=d)).isoformat(timespec="seconds"), "acerto") for d in (3, 24)] * 6
    c = sqlite3.connect(cfg.logs / "trabalho.db")
    c.executemany("INSERT INTO experiencias (funcionario, data_hora, tipo, resumo, origem) VALUES (?,?,?,'t','pipeline')", linhas)
    c.commit()
    c.close()
    maos = {m["id"]: m for m in sala.abrir(cfg, 1)["maos"]}
    coord = maos["coord_engenharia"]  # a limpeza não está na reunião da liderança: a coordenação leva o alerta
    assert "1 pessoa(s) do andar com acerto em queda" in coord["motivo"]
    nome_limpeza = organizacao.por_id(cfg)["limpeza"]["nome"]
    assert f"{nome_limpeza} (" in coord["fala"] and "-50,0 pontos" in coord["fala"]
    nome_validacao = organizacao.por_id(cfg)["validacao"]["nome"]
    assert nome_validacao not in coord["fala"]  # estável não entra no alerta
