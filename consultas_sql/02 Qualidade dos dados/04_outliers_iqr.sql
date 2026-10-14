-- titulo: Valores atípicos (outliers) pelo método IQR
-- pergunta: Há valores muito fora do padrão (ex.: venda de R$ 1 milhão digitada errado)?
-- como_ler: Outlier = abaixo de Q1 − 1,5×IQR ou acima de Q3 + 1,5×IQR. Revise antes de excluir: pode ser real.
-- requer: tratado.vendas (valor)
WITH quartis AS (
    SELECT
        percentile_cont(0.25) WITHIN GROUP (ORDER BY valor) AS q1,
        percentile_cont(0.75) WITHIN GROUP (ORDER BY valor) AS q3
    FROM tratado.vendas
)
SELECT
    v.*,
    round((q.q1 - 1.5 * (q.q3 - q.q1))::numeric, 2) AS limite_inferior,
    round((q.q3 + 1.5 * (q.q3 - q.q1))::numeric, 2) AS limite_superior
FROM tratado.vendas AS v
CROSS JOIN quartis AS q
WHERE v.valor < q.q1 - 1.5 * (q.q3 - q.q1)
   OR v.valor > q.q3 + 1.5 * (q.q3 - q.q1)
ORDER BY v.valor DESC;
