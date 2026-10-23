-- titulo: Educacao: volume e media_final por lote
-- pergunta: Quantas linhas cada lote sintético de educacao tem, e qual a soma e a média de media_final?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_educacao
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(media_final)::numeric, 2) AS soma_media_final,
       round(avg(media_final)::numeric, 4) AS media_media_final, max(_processado_em) AS processado_em
FROM treino.treino_educacao
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
