-- titulo: Erros mais frequentes
-- pergunta: Quais problemas mais se repetem nas planilhas que chegam?
-- como_ler: Os primeiros da lista são os que mais custam retrabalho. Leve-os para a área que gera a planilha (corrigir na origem).
-- requer: robo.ocorrencias (criada automaticamente)
SELECT
    mensagem,
    coalesce(coluna, '—')                AS coluna,
    count(DISTINCT arquivo)              AS arquivos_afetados,
    count(*)                             AS vezes,
    sum(quantidade)                      AS celulas_afetadas,
    max(processado_em)::date             AS ultima_vez
FROM robo.ocorrencias
WHERE nivel = 'ERRO'
GROUP BY 1, 2
ORDER BY arquivos_afetados DESC, vezes DESC;
