-- titulo: Pareto dos motivos de insatisfação
-- pergunta: Quais poucos motivos explicam a maior parte da insatisfação?
-- como_ler: Os motivos até ~80% do acumulado são a prioridade (princípio de Pareto). Considera notas 1 e 2.
-- requer: tratado.fato_csat (nota_csat, motivo)
WITH motivos AS (
    SELECT coalesce(motivo, 'Não informado') AS motivo, count(*) AS insatisfeitos
    FROM tratado.fato_csat
    WHERE nota_csat <= 2
    GROUP BY 1
)
SELECT
    motivo,
    insatisfeitos,
    round(100.0 * insatisfeitos / sum(insatisfeitos) OVER (), 1) AS pct,
    round(100.0 * sum(insatisfeitos) OVER (ORDER BY insatisfeitos DESC, motivo ROWS UNBOUNDED PRECEDING)
          / sum(insatisfeitos) OVER (), 1)                       AS pct_acumulado
FROM motivos
ORDER BY insatisfeitos DESC, motivo;
