-- titulo: Vendas: regiao com participação e valor_da_venda
-- pergunta: Como as linhas e a métrica se dividem por regiao no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_vendas
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_vendas ORDER BY _processado_em DESC LIMIT 1)
SELECT regiao, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(sum(valor_da_venda)::numeric, 4) AS soma_valor_da_venda
FROM treino.treino_vendas
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY regiao
ORDER BY linhas DESC;
