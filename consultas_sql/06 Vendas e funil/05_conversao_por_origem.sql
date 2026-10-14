-- titulo: Conversão por origem do lead
-- pergunta: Qual canal de aquisição traz leads que mais convertem em matrícula?
-- como_ler: Combine volume e taxa: uma origem pequena com conversão alta pode merecer mais investimento.
-- requer: tratado.funil (id_lead, etapa, origem)
SELECT
    origem,
    count(DISTINCT id_lead)                                                         AS leads,
    count(DISTINCT id_lead) FILTER (WHERE lower(etapa) = 'matricula')               AS matriculas,
    round(100.0 * count(DISTINCT id_lead) FILTER (WHERE lower(etapa) = 'matricula')
          / nullif(count(DISTINCT id_lead), 0), 1)                                   AS conversao_pct
FROM tratado.funil
GROUP BY origem
ORDER BY conversao_pct DESC, leads DESC;
