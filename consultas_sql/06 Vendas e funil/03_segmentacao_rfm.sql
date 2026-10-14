-- titulo: Segmentação RFM de clientes
-- pergunta: Quais clientes são campeões, quais estão em risco e quais estão hibernando?
-- como_ler: R = recência (dias desde a última compra), F = frequência, M = valor. Notas de 1 a 5 (5 = melhor). Use os segmentos para campanhas diferentes.
-- requer: tratado.vendas (id_cliente, data_venda, valor)
WITH referencia AS (SELECT max(data_venda) AS hoje FROM tratado.vendas),
clientes AS (
    SELECT id_cliente,
           (SELECT hoje FROM referencia) - max(data_venda) AS recencia_dias,
           count(*)                                        AS frequencia,
           sum(valor)                                      AS valor_total
    FROM tratado.vendas
    GROUP BY id_cliente
),
notas AS (
    SELECT *,
           ntile(5) OVER (ORDER BY recencia_dias DESC) AS r,
           ntile(5) OVER (ORDER BY frequencia)         AS f,
           ntile(5) OVER (ORDER BY valor_total)        AS m
    FROM clientes
)
SELECT
    id_cliente, recencia_dias, frequencia, round(valor_total::numeric, 2) AS valor_total, r, f, m,
    CASE
        WHEN r >= 4 AND f >= 4 THEN 'Campeões'
        WHEN r >= 3 AND f >= 3 THEN 'Leais'
        WHEN r >= 4 AND f <= 2 THEN 'Novos / promissores'
        WHEN r <= 2 AND f >= 3 THEN 'Em risco'
        WHEN r <= 2 AND f <= 2 THEN 'Hibernando'
        ELSE 'Precisam de atenção'
    END AS segmento
FROM notas
ORDER BY r DESC, f DESC, m DESC;
