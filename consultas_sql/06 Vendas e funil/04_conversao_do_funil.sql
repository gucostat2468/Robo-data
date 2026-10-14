-- titulo: Conversão do funil por etapa
-- pergunta: Onde perdemos mais leads no funil?
-- como_ler: conv_etapa_anterior mostra o "vazamento" de cada passagem; a menor taxa é o gargalo. Ajuste a lista de etapas (VALUES) para o seu funil.
-- requer: tratado.funil (id_lead, etapa)
WITH ordem(etapa, posicao) AS (
    VALUES ('lead', 1), ('contato', 2), ('proposta', 3), ('matricula', 4)
),
contagem AS (
    SELECT o.posicao, o.etapa, count(DISTINCT f.id_lead) AS leads
    FROM ordem AS o
    LEFT JOIN tratado.funil AS f ON lower(f.etapa) = o.etapa
    GROUP BY o.posicao, o.etapa
)
SELECT
    etapa,
    leads,
    round(100.0 * leads / nullif(first_value(leads) OVER (ORDER BY posicao), 0), 1) AS conv_desde_inicio_pct,
    round(100.0 * leads / nullif(lag(leads) OVER (ORDER BY posicao), 0), 1)         AS conv_etapa_anterior_pct
FROM contagem
ORDER BY posicao;
