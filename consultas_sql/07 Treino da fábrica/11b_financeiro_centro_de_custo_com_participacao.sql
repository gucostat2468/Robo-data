-- titulo: Financeiro: centro_de_custo com participação e valor_do_titulo
-- pergunta: Como as linhas e a métrica se dividem por centro_de_custo no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_financeiro
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_financeiro ORDER BY _processado_em DESC LIMIT 1)
SELECT centro_de_custo, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(sum(valor_do_titulo)::numeric, 4) AS soma_valor_do_titulo
FROM treino.treino_financeiro
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY centro_de_custo
ORDER BY linhas DESC;
