-- titulo: Pesquisa mercado: marca_avaliada com participação e nota_de_consideracao
-- pergunta: Como as linhas e a métrica se dividem por marca_avaliada no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_pesquisa_mercado
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_pesquisa_mercado ORDER BY _processado_em DESC LIMIT 1)
SELECT marca_avaliada, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(avg(nota_de_consideracao)::numeric, 4) AS media_nota_de_consideracao
FROM treino.treino_pesquisa_mercado
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY marca_avaliada
ORDER BY linhas DESC;
