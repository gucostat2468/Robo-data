-- titulo: Curva abc: categoria com participação e faturamento
-- pergunta: Como as linhas e a métrica se dividem por categoria no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_curva_abc
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_curva_abc ORDER BY _processado_em DESC LIMIT 1)
SELECT categoria, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(sum(faturamento)::numeric, 4) AS soma_faturamento
FROM treino.treino_curva_abc
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY categoria
ORDER BY linhas DESC;
