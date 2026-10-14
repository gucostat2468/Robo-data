-- titulo: Linhas descartadas na limpeza
-- pergunta: Quanto de cada planilha foi descartado (duplicadas, linhas de total, linhas vazias)?
-- como_ler: Descarte alto e recorrente (acima de 5%) merece investigação: pode ser duplicidade na extração da origem.
-- requer: robo.lotes (criada automaticamente)
SELECT
    processado_em::date                                   AS dia,
    arquivo,
    linhas_entrada,
    linhas_saida,
    linhas_entrada - linhas_saida                         AS descartadas,
    round(100.0 * (linhas_entrada - linhas_saida) / nullif(linhas_entrada, 0), 1) AS pct_descartado
FROM robo.lotes
WHERE status = 'sucesso'
ORDER BY pct_descartado DESC NULLS LAST, processado_em DESC;
