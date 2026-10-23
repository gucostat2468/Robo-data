-- titulo: Quem recebeu demanda nos últimos 7 dias
-- pergunta: Alguém ficou para trás? Quantas demandas cada pessoa recebeu e concluiu?
-- como_ler: Compare com o quadro: quem não aparece aqui não recebeu demanda na semana (veja o motivo em demandas_registro).
-- requer: robo.memoria_solicitacoes
SELECT funcionario, andar, count(*) AS demandas, count(*) FILTER (WHERE estado = 'concluida') AS concluidas,
       max(criada_em) AS ultima
FROM robo.memoria_solicitacoes
WHERE origem = 'demanda_sintetica' AND criada_em::timestamp >= now() - interval '7 days'
GROUP BY funcionario, andar
ORDER BY demandas, funcionario;
