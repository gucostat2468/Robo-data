"""Gera consultas_sql/07 Treino da fábrica/: duas consultas por regra de negócio, com as colunas REAIS que a esteira
carrega no schema treino (as mesmas de robo/regras_negocio.py). Rodar de novo depois de criar uma regra nova:

    python ferramentas/gerar_consultas_treino.py
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from robo import regras_negocio  # noqa: E402
from robo.sql_treino import _colunas  # noqa: E402

PASTA = RAIZ / "consultas_sql" / "07 Treino da fábrica"
OP = {"soma": "sum", "media": "avg", "nps": "avg"}


def main():
    PASTA.mkdir(parents=True, exist_ok=True)
    for n, r in enumerate(regras_negocio.REGRAS, 1):
        met, seg = _colunas(r)
        tab = f"treino.treino_{r.id}"
        nome = r.id.replace("_", " ")
        (PASTA / f"{n:02d}a_{r.id}_volume_e_metrica_por_lote.sql").write_text(
            f"-- titulo: {nome.capitalize()}: volume e {met} por lote\n"
            f"-- pergunta: Quantas linhas cada lote sintético de {nome} tem, e qual a soma e a média de {met}?\n"
            f"-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.\n"
            f"-- requer: {tab}\n"
            f"SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum({met})::numeric, 2) AS soma_{met},\n"
            f"       round(avg({met})::numeric, 4) AS media_{met}, max(_processado_em) AS processado_em\n"
            f"FROM {tab}\nGROUP BY _arquivo_origem\nORDER BY processado_em DESC;\n", encoding="utf-8")
        (PASTA / f"{n:02d}b_{r.id}_{seg}_com_participacao.sql").write_text(
            f"-- titulo: {nome.capitalize()}: {seg} com participação e {met}\n"
            f"-- pergunta: Como as linhas e a métrica se dividem por {seg} no lote mais recente?\n"
            f"-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.\n"
            f"-- requer: {tab}\n"
            f"WITH ultimo AS (SELECT _arquivo_origem FROM {tab} ORDER BY _processado_em DESC LIMIT 1)\n"
            f"SELECT {seg}, count(*) AS linhas,\n"
            f"       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,\n"
            f"       round({OP[r.op]}({met})::numeric, 4) AS {('soma' if r.op == 'soma' else 'media')}_{met}\n"
            f"FROM {tab}\nWHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)\n"
            f"GROUP BY {seg}\nORDER BY linhas DESC;\n", encoding="utf-8")
    print(f"{2 * len(regras_negocio.REGRAS)} consultas em {PASTA}")


if __name__ == "__main__":
    main()
