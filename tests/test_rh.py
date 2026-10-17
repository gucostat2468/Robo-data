import pytest
from openpyxl import Workbook

from robo import rh, skills
from robo.agentes import NATIVOS, Equipe, ErroAgente
from robo.analise import ANALISTAS
from robo.pipeline import SUCESSO, processar_arquivo


def test_toda_skill_tem_prova_e_todas_passam():
    for sid in skills.REGISTRO:
        if skills.REGISTRO[sid].origem != "nativa":
            continue
        casos = rh.provas_da_skill(sid)
        assert casos, f"{sid} sem prova técnica"
        assert all(c["aprovado"] for c in casos), (sid, [c for c in casos if not c["aprovado"]])


def test_equipe_nativa_e_analistas_aprovados_no_processo_seletivo():
    from robo.producao import SUPERVISORES
    for a in NATIVOS + SUPERVISORES + [{**x, "id": "analise_" + x["id"]} for x in ANALISTAS]:
        f = rh.ficha({**a, "skills": []})
        assert f["provas"]["aprovado"] and f["provas"]["total"] >= 2, (a["id"], f["provas"]["bloqueios"])
        assert f["cargo"] and f["metodologias"] and f["limites"] and f["nivel"] in rh.NOME_NIVEL.values()


def test_risco_depende_dos_parametros():
    assert rh.risco_de("validar_email", {}) == "baixo"
    assert rh.risco_de("validar_email", {"invalidos": "remover"}) == "alto"
    assert rh.risco_de("preencher_vazios", {"metodo": "media"}) == "alto"
    assert rh.nivel_permite("junior", "baixo") and not rh.nivel_permite("junior", "medio")
    assert rh.nivel_permite("pleno", "medio") and not rh.nivel_permite("pleno", "alto")


def test_junior_nao_pode_tarefa_de_risco_e_promocao_libera(cfg_factory):
    cfg = cfg_factory()
    eq = Equipe(cfg.agentes, cfg.skills)
    novo = {"id": "joao", "nome": "João", "nivel": "junior", "posicao": "limpeza",
            "skills": [{"skill": "mapear_valores", "parametros": {"coluna": "uf", "mapa": {"sp": "SP"}}}]}
    with pytest.raises(ErroAgente, match="nível Júnior não permite"):
        eq.salvar(novo)
    eq.salvar({**novo, "nivel": "pleno"})
    assert "joao" not in eq.problemas


def _planilha(pastas, nome="base.xlsx"):
    wb = Workbook()
    ws = wb.active
    ws.append(["ID", "UF", "Email"])
    ws.append(["1", "sp", "ANA@X.COM"])
    ws.append(["2", "rj", "invalido"])
    caminho = pastas / "Bases-Limpeza" / nome
    wb.save(caminho)
    return caminho


def test_estagiario_trabalha_em_observacao_sem_alterar_dados(pastas, cfg_factory):
    cfg = cfg_factory()
    Equipe(cfg.agentes, cfg.skills).salvar({
        "id": "est", "nome": "Estela", "nivel": "estagiario", "posicao": "limpeza",
        "skills": [{"skill": "padronizar_texto", "parametros": {"colunas": ["uf"], "modo": "maiusculo"}},
                   {"skill": "validar_email", "parametros": {"colunas": ["email"]}}]})
    r = processar_arquivo(_planilha(pastas), cfg)
    assert r.status == SUCESSO  # o erro de e-mail que ela acharia NÃO reprova
    assert list(r.tabelas["dados"]["uf"]) == ["sp", "rj"]  # e nada foi alterado
    obs = [o for o in r.relatorio.ocorrencias if "Estagiário Estela em observação" in o.mensagem]
    assert obs and "alteraria" in obs[0].mensagem and "encontraria 1" in obs[0].mensagem


def test_skill_personalizada_reprovada_na_prova_nao_e_contratada(cfg_factory):
    cfg = cfg_factory()
    cfg.skills.mkdir(parents=True, exist_ok=True)
    (cfg.skills / "ruim.py").write_text('''
import pandas as pd
from robo.skills import Param, skill

def _df():
    return pd.DataFrame({"v": [1, 2]})

@skill(id="dobrar", nome="Dobrar", categoria="Minhas", descricao="Dobra", parametros=[Param("coluna", "coluna", "Coluna")])
def dobrar(df, p, ctx):
    df[p["coluna"]] = df[p["coluna"]] * 3  # bug: triplica
    return df

dobrar.provas = [("Dobra o valor", _df(), {"coluna": "v"}, lambda d, r: list(d["v"]) == [2, 4])]
''', encoding="utf-8")
    eq = Equipe(cfg.agentes, cfg.skills)
    with pytest.raises(ErroAgente, match="processo seletivo"):
        eq.salvar({"id": "xavier", "nome": "Xavier", "nivel": "senior", "skills": [{"skill": "dobrar", "parametros": {"coluna": "v"}}]})
