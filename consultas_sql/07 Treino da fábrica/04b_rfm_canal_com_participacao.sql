-- titulo: Rfm: canal com participação e valor_total
-- pergunta: Como as linhas e a métrica se dividem por canal no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_rfm
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_rfm ORDER BY _processado_em DESC LIMIT 1)
SELECT canal, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(sum(valor_total)::numeric, 4) AS soma_valor_total
FROM treino.treino_rfm
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY canal
ORDER BY linhas DESC;
