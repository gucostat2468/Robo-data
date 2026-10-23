-- titulo: Folha: departamento com participação e salario_base
-- pergunta: Como as linhas e a métrica se dividem por departamento no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_folha
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_folha ORDER BY _processado_em DESC LIMIT 1)
SELECT departamento, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(sum(salario_base)::numeric, 4) AS soma_salario_base
FROM treino.treino_folha
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY departamento
ORDER BY linhas DESC;
