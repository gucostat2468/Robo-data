-- titulo: Leads: canal com participação e investimento
-- pergunta: Como as linhas e a métrica se dividem por canal no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_leads
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_leads ORDER BY _processado_em DESC LIMIT 1)
SELECT canal, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(sum(investimento)::numeric, 4) AS soma_investimento
FROM treino.treino_leads
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY canal
ORDER BY linhas DESC;
