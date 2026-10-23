-- titulo: Ponto: equipe com participação e horas_trabalhadas
-- pergunta: Como as linhas e a métrica se dividem por equipe no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_ponto
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_ponto ORDER BY _processado_em DESC LIMIT 1)
SELECT equipe, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(avg(horas_trabalhadas)::numeric, 4) AS media_horas_trabalhadas
FROM treino.treino_ponto
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY equipe
ORDER BY linhas DESC;
