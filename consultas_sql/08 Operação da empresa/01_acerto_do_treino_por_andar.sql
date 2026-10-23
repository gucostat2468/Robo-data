-- titulo: Acerto do treino por andar e nível (últimos 7 dias)
-- pergunta: Em que andar e em que nível de dificuldade a equipe mais erra no treino?
-- como_ler: Taxa de acerto = tentativas certas / tentativas. Nível de dificuldade 1 (fácil) a 4 (difícil).
-- requer: robo.memoria_treino_tentativas
SELECT andar, nivel, count(*) AS tentativas, sum(acertou) AS acertos,
       round(100.0 * sum(acertou) / count(*), 1) AS taxa_acerto_pct
FROM robo.memoria_treino_tentativas
WHERE data_hora::timestamp >= now() - interval '7 days'
GROUP BY andar, nivel
ORDER BY andar, nivel;
