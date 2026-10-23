-- titulo: Funil: volume e valor_da_oportunidade por lote
-- pergunta: Quantas linhas cada lote sintético de funil tem, e qual a soma e a média de valor_da_oportunidade?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_funil
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(valor_da_oportunidade)::numeric, 2) AS soma_valor_da_oportunidade,
       round(avg(valor_da_oportunidade)::numeric, 4) AS media_valor_da_oportunidade, max(_processado_em) AS processado_em
FROM treino.treino_funil
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
