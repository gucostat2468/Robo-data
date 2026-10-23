-- titulo: Nps: curso com participação e nota_nps
-- pergunta: Como as linhas e a métrica se dividem por curso no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_nps
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_nps ORDER BY _processado_em DESC LIMIT 1)
SELECT curso, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(avg(nota_nps)::numeric, 4) AS media_nota_nps
FROM treino.treino_nps
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY curso
ORDER BY linhas DESC;
