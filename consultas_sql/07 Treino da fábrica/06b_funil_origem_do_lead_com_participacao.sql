-- titulo: Funil: origem_do_lead com participação e valor_da_oportunidade
-- pergunta: Como as linhas e a métrica se dividem por origem_do_lead no lote mais recente?
-- como_ler: Participação = parte do total de linhas do lote. Dado SINTÉTICO de treino.
-- requer: treino.treino_funil
WITH ultimo AS (SELECT _arquivo_origem FROM treino.treino_funil ORDER BY _processado_em DESC LIMIT 1)
SELECT origem_do_lead, count(*) AS linhas,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS participacao_pct,
       round(sum(valor_da_oportunidade)::numeric, 4) AS soma_valor_da_oportunidade
FROM treino.treino_funil
WHERE _arquivo_origem = (SELECT _arquivo_origem FROM ultimo)
GROUP BY origem_do_lead
ORDER BY linhas DESC;
