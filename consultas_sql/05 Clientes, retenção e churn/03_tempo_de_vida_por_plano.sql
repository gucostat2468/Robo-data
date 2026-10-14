-- titulo: Tempo de vida do cliente por plano
-- pergunta: Quanto tempo, em média, um cliente fica em cada plano?
-- como_ler: Use a mediana (menos sensível a extremos). Clientes ativos contam até a data mais recente da base.
-- requer: tratado.clientes (data_entrada, data_saida, plano)
WITH referencia AS (
    SELECT greatest(max(data_entrada), coalesce(max(data_saida), max(data_entrada))) AS hoje FROM tratado.clientes
)
SELECT
    plano,
    count(*)                                                                              AS clientes,
    count(*) FILTER (WHERE data_saida IS NOT NULL)                                        AS cancelados,
    round(avg(coalesce(data_saida, r.hoje) - data_entrada) / 30.4, 1)                     AS meses_medio,
    round((percentile_cont(0.5) WITHIN GROUP (ORDER BY coalesce(data_saida, r.hoje) - data_entrada) / 30.4)::numeric, 1) AS meses_mediana
FROM tratado.clientes CROSS JOIN referencia AS r
GROUP BY plano
ORDER BY meses_mediana DESC;
