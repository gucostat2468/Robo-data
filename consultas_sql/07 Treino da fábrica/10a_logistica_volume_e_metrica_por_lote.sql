-- titulo: Logistica: volume e atraso_dias por lote
-- pergunta: Quantas linhas cada lote sintético de logistica tem, e qual a soma e a média de atraso_dias?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_logistica
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(atraso_dias)::numeric, 2) AS soma_atraso_dias,
       round(avg(atraso_dias)::numeric, 4) AS media_atraso_dias, max(_processado_em) AS processado_em
FROM treino.treino_logistica
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
