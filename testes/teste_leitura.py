from robo.leitura import ler_arquivo


def teste_cabecalho_abaixo_do_titulo(planilha_baguncada):
    tabelas = ler_arquivo(planilha_baguncada)
    df = tabelas["Relatório"]
    assert list(df.columns)[0] == "ID Resposta"
    assert df.attrs["linha_cabecalho"] == 3
    assert df.index[0] == 4  # número da linha no Excel


def teste_csv_ponto_e_virgula_latin1(tmp_path):
    caminho = tmp_path / "base.csv"
    caminho.write_bytes("Nome;Cidade;Valor\nJoão;São Paulo;1.234,50\nMaria;Brasília;10,00\n".encode("cp1252"))
    df = ler_arquivo(caminho)["base"]
    assert list(df.columns) == ["Nome", "Cidade", "Valor"]
    assert df.iloc[0, 0] == "João"
    assert len(df) == 2


def teste_csv_virgula(tmp_path):
    caminho = tmp_path / "b.csv"
    caminho.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    assert ler_arquivo(caminho)["b"].shape == (2, 2)
