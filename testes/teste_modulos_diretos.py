"""Teste DIRETO dos módulos que a visão de gestão apontou sem teste próprio (antes só eram exercitados de tabela).
Cada teste prova uma regra de negócio do módulo, não só que ele importa."""

import os
import time

import pandas as pd
import pytest
import yaml

from robo.relatorio import Relatorio


# ----------------------------------------------------------------------------- robo.validacao
def _validar(df, regra):
    from robo.validacao import validar_tabela
    df.index = range(2, 2 + len(df))
    rel = Relatorio("t.xlsx")
    validar_tabela(df, "dados", regra, rel)
    return {o.mensagem: o for o in rel.erros}


def teste_validacao_cada_regra_barra_o_que_deve():
    df = pd.DataFrame({"id": [1, 2, 2], "nota_nps_aluno": [10, 11, None], "uf": ["SP", "XX", "rj"]})
    erros = _validar(df, {"colunas_obrigatorias": ["id", "nota_nps"], "nao_nulos": ["nota_nps_aluno"],
                          "chave_unica": ["id"], "faixas": {"nota_nps_aluno": {"min": 0, "max": 10}},
                          "valores_permitidos": {"uf": ["SP", "RJ"]}, "minimo_linhas": 5})
    assert "você quis dizer 'nota_nps_aluno'" in erros["Colunas obrigatórias ausentes"].exemplos[0]  # sugere, não troca
    assert erros["Células vazias em coluna obrigatória"].quantidade == 1
    assert erros["Chave única repetida (id)"].quantidade == 2
    assert erros["Valores fora da faixa permitida (0 a 10)"].exemplos == ["linha 3: 11.0"]
    assert erros["Valores fora da lista permitida"].exemplos == ["linha 3: 'XX'"]  # 'rj' passa: sem diferenciar maiúscula
    assert any(m.startswith("Tabela com 3 linha(s)") for m in erros)


def teste_validacao_sem_regra_nao_inventa_erro():
    assert _validar(pd.DataFrame({"a": [1, 2]}), {}) == {}


# ----------------------------------------------------------------------------- robo.escrita
def teste_escrita_csv_neutraliza_formula_e_respeita_separador(tmp_path):
    from robo.escrita import gravar_tabelas
    df = pd.DataFrame({"nome": ["=HYPERLINK(\"http://x\")", "Ana"], "valor": [1.5, 2.25]})
    arquivos, avisos = gravar_tabelas({"t": df}, tmp_path, "saida", {"formato": "csv"})
    texto = arquivos[0].read_text(encoding="utf-8-sig")
    assert avisos == [] and texto.splitlines()[0] == "nome;valor"
    assert "'=HYPERLINK" in texto and "1,5" in texto  # célula com fórmula vira texto; decimal com vírgula
    assert not list(tmp_path.glob("*.tmp*"))  # gravação atômica não deixa temporário


def teste_escrita_formato_invalido_e_ambos(tmp_path):
    from robo.escrita import gravar_tabelas
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError):
        gravar_tabelas({"t": df}, tmp_path, "x", {"formato": "pdf"})
    arquivos, _ = gravar_tabelas({"t": df}, tmp_path, "x", {"formato": "ambos"})
    assert sorted(p.suffix for p in arquivos) == [".csv", ".xlsx"]


# ----------------------------------------------------------------------------- robo.modelagem
def teste_modelagem_dicionario_calendario_e_fato_dimensao():
    from robo import modelagem
    df = pd.DataFrame({"curso": ["Direito", "Medicina", "Direito"], "modalidade": ["EAD", "Presencial", "EAD"],
                       "nota": [10, 7, 9], "data": pd.to_datetime(["2026-01-30", "2026-02-01", "2026-02-02"])})
    assert modelagem.tipo_amigavel(df["nota"]) != modelagem.tipo_amigavel(df["curso"])
    dic = modelagem.dicionario_dados({"nps": df})
    assert set(dic.iloc[:, 1]) >= {"curso", "nota"} or len(dic) == 4
    cal = modelagem.tabela_calendario(df["data"])
    dias = pd.to_datetime(cal["data"])
    # ano completo (o Power BI exige calendário contínuo e de anos inteiros), um dia por linha, sem buraco
    assert dias.min() == pd.Timestamp("2026-01-01") and dias.max() == pd.Timestamp("2026-12-31")
    assert len(cal) == 365 and dias.is_monotonic_increasing and dias.is_unique
    rel = Relatorio("t.xlsx")
    tabs = modelagem.modelar(df, "nps", {"fato": "fato_nps", "dimensoes": {"dim_curso": {"colunas": ["curso", "modalidade"],
                                                                                         "chave": "id_curso"}}}, rel)
    assert len(tabs["dim_curso"]) == 2 and "id_curso" in tabs["fato_nps"] and "curso" not in tabs["fato_nps"]


# ----------------------------------------------------------------------------- robo.manutencao
def teste_manutencao_apaga_so_o_que_passou_da_retencao(cfg_factory):
    from robo.manutencao import executar_manutencao
    cfg = cfg_factory(manutencao={"dias_retencao_originais": 30, "dias_retencao_relatorios": 0, "dias_retencao_logs": 30})
    cfg.criar_pastas()
    velho, novo = cfg.originais / "velho.xlsx", cfg.originais / "novo.xlsx"
    rel = cfg.relatorios / "antigo.txt"
    for p in (velho, novo, rel):
        p.write_text("x")
    antigo = time.time() - 40 * 86400
    os.utime(velho, (antigo, antigo))
    os.utime(rel, (antigo, antigo))
    r = executar_manutencao(cfg)
    assert r["originais"] == 1 and not velho.exists() and novo.exists()
    assert r["relatorios"] == 0 and rel.exists()  # retenção 0 = guardar para sempre


# ----------------------------------------------------------------------------- robo.ideias
def teste_ideias_vem_da_memoria_com_motivo_e_dono(planilha_baguncada, cfg_factory):
    from conftest import REGRA_NPS
    from robo import ideias, memoria
    from robo.pipeline import processar_arquivo
    cfg = cfg_factory(regras=[{**REGRA_NPS, "valores_permitidos": {"uf": ["SP"]}}])
    r = processar_arquivo(planilha_baguncada, cfg)
    for _ in range(3):  # o mesmo erro 3x → ideia de prevenir na origem
        memoria.registrar_execucao(cfg, r)
    lista = ideias.gerar(cfg)
    assert lista and all(i["motivo"] and i["primeiro_passo"] and i["dono"] for i in lista)
    assert any(i["titulo"].startswith("Prevenir na origem") for i in lista)
    assert [i["impacto"] for i in lista] == sorted((i["impacto"] for i in lista), reverse=True)


# ----------------------------------------------------------------------------- robo.painel.configuracao
def teste_configuracao_edita_so_o_permitido_e_preserva_comentarios(tmp_path):
    from robo.painel import configuracao
    arq = tmp_path / "config.yaml"
    arq.write_text("# meu comentário\nbanco:\n  host: localhost  # servidor\n  porta: 5432\n", encoding="utf-8")
    configuracao.definir(arq, "banco", "porta", 55432)
    texto = arq.read_text(encoding="utf-8")
    assert "# meu comentário" in texto and "# servidor" in texto
    assert yaml.safe_load(texto)["banco"] == {"host": "localhost", "porta": 55432}
    with pytest.raises(ValueError):
        configuracao.definir(arq, "painel", "senha_hash", "x")  # senha só pela rota própria
    configuracao.definir_senha(arq, "pbkdf2$abc")
    assert yaml.safe_load(arq.read_text(encoding="utf-8"))["painel"]["senha_hash"] == "pbkdf2$abc"


def teste_configuracao_cria_a_partir_do_exemplo(tmp_path):
    from robo.painel import configuracao
    arq = configuracao.garantir_arquivo(tmp_path / "novo.yaml")
    assert arq.exists() and "regras" in yaml.safe_load(arq.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- robo.painel.sistema
def teste_sistema_inicializacao_do_windows(tmp_path, monkeypatch):
    from robo.painel import sistema
    monkeypatch.setattr(sistema, "EH_WINDOWS", False)
    assert sistema.pasta_inicializacao() is None and sistema.inicializacao_ligada() is False
    with pytest.raises(RuntimeError):
        sistema.definir_inicializacao(True)
    monkeypatch.setattr(sistema, "EH_WINDOWS", True)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    pasta = sistema.pasta_inicializacao()
    pasta.mkdir(parents=True)
    assert sistema.definir_inicializacao(True) is True
    assert "/oculto" in (pasta / sistema.ARQUIVO_INICIALIZACAO).read_text(encoding="utf-16")
    assert sistema.definir_inicializacao(False) is False


def teste_sistema_texto_para_powershell_nao_deixa_injetar():
    from robo.painel.sistema import _ps_texto
    assert _ps_texto("C:/Usuário/O'Brien'; rm -r x") == "'C:/Usuário/O''Brien''; rm -r x'"


# ----------------------------------------------------------------------------- robo.comandos
def teste_comandos_status_e_varrer(planilha_baguncada, cfg_factory, capsys):
    from robo import comandos
    cfg = cfg_factory()
    caminho = cfg.logs.parent / "config_teste.yaml"
    caminho.write_text(yaml.safe_dump(cfg.dados, allow_unicode=True), encoding="utf-8")
    assert comandos.principal(["--config", str(caminho), "status"]) == 0
    assert "aguardando" in capsys.readouterr().out.lower()
    assert comandos.principal(["--config", str(caminho), "varrer"]) == 0
    assert (cfg.tratadas / "nps_outubro.xlsx").exists()


# ----------------------------------------------------------------------------- robo.habilidades.nativas
def teste_habilidades_nativas_todas_documentadas():
    from robo.habilidades import nativas
    from robo import habilidades
    nativas_ids = [h for h in habilidades.catalogo() if h.get("origem", "nativa") == "nativa"]
    assert len(nativas_ids) >= 20
    for h in nativas_ids:  # cada habilidade explica quando/como usar (é o que o funcionário consulta antes de aplicar)
        k = h["conhecimento"]
        assert len(k) >= 60 and any(m in k for m in ("QUANDO USAR", "METODOLOGIA", "LGPD")), h["id"]
    assert callable(nativas.normalizar_documento)


# ----------------------------------------------------------------------------- robo.__main__
def teste_python_menos_m_robo_abre_a_ajuda():
    import subprocess
    import sys
    from robo.config import RAIZ_PROJETO
    r = subprocess.run([sys.executable, "-m", "robo", "--help"], cwd=RAIZ_PROJETO, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "Bases-Limpeza" in r.stdout and "demo" in r.stdout
