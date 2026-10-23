-- titulo: Rfm: volume e valor_total por lote
-- pergunta: Quantas linhas cada lote sintético de rfm tem, e qual a soma e a média de valor_total?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_rfm
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(valor_total)::numeric, 2) AS soma_valor_total,
       round(avg(valor_total)::numeric, 4) AS media_valor_total, max(_processado_em) AS processado_em
FROM treino.treino_rfm
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
