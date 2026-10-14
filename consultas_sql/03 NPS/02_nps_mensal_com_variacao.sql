-- titulo: NPS mensal com variação
-- pergunta: Como o NPS evolui mês a mês?
-- como_ler: variacao_pontos compara com o mês anterior. Variação menor que a margem de erro não é mudança real (veja a consulta de teste de diferença).
-- requer: tratado.fato_nps (nota_nps, data_resposta)
WITH mensal AS (
    SELECT
        date_trunc('month', data_resposta)::date AS mes,
        count(*)                                 AS respostas,
        round(100.0 * (count(*) FILTER (WHERE nota_nps >= 9) - count(*) FILTER (WHERE nota_nps <= 6)) / count(*), 1) AS nps
    FROM tratado.fato_nps
    WHERE nota_nps IS NOT NULL AND data_resposta IS NOT NULL
    GROUP BY 1
)
SELECT
    mes,
    respostas,
    nps,
    nps - lag(nps) OVER (ORDER BY mes) AS variacao_pontos
FROM mensal
ORDER BY mes;
