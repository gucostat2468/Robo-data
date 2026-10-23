-- titulo: Estoque: volume e estoque_un por lote
-- pergunta: Quantas linhas cada lote sintético de estoque tem, e qual a soma e a média de estoque_un?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_estoque
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(estoque_un)::numeric, 2) AS soma_estoque_un,
       round(avg(estoque_un)::numeric, 4) AS media_estoque_un, max(_processado_em) AS processado_em
FROM treino.treino_estoque
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
