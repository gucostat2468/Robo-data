-- titulo: Completude por coluna
-- pergunta: Qual o percentual de preenchimento de cada coluna de uma tabela?
-- como_ler: Colunas com menos de 80% de preenchimento não devem sustentar conclusões sozinhas. Troque tratado.fato_nps pela tabela que quiser.
-- requer: tratado.fato_nps (ou qualquer tabela: troque o nome na linha FROM)
SELECT
    j.key                                                                   AS coluna,
    count(*)                                                                AS linhas,
    count(*) FILTER (WHERE j.value = 'null'::jsonb)                         AS vazios,
    round(100.0 * count(*) FILTER (WHERE j.value <> 'null'::jsonb) / count(*), 1) AS pct_preenchido
FROM tratado.fato_nps AS t
CROSS JOIN LATERAL jsonb_each(to_jsonb(t)) AS j
GROUP BY j.key
ORDER BY pct_preenchido, coluna;
