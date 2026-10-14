-- titulo: CSAT geral e por canal
-- pergunta: Qual a satisfação com o atendimento em cada canal?
-- como_ler: CSAT = % de notas 4 e 5 (top-2-box) numa escala de 1 a 5. A linha "TOTAL" é o geral.
-- requer: tratado.fato_csat (nota_csat de 1 a 5, canal)
SELECT
    coalesce(canal, 'TOTAL')                                          AS canal,
    count(*)                                                          AS respostas,
    round(avg(nota_csat), 2)                                          AS nota_media,
    round(100.0 * count(*) FILTER (WHERE nota_csat >= 4) / count(*), 1) AS csat_pct
FROM tratado.fato_csat
WHERE nota_csat IS NOT NULL
GROUP BY ROLLUP (canal)
ORDER BY canal NULLS LAST;
