-- titulo: Duplicidades por chave
-- pergunta: Existe o mesmo ID repetido entre arquivos diferentes?
-- como_ler: O robô bloqueia duplicidade dentro do arquivo (chave_unica). Esta consulta acha repetição ENTRE arquivos — ex.: a mesma resposta enviada em dois meses.
-- requer: tratado.fato_nps (id_resposta, _arquivo_origem)
SELECT
    id_resposta,
    count(*)                                         AS vezes,
    string_agg(DISTINCT _arquivo_origem, ', ')       AS arquivos
FROM tratado.fato_nps
GROUP BY id_resposta
HAVING count(*) > 1
ORDER BY vezes DESC, id_resposta;
