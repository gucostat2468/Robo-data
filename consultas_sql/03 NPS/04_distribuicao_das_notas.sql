-- titulo: Distribuição das notas (0 a 10)
-- pergunta: Como as notas se distribuem? Há concentração em alguma nota?
-- como_ler: Muitos 7-8 (neutros) = clientes "quase lá": ações simples podem convertê-los em promotores.
-- requer: tratado.fato_nps (nota_nps)
SELECT
    nota_nps                                                AS nota,
    CASE WHEN nota_nps >= 9 THEN 'Promotor'
         WHEN nota_nps >= 7 THEN 'Neutro'
         ELSE 'Detrator' END                                AS grupo,
    count(*)                                                AS respostas,
    round(100.0 * count(*) / sum(count(*)) OVER (), 1)      AS pct
FROM tratado.fato_nps
WHERE nota_nps IS NOT NULL
GROUP BY nota_nps
ORDER BY nota_nps;
