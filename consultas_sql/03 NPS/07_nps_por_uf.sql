-- titulo: Ranking de NPS por UF
-- pergunta: Em quais estados a experiência é melhor ou pior?
-- como_ler: Compare cada UF com o NPS geral (coluna diferenca_vs_geral). Considere só UFs com base suficiente.
-- requer: tratado.fato_nps (nota_nps, uf)
WITH por_uf AS (
    SELECT
        uf,
        count(*) AS respostas,
        100.0 * (count(*) FILTER (WHERE nota_nps >= 9) - count(*) FILTER (WHERE nota_nps <= 6)) / count(*) AS nps
    FROM tratado.fato_nps
    WHERE nota_nps IS NOT NULL
    GROUP BY uf
),
geral AS (
    SELECT 100.0 * (count(*) FILTER (WHERE nota_nps >= 9) - count(*) FILTER (WHERE nota_nps <= 6)) / count(*) AS nps
    FROM tratado.fato_nps WHERE nota_nps IS NOT NULL
)
SELECT
    p.uf,
    p.respostas,
    round(p.nps, 1)              AS nps,
    round(p.nps - g.nps, 1)      AS diferenca_vs_geral,
    rank() OVER (ORDER BY p.nps DESC) AS posicao
FROM por_uf AS p CROSS JOIN geral AS g
ORDER BY posicao;
