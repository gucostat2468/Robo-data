-- titulo: Quem trabalhou com prova (etapas de job por pessoa)
-- pergunta: Cada funcionário fez quantas etapas de trabalho real, e quantas deram certo?
-- como_ler: Uma etapa de job é uma parte do trabalho feita por uma pessoa, com início e fim.
-- requer: robo.memoria_jobs_etapas
SELECT funcionario, count(*) AS etapas, sum(ok) AS ok, min(inicio) AS primeira, max(fim) AS ultima
FROM robo.memoria_jobs_etapas
WHERE funcionario IS NOT NULL
GROUP BY funcionario
ORDER BY etapas DESC;
