-- titulo: Churn: plano com participação e mensalidade
-- pergunta: Como as linhas e a métrica se dividem por plano no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_churn
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_churn ORDER BY _processado_em DESC LIMIT 1)
SELECT plano, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(avg(mensalidade)::numeric, 4) AS media_mensalidade
FROM treino.treino_churn
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY plano
ORDER BY linhas DESC;
