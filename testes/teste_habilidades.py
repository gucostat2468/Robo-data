import pandas as pd
import pytest
from openpyxl import Workbook

from robo import habilidades
from robo.agentes import Equipe, ErroAgente
from robo.pipeline import REPROVADO, SUCESSO, processar_arquivo
from robo.relatorio import Relatorio


def rodar(nome, df, **parametros):
    rel = Relatorio("t.xlsx")
    df = df.copy()
    df.index = range(2, len(df) + 2)
    saida = habilidades.executar_habilidade(df, {"habilidade": nome, "parametros": parametros}, rel, "dados", "t.xlsx", "Teste")
    return saida, rel


def teste_catalogo_completo_e_documentado():
    cat = habilidades.catalogo()
    assert len(cat) >= 24
    for s in cat:
        assert s["nome"] and s["descricao"] and s["conhecimento"], s["id"]


def teste_padronizar_texto_titulo_portugues():
    out, _ = rodar("padronizar_texto", pd.DataFrame({"nome": ["MARIA DA SILVA", "joão dos santos"]}), colunas="nome", modo="titulo")
    assert out["nome"].tolist() == ["Maria da Silva", "João dos Santos"]


def teste_de_para_ignora_acento_e_caixa_e_acusa_nao_mapeados():
    df = pd.DataFrame({"modalidade": ["A Distância", "online", "presencial", "Híbrido"]})
    out, rel = rodar("mapear_valores", df, coluna="modalidade", mapa="a distancia=EAD\nonline=EAD\npresencial=Presencial",
                     nao_mapeados="erro")
    assert out["modalidade"].tolist()[:3] == ["EAD", "EAD", "Presencial"]
    assert rel.tem_erros and "Híbrido" in rel.erros[0].exemplos[0]


def teste_cpf_cnpj_com_digito_e_zero_perdido():
    # 2º: o Excel transformou o CPF 012.345.678-90 em número e perdeu o zero; 3º: dígitos repetidos (inválido)
    df = pd.DataFrame({"cpf": ["529.982.247-25", 1234567890.0, "111.111.111-11", None]})
    out, rel = rodar("normalizar_documento", df, colunas="cpf", formato="formatado", invalidos="aviso")
    assert out["cpf"].tolist()[:2] == ["529.982.247-25", "012.345.678-90"]
    assert len(rel.avisos) == 1 and rel.avisos[0].quantidade == 1
    out, rel = rodar("normalizar_documento", pd.DataFrame({"doc": ["11.222.333/0001-81"]}), colunas="doc")
    assert out["doc"].iloc[0] == "11222333000181" and not rel.tem_erros


def teste_email_telefone_cep():
    out, rel = rodar("validar_email", pd.DataFrame({"email": [" Ana@Empresa.COM ", "sem-arroba"]}), colunas="email", invalidos="vazio")
    assert out["email"].iloc[0] == "ana@empresa.com" and pd.isna(out["email"].iloc[1])
    out, rel = rodar("normalizar_telefone", pd.DataFrame({"tel": ["+55 (11) 98765-4321", "3456-7890", "123"]}),
                     colunas="tel", ddd_padrao="21", invalidos="aviso")
    assert out["tel"].tolist()[:2] == ["(11) 98765-4321", "(21) 3456-7890"] and rel.avisos[0].quantidade == 1
    out, _ = rodar("normalizar_cep", pd.DataFrame({"cep": [1310100, "04567-000"]}), colunas="cep")
    assert out["cep"].tolist() == ["01310-100", "04567-000"]


def teste_classificar_nps_e_csat():
    out, rel = rodar("classificar_nps", pd.DataFrame({"nota": [10, 9, 8, 7, 6, 0]}), coluna="nota")
    assert out["grupo_nps"].tolist() == ["Promotor", "Promotor", "Neutro", "Neutro", "Detrator", "Detrator"]
    assert any("NPS desta base: 0.0" in o.mensagem for o in rel.ocorrencias)
    _, rel = rodar("classificar_nps", pd.DataFrame({"nota": [10, 11]}), coluna="nota")
    assert rel.tem_erros
    out, _ = rodar("classificar_csat", pd.DataFrame({"n": [5, 4, 3]}), coluna="n")
    assert out["satisfeito"].tolist() == ["Sim", "Sim", "Não"]


def teste_codificacao_de_verbatins():
    df = pd.DataFrame({"comentario": ["Mensalidade muito cara", "Atendente demorou demais", "Adorei", None]})
    out, rel = rodar("categorizar_texto", df, coluna="comentario",
                     temas={"Preço": "caro, mensalidade, valor", "Atendimento": "atend, demor"})
    assert out["tema"].tolist()[:3] == ["Preço", "Atendimento", "Outros"] and pd.isna(out["tema"].iloc[3])


def teste_faixas_outliers_calculada_filtro():
    out, _ = rodar("classificar_faixas", pd.DataFrame({"idade": [17, 18, 30, 50]}), coluna="idade", nova_coluna="faixa",
                   limites="18, 25, 45", rotulos="<18, 18-24, 25-44, 45+")
    assert out["faixa"].tolist() == ["<18", "18-24", "25-44", "45+"]
    df = pd.DataFrame({"valor": [10.0, 11, 12, 13, 9, 10, 1000]})
    out, _ = rodar("outliers", df, coluna="valor")
    assert out["valor_outlier"].tolist()[-1] == "Sim" and out["valor_outlier"].tolist()[0] == "Não"
    out, _ = rodar("coluna_calculada", pd.DataFrame({"q": pd.array([2, 3], dtype="Int64"), "p": [1.5, 2.0]}),
                   nova_coluna="total", expressao="q * p")
    assert out["total"].tolist() == [3.0, 6.0]
    out, rel = rodar("filtrar_linhas", pd.DataFrame({"status": ["ok", "teste", "ok"]}), condicao="status != 'teste'")
    assert len(out) == 2


def teste_duplicidade_manter_ultimo_e_anonimizar():
    df = pd.DataFrame({"id": ["1", "1", "2"], "nota": [5, 9, 7]})
    out, rel = rodar("checar_duplicados", df, colunas="id", acao="manter_ultimo")
    assert out["nota"].tolist() == [9, 7]
    out, _ = rodar("anonimizar", pd.DataFrame({"cpf": ["52998224725", "52998224725"], "email": ["ana@x.com", None]}),
                   colunas="cpf", metodo="hash", sal="segredo")
    assert out["cpf"].iloc[0] == out["cpf"].iloc[1] and len(out["cpf"].iloc[0]) == 16 and out["cpf"].iloc[0] != "52998224725"
    out, _ = rodar("anonimizar", pd.DataFrame({"email": ["ana@x.com"]}), colunas="email", metodo="mascarar")
    assert out["email"].iloc[0] == "a***@x.com"


def teste_parametros_e_colunas_inexistentes_viram_erro_claro():
    _, rel = rodar("padronizar_texto", pd.DataFrame({"a": ["x"]}), colunas="nao_existe")
    assert rel.tem_erros and "nao_existe" in rel.erros[0].mensagem
    _, rel = rodar("mapear_valores", pd.DataFrame({"a": ["x"]}), coluna="a")
    assert rel.tem_erros and "obrigatório" in rel.erros[0].mensagem
    _, rel = rodar("habilidade_que_nao_existe", pd.DataFrame({"a": [1]}))
    assert rel.tem_erros


# ------------------------------------------------------------------ equipe / agentes
def _planilha(pastas, nome):
    wb = Workbook()
    ws = wb.active
    ws.append(["ID", "Telefone", "Nota", "Comentário"])
    ws.append(["1", "11987654321", 10, "atendimento ótimo"])
    ws.append(["2", "(21) 3456-7890", 3, "muito caro"])
    caminho = pastas / "Bases-Limpeza" / nome
    wb.save(caminho)
    return caminho


def teste_agente_personalizado_trabalha_no_pipeline(pastas, cfg_factory, tmp_path):
    cfg = cfg_factory()
    equipe = Equipe(cfg.agentes, cfg.habilidades)
    equipe.salvar({"id": "tina", "nome": "Tina", "papel": "Contatos", "cor": "#F97316", "posicao": "limpeza",
                   "aplicar_em": ["nps_*"], "habilidades": [
                       {"habilidade": "normalizar_telefone", "parametros": {"colunas": ["telefone"]}},
                       {"habilidade": "classificar_nps", "parametros": {"coluna": "nota"}}]})
    equipe.salvar({"id": "modelagem", "habilidades": [
        {"habilidade": "categorizar_texto", "parametros": {"coluna": "comentario", "temas": {"Preço": "caro", "Atendimento": "atend"}}}]})
    nomes = [a["id"] for a in Equipe(cfg.agentes, cfg.habilidades).lista()]
    assert nomes.index("tina") == nomes.index("limpeza") + 1

    etapas = []
    r = processar_arquivo(_planilha(pastas, "nps_out.xlsx"), cfg, ao_etapa=lambda e, a, **k: etapas.append(e))
    assert r.status == SUCESSO, r.relatorio.texto()
    df = r.tabelas["dados"]
    assert df["telefone"].tolist() == ["(11) 98765-4321", "(21) 3456-7890"]
    assert df["grupo_nps"].tolist() == ["Promotor", "Detrator"]
    assert df["tema"].tolist() == ["Atendimento", "Preço"]
    assert "agente:tina" in etapas

    # aplicar_em: arquivo que não casa com nps_* não passa pela Tina
    r2 = processar_arquivo(_planilha(pastas, "vendas.xlsx"), cfg)
    assert "grupo_nps" not in r2.tabelas["dados"].columns


def teste_agente_invalido_reprova_em_vez_de_publicar_errado(pastas, cfg_factory):
    cfg = cfg_factory()
    (cfg.agentes).mkdir(parents=True, exist_ok=True)
    (cfg.agentes / "quebrado.yaml").write_text("id: quebrado\nnome: Q\nposicao: limpeza\nhabilidades:\n  - habilidade: nao_existe\n",
                                               encoding="utf-8")
    r = processar_arquivo(_planilha(pastas, "x.xlsx"), cfg)
    assert r.status == REPROVADO and "configuração inválida" in r.relatorio.texto()


def teste_salvar_recusa_configuracao_invalida_e_nativos(cfg_factory):
    cfg = cfg_factory()
    equipe = Equipe(cfg.agentes, cfg.habilidades)
    with pytest.raises(ErroAgente):
        equipe.salvar({"id": "Nome Com Espaço", "nome": "x"})
    with pytest.raises(ErroAgente):
        equipe.salvar({"id": "x1", "nome": "X", "habilidades": [{"habilidade": "mapear_valores", "parametros": {}}]})
    with pytest.raises(ErroAgente):
        equipe.excluir("limpeza")
    equipe.salvar({"id": "x1", "nome": "X"})
    equipe.excluir("x1")
    assert "x1" not in [a["id"] for a in equipe.lista()]


def teste_habilidade_personalizada_em_python(pastas, cfg_factory):
    cfg = cfg_factory()
    cfg.habilidades.mkdir(parents=True, exist_ok=True)
    (cfg.habilidades / "vip.py").write_text('''
from robo.habilidades import Param, habilidade

@habilidade(id="marcar_vip", nome="Marcar VIP", categoria="Minhas habilidades", descricao="VIP acima do limite",
       parametros=[Param("coluna", "coluna", "Valor"), Param("limite", "numero", "Limite", padrao=5)])
def marcar_vip(df, p, ctx):
    df["vip"] = (df[p["coluna"]] >= p["limite"]).map({True: "Sim", False: "Não"})
    return df

import pandas as pd
marcar_vip.provas = [("VIP acima do limite", pd.DataFrame({"v": [1, 9]}), {"coluna": "v"},
                      lambda r, rel: r["vip"].tolist() == ["Não", "Sim"])]
''', encoding="utf-8")
    equipe = Equipe(cfg.agentes, cfg.habilidades)
    assert habilidades.REGISTRO["marcar_vip"].origem == "personalizada"
    equipe.salvar({"id": "vip", "nome": "Vic", "posicao": "modelagem",
                   "habilidades": [{"habilidade": "marcar_vip", "parametros": {"coluna": "nota"}}]})
    r = processar_arquivo(_planilha(pastas, "a.xlsx"), cfg)
    assert r.tabelas["dados"]["vip"].tolist() == ["Sim", "Não"]


def teste_habilidade_sem_prova_nao_e_contratada(cfg_factory):
    import pytest
    from robo.agentes import ErroAgente
    cfg = cfg_factory()
    cfg.habilidades.mkdir(parents=True, exist_ok=True)
    (cfg.habilidades / "sem_prova.py").write_text('''
from robo.habilidades import habilidade

@habilidade(id="sem_prova", nome="Sem prova", categoria="Teste", descricao="não tem prova técnica")
def sem_prova(df, p, ctx):
    return df
''', encoding="utf-8")
    with pytest.raises(ErroAgente, match="não tem prova técnica"):
        Equipe(cfg.agentes, cfg.habilidades).salvar({"id": "zeca", "nome": "Zeca", "posicao": "limpeza",
                                                     "habilidades": [{"habilidade": "sem_prova"}]})


def teste_personalizada_nao_substitui_nativa(cfg_factory):
    cfg = cfg_factory()
    cfg.habilidades.mkdir(parents=True, exist_ok=True)
    (cfg.habilidades / "falsa.py").write_text('''
from robo.habilidades import habilidade

@habilidade(id="validar_email", nome="E-mail falso", categoria="Teste", descricao="tenta trocar a nativa")
def falsa(df, p, ctx):
    return df
''', encoding="utf-8")
    Equipe(cfg.agentes, cfg.habilidades)
    assert habilidades.REGISTRO["validar_email"].origem == "nativa"
    assert any("já é de uma habilidade nativa" in e for e in habilidades.ERROS_CARGA)


def teste_nps_nao_classifica_nota_invalida_mantida():
    import pandas as pd
    from robo.habilidades import executar_habilidade
    from robo.relatorio import Relatorio
    df = pd.DataFrame({"nota": [10, 11, 3]})
    r = executar_habilidade(df, {"habilidade": "classificar_nps", "parametros": {"coluna": "nota", "invalidos": "aviso"}},
                            Relatorio("x"), "t", "x", "teste")
    assert r["grupo_nps"].tolist()[0] == "Promotor" and pd.isna(r["grupo_nps"].tolist()[1])
