-- titulo: Detratores recentes para contato (closed loop)
-- pergunta: Quem são os detratores dos últimos 30 dias para a operação retornar?
-- como_ler: Lista acionável para o time de relacionamento. Contato em até 48h aumenta a recuperação. "Últimos 30 dias" conta a partir da data mais recente da base.
-- requer: tratado.fato_nps (id_resposta, data_resposta, nota_nps, comentario, id_curso) e tratado.dim_curso
SELECT
    f.id_resposta,
    f.data_resposta,
    f.nota_nps,
    c.curso,
    f.comentario
FROM tratado.fato_nps AS f
LEFT JOIN tratado.dim_curso AS c USING (id_curso)
WHERE f.nota_nps <= 6
  AND f.data_resposta >= (SELECT max(data_resposta) FROM tratado.fato_nps) - 30
ORDER BY f.nota_nps, f.data_resposta DESC;
