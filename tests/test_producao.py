"""O portão de produção pega o que os agentes individuais deixariam passar."""

import json
import os
import uuid

import pandas as pd
import pytest
from openpyxl import Workbook

from conftest import REGRA_NPS
from robo.agentes import Equipe
from robo.pipeline import REPROVADO, SUCESSO, processar_arquivo


def test_aprovado_tem_checklist_assinado(planilha_baguncada, cfg_factory):
    cfg = cfg_factory([REGRA_NPS])
    r = processar_arquivo(planilha_baguncada, cfg)
    assert r.status == SUCESSO and r.checklist["liberado"]
    conc = [o for o in r.relatorio.ocorrencias if "Supervisor de planilhas" in o.mensagem]
    assert conc and "aprovadas" in conc[0].mensagem
    aba = pd.read_excel(cfg.relatorios / "nps_outubro_qualidade.xlsx", sheet_name="checklist_producao")
    assert (aba["status"] == "OK").all()


def test_supervisor_barra_linhas_que_somem_sem_explicacao(pastas, cfg_factory):
    cfg = cfg_factory()
    cfg.skills.mkdir(parents=True, exist_ok=True)
    (cfg.skills / "some.py").write_text('''
import pandas as pd
from robo.skills import Param, skill

def _df():
    return pd.DataFrame({"a": [1, 2]})

@skill(id="tira_primeira", nome="Tira a primeira", categoria="Teste", descricao="bug: some com uma linha sem avisar")
def tira_primeira(df, p, ctx):
    return df.iloc[1:]

tira_primeira.provas = [("Devolve tabela", _df(), {}, lambda d, r: isinstance(d, pd.DataFrame))]
''', encoding="utf-8")
    Equipe(cfg.agentes, cfg.skills).salvar({"id": "bugado", "nome": "Bugado", "nivel": "senior", "skills": [{"skill": "tira_primeira"}]})
    wb = Workbook(); ws = wb.active
    ws.append(["id", "v"]); ws.append(["1", 10]); ws.append(["2", 20])
    caminho = pastas / "Bases-Limpeza" / "base.xlsx"; wb.save(caminho)
    r = processar_arquivo(caminho, cfg)
    assert r.status == REPROVADO
    assert "Conciliação de linhas" in r.relatorio.texto()
    assert not (cfg.tratadas / "base.xlsx").exists()


DSN = os.environ.get("ROBO_TESTE_PG")


@pytest.mark.skipif(not DSN, reason="defina ROBO_TESTE_PG para testar com PostgreSQL")
def test_dba_desfaz_carga_que_nao_bate(planilha_baguncada, cfg_factory, monkeypatch):
    import psycopg

    from robo import banco as mod
    d = dict(p.split("=", 1) for p in DSN.split())
    nome = f"robo_dba_{uuid.uuid4().hex[:8]}"
    cfg_b = {"habilitado": True, "host": d.get("host"), "porta": int(d.get("port", 5432)), "usuario": d.get("user", "postgres"),
             "senha": d.get("password", ""), "banco": nome}
    original = mod.Banco._copiar

    def copiar_com_perda(self, conn, schema, tabela, df, tipos):  # simula uma carga que perde uma linha no caminho
        if schema == "tratado" and len(df) > 1:
            df = df.iloc[1:]
        return original(self, conn, schema, tabela, df, tipos)

    monkeypatch.setattr(mod.Banco, "_copiar", copiar_com_perda)
    try:
        r = processar_arquivo(planilha_baguncada, cfg_factory([REGRA_NPS], banco=cfg_b))
        assert r.status == REPROVADO and "DBA barrou a carga" in r.relatorio.texto()
        with psycopg.connect(host=cfg_b["host"], port=cfg_b["porta"], user=cfg_b["usuario"], password=cfg_b["senha"], dbname=nome) as c:
            tem = c.execute("SELECT to_regclass('tratado.nps_outubro')").fetchone()[0]
            assert tem is None or c.execute("SELECT count(*) FROM tratado.nps_outubro").fetchone()[0] == 0
    finally:
        with psycopg.connect(host=cfg_b["host"], port=cfg_b["porta"], user=cfg_b["usuario"], password=cfg_b["senha"],
                             dbname="postgres", autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)')


def test_coordenador_de_analise_revisa(pastas, cfg_factory):
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from test_analise import _salvar_xlsx, base_nps
    cfg = cfg_factory()
    arq = pastas / "Bases-Limpeza" / "nps_set.xlsx"
    _salvar_xlsx(base_nps(), arq)
    r = processar_arquivo(arq, cfg)
    assert r.status == SUCESSO and r.checklist_analise["aprovado"]
    detalhe = json.loads((cfg.logs / "execucoes" / f"{r.id}.json").read_text(encoding="utf-8"))
    assert detalhe["checklist_analise"]["coordenador"] == "Marcos"
