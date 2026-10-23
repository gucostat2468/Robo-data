-- titulo: Ponto: volume e horas_trabalhadas por lote
-- pergunta: Quantas linhas cada lote sintético de ponto tem, e qual a soma e a média de horas_trabalhadas?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_ponto
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(horas_trabalhadas)::numeric, 2) AS soma_horas_trabalhadas,
       round(avg(horas_trabalhadas)::numeric, 4) AS media_horas_trabalhadas, max(_processado_em) AS processado_em
FROM treino.treino_ponto
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
