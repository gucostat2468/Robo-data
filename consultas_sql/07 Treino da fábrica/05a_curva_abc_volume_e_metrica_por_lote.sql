-- titulo: Curva abc: volume e faturamento por lote
-- pergunta: Quantas linhas cada lote sintético de curva abc tem, e qual a soma e a média de faturamento?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_curva_abc
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(faturamento)::numeric, 2) AS soma_faturamento,
       round(avg(faturamento)::numeric, 4) AS media_faturamento, max(_processado_em) AS processado_em
FROM treino.treino_curva_abc
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
