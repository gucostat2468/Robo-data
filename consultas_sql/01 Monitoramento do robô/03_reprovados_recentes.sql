-- titulo: Reprovados recentes com motivo
-- pergunta: Quais arquivos foram reprovados e por quê?
-- como_ler: Cada linha é um arquivo reprovado com o resumo dos erros. Detalhes completos na tela Reprovados do painel.
-- requer: robo.lotes (criada automaticamente)
SELECT
    processado_em,
    arquivo,
    erros,
    avisos,
    mensagem AS resumo_dos_erros
FROM robo.lotes
WHERE status = 'reprovado'
ORDER BY processado_em DESC
LIMIT 100;
