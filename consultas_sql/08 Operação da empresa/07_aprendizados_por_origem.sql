-- titulo: O que a empresa aprendeu, por origem e resultado
-- pergunta: De onde vêm os aprendizados (esteira, treino, fábrica, semente) e quanto é erro?
-- como_ler: Semente = erros típicos carregados de propósito; nunca conta como trabalho de ninguém.
-- requer: robo.memoria_aprendizados
SELECT origem, resultado, count(*) AS aprendizados, count(DISTINCT funcionario) AS pessoas,
       count(DISTINCT competencia) AS competencias
FROM robo.memoria_aprendizados
GROUP BY origem, resultado
ORDER BY origem, resultado;
