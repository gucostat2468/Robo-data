-- titulo: Leads: volume e investimento por lote
-- pergunta: Quantas linhas cada lote sintético de leads tem, e qual a soma e a média de investimento?
-- como_ler: Uma linha por planilha da fábrica (TREINO_*). Dado SINTÉTICO de treino, nunca produção.
-- requer: treino.treino_leads
SELECT _arquivo_origem AS lote, count(*) AS linhas, round(sum(investimento)::numeric, 2) AS soma_investimento,
       round(avg(investimento)::numeric, 4) AS media_investimento, max(_processado_em) AS processado_em
FROM treino.treino_leads
GROUP BY _arquivo_origem
ORDER BY processado_em DESC;
