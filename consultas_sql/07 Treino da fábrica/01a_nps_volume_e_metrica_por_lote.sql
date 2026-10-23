-- titulo: Nps: volume e nota_nps por lote
-- pergunta: Quantas linhas cada lote sintético de nps tem, e qual a soma e a média de nota_nps?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_nps
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(nota_nps)::numeric, 2) AS soma_nota_nps,
       round(avg(nota_nps)::numeric, 4) AS media_nota_nps, max(_processado_em) AS processado_em
FROM treino.treino_nps
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
