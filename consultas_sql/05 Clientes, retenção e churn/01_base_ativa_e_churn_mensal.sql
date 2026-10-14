-- titulo: Base ativa e churn mensal
-- pergunta: Quantos clientes entram, saem e qual a taxa de cancelamento (churn) por mês?
-- como_ler: churn_pct = cancelados no mês ÷ ativos no início do mês. Compare com a meta e com a sazonalidade do ano anterior.
-- requer: tratado.clientes (id_cliente, data_entrada, data_saida vazia = ativo)
WITH limites AS (
    SELECT date_trunc('month', min(data_entrada))::date AS inicio,
           date_trunc('month', greatest(max(data_entrada), coalesce(max(data_saida), max(data_entrada))))::date AS fim
    FROM tratado.clientes
),
meses AS (
    SELECT m::date AS mes FROM limites, generate_series(inicio, fim, interval '1 month') AS m
),
movimento AS (
    SELECT
        m.mes,
        count(c.id_cliente) FILTER (WHERE c.data_entrada < m.mes AND (c.data_saida IS NULL OR c.data_saida >= m.mes)) AS ativos_inicio,
        count(c.id_cliente) FILTER (WHERE c.data_entrada >= m.mes AND c.data_entrada < m.mes + interval '1 month')  AS novos,
        count(c.id_cliente) FILTER (WHERE c.data_saida >= m.mes AND c.data_saida < m.mes + interval '1 month')      AS cancelados
    FROM meses AS m
    CROSS JOIN tratado.clientes AS c
    GROUP BY m.mes
)
SELECT
    mes, ativos_inicio, novos, cancelados,
    ativos_inicio + novos - cancelados                           AS ativos_fim,
    round(100.0 * cancelados / nullif(ativos_inicio, 0), 2)      AS churn_pct
FROM movimento
ORDER BY mes;
