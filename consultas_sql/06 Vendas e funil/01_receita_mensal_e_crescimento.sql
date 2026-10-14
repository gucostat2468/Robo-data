-- titulo: Receita mensal e crescimento
-- pergunta: Como a receita evolui e quanto cresce mês a mês?
-- como_ler: crescimento_pct compara com o mês anterior; ticket_medio = receita ÷ vendas.
-- requer: tratado.vendas (data_venda, valor)
WITH mensal AS (
    SELECT date_trunc('month', data_venda)::date AS mes, count(*) AS vendas, sum(valor) AS receita
    FROM tratado.vendas
    GROUP BY 1
)
SELECT
    mes,
    vendas,
    round(receita::numeric, 2)                                                       AS receita,
    round((receita / vendas)::numeric, 2)                                            AS ticket_medio,
    round((100 * (receita / nullif(lag(receita) OVER (ORDER BY mes), 0) - 1))::numeric, 1) AS crescimento_pct
FROM mensal
ORDER BY mes;
