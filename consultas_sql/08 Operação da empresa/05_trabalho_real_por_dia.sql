-- titulo: Trabalho real por dia (jobs com evidência)
-- pergunta: Quanto trabalho com prova a empresa fez por dia, e de que tipo?
-- como_ler: Só conta job FECHADO (com fim). Plantão de rotina não é trabalho e não aparece aqui.
-- requer: robo.memoria_jobs
SELECT inicio::date AS dia, tipo, origem, count(*) AS jobs,
       count(*) FILTER (WHERE estado = 'concluido') AS concluidos,
       round(avg(extract(epoch FROM fim::timestamp - inicio::timestamp))::numeric, 1) AS segundos_medios
FROM robo.memoria_jobs
WHERE fim IS NOT NULL
GROUP BY dia, tipo, origem
ORDER BY dia DESC, jobs DESC;
