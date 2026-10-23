-- titulo: Csat ces: volume e nota_csat por lote
-- pergunta: Quantas linhas cada lote sintético de csat ces tem, e qual a soma e a média de nota_csat?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_csat_ces
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(nota_csat)::numeric, 2) AS soma_nota_csat,
       round(avg(nota_csat)::numeric, 4) AS media_nota_csat, max(_processado_em) AS processado_em
FROM treino.treino_csat_ces
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
