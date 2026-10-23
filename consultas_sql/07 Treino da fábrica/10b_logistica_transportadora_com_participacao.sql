-- titulo: Logistica: transportadora com participação e atraso_dias
-- pergunta: Como as linhas e a métrica se dividem por transportadora no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_logistica
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_logistica ORDER BY _processado_em DESC LIMIT 1)
SELECT transportadora, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(avg(atraso_dias)::numeric, 4) AS media_atraso_dias
FROM treino.treino_logistica
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY transportadora
ORDER BY linhas DESC;
