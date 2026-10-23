-- titulo: Demandas por andar, nível e resultado
-- pergunta: Cada andar recebeu trabalho em que nível, e quanto foi concluído?
-- como_ler: Origem demanda_sintetica = trabalho distribuído pela equipe de demandas (dados sintéticos).
-- requer: robo.memoria_solicitacoes
SELECT andar, plano::jsonb ->> 'nivel' AS nivel, estado, count(*) AS demandas
FROM robo.memoria_solicitacoes
WHERE origem = 'demanda_sintetica'
GROUP BY andar, nivel, estado
ORDER BY andar, nivel, estado;
