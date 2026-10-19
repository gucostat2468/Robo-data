// =====================================================================================================
// POWER QUERY (linguagem M) — carga do modelo estrela "Robô de Planilhas"
// =====================================================================================================
// Cada bloco "CONSULTA: <nome>" abaixo é UMA consulta. Para criar cada uma:
//   Página Inicial → Transformar dados (abre o Editor do Power Query) → Página Inicial → Nova fonte →
//   Consulta nula → (a consulta "Consulta1" aparece à esquerda) → Exibição → Editor avançado →
//   apague o que estiver lá → cole o bloco (de "let" até o "in ..." final) → Concluído →
//   clique com o botão direito em "Consulta1" → Renomear → digite o nome exato do bloco.
//
// UMA ÚNICA CHAVE ESCOLHE A ORIGEM: o parâmetro Origem.
//   "PostgreSQL" → lê ao vivo as views do schema bi no Neon (usuário robo_leitura, só leitura, SSL).
//   "Excel"      → lê powerbi/dados/modelo_estrela.xlsx (mesmas tabelas, mesmas colunas, mesmos números).
// Trocar a origem depois = mudar só o parâmetro (Página Inicial → Gerenciar parâmetros). Nenhuma consulta muda.
//
// SENHA: NUNCA vai neste arquivo nem no .pbix. Na primeira atualização o Power BI pede usuário e senha
// (escolha "Banco de dados", usuário robo_leitura) e guarda a credencial no cofre do Windows, fora do relatório.
//
// ORDEM DE CRIAÇÃO: parâmetros (1) → função fxTabelaBI (2) → dimensões (3) → fatos (4).
// Depois: clique com o botão direito em fxTabelaBI → desmarque "Habilitar carga" (é auxiliar, não vira tabela).
// =====================================================================================================


// =====================================================================================================
// 1. PARÂMETROS  (Página Inicial → Gerenciar parâmetros → Novo parâmetro — ou cole como consulta nula)
// =====================================================================================================

// ---------- CONSULTA: Origem
"PostgreSQL" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true, List = {"PostgreSQL", "Excel"}, DefaultValue = "PostgreSQL"]

// ---------- CONSULTA: Servidor
// O "Hostname" do Neon: na Connection string, o trecho depois do @ e antes da / (ex.: ep-xxxx.sa-east-1.aws.neon.tech).
// Não é segredo, mas também não está no repositório: copie do painel do Neon (Dashboard → Connect).
"ep-xxxx.sa-east-1.aws.neon.tech" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]

// ---------- CONSULTA: Banco
"Roboplanilhas" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]

// ---------- CONSULTA: CaminhoExcel
// Caminho completo do arquivo no SEU computador (Shift + botão direito no arquivo → "Copiar como caminho").
"C:\Robo-data\powerbi\dados\modelo_estrela.xlsx" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]


// =====================================================================================================
// 2. FUNÇÃO AUXILIAR — devolve a tabela pedida da origem escolhida (desabilite a carga dela)
// =====================================================================================================

// ---------- CONSULTA: fxTabelaBI
let
    fxTabelaBI = (nome as text) as table =>
        if Origem = "PostgreSQL" then
            let
                // PostgreSQL.Database usa o driver Npgsql que já vem no Power BI Desktop. A conexão é criptografada
                // (SSL) por padrão — deixe marcado "Criptografar conexões" em Configurações da fonte de dados.
                Fonte = PostgreSQL.Database(Servidor, Banco, [CreateNavigationProperties = false]),
                // Navegação: schema "bi", objeto = nome da view. Navegar assim permite "query folding": o filtro e a
                // seleção de colunas viram SQL executado NO Neon, e só o resultado viaja pela internet.
                Tabela = Fonte{[Schema = "bi", Item = nome]}[Data]
            in
                Tabela
        else
            let
                Livro = Excel.Workbook(File.Contents(CaminhoExcel), true, true),
                // true = a 1ª linha da aba vira cabeçalho (o exportar_estrela.py grava o cabeçalho na linha 1)
                Tabela = Livro{[Item = nome, Kind = "Sheet"]}[Data]
            in
                Tabela
in
    fxTabelaBI


// =====================================================================================================
// 3. DIMENSÕES (quem / o quê / onde / quando) — lado "1" das relações
// =====================================================================================================

// ---------- CONSULTA: dim_funcionario
let
    Fonte = fxTabelaBI("dim_funcionario"),
    // Tipos explícitos: mesmo vindo tipado do PostgreSQL, fixar o tipo aqui faz o Excel e o banco produzirem
    // EXATAMENTE o mesmo modelo — e evita o erro "não é possível comparar Integer com Text" nas relações.
    Tipos = Table.TransformColumnTypes(Fonte, {
        {"funcionario_id", type text}, {"nome", type text}, {"cargo", type text}, {"nivel_cargo", type text},
        {"nivel_cargo_ordem", Int64.Type}, {"andar", Int64.Type}, {"area", type text},
        {"gestor_id", type text}, {"gestor_nome", type text}, {"no_quadro", Int64.Type}}, "pt-BR"),
    // Limpeza: espaços sobrando quebram a ordenação e duplicam categorias ("Head" ≠ "Head ").
    SemEspacos = Table.TransformColumns(Tipos, {
        {"nome", Text.Trim, type text}, {"cargo", Text.Trim, type text}, {"nivel_cargo", Text.Trim, type text}}),
    // Pessoa que saiu do quadro vem sem nível de cargo: rótulo explícito em vez de "(Em branco)" no gráfico.
    NivelCargo = Table.ReplaceValue(SemEspacos, "", "(fora do quadro)", Replacer.ReplaceValue, {"nivel_cargo"}),
    // Coluna de texto amigável para segmentação "Situação".
    Situacao = Table.AddColumn(NivelCargo, "situacao_quadro",
        each if [no_quadro] = 1 then "No quadro" else "Fora do quadro atual", type text),
    // Garantia do lado "1": uma linha por funcionário (se vier duplicado, a relação 1:* nem é criada).
    SemDuplicados = Table.Distinct(Situacao, {"funcionario_id"})
in
    SemDuplicados

// ---------- CONSULTA: dim_competencia
let
    Fonte = fxTabelaBI("dim_competencia"),
    Tipos = Table.TransformColumnTypes(Fonte, {
        {"competencia_id", type text}, {"competencia", type text}, {"ferramenta", type text},
        {"designer_id", type text}, {"designer_nome", type text}, {"descricao", type text}}, "pt-BR"),
    SemEspacos = Table.TransformColumns(Tipos, {{"competencia", Text.Trim, type text}}),
    SemDuplicados = Table.Distinct(SemEspacos, {"competencia_id"})
in
    SemDuplicados

// ---------- CONSULTA: dim_andar
let
    Fonte = fxTabelaBI("dim_andar"),
    Tipos = Table.TransformColumnTypes(Fonte, {
        {"andar", Int64.Type}, {"andar_nome", type text}, {"andar_rotulo", type text}}, "pt-BR"),
    // Rótulo curto para eixos ("1º", "2º"...; o andar 0 = quem saiu do organograma)
    Curto = Table.AddColumn(Tipos, "andar_curto",
        each if [andar] = 0 then "Fora" else Text.From([andar]) & "º", type text)
in
    Curto

// ---------- CONSULTA: dim_nivel
let
    Fonte = fxTabelaBI("dim_nivel"),
    Tipos = Table.TransformColumnTypes(Fonte, {{"nivel", Int64.Type}, {"nivel_nome", type text}}, "pt-BR"),
    Curto = Table.AddColumn(Tipos, "nivel_curto", each "Nível " & Text.From([nivel]), type text)
in
    Curto

// ---------- CONSULTA: dim_data
// Calendário contínuo (um dia por linha, do primeiro ao último dia com dados). Depois de carregar:
// Modelo → selecione dim_data → Ferramentas de tabela → Marcar como tabela de datas → coluna "data".
let
    Fonte = fxTabelaBI("dim_data"),
    Tipos = Table.TransformColumnTypes(Fonte, {
        {"data", type date}, {"ano", Int64.Type}, {"mes", Int64.Type}, {"mes_nome", type text},
        {"ano_mes", type text}, {"dia", Int64.Type}, {"dia_semana", Int64.Type}, {"dia_semana_nome", type text},
        {"semana_iso", Int64.Type}, {"fim_de_semana", Int64.Type}}, "pt-BR"),
    // Rótulo "19/10" para eixo de gráfico (ordenar por "data" com Classificar por coluna).
    DiaMes = Table.AddColumn(Tipos, "dia_mes", each Date.ToText([data], "dd/MM"), type text)
in
    DiaMes


// =====================================================================================================
// 4. FATOS (o que aconteceu) — lado "*" das relações
// =====================================================================================================

// ---------- CONSULTA: fato_treino
let
    Fonte = fxTabelaBI("fato_treino"),
    Tipos = Table.TransformColumnTypes(Fonte, {
        {"tentativa_id", Int64.Type}, {"data_hora", type datetime}, {"data", type date}, {"hora", Int64.Type},
        {"funcionario_id", type text}, {"andar", Int64.Type}, {"cargo_nivel", type text},
        {"competencia_id", type text}, {"nivel", Int64.Type}, {"acertou", Int64.Type}, {"errou", Int64.Type},
        {"nota", type number}, {"segundos", type number}, {"tipo_erro", type text},
        {"rodada", type text}, {"versao_codigo", type text}}, "pt-BR"),
    // "andar" aqui é o andar NO MOMENTO da tentativa. O modelo filtra andar pela pessoa (dim_andar → dim_funcionario).
    // Renomear evita alguém arrastar a coluna errada para o eixo.
    Renomeada = Table.RenameColumns(Tipos, {{"andar", "andar_na_tentativa"}}),
    // Texto de exibição do erro: "achou_outra_coisa" → "Achou outra coisa" (limpeza no PQ, não no DAX).
    ErroLegivel = Table.AddColumn(Renomeada, "tipo_erro_rotulo",
        each let t = Text.Replace([tipo_erro], "_", " ") in Text.Upper(Text.Start(t, 1)) & Text.Middle(t, 1),
        type text),
    // Performance: tirar o que nenhum visual usa. "rodada" e "versao_codigo" servem à auditoria, não ao painel.
    SemColunasTecnicas = Table.RemoveColumns(ErroLegivel, {"rodada", "versao_codigo"})
in
    SemColunasTecnicas

// ---------- CONSULTA: fato_evolucao_nivel
let
    Fonte = fxTabelaBI("fato_evolucao_nivel"),
    Tipos = Table.TransformColumnTypes(Fonte, {
        {"evento_id", Int64.Type}, {"data_hora", type datetime}, {"data", type date},
        {"funcionario_id", type text}, {"competencia_id", type text}, {"nivel_de", Int64.Type},
        {"nivel_para", Int64.Type}, {"variacao", Int64.Type}, {"tipo_evento", type text}, {"motivo", type text}}, "pt-BR")
in
    Tipos

// ---------- CONSULTA: fato_nivel_atual
// Foto de hoje (sem data): NÃO se liga à dim_data. "desde" é só informativo.
let
    Fonte = fxTabelaBI("fato_nivel_atual"),
    Tipos = Table.TransformColumnTypes(Fonte, {
        {"funcionario_id", type text}, {"competencia_id", type text}, {"nivel", Int64.Type},
        {"desde", type datetime}}, "pt-BR")
in
    Tipos

// ---------- CONSULTA: fato_interacoes
let
    Fonte = fxTabelaBI("fato_interacoes"),
    Tipos = Table.TransformColumnTypes(Fonte, {
        {"interacao_id", Int64.Type}, {"data_hora", type datetime}, {"data", type date},
        {"de_id", type text}, {"para_id", type text}, {"tipo", type text}, {"texto", type text},
        {"ref", type text}}, "pt-BR"),
    // Texto livre: tira quebras de linha e espaços duplos (a tabela do painel fica com altura de linha estável).
    TextoLimpo = Table.TransformColumns(Tipos, {{"texto", each Text.Trim(Text.Clean(_)), type text}}),
    // Conversa sem destinatário ("aviso geral") chega como "" → vira nulo, para não casar com ninguém na relação.
    ParaNulo = Table.ReplaceValue(TextoLimpo, "", null, Replacer.ReplaceValue, {"para_id"}),
    TipoRotulo = Table.AddColumn(ParaNulo, "tipo_rotulo", each
        if [tipo] = "pedido" then "Pedido de ajuda"
        else if [tipo] = "mentoria" then "Mentoria"
        else if [tipo] = "troca" then "Troca de experiência"
        else if [tipo] = "retorno" then "Retorno"
        else if [tipo] = "resposta" then "Resposta"
        else Text.Proper([tipo]), type text)
in
    TipoRotulo

// ---------- CONSULTA: fato_mentorias
let
    Fonte = fxTabelaBI("fato_mentorias"),
    Tipos = Table.TransformColumnTypes(Fonte, {
        {"mentoria_id", Int64.Type}, {"data_hora", type datetime}, {"data", type date},
        {"mentor_id", type text}, {"aprendiz_id", type text}, {"competencia_id", type text},
        {"nivel", Int64.Type}, {"situacao", type text}, {"ajudou", Int64.Type}, {"fechada", Int64.Type},
        {"fechada_em", type datetime}}, "pt-BR"),
    SituacaoRotulo = Table.AddColumn(Tipos, "situacao_rotulo", each
        if [situacao] = "aberta" then "Aberta (aguarda próxima tentativa)"
        else if [situacao] = "ajudou" then "Ajudou"
        else if [situacao] = "nao_ajudou" then "Não ajudou"
        else Text.Proper([situacao]), type text)
in
    SituacaoRotulo

// ---------- CONSULTA: fato_rotinas
let
    Fonte = fxTabelaBI("fato_rotinas"),
    Tipos = Table.TransformColumnTypes(Fonte, {
        {"execucao_id", Int64.Type}, {"data_hora", type datetime}, {"data", type date}, {"rotina", type text},
        {"status", type text}, {"com_erro", Int64.Type}, {"segundos", type number}}, "pt-BR")
in
    Tipos

// ---------- CONSULTA: fato_rh_movimentos
// Hoje com ZERO linhas (nenhuma promoção formal registrada). Carregue mesmo assim: as colunas existem,
// a relação fica pronta e a página de RH passa a mostrar dados sozinha quando o 1º movimento entrar.
let
    Fonte = fxTabelaBI("fato_rh_movimentos"),
    Tipos = Table.TransformColumnTypes(Fonte, {
        {"movimento_id", Int64.Type}, {"data_hora", type datetime}, {"data", type date},
        {"funcionario_id", type text}, {"tipo", type text}, {"de_nivel", type text}, {"para_nivel", type text},
        {"competencia_id", type text}, {"situacao", type text}, {"proposto_por", type text},
        {"validado_por", type text}, {"motivo", type text}}, "pt-BR")
in
    Tipos

// ---------- CONSULTA: _Medidas
// Tabela vazia que só guarda as medidas (o Power BI exige uma tabela "dona" para cada medida).
// Depois de criar a 1ª medida, oculte a coluna "Coluna1": a tabela vira um ícone de calculadora no topo da lista.
let
    Fonte = #table(type table [Coluna1 = text], {})
in
    Fonte
