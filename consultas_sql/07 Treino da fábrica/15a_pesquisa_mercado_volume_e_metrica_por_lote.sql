-- titulo: Pesquisa mercado: volume e nota_de_consideracao por lote
-- pergunta: Quantas linhas cada lote sintético de pesquisa mercado tem, e qual a soma e a média de nota_de_consideracao?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_pesquisa_mercado
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(nota_de_consideracao)::numeric, 2) AS soma_nota_de_consideracao,
       round(avg(nota_de_consideracao)::numeric, 4) AS media_nota_de_consideracao, max(_processado_em) AS processado_em
FROM treino.treino_pesquisa_mercado
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
