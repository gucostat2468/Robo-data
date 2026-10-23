-- titulo: Educacao: curso com participação e media_final
-- pergunta: Como as linhas e a métrica se dividem por curso no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_educacao
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_educacao ORDER BY _processado_em DESC LIMIT 1)
SELECT curso, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(avg(media_final)::numeric, 4) AS media_media_final
FROM treino.treino_educacao
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY curso
ORDER BY linhas DESC;
