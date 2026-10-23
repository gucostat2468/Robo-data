-- titulo: Csat ces: canal_de_atendimento com participação e nota_csat
-- pergunta: Como as linhas e a métrica se dividem por canal_de_atendimento no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_csat_ces
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_csat_ces ORDER BY _processado_em DESC LIMIT 1)
SELECT canal_de_atendimento, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(avg(nota_csat)::numeric, 4) AS media_nota_csat
FROM treino.treino_csat_ces
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY canal_de_atendimento
ORDER BY linhas DESC;
