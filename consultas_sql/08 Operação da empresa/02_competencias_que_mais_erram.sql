-- titulo: Competências com mais erros no treino
-- pergunta: Quais competências a empresa mais erra, e com que tipo de erro?
-- como_ler: As primeiras linhas são onde o treino deve focar. tipo_erro vem da correção automática do caso.
-- requer: robo.memoria_treino_tentativas
SELECT competencia, coalesce(nullif(tipo_erro, ''), '(sem tipo)') AS tipo_erro, count(*) AS erros,
       count(DISTINCT funcionario) AS pessoas
FROM robo.memoria_treino_tentativas
WHERE acertou = 0
GROUP BY competencia, tipo_erro
ORDER BY erros DESC
LIMIT 30;
