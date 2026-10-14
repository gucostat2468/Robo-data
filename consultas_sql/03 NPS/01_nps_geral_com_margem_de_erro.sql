-- titulo: NPS geral com margem de erro
-- pergunta: Qual é o NPS e quão confiável é esse número?
-- como_ler: NPS = %promotores (9-10) − %detratores (0-6). A margem (95% de confiança) diz o quanto o NPS pode variar só pelo acaso da amostra: NPS 40 ± 8 significa "entre 32 e 48".
-- requer: tratado.fato_nps (nota_nps)
WITH base AS (
    SELECT
        count(*)                         AS n,
        avg((nota_nps >= 9)::int)        AS p_prom,
        avg((nota_nps <= 6)::int)        AS p_det
    FROM tratado.fato_nps
    WHERE nota_nps IS NOT NULL
)
SELECT
    n                                                          AS respostas,
    round(100 * p_prom, 1)                                     AS pct_promotores,
    round(100 * (1 - p_prom - p_det), 1)                       AS pct_neutros,
    round(100 * p_det, 1)                                      AS pct_detratores,
    round(100 * (p_prom - p_det), 1)                           AS nps,
    round(100 * 1.96 * sqrt((p_prom + p_det - (p_prom - p_det) ^ 2) / nullif(n, 0)), 1) AS margem_erro_95
FROM base;
