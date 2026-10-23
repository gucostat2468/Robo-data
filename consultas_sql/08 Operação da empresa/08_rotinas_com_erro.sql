-- titulo: Rotinas: execuções, erros e duração
-- pergunta: Quais rotinas automáticas mais falham ou mais demoram?
-- como_ler: status 'erro' = a rotina quebrou; 'em_dia' = verificou e não tinha o que fazer.
-- requer: robo.memoria_rotinas_execucoes
SELECT nome, count(*) AS execucoes, count(*) FILTER (WHERE status = 'erro') AS erros,
       round(avg(segundos)::numeric, 2) AS segundos_medios, max(inicio) AS ultima
FROM robo.memoria_rotinas_execucoes
GROUP BY nome
ORDER BY erros DESC, execucoes DESC;
