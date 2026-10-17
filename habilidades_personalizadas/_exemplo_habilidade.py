"""MODELO de habilidade personalizada (arquivos que começam com "_" são ignorados).

Para criar a sua:
  1. Copie este arquivo com outro nome, por exemplo: marcar_vip.py
  2. Ajuste id, nome, parâmetros e a lógica.
  3. Salve. No painel (Agentes e habilidades) ela aparece no catálogo, pronta para adicionar a um agente.

Prova técnica (OBRIGATÓRIA): sem ela o RH não aprova nenhum agente que use a habilidade.
  Cada prova é (descrição, tabela de exemplo, parâmetros, conferência(resultado, relatorio) -> True/False).

Regras de ouro:
  - receba df (tabela), p (parâmetros já validados) e ctx (onde registrar ocorrências);
  - devolva SEMPRE a tabela (df);
  - use ctx.erro(...) para reprovar o arquivo, ctx.aviso(...) para alertar e ctx.info(...) para documentar.
"""

import pandas as pd

from robo.habilidades import Param, habilidade


@habilidade(
    id="marcar_vip",
    nome="Marcar clientes VIP",
    categoria="Minhas habilidades",
    descricao="Cria a coluna vip (Sim/Não) para valores acima de um limite.",
    parametros=[
        Param("coluna", "coluna", "Coluna de valor"),
        Param("limite", "numero", "Valor mínimo para ser VIP", padrao=1000),
    ],
    conhecimento="QUANDO USAR: priorizar clientes de maior valor em ações de relacionamento.",
)
def marcar_vip(df, p, ctx):
    valores = df[p["coluna"]].astype("float64")
    df["vip"] = (valores >= p["limite"]).map({True: "Sim", False: "Não"})
    ctx.info(f"{int((df['vip'] == 'Sim').sum())} cliente(s) VIP", coluna=p["coluna"])
    return df


# prova técnica: um caso com resposta conhecida (500 não é VIP, 1500 é)
marcar_vip.provas = [
    ("Marca VIP só acima do limite", pd.DataFrame({"valor": [500.0, 1500.0]}), {"coluna": "valor", "limite": 1000},
     lambda resultado, relatorio: resultado["vip"].tolist() == ["Não", "Sim"]),
]
