-- titulo: CSAT geral e por canal
-- pergunta: Qual a satisfação com o atendimento em cada canal?
-- como_ler: CSAT = % de notas 4 e 5 (top-2-box) numa escala de 1 a 5. A linha "TOTAL" é o geral.
-- requer: tratado.fato_csat (nota_csat de 1 a 5, canal)
SELECT
    CASE WHEN grouping(canal) = 1 THEN 'TOTAL' ELSE coalesce(canal, '(sem canal)') END AS canal,
    count(*)                                                          AS respostas,
    round(avg(nota_csat), 2)                                          AS nota_media,
    round(100.0 * count(*) FILTER (WHERE nota_csat >= 4) / count(*), 1) AS csat_pct
FROM tratado.fato_csat
WHERE nota_csat IS NOT NULL
GROUP BY ROLLUP (canal)
ORDER BY grouping(canal), canal;  -- TOTAL sempre por último
