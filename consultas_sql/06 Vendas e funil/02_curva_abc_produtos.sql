-- titulo: Curva ABC de produtos
-- pergunta: Quais produtos concentram a receita?
-- como_ler: A = até 80% da receita acumulada (foco máximo), B = até 95%, C = o restante (cauda longa).
-- requer: tratado.vendas (produto, valor)
WITH por_produto AS (
    SELECT produto, sum(valor) AS receita FROM tratado.vendas GROUP BY produto
),
acumulado AS (
    SELECT produto, receita,
           sum(receita) OVER (ORDER BY receita DESC, produto ROWS UNBOUNDED PRECEDING) / sum(receita) OVER () AS pct_acum
    FROM por_produto
)
SELECT
    produto,
    round(receita::numeric, 2)                       AS receita,
    round((100 * pct_acum)::numeric, 1)              AS pct_acumulado,
    CASE WHEN pct_acum <= 0.80 THEN 'A' WHEN pct_acum <= 0.95 THEN 'B' ELSE 'C' END AS classe
FROM acumulado
ORDER BY receita DESC;
