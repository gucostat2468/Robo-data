-- =====================================================================
--  EXEMPLO (desativado: arquivos que começam com "_" são ignorados).
--  Para ativar: renomeie para "10_nps_mensal.sql" e ajuste os nomes de tabela/coluna.
--
--  Este é o "T" do ELT: a regra de negócio do NPS fica no banco, num só lugar,
--  e todo relatório (Power BI, Excel, Python) lê o mesmo número.
-- =====================================================================
CREATE OR REPLACE VIEW analitico.vw_nps_mensal AS
SELECT
    date_trunc('month', f.data_resposta)::date                               AS mes,
    c.curso,
    count(*)                                                                 AS respostas,
    count(*) FILTER (WHERE f.nota_nps >= 9)                                  AS promotores,
    count(*) FILTER (WHERE f.nota_nps BETWEEN 7 AND 8)                       AS neutros,
    count(*) FILTER (WHERE f.nota_nps <= 6)                                  AS detratores,
    round(100.0 * (count(*) FILTER (WHERE f.nota_nps >= 9)
                 - count(*) FILTER (WHERE f.nota_nps <= 6)) / count(*), 1)   AS nps
FROM tratado.fato_nps f
JOIN tratado.dim_curso c USING (id_curso)
GROUP BY 1, 2;
