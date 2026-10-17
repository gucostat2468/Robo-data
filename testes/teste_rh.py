import pytest
from openpyxl import Workbook

from robo import rh, habilidades
from robo.agentes import NATIVOS, Equipe, ErroAgente
from robo.analise import ANALISTAS
from robo.pipeline import SUCESSO, processar_arquivo


def teste_toda_habilidade_tem_prova_e_todas_passam():
    for sid in habilidades.REGISTRO:
        if habilidades.REGISTRO[sid].origem != "nativa":
            continue
        casos = rh.provas_da_habilidade(sid)
        assert casos, f"{sid} sem prova técnica"
        assert all(c["aprovado"] for c in casos), (sid, [c for c in casos if not c["aprovado"]])


def teste_equipe_nativa_e_analistas_aprovados_no_processo_seletivo():
    from robo.excel import EQUIPE_EXCEL
    from robo.producao import SUPERVISORES
    for a in NATIVOS + SUPERVISORES + EQUIPE_EXCEL + [{**x, "id": "analise_" + x["id"]} for x in ANALISTAS]:
        f = rh.ficha({**a, "habilidades": []})
        assert f["provas"]["aprovado"] and f["provas"]["total"] >= 2, (a["id"], f["provas"]["bloqueios"])
        assert f["cargo"] and f["metodologias"] and f["limites"] and f["nivel"] in rh.NOME_NIVEL.values()


def teste_risco_depende_dos_parametros():
    assert rh.risco_de("validar_email", {}) == "baixo"
    assert rh.risco_de("validar_email", {"invalidos": "remover"}) == "alto"
    assert rh.risco_de("preencher_vazios", {"metodo": "media"}) == "alto"
    assert rh.nivel_permite("junior", "baixo") and not rh.nivel_permite("junior", "medio")
    assert rh.nivel_permite("pleno", "medio") and not rh.nivel_permite("pleno", "alto")


def teste_junior_nao_pode_tarefa_de_risco_e_promocao_libera(cfg_factory):
    cfg = cfg_factory()
    eq = Equipe(cfg.agentes, cfg.habilidades)
    novo = {"id": "joao", "nome": "João", "nivel": "junior", "posicao": "limpeza",
            "habilidades": [{"habilidade": "mapear_valores", "parametros": {"coluna": "uf", "mapa": {"sp": "SP"}}}]}
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


def teste_estagiario_trabalha_em_observacao_sem_alterar_dados(pastas, cfg_factory):
    cfg = cfg_factory()
    Equipe(cfg.agentes, cfg.habilidades).salvar({
        "id": "est", "nome": "Estela", "nivel": "estagiario", "posicao": "limpeza",
        "habilidades": [{"habilidade": "padronizar_texto", "parametros": {"colunas": ["uf"], "modo": "maiusculo"}},
                   {"habilidade": "validar_email", "parametros": {"colunas": ["email"]}}]})
    r = processar_arquivo(_planilha(pastas), cfg)
    assert r.status == SUCESSO  # o erro de e-mail que ela acharia NÃO reprova
    assert list(r.tabelas["dados"]["uf"]) == ["sp", "rj"]  # e nada foi alterado
    obs = [o for o in r.relatorio.ocorrencias if "Estagiário Estela em observação" in o.mensagem]
    assert obs and "alteraria" in obs[0].mensagem and "encontraria 1" in obs[0].mensagem


def teste_habilidade_personalizada_reprovada_na_prova_nao_e_contratada(cfg_factory):
    cfg = cfg_factory()
    cfg.habilidades.mkdir(parents=True, exist_ok=True)
    (cfg.habilidades / "ruim.py").write_text('''
import pandas as pd
from robo.habilidades import Param, habilidade

def _df():
    return pd.DataFrame({"v": [1, 2]})

@habilidade(id="dobrar", nome="Dobrar", categoria="Minhas", descricao="Dobra", parametros=[Param("coluna", "coluna", "Coluna")])
def dobrar(df, p, ctx):
    df[p["coluna"]] = df[p["coluna"]] * 3  # bug: triplica
    return df

dobrar.provas = [("Dobra o valor", _df(), {"coluna": "v"}, lambda d, r: list(d["v"]) == [2, 4])]
''', encoding="utf-8")
    eq = Equipe(cfg.agentes, cfg.habilidades)
    with pytest.raises(ErroAgente, match="processo seletivo"):
        eq.salvar({"id": "xavier", "nome": "Xavier", "nivel": "senior", "habilidades": [{"habilidade": "dobrar", "parametros": {"coluna": "v"}}]})
