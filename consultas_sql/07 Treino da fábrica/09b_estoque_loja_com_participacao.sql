-- titulo: Estoque: loja com participação e estoque_un
-- pergunta: Como as linhas e a métrica se dividem por loja no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_estoque
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_estoque ORDER BY _processado_em DESC LIMIT 1)
SELECT loja, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(sum(estoque_un)::numeric, 4) AS soma_estoque_un
FROM treino.treino_estoque
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY loja
ORDER BY linhas DESC;
