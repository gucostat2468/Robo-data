-- titulo: Churn: volume e mensalidade por lote
-- pergunta: Quantas linhas cada lote sintético de churn tem, e qual a soma e a média de mensalidade?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_churn
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(mensalidade)::numeric, 2) AS soma_mensalidade,
       round(avg(mensalidade)::numeric, 4) AS media_mensalidade, max(_processado_em) AS processado_em
FROM treino.treino_churn
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
