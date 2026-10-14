-- titulo: Tamanho das tabelas por camada
-- pergunta: Quanto espaço e quantas linhas cada tabela ocupa no banco?
-- como_ler: Contagem aproximada (estatística do PostgreSQL). Útil para planejar limpeza da camada bruta.
-- requer: nada (catálogo do PostgreSQL)
SELECT
    schemaname                                        AS camada,
    relname                                           AS tabela,
    n_live_tup                                        AS linhas_aprox,
    pg_size_pretty(pg_total_relation_size(relid))     AS tamanho
FROM pg_stat_user_tables
WHERE schemaname IN ('bruto', 'tratado', 'analitico', 'robo')
ORDER BY pg_total_relation_size(relid) DESC;
