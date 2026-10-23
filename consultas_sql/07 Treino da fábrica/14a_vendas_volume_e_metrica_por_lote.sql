-- titulo: Vendas: volume e valor_da_venda por lote
-- pergunta: Quantas linhas cada lote sintético de vendas tem, e qual a soma e a média de valor_da_venda?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_vendas
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(valor_da_venda)::numeric, 2) AS soma_valor_da_venda,
       round(avg(valor_da_venda)::numeric, 4) AS media_valor_da_venda, max(_processado_em) AS processado_em
FROM treino.treino_vendas
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
