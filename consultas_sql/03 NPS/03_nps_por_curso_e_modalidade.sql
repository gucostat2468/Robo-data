-- titulo: NPS por curso e modalidade
-- pergunta: Quais cursos/modalidades puxam o NPS para cima ou para baixo?
-- como_ler: Grupos com menos de 30 respostas aparecem marcados — não tire conclusão deles isoladamente.
-- requer: tratado.fato_nps (nota_nps, id_curso) e tratado.dim_curso (curso, modalidade)
SELECT
    c.curso,
    c.modalidade,
    count(*)                                                                  AS respostas,
    round(100.0 * (count(*) FILTER (WHERE f.nota_nps >= 9) - count(*) FILTER (WHERE f.nota_nps <= 6)) / count(*), 1) AS nps,
    CASE WHEN count(*) < 30 THEN 'base pequena' ELSE 'ok' END                AS confiabilidade
FROM tratado.fato_nps AS f
JOIN tratado.dim_curso AS c USING (id_curso)
WHERE f.nota_nps IS NOT NULL
GROUP BY c.curso, c.modalidade
ORDER BY nps DESC;
