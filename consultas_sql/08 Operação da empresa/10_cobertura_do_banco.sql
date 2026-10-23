-- titulo: Cobertura do banco: tabelas vazias e por quê (último levantamento)
-- pergunta: Que tabelas ainda estão vazias, e o que falta acontecer para enchê-las?
-- como_ler: Situação 'vazia: funcionalidade não acionada' tem a causa e o que a enche na mesma linha.
-- requer: robo.memoria_cobertura_persistencia
SELECT onde, schema, tabela, linhas, situacao, causa, gatilho
FROM robo.memoria_cobertura_persistencia
WHERE levantamento = (SELECT max(levantamento) FROM robo.memoria_cobertura_persistencia)
  AND situacao <> 'com dados'
ORDER BY onde, schema, tabela;
