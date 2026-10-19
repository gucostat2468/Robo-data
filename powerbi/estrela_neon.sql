-- =====================================================================================
-- MODELO ESTRELA DA EMPRESA NO POSTGRESQL (schema bi) — gerado por powerbi/exportar_estrela.py, não edite à mão.
-- Rode no SQL Editor do Neon (ou psql) como o dono do banco. Pode rodar de novo: recria tudo sem perder nada
-- (as views só LEEM o schema robo; as tabelas *_base guardam o organograma e o catálogo, que vivem no código).
-- Os turnos da nuvem (robo/nuvem.py) só escrevem no schema robo — o schema bi nunca é tocado por eles.
-- =====================================================================================
CREATE SCHEMA IF NOT EXISTS bi;
DROP VIEW IF EXISTS bi.dim_data, bi.dim_funcionario, bi.dim_competencia, bi.fato_treino, bi.fato_interacoes,
  bi.fato_mentorias, bi.fato_rh_movimentos, bi.fato_rotinas, bi.fato_evolucao_nivel, bi.fato_nivel_atual CASCADE;
DROP TABLE IF EXISTS bi.dim_funcionario_base, bi.dim_competencia_base, bi.dim_andar, bi.dim_nivel;
CREATE TABLE bi.dim_funcionario_base (funcionario_id TEXT PRIMARY KEY, nome TEXT, cargo TEXT, nivel_cargo TEXT,
  nivel_cargo_ordem INT, andar INT, area TEXT, gestor_id TEXT, gestor_nome TEXT, no_quadro INT);
CREATE TABLE bi.dim_competencia_base (competencia_id TEXT PRIMARY KEY, competencia TEXT, ferramenta TEXT,
  designer_id TEXT, designer_nome TEXT, descricao TEXT);
CREATE TABLE bi.dim_andar (andar INT PRIMARY KEY, andar_nome TEXT, andar_rotulo TEXT);
CREATE TABLE bi.dim_nivel (nivel INT PRIMARY KEY, nivel_nome TEXT);

INSERT INTO bi.dim_funcionario_base (funcionario_id, nome, cargo, nivel_cargo, nivel_cargo_ordem, andar, area, gestor_id, gestor_nome, no_quadro) VALUES
  ('recepcao', 'Rita', 'Recepção', 'Sênior', 4, 1, 'nativo', 'coord_engenharia', 'Carla', 1),
  ('leitura', 'Leo', 'Leitura (Extração)', 'Sênior', 4, 1, 'nativo', 'coord_engenharia', 'Carla', 1),
  ('limpeza', 'Lia', 'Limpeza', 'Especialista', 5, 1, 'nativo', 'coord_engenharia', 'Carla', 1),
  ('validacao', 'Otto', 'Auditoria (Validação)', 'Sênior', 4, 1, 'nativo', 'coord_engenharia', 'Carla', 1),
  ('modelagem', 'Ana', 'Modelagem', 'Sênior', 4, 1, 'nativo', 'coord_engenharia', 'Carla', 1),
  ('banco', 'Beto', 'Banco de dados (ELT)', 'Sênior', 4, 1, 'nativo', 'dba', 'Dora', 1),
  ('publicacao', 'Duda', 'Publicação e arquivo', 'Sênior', 4, 1, 'nativo', 'coord_engenharia', 'Carla', 1),
  ('analise_perfil', 'Bia', 'Perfil dos dados', 'Sênior', 4, 2, 'analista', 'coord_analise', 'Marcos', 1),
  ('analise_indicadores', 'Caio', 'Indicadores (NPS, CSAT, CES)', 'Especialista', 5, 2, 'analista', 'coord_analise', 'Marcos', 1),
  ('analise_estatistica', 'Davi', 'Estatística', 'Sênior', 4, 2, 'analista', 'coord_analise', 'Marcos', 1),
  ('analise_monitoramento', 'Eva', 'Monitoramento', 'Sênior', 4, 2, 'analista', 'coord_analise', 'Marcos', 1),
  ('analise_relator', 'Fábio', 'Relator', 'Sênior', 4, 2, 'analista', 'coord_analise', 'Marcos', 1),
  ('excel_supervisor', 'Ricardo', 'Gerente da Sala Excel', 'Gerente', 7, 3, 'excel', 'head_bi', 'Felipe', 1),
  ('excel_pesquisa', 'Pedro', 'Especialista em Pesquisa de Mercado', 'Especialista', 5, 3, 'excel', 'coord_excel', 'Sílvia', 1),
  ('excel_formulas', 'Lúcia', 'Especialista em Fórmulas e Power Query', 'Especialista', 5, 3, 'excel', 'coord_excel', 'Sílvia', 1),
  ('excel_trade', 'Tânia', 'Especialista em Trade Marketing', 'Especialista', 5, 3, 'excel', 'coord_excel', 'Sílvia', 1),
  ('excel_dinamicas', 'Gabriel', 'Especialista em Tabelas Dinâmicas e Dashboards', 'Especialista', 5, 3, 'excel', 'coord_excel', 'Sílvia', 1),
  ('supervisor', 'Saulo', 'Supervisor de Planilhas', 'Sênior', 4, 1, 'supervisor', 'coord_engenharia', 'Carla', 1),
  ('dba', 'Dora', 'DBA PostgreSQL', 'Sênior', 4, 1, 'supervisor', 'coord_engenharia', 'Carla', 1),
  ('coord_engenharia', 'Carla', 'Coordenadora de Engenharia de Dados', 'Coordenador(a)', 6, 1, 'supervisor', 'ger_engenharia', 'Marcelo', 1),
  ('coord_analise', 'Marcos', 'Coordenador de Análise e Ciência de Dados', 'Coordenador(a)', 6, 2, 'supervisor', 'ger_analise', 'Patrícia', 1),
  ('canal_nina', 'Nina', 'Assistente do canal', 'Júnior', 2, 4, 'canal', 'canal_helena', 'Helena', 1),
  ('canal_iara', 'Iara', 'Ideias e evolução da plataforma', 'Sênior', 4, 4, 'canal', 'ger_operacoes', 'Renata', 1),
  ('canal_helena', 'Helena', 'RH e desenvolvimento da equipe', 'Coordenador(a)', 6, 4, 'canal', 'head_rh', 'Juliana', 1),
  ('ger_engenharia', 'Marcelo', 'Gerente de Engenharia de Dados', 'Gerente', 7, 1, 'quadro', 'head_engenharia', 'Eduardo', 1),
  ('eng_pleno_tipos', 'Júlia', 'Engenheira de Dados Pleno', 'Pleno', 3, 1, 'quadro', 'coord_engenharia', 'Carla', 1),
  ('eng_pleno_releitura', 'Rafael', 'Engenheiro de Dados Pleno', 'Pleno', 3, 1, 'quadro', 'coord_engenharia', 'Carla', 1),
  ('eng_junior_espacos', 'Bruno', 'Analista de Dados Júnior', 'Júnior', 2, 1, 'quadro', 'eng_pleno_tipos', 'Júlia', 1),
  ('eng_junior_auditoria', 'Camila', 'Analista de Dados Júnior', 'Júnior', 2, 1, 'quadro', 'eng_pleno_tipos', 'Júlia', 1),
  ('eng_estagiario', 'Théo', 'Estagiário de Engenharia de Dados', 'Estagiário', 1, 1, 'quadro', 'eng_pleno_releitura', 'Rafael', 1),
  ('ger_analise', 'Patrícia', 'Gerente de Analytics e Customer Insights', 'Gerente', 7, 2, 'quadro', 'dir_analytics', 'Rogério', 1),
  ('ana_pleno_recalculo', 'Sérgio', 'Analista de Dados Pleno', 'Pleno', 3, 2, 'quadro', 'coord_analise', 'Marcos', 1),
  ('ana_pleno_base', 'Larissa', 'Analista de Customer Insights Pleno', 'Pleno', 3, 2, 'quadro', 'coord_analise', 'Marcos', 1),
  ('ana_junior_faixas', 'Igor', 'Analista de Dados Júnior', 'Júnior', 2, 2, 'quadro', 'ana_pleno_recalculo', 'Sérgio', 1),
  ('ana_estagiario', 'Manu', 'Estagiária de Análise de Dados', 'Estagiário', 1, 2, 'quadro', 'ana_pleno_base', 'Larissa', 1),
  ('coord_excel', 'Sílvia', 'Coordenadora da Sala Excel', 'Coordenador(a)', 6, 3, 'quadro', 'excel_supervisor', 'Ricardo', 1),
  ('xl_pleno_formulas', 'Hugo', 'Analista de Excel Pleno', 'Pleno', 3, 3, 'quadro', 'coord_excel', 'Sílvia', 1),
  ('xl_junior_formatos', 'Paula', 'Analista de Excel Júnior', 'Júnior', 2, 3, 'quadro', 'xl_pleno_formulas', 'Hugo', 1),
  ('xl_estagiario', 'Enzo', 'Estagiário da Sala Excel', 'Estagiário', 1, 3, 'quadro', 'xl_pleno_formulas', 'Hugo', 1),
  ('ger_operacoes', 'Renata', 'Gerente de Operações e Governança de Dados', 'Gerente', 7, 4, 'quadro', 'dir_operacoes', 'Cláudia', 1),
  ('gov_pleno_lgpd', 'Vitor', 'Analista de Governança Pleno', 'Pleno', 3, 4, 'quadro', 'canal_helena', 'Helena', 1),
  ('gov_estagiaria', 'Lara', 'Estagiária de Documentação de Dados', 'Estagiário', 1, 4, 'quadro', 'gov_pleno_lgpd', 'Vitor', 1),
  ('ger_ti', 'Gustavo', 'Gerente de TI e Infraestrutura', 'Gerente', 7, 5, 'ti', 'head_ti', 'André', 1),
  ('coord_devops', 'Fernanda', 'Coordenadora de DevOps e Confiabilidade (SRE)', 'Coordenador(a)', 6, 5, 'ti', 'ger_ti', 'Gustavo', 1),
  ('sec_senior', 'Wagner', 'Especialista Sênior em Segurança da Informação', 'Sênior', 4, 5, 'ti', 'coord_devops', 'Fernanda', 1),
  ('cloud_aws', 'Marina', 'Arquiteta de Cloud (AWS)', 'Especialista', 5, 5, 'ti', 'ger_ti', 'Gustavo', 1),
  ('dev_pleno', 'Diego', 'Desenvolvedor Python Pleno', 'Pleno', 3, 5, 'ti', 'coord_devops', 'Fernanda', 1),
  ('infra_pleno', 'Rodrigo', 'Analista de Infraestrutura Pleno', 'Pleno', 3, 5, 'ti', 'coord_devops', 'Fernanda', 1),
  ('dev_junior', 'Letícia', 'Desenvolvedora Júnior', 'Júnior', 2, 5, 'ti', 'dev_pleno', 'Diego', 1),
  ('devops_estagiario', 'Caíque', 'Estagiário de DevOps', 'Estagiário', 1, 5, 'ti', 'infra_pleno', 'Rodrigo', 1),
  ('airflow_especialista', 'Henrique', 'Especialista em Orquestração de Dados (Apache Airflow)', 'Especialista', 5, 5, 'ti', 'ger_ti', 'Gustavo', 1),
  ('airflow_pleno', 'Bianca', 'Engenheira de Dados Pleno', 'Pleno', 3, 5, 'ti', 'airflow_especialista', 'Henrique', 1),
  ('airflow_estagiario', 'Davi', 'Estagiário de Engenharia de Dados (Airflow)', 'Estagiário', 1, 5, 'ti', 'airflow_pleno', 'Bianca', 1),
  ('dir_dados', 'Beatriz', 'Diretora de Dados e Engenharia (CDO)', 'Diretor(a)', 9, 1, 'lideranca', 'dono', 'Você (dono)', 1),
  ('dir_analytics', 'Rogério', 'Diretor de Analytics, Ciência de Dados e BI', 'Diretor(a)', 9, 2, 'lideranca', 'dono', 'Você (dono)', 1),
  ('dir_operacoes', 'Cláudia', 'Diretora de Operações e Governança', 'Diretor(a)', 9, 4, 'lideranca', 'dono', 'Você (dono)', 1),
  ('dir_pessoas', 'Marta', 'Diretora de Pessoas e Cultura (CHRO)', 'Diretor(a)', 9, 4, 'lideranca', 'dono', 'Você (dono)', 1),
  ('dir_tecnologia', 'Alexandre', 'Diretor de Tecnologia (CTO)', 'Diretor(a)', 9, 5, 'lideranca', 'dono', 'Você (dono)', 1),
  ('head_engenharia', 'Eduardo', 'Head de Engenharia de Dados', 'Head', 8, 1, 'lideranca', 'dir_dados', 'Beatriz', 1),
  ('head_ciencia', 'Natália', 'Head de Ciência de Dados', 'Head', 8, 2, 'lideranca', 'dir_analytics', 'Rogério', 1),
  ('head_bi', 'Felipe', 'Head de BI e Excel', 'Head', 8, 3, 'lideranca', 'dir_analytics', 'Rogério', 1),
  ('head_governanca', 'Simone', 'Head de Governança de Dados', 'Head', 8, 4, 'lideranca', 'dir_operacoes', 'Cláudia', 1),
  ('head_rh', 'Juliana', 'Head de Gente e Gestão', 'Head', 8, 4, 'lideranca', 'dir_pessoas', 'Marta', 1),
  ('head_ti', 'André', 'Head de Infraestrutura e Segurança', 'Head', 8, 5, 'lideranca', 'dir_tecnologia', 'Alexandre', 1),
  ('cd_senior_drivers', 'Vinícius', 'Cientista de Dados Sênior', 'Sênior', 4, 2, 'lideranca', 'head_ciencia', 'Natália', 1),
  ('cd_pleno_segmentos', 'Carolina', 'Cientista de Dados Pleno', 'Pleno', 3, 2, 'lideranca', 'head_ciencia', 'Natália', 1),
  ('cd_junior_anomalias', 'Lucas', 'Cientista de Dados Júnior', 'Júnior', 2, 2, 'lideranca', 'cd_senior_drivers', 'Vinícius', 1),
  ('rh_rs', 'Priscila', 'Analista de Recrutamento e Seleção Pleno', 'Pleno', 3, 4, 'lideranca', 'canal_helena', 'Helena', 1),
  ('rh_td', 'Roberta', 'Analista de Treinamento e Desenvolvimento Pleno', 'Pleno', 3, 4, 'lideranca', 'canal_helena', 'Helena', 1),
  ('rh_desempenho', 'Mauro', 'Analista de Desempenho Sênior', 'Sênior', 4, 4, 'lideranca', 'canal_helena', 'Helena', 1),
  ('rh_people', 'Tiago', 'Analista de People Analytics Pleno', 'Pleno', 3, 4, 'lideranca', 'rh_desempenho', 'Mauro', 1),
  ('head_python', 'Henrique', 'Head de Engenharia Python', 'Head', 8, 5, 'lideranca', 'dir_tecnologia', 'Alexandre', 1),
  ('esp_pandas', 'Sofia', 'Especialista em pandas', 'Especialista', 5, 5, 'lideranca', 'head_python', 'Henrique', 1),
  ('esp_numpy', 'Nicolas', 'Especialista em numpy', 'Especialista', 5, 5, 'lideranca', 'head_python', 'Henrique', 1),
  ('esp_openpyxl', 'Olívia', 'Especialista em openpyxl (Excel)', 'Especialista', 5, 5, 'lideranca', 'head_python', 'Henrique', 1),
  ('esp_xlrd', 'Xavier', 'Especialista em xlrd (.xls antigo)', 'Especialista', 5, 5, 'lideranca', 'head_python', 'Henrique', 1),
  ('esp_yaml', 'Elisa', 'Especialista em PyYAML (configuração)', 'Especialista', 5, 5, 'lideranca', 'head_python', 'Henrique', 1),
  ('esp_psycopg', 'Pietro', 'Especialista em psycopg (PostgreSQL)', 'Especialista', 5, 5, 'lideranca', 'head_python', 'Henrique', 1),
  ('esp_sqlite', 'Silas', 'Especialista em sqlite3 (memória da empresa)', 'Especialista', 5, 5, 'lideranca', 'head_python', 'Henrique', 1),
  ('rh_estagiaria', 'Bianca', 'Estagiária de RH', 'Estagiário', 1, 4, 'lideranca', 'rh_desempenho', 'Mauro', 1),
  ('head_casos', 'Otávio', 'Head da Sala de Casos', 'Head', 8, 4, 'lideranca', 'dono', 'Você (dono)', 1),
  ('casos_engenharia', 'Lívia', 'Designer de Casos', 'Especialista', 5, 4, 'lideranca', 'head_casos', 'Otávio', 1),
  ('casos_analytics', 'Murilo', 'Designer de Casos', 'Especialista', 5, 4, 'lideranca', 'head_casos', 'Otávio', 1),
  ('casos_governanca', 'Raquel', 'Designer de Casos', 'Especialista', 5, 4, 'lideranca', 'head_casos', 'Otávio', 1),
  ('casos_ti', 'Augusto', 'Designer de Casos', 'Especialista', 5, 4, 'lideranca', 'head_casos', 'Otávio', 1),
  ('casos_revisor', 'Valéria', 'Revisora Independente de Casos', 'Especialista', 5, 4, 'lideranca', 'head_casos', 'Otávio', 1),
  ('casos_planejamento', 'Yasmin', 'Planejadora de Treino', 'Sênior', 4, 4, 'lideranca', 'head_casos', 'Otávio', 1);

INSERT INTO bi.dim_competencia_base (competencia_id, competencia, ferramenta, designer_id, designer_nome, descricao) VALUES
  ('limpeza', 'Limpar e barrar planilha', 'diagnosticar_planilha', 'casos_engenharia', 'Lívia', 'O pipeline real em diagnóstico: contar as linhas certas e barrar defeito.'),
  ('calculo', 'Calcular o pedido', 'calcular', 'casos_analytics', 'Murilo', 'Entender o pedido em português e acertar o número de cada grupo.'),
  ('indicadores', 'NPS com a base certa', 'perfil_indicadores', 'casos_analytics', 'Murilo', 'NPS e base (n) certos.'),
  ('lgpd', 'Achar dado pessoal', 'dados_pessoais', 'casos_governanca', 'Raquel', 'Apontar exatamente as colunas com dado pessoal (nem mais, nem menos).'),
  ('anomalias', 'Achar anomalias', 'anomalias', 'casos_analytics', 'Murilo', 'Regra de Tukey (3×IQR): quantas fora da faixa em cada coluna.'),
  ('segmentacao', 'Achar os perfis', 'segmentacao', 'casos_analytics', 'Murilo', 'Número certo de grupos plantados.'),
  ('drivers', 'Achar o que move o NPS', 'drivers', 'casos_analytics', 'Murilo', 'O 1º driver é o plantado.'),
  ('conhecimento', 'Achar o conhecimento certo', 'conhecimento', 'casos_governanca', 'Raquel', 'Recuperar a lição certa do caderno da empresa (não conta como ''aplicada'').'),
  ('historico', 'Ler o histórico', 'historico', 'casos_engenharia', 'Lívia', 'As 10 últimas execuções, na ordem certa.'),
  ('ronda_ti', 'Ronda de TI', 'ronda_ti', 'casos_ti', 'Augusto', 'Detectar exatamente os problemas plantados no computador de teste.'),
  ('orquestracao', 'SLA das rotinas (Airflow)', 'orquestracao', 'casos_ti', 'Augusto', 'Apontar exatamente as rotinas atrasadas, com erro e lentas pela regra de SLA — nenhuma isca.'),
  ('resumo_executivo', 'Resumo sem inventar', 'resumo_executivo', 'casos_governanca', 'Raquel', 'Todas as partes, nenhum número que não veio das etapas.'),
  ('desempenho', 'Conta de desempenho (RH)', 'desempenho', 'casos_governanca', 'Raquel', 'Taxa e situação de cada pessoa pela regra da política de RH.'),
  ('sql', 'Mesma conta em SQL', 'consulta_sql', 'casos_engenharia', 'Lívia', 'O SQL gerado roda no PostgreSQL (somente leitura) e bate com a verdade.'),
  ('revisao_casos', 'Revisar caso de treino', 'revisar_caso', 'casos_governanca', 'Raquel', 'Sala de Casos: integridade, reprodutibilidade e conferência — reprovar o caso com defeito e aprovar o certo.');

INSERT INTO bi.dim_andar (andar, andar_nome, andar_rotulo) VALUES
  (1, 'Engenharia de Dados', '1º · Engenharia de Dados'),
  (2, 'Analytics e Ciência de Dados', '2º · Analytics e Ciência de Dados'),
  (3, 'Sala Excel e BI', '3º · Sala Excel e BI'),
  (4, 'Operações, governança, canal e Pessoas (RH)', '4º · Operações, governança, canal e Pessoas (RH)'),
  (5, 'TI, DevOps e segurança', '5º · TI, DevOps e segurança'),
  (0, 'Fora do quadro atual', '— · Fora do quadro atual');

INSERT INTO bi.dim_nivel (nivel, nivel_nome) VALUES
  (1, '1 · Básico'),
  (2, '2 · Intermediário'),
  (3, '3 · Avançado'),
  (4, '4 · Difícil'),
  (5, '5 · Desafio');

-- ============================================================ FATOS (views: sempre ao vivo, só leem o schema robo)
CREATE OR REPLACE VIEW bi.fato_treino AS
SELECT t.id AS tentativa_id, t.data_hora::timestamp AS data_hora, t.data_hora::timestamp::date AS data,
       EXTRACT(HOUR FROM t.data_hora::timestamp)::int AS hora, t.funcionario AS funcionario_id, t.andar::int AS andar,
       t.cargo_nivel, t.competencia AS competencia_id, t.nivel::int AS nivel,
       COALESCE(t.acertou, 0)::int AS acertou, (1 - COALESCE(t.acertou, 0))::int AS errou, t.nota, t.segundos,
       COALESCE(NULLIF(t.tipo_erro, ''), CASE WHEN t.acertou = 1 THEN '(sem erro)' ELSE '(não informado)' END) AS tipo_erro,
       t.rodada, t.versao_codigo
FROM robo.memoria_treino_tentativas t;

CREATE OR REPLACE VIEW bi.fato_interacoes AS
SELECT i.id AS interacao_id, i.data_hora::timestamp AS data_hora, i.data_hora::timestamp::date AS data,
       i.de AS de_id, COALESCE(i.para, '') AS para_id, i.tipo, i.texto, COALESCE(i.ref, '') AS ref
FROM robo.memoria_interacoes i;

CREATE OR REPLACE VIEW bi.fato_mentorias AS
SELECT m.id AS mentoria_id, m.data_hora::timestamp AS data_hora, m.data_hora::timestamp::date AS data,
       m.mentor AS mentor_id, m.aprendiz AS aprendiz_id, m.competencia AS competencia_id, m.nivel::int AS nivel, m.situacao,
       CASE WHEN m.situacao = 'ajudou' THEN 1 ELSE 0 END AS ajudou,
       CASE WHEN m.situacao = 'aberta' THEN 0 ELSE 1 END AS fechada, NULLIF(m.fechada_em, '')::timestamp AS fechada_em
FROM robo.memoria_mentorias m;

CREATE OR REPLACE VIEW bi.fato_rh_movimentos AS
SELECT r.id AS movimento_id, r.data_hora::timestamp AS data_hora, r.data_hora::timestamp::date AS data,
       r.funcionario AS funcionario_id, r.tipo, r.de_nivel, r.para_nivel, r.competencia AS competencia_id, r.situacao,
       r.proposto_por, r.validado_por, r.motivo
FROM robo.memoria_rh_movimentos r;

CREATE OR REPLACE VIEW bi.fato_rotinas AS
SELECT e.id AS execucao_id, e.inicio::timestamp AS data_hora, e.inicio::timestamp::date AS data, e.nome AS rotina,
       e.status, CASE WHEN e.status = 'erro' THEN 1 ELSE 0 END AS com_erro, e.segundos
FROM robo.memoria_rotinas_execucoes e;

CREATE OR REPLACE VIEW bi.fato_evolucao_nivel AS
SELECT v.id AS evento_id, v.data_hora::timestamp AS data_hora, v.data_hora::timestamp::date AS data,
       v.funcionario AS funcionario_id, v.competencia AS competencia_id, v.de::int AS nivel_de, v.para::int AS nivel_para,
       COALESCE(v.para - v.de, 0)::int AS variacao,
       CASE WHEN v.de IS NULL THEN 'inicial' WHEN v.para > v.de THEN 'subiu' ELSE 'desceu' END AS tipo_evento, v.motivo
FROM robo.memoria_treino_niveis_eventos v;

CREATE OR REPLACE VIEW bi.fato_nivel_atual AS
SELECT n.funcionario AS funcionario_id, n.competencia AS competencia_id, n.nivel::int AS nivel,
       n.desde::timestamp AS desde
FROM robo.memoria_treino_niveis n;

-- ============================================================ DIMENSÕES
CREATE OR REPLACE VIEW bi.dim_funcionario AS
SELECT funcionario_id, nome, cargo, nivel_cargo, nivel_cargo_ordem, andar, area, gestor_id, gestor_nome, no_quadro
FROM bi.dim_funcionario_base
UNION ALL
SELECT x.id, x.id, '(fora do quadro atual)', '', 0, 0, '', '', '', 0
FROM (SELECT funcionario AS id FROM robo.memoria_treino_tentativas
      UNION SELECT de FROM robo.memoria_interacoes UNION SELECT NULLIF(para, '') FROM robo.memoria_interacoes
      UNION SELECT mentor FROM robo.memoria_mentorias UNION SELECT aprendiz FROM robo.memoria_mentorias
      UNION SELECT funcionario FROM robo.memoria_rh_movimentos UNION SELECT funcionario FROM robo.memoria_treino_niveis_eventos
      UNION SELECT funcionario FROM robo.memoria_treino_niveis) x
WHERE x.id IS NOT NULL AND x.id NOT IN (SELECT funcionario_id FROM bi.dim_funcionario_base);

CREATE OR REPLACE VIEW bi.dim_competencia AS
SELECT competencia_id, competencia, ferramenta, designer_id, designer_nome, descricao FROM bi.dim_competencia_base
UNION ALL
SELECT x.id, x.id, '', '', '', '(fora do catálogo atual)'
FROM (SELECT competencia AS id FROM robo.memoria_treino_tentativas UNION SELECT competencia FROM robo.memoria_mentorias
      UNION SELECT competencia FROM robo.memoria_treino_niveis_eventos UNION SELECT competencia FROM robo.memoria_treino_niveis) x
WHERE x.id IS NOT NULL AND x.id NOT IN (SELECT competencia_id FROM bi.dim_competencia_base);

CREATE OR REPLACE VIEW bi.dim_data AS
WITH limites AS (
  SELECT MIN(d) AS ini, MAX(d) AS fim FROM (
    SELECT data FROM bi.fato_treino UNION ALL SELECT data FROM bi.fato_interacoes UNION ALL SELECT data FROM bi.fato_mentorias
    UNION ALL SELECT data FROM bi.fato_rh_movimentos UNION ALL SELECT data FROM bi.fato_rotinas
    UNION ALL SELECT data FROM bi.fato_evolucao_nivel) t(d))
SELECT g::date AS data, EXTRACT(YEAR FROM g)::int AS ano, EXTRACT(MONTH FROM g)::int AS mes,
       (ARRAY['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'])[EXTRACT(MONTH FROM g)::int] AS mes_nome,
       to_char(g, 'YYYY-MM') AS ano_mes, EXTRACT(DAY FROM g)::int AS dia, EXTRACT(ISODOW FROM g)::int AS dia_semana,
       (ARRAY['seg','ter','qua','qui','sex','sáb','dom'])[EXTRACT(ISODOW FROM g)::int] AS dia_semana_nome,
       EXTRACT(WEEK FROM g)::int AS semana_iso, CASE WHEN EXTRACT(ISODOW FROM g) >= 6 THEN 1 ELSE 0 END AS fim_de_semana
FROM limites, generate_series(limites.ini, limites.fim, interval '1 day') g;

-- ============================================================ quem lê (o app do celular e o Power BI usam robo_leitura)
GRANT USAGE ON SCHEMA bi TO robo_leitura;
GRANT SELECT ON ALL TABLES IN SCHEMA bi TO robo_leitura;
ALTER DEFAULT PRIVILEGES IN SCHEMA bi GRANT SELECT ON TABLES TO robo_leitura;
