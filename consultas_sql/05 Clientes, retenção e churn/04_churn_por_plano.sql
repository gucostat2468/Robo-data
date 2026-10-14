-- titulo: Churn acumulado por plano
-- pergunta: Qual plano perde mais clientes?
-- como_ler: Percentual de todos os clientes que já entraram no plano e cancelaram. Cruze com NPS por plano para entender a causa.
-- requer: tratado.clientes (plano, data_saida)
SELECT
    plano,
    count(*)                                                                AS clientes,
    count(*) FILTER (WHERE data_saida IS NOT NULL)                          AS cancelados,
    round(100.0 * count(*) FILTER (WHERE data_saida IS NOT NULL) / count(*), 1) AS churn_acumulado_pct
FROM tratado.clientes
GROUP BY plano
ORDER BY churn_acumulado_pct DESC;
