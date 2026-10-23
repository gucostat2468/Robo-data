-- titulo: Financeiro: volume e valor_do_titulo por lote
-- pergunta: Quantas linhas cada lote sintético de financeiro tem, e qual a soma e a média de valor_do_titulo?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_financeiro
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(valor_do_titulo)::numeric, 2) AS soma_valor_do_titulo,
       round(avg(valor_do_titulo)::numeric, 4) AS media_valor_do_titulo, max(_processado_em) AS processado_em
FROM treino.treino_financeiro
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
