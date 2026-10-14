-- titulo: Esforço do cliente (CES) por canal
-- pergunta: Em qual canal o cliente tem mais dificuldade para resolver o problema?
-- como_ler: Escala de 1 a 7 ("foi fácil resolver"), quanto MAIOR melhor. % fácil = notas 5 a 7. Canal com CES baixo é candidato a revisão de processo.
-- requer: tratado.fato_csat (nota_ces de 1 a 7, canal)
SELECT
    canal,
    count(*)                                                           AS respostas,
    round(avg(nota_ces), 2)                                            AS ces_medio,
    round(100.0 * count(*) FILTER (WHERE nota_ces >= 5) / count(*), 1)  AS pct_facil,
    round(100.0 * count(*) FILTER (WHERE nota_ces <= 3) / count(*), 1)  AS pct_dificil
FROM tratado.fato_csat
WHERE nota_ces IS NOT NULL
GROUP BY canal
ORDER BY ces_medio;
