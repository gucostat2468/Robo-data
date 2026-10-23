-- titulo: Folha: volume e salario_base por lote
-- pergunta: Quantas linhas cada lote sintético de folha tem, e qual a soma e a média de salario_base?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_folha
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(salario_base)::numeric, 2) AS soma_salario_base,
       round(avg(salario_base)::numeric, 4) AS media_salario_base, max(_processado_em) AS processado_em
FROM treino.treino_folha
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
