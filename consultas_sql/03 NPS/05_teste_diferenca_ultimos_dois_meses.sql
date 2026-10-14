-- titulo: A mudança do NPS é real? (teste entre os 2 últimos meses)
-- pergunta: A variação do NPS do último mês é estatisticamente significativa ou é ruído?
-- como_ler: |z| ≥ 1,96 → diferença significativa a 95% de confiança. Abaixo disso, não comunique como "melhora" ou "piora".
-- requer: tratado.fato_nps (nota_nps, data_resposta)
WITH mensal AS (
    SELECT
        date_trunc('month', data_resposta)::date  AS mes,
        count(*)                                  AS n,
        avg((nota_nps >= 9)::int)                 AS p_prom,
        avg((nota_nps <= 6)::int)                 AS p_det
    FROM tratado.fato_nps
    WHERE nota_nps IS NOT NULL AND data_resposta IS NOT NULL
    GROUP BY 1
),
ultimos AS (
    SELECT *, row_number() OVER (ORDER BY mes DESC) AS ordem,
           (p_prom + p_det - (p_prom - p_det) ^ 2) / n AS variancia
    FROM mensal
),
comparacao AS (
    SELECT
        a.mes AS mes_atual, b.mes AS mes_anterior,
        round(100 * (a.p_prom - a.p_det), 1) AS nps_atual,
        round(100 * (b.p_prom - b.p_det), 1) AS nps_anterior,
        100 * ((a.p_prom - a.p_det) - (b.p_prom - b.p_det)) AS diferenca,
        100 * sqrt(a.variancia + b.variancia)              AS erro_padrao
    FROM ultimos a JOIN ultimos b ON a.ordem = 1 AND b.ordem = 2
)
SELECT
    mes_atual, nps_atual, mes_anterior, nps_anterior,
    round(diferenca, 1)                                   AS diferenca_pontos,
    round(diferenca / nullif(erro_padrao, 0), 2)          AS z,
    CASE WHEN abs(diferenca / nullif(erro_padrao, 0)) >= 1.96
         THEN 'Significativa (95%)' ELSE 'Não significativa — pode ser acaso' END AS conclusao
FROM comparacao;
