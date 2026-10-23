-- titulo: Fábrica de planilhas: lotes por regra e resultado
-- pergunta: Quantos lotes sintéticos cada regra de negócio teve, e a esteira acertou o gabarito?
-- como_ler: conferido_ok = a esteira entregou o que o gabarito manda; divergente = a esteira errou.
-- requer: robo.memoria_fabrica_lotes
SELECT regra, estado, count(*) AS lotes, sum(linhas) AS linhas, max(data_hora) AS ultimo
FROM robo.memoria_fabrica_lotes
GROUP BY regra, estado
ORDER BY regra, estado;
