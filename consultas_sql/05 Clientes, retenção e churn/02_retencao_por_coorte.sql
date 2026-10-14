-- titulo: Retenção por coorte (safra de entrada)
-- pergunta: Dos clientes que entraram em cada mês, quantos % continuam ativos após N meses?
-- como_ler: Leia cada coorte na horizontal. Queda forte nos meses 1-3 indica problema de onboarding; no Power BI, use uma matriz (coorte × mês de vida) com formatação condicional.
-- requer: tratado.clientes (id_cliente, data_entrada, data_saida)
WITH base AS (
    SELECT id_cliente, date_trunc('month', data_entrada)::date AS coorte, data_saida
    FROM tratado.clientes
    WHERE data_entrada IS NOT NULL
),
limite AS (
    SELECT date_trunc('month', greatest(max(data_entrada), coalesce(max(data_saida), max(data_entrada))))::date AS ultimo
    FROM tratado.clientes
),
grade AS (
    SELECT b.coorte, b.id_cliente, b.data_saida, m::date AS mes
    FROM base AS b
    CROSS JOIN limite AS l
    CROSS JOIN LATERAL generate_series(b.coorte, l.ultimo, interval '1 month') AS m
)
SELECT
    coorte,
    ((date_part('year', mes) - date_part('year', coorte)) * 12 + date_part('month', mes) - date_part('month', coorte))::int AS mes_de_vida,
    count(*)                                                                                       AS clientes_na_coorte,
    count(*) FILTER (WHERE data_saida IS NULL OR data_saida >= mes + interval '1 month')           AS ainda_ativos,
    round(100.0 * count(*) FILTER (WHERE data_saida IS NULL OR data_saida >= mes + interval '1 month') / count(*), 1) AS retencao_pct
FROM grade
GROUP BY coorte, mes
ORDER BY coorte, mes_de_vida;
