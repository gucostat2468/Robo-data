-- titulo: Volume e período por arquivo de origem
-- pergunta: Quantas linhas e qual período de datas veio em cada arquivo?
-- como_ler: Períodos sobrepostos entre arquivos podem indicar duplicidade; buracos indicam meses faltando.
-- requer: tratado.fato_nps (data_resposta, _arquivo_origem)
SELECT
    _arquivo_origem         AS arquivo,
    count(*)                AS linhas,
    min(data_resposta)      AS primeira_data,
    max(data_resposta)      AS ultima_data,
    max(_processado_em)     AS processado_em
FROM tratado.fato_nps
GROUP BY 1
ORDER BY primeira_data;
