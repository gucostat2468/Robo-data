-- =====================================================================
--  CAMADA ANALÍTICA — monitoramento das cargas do robô
--  Executado automaticamente depois de cada carga bem-sucedida.
--  No Power BI: Obter dados > Banco de dados PostgreSQL > analitico.vw_cargas
-- =====================================================================
CREATE OR REPLACE VIEW analitico.vw_cargas AS
SELECT
    lote_id,
    arquivo,
    status,
    processado_em,
    processado_em::date        AS data_processamento,
    linhas_entrada,
    linhas_saida,
    erros,
    avisos,
    array_to_string(tabelas, ', ') AS tabelas
FROM robo.lotes;
