-- titulo: Cargas por dia
-- pergunta: Quantos arquivos o robô processou por dia, e quantos foram reprovados?
-- como_ler: Acompanhe a taxa de aprovação. Queda brusca indica mudança no layout das planilhas de origem.
-- requer: robo.lotes (criada automaticamente)
SELECT
    processado_em::date                                        AS dia,
    count(*)                                                   AS arquivos,
    count(*) FILTER (WHERE status = 'sucesso')                 AS aprovados,
    count(*) FILTER (WHERE status = 'reprovado')               AS reprovados,
    round(100.0 * count(*) FILTER (WHERE status = 'sucesso') / count(*), 1) AS pct_aprovacao,
    sum(linhas_saida)                                          AS linhas_publicadas
FROM robo.lotes
GROUP BY 1
ORDER BY 1 DESC;
