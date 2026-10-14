-- titulo: CSAT mensal
-- pergunta: A satisfação com o atendimento está melhorando?
-- como_ler: Acompanhe junto com o volume: meses com pouca resposta oscilam mais.
-- requer: tratado.fato_csat (nota_csat, data_resposta)
SELECT
    date_trunc('month', data_resposta)::date                           AS mes,
    count(*)                                                           AS respostas,
    round(100.0 * count(*) FILTER (WHERE nota_csat >= 4) / count(*), 1) AS csat_pct
FROM tratado.fato_csat
WHERE nota_csat IS NOT NULL
GROUP BY 1
ORDER BY 1;
