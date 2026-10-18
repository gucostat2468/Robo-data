"""O banco de registros documentado e protegido por inteiro: tabela nova sem descrição ou sem proteção reprova o teste."""

from robo import dicionario_dados
from robo.config import RAIZ_PROJETO


def teste_toda_tabela_documentada_e_protegida(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    e = dicionario_dados.estado(cfg)
    assert e["sem_documentacao"] == [], "documente em robo/dicionario_dados.py e rode: python -m robo banco-doc"
    assert e["desprotegidas"] == []
    assert e["integridade"] == "ok" and e["modo_diario"] == "wal"
    assert {t["tabela"] for t in e["tabelas"]} == set(dicionario_dados.TABELAS)
    assert all(t["imutavel"] for t in e["tabelas"] if t["regra"] == dicionario_dados.IMUTAVEL and t["tabela"] in
               ("treino_tentativas", "treino_niveis_eventos", "decisoes_eventos", "sala_eventos", "registro_conhecimento"))
    assert not e["postgres"]["ok"] and "desligado" in e["postgres"]["motivo"]


def teste_documentacao_do_banco_esta_em_dia():
    atual = (RAIZ_PROJETO / "documentacao" / "banco_de_dados.md").read_text(encoding="utf-8")
    assert atual == dicionario_dados.gerar_markdown(), "rode: python -m robo banco-doc"
