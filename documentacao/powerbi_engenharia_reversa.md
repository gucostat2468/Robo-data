# Power BI — engenharia reversa documentada (para reproduzir no nosso painel web)

> **Para quem é:** quem mantém o painel web do robô (`robo/painel/estaticos/paineis.js`, JavaScript puro, sem framework) e quer que ele "pareça e se comporte como Power BI".
> **Como foi feito:** ninguém abriu o Power BI para escrever isto. Tudo vem da **documentação oficial da Microsoft** (learn.microsoft.com/power-bi, o repositório público de *schemas* JSON e o blog), lida em **outubro/2026**. Cada seção traz o link de onde a informação saiu.
> **Regra de honestidade:** quando a documentação não confirma algo, o texto diz **"não verificado"**. Nada foi inventado. Se o Power BI que você tem instalado mostrar algo diferente, vale o que está na tela — a Microsoft atualiza o produto todo mês.
> **Arquivo irmão (para máquina ler):** `powerbi/catalogo_powerbi.json`.

---

## Sumário

1. [Antes de tudo: o que mudou em 2025-2026](#1-antes-de-tudo-o-que-mudou-em-2025-2026)
2. [As camadas do aplicativo (faixa de opções, modos de exibição, painéis)](#2-as-camadas-do-aplicativo)
3. [Catálogo completo dos visuais nativos](#3-catálogo-completo-dos-visuais-nativos)
4. [Interações (o "comportamento" do Power BI)](#4-interações)
5. [Sistema de design (tema, cores, fontes, tela, acessibilidade)](#5-sistema-de-design)
6. [Formato de arquivo: PBIX, PBIP, PBIR e TMDL](#6-formato-de-arquivo)
7. [Power BI Service: dashboards, relatórios, apps, comentários, assinaturas](#7-power-bi-service)
8. [Como reproduzimos no nosso painel (viabilidade e prioridade)](#8-como-reproduzimos-no-nosso-painel)
9. [O que não consegui verificar](#9-o-que-não-consegui-verificar)
10. [Fontes](#10-fontes)

---

## 1. Antes de tudo: o que mudou em 2025-2026

Algumas coisas que muita gente "sabe" sobre o Power BI estão desatualizadas. Segundo a documentação atual:

| Antes (o que se costuma dizer) | Agora (documentação de 2026) | Fonte |
|---|---|---|
| Temas ficam na guia **Exibir** | Temas ficam na nova guia **Design** (Galeria de temas, Personalizar tema, Importar, Baixar tema, Tamanho da página, Plano de fundo, Papel de parede) | [Design ribbon](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-design-ribbon) |
| O tema base padrão é o "Clássico" | Novos relatórios usam o tema base **Fluent 2**; existem também **Classic 2026** e **Classic 2018** | [Visual defaults](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-reports-visual-defaults) |
| A página padrão tem 1280×720 | No Fluent 2, **páginas novas nascem com 1920×1080** (fundo e "papel de parede" em tons de cinza, cantos arredondados, títulos ligados, títulos de eixo desligados) | [Visual defaults](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-reports-visual-defaults) |
| Existem "Cartão" e "Cartão de várias linhas"/"Multicartão" | Desde **novembro/2025** o **novo Cartão** (antes "Card (new)") é o cartão padrão e substitui cartão único e multicartão; os antigos continuam disponíveis em "Restaurar visuais padrão" | [Card visual](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-card) |
| O relatório é salvo como `report.json` | O **PBIR** (pasta `definition\` com um arquivo JSON por página/visual) é o **formato padrão e GA**; relatórios antigos são convertidos ao salvar | [PBIR](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report) |
| Q&A é um recurso permanente | O visual Q&A está **sendo descontinuado** (a página de visão geral diz dez/2026; a página do Q&A diz que "as experiências de Q&A saem em fevereiro de 2027"). A recomendação é Copilot | [Visão geral](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualizations-overview), [Q&A](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-q-and-a) |
| Mapa (Bing) é o mapa padrão | O visual **Bing Maps** (mapa e mapa coroplético) está com descontinuação agendada; recomenda-se **Azure Maps** | [Mapas](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-map-visualizations-overview) |
| "Narrativa inteligente" | Hoje chama-se visual **Narrativa** com dois modos: **Copilot** e **Personalizado** | [Smart narrative](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-smart-narrative) |
| Modo de exibição "Dados" | Hoje chama-se **Table view** (Exibição de tabela) | [Table view](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-data-view) |

> Observação: há cópias da documentação (em outras regiões/idiomas) que ainda dizem que o Fluent 2 está "em versão prévia" e que o Classic 2026 é o padrão. A página em inglês atualizada em 31/08/2026 diz que o Fluent 2 é o padrão. Trate como **"padrão a partir de 2026, pode variar conforme a versão instalada"**.

---

## 2. As camadas do aplicativo

Pense no Power BI Desktop como um prédio de quatro andares: **faixa de opções** (os botões no topo), **modos de exibição** (os ícones na lateral esquerda), **painéis** (as colunas à direita) e **tela** (o meio, onde ficam os gráficos).
Fonte geral: [Tour do editor de relatórios](https://learn.microsoft.com/en-us/power-bi/create-reports/service-the-report-editor-take-a-tour), [Introdução ao Desktop](https://learn.microsoft.com/en-us/power-bi/fundamentals/desktop-getting-started).

### 2.1 Faixa de opções (ribbon)

A faixa segue o padrão do Office: tem **barra de pesquisa** de comandos, é **dinâmica** (mostra só o que faz sentido para o que está selecionado), pode ser **recolhida**, aceita **Alt** para atalhos (*keytips*) e **Ctrl+F6** para chegar nela pelo teclado. Ao selecionar uma medida ou coluna aparecem as guias contextuais **Ferramentas de medida** / **Ferramentas de coluna**, onde se digita cadeia de formato.
Fonte: [Ribbon](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-ribbon).

A página oficial atual **não traz mais a lista completa de botões por guia**. Abaixo está só o que consegui **confirmar** em páginas oficiais (cada linha cita a página):

| Guia | Botões confirmados na documentação | Fonte |
|---|---|---|
| **Página Inicial** (Home) | Obter dados (Get data → Excel…), Transformar dados (abre o Power Query), Inserir dados (Enter data), Publicar | [Desktop getting started](https://learn.microsoft.com/en-us/power-bi/fundamentals/desktop-getting-started), [Navigators](https://learn.microsoft.com/en-us/power-bi/create-reports/button-navigators) |
| **Inserir** (Insert) | Botões (Seta, Voltar, Indicador, Em branco, **Navegador → Navegador de páginas / Navegador de indicadores**, Aplicar todas as segmentações, Limpar todas as segmentações), grupo **Power Platform → Power Automate** | [Buttons](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-buttons), [Power Automate](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-automate-visual) |
| **Modelagem** (Modeling) | Nova medida, Nova tabela, **Novo parâmetro → Campos** (parâmetro de campo) / **Intervalo numérico** (parâmetro hipotético) | [What-if](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-what-if), [Field parameters](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-field-parameters) |
| **Exibir** (View) | Exibição da página (Ajustar à página, Ajustar à largura, Tamanho real), Mostrar linhas de grade, Ajustar à grade, Bloquear objetos, painéis **Indicadores**, **Seleção**, **Sincronizar segmentações**, **Layout móvel**, Analisador de desempenho | [Display settings](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-report-display-settings), [Bookmarks](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-bookmarks), [Slicers](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-slicers), [Mobile layout](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-create-mobile-optimized-report-mobile-layout-view) |
| **Design** (nova) | Galeria **Temas** (+ "Galeria de temas"), **Personalizar tema** (abre o painel Tema), **Importar tema**, **Baixar tema**, grupo **Personalizar página** (Tamanho da página, Plano de fundo da página, Papel de parede), "Como criar um tema" | [Design ribbon](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-design-ribbon), [Report themes](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-report-themes) |
| **Otimizar** (Optimize) | **Pausar visuais**, **Atualizar visuais**, **Predefinições de otimização** (Redução de consultas / Interatividade [padrão] / Personalizar), **Analisador de desempenho**, botões Aplicar/Limpar todas as segmentações | [Optimize ribbon](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-optimize-ribbon) |
| **Formatar** (contextual, com visual selecionado) | **Editar interações**, **Aplicar filtros de drill down a → Página inteira** | [Visual interactions](https://learn.microsoft.com/en-us/power-bi/create-reports/service-reports-visual-interactions) |
| **Dados/Drill** (contextual) | **Tabela visual** ("Mostrar como tabela"), **Tabela de ponto de dados** | [Show data](https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-show-data) |
| **Ajuda** (Help) | **Não verificado** em página oficial atual (fontes de terceiros citam links para comunidade, documentação, treinamento) | — |

**Arquivo → Opções e configurações → Opções** é onde ficam: recursos em versão prévia, script R/Python, e em **Arquivo atual → Configurações de relatório**: *Exportar dados*, *Personalizar visuais*, *Copiar nomes de objetos*, *Persistir nível de hierarquia* de parâmetros de campo, *drill-through entre relatórios*.
Fontes: [Export data](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-export-data), [Personalize](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-personalize-visuals), [PBIR](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report).

### 2.2 Os modos de exibição (ícones à esquerda)

| Modo | Para que serve | Fonte |
|---|---|---|
| **Relatório** (Report view) | Montar páginas com visuais. É onde moram as guias Inserir/Formatar e os painéis Filtros/Visualizações/Dados. | [Report editor](https://learn.microsoft.com/en-us/power-bi/create-reports/service-the-report-editor-take-a-tour) |
| **Tabela** (Table view, antigo "Dados") | Ver os dados **depois** de carregados no modelo: grade, barra de fórmulas DAX, busca, ordenar/filtrar, copiar célula/coluna/tabela. Some se tudo for DirectQuery. | [Table view](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-data-view) |
| **Modelo** (Model view) | Diagrama das tabelas e relacionamentos (1:\*, seta = direção do filtro, seta dupla = "Ambos"). Cabeçalhos dos cartões usam a cor do tema. Avisa lentidão acima de 75 tabelas e sugere layout personalizado. | [Model view](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-relationship-view) |
| **Consulta DAX** (DAX query view) | Escrever `EVALUATE`/`DEFINE MEASURE`, rodar, ver grade de resultados; **Atualizar modelo com alterações**; consultas rápidas (Mostrar 100 primeiras linhas, estatísticas de coluna, Avaliar medida). Limites: 15 MB e 1.000.000 de valores por consulta. | [DAX query view](https://learn.microsoft.com/en-us/power-bi/transform-model/dax-query-view) |
| **TMDL** (TMDL view) | Editor de código do modelo semântico em TMDL: arrasta objeto do painel Dados → gera script `createOrReplace`; botões **Aplicar** e **Visualizar** (diff). GA no Desktop, versão prévia na web. | [TMDL view](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-tmdl-view) |

### 2.3 Os painéis

| Painel | O que tem | Fonte |
|---|---|---|
| **Visualizações** | Galeria de ícones de visuais + três abas: **Criar visual** (Build: as "caixas"/*wells* de campos), **Formatar visual** (pincel; subdividido em abas **Visual** e **Geral**) e **Análise** (lupa: linhas de referência, previsão, anomalias). Também abriga a área **Drill-through** e filtros. | [Report editor](https://learn.microsoft.com/en-us/power-bi/create-reports/service-the-report-editor-take-a-tour) |
| **Dados** (antes "Campos") | Tabelas, pastas e campos do modelo. Marcar a caixa de um campo cria/atualiza o visual e o Power BI escolhe a caixa (*well*); arrastar dá controle. Visto verde = tabela em uso. Valor não numérico arrastado para *Valores* vira "Contagem de…". | [Report editor](https://learn.microsoft.com/en-us/power-bi/create-reports/service-the-report-editor-take-a-tour) |
| **Filtros** | Três níveis: **neste visual**, **nesta página**, **em todas as páginas** (+ drill-through). Tipos: básico, avançado, Top N, data relativa. Pode ser **bloqueado**, **oculto** e **formatado** como o relatório. Recolhe com `>>`. | [Add filter](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-report-add-filter), [Report editor](https://learn.microsoft.com/en-us/power-bi/create-reports/service-the-report-editor-take-a-tour) |
| **Seleção** | Lista todos os objetos da página; ícone de **olho** liga/desliga visibilidade (salva nos indicadores); aba **Ordem de tabulação** (ordem do teclado, setas para mover, clicar no número tira da ordem). | [Bookmarks](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-bookmarks), [Acessibilidade](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-accessibility-creating-reports) |
| **Indicadores** (Bookmarks) | Adicionar, renomear, atualizar, agrupar, reordenar (arrastar), **Exibir** (modo apresentação de slides). | [Bookmarks](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-bookmarks) |
| **Sincronizar segmentações** | Colunas **Sincronizar** e **Visível** por página; "Opções avançadas" com nome de grupo. Aparece entre Filtros e Visualizações. | [Slicers](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-slicers) |
| **Analisador de desempenho** | Iniciar gravação → Atualizar visuais → tempo por visual em **Consulta DAX**, **Direct query**, **Exibição do visual**, **Outros**, **Parâmetros avaliados**; Copiar consulta, Executar no DAX query view, Exportar (.json). | [Performance analyzer](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-performance-analyzer) |
| **Tema** (aberto por *Personalizar tema*) | Configurações do tema (tema base, importar/exportar), Cores (paletas Versa, Sunset, Accessible Default, Electric…), Texto, Propriedades do visual (fundo, borda, ícones de cabeçalho, dica de ferramenta, sombra, preenchimento), Página (tela, plano de fundo, papel de parede), Painel de filtros, Cartões de filtro. | [Visual defaults](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-reports-visual-defaults) |

### 2.4 Tela, abas de página e layout móvel

- **Tela (canvas):** cada aba no rodapé é uma página; o **+** cria página nova; clicar com o botão direito na aba renomeia. Fonte: [Drillthrough](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-drillthrough), [Report editor](https://learn.microsoft.com/en-us/power-bi/create-reports/service-the-report-editor-take-a-tour).
- **Configurações da tela** (Formatar página → Configurações da tela): Tipo **16:9 (padrão)**, 4:3, Carta, **Dica de ferramenta**, Personalizado; tamanhos 16:9 oferecidos: **1280×720 (HD)**, 1920×1080 (Full HD), 2560×1440 (QHD), 3840×2160 (4K); alinhamento vertical **Superior/Meio**. Exibição: **Ajustar à página (padrão)**, Ajustar à largura, Tamanho real. Fonte: [Display settings](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-report-display-settings).
- **Layout móvel:** alternador no rodapé ou **Exibir → Layout móvel**; tela de celular com grade fina, painel **Visuais da página** (arrastar para a tela), painel Visualizações (formatação só do layout móvel), painel Seleção (camadas) e **Criar layout móvel automaticamente** (lê da esquerda para a direita, de cima para baixo; não lida com imagem de fundo). Dicas de ferramenta ficam desligadas na tela de edição móvel. Fonte: [Mobile layout](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-create-mobile-optimized-report-mobile-layout-view).

---

## 3. Catálogo completo dos visuais nativos

**Como ler as tabelas:** "Caixas (wells)" são os lugares onde se arrastam campos no painel *Criar visual*. Os nomes estão em inglês como aparecem na documentação, com a tradução usual entre parênteses. "Não usar quando" junta o que a própria Microsoft diz nas "Considerações e limitações" com o bom senso de visualização — quando é opinião minha, está marcado *(boa prática)*.

> **Dicas de ferramenta (Tooltips):** quase todo gráfico aceita campos extras numa caixa *Tooltips*; e qualquer visual pode usar uma **página de dica de ferramenta** (ver §4.6). A caixa *Small multiples* (Pequenos múltiplos) existe nos gráficos de **barras, colunas, linha e área**. Fontes: [Tooltips](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-tooltips), [Small multiples](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-small-multiples).

### 3.1 Comparação e tendência

| Visual | Caixas (wells) | Pergunta de negócio | Não usar quando | Fonte |
|---|---|---|---|---|
| **Colunas empilhadas / agrupadas / 100% empilhadas** (Stacked, Clustered, 100% Stacked column) | **X-axis** (Eixo X), **Y-axis** (Eixo Y), **Legend** (Legenda), **Small multiples**, Tooltips. Combinações válidas: 1 campo no X + 1 medida no Y; ou + exatamente 1 campo na Legenda; ou várias medidas no Y (aí **não aceita Legenda**). | "Quanto cada categoria/mês vale?" (agrupada compara séries lado a lado; empilhada mostra composição do total; 100% mostra só a proporção) | Muitas séries empilhadas (difícil comparar o meio da pilha) *(boa prática)*; eixo hierárquico em small multiples não é suportado; não dá para fixar o intervalo do eixo contínuo | [Column charts](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-column-charts) |
| **Barras empilhadas / agrupadas / 100% empilhadas** (Bar) | Mesmas caixas das colunas, na horizontal. **Não verificado:** a página de barras não foi lida; pela lógica do visual a categoria fica no eixo vertical. | "Ranking de categorias com nome comprido" (a Microsoft recomenda barras quando os rótulos são longos) | Séries temporais (prefira colunas/linha) | [Visão geral](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualizations-overview) |
| **Linha** (Line chart) | **X-axis**, **Y-axis**, **Secondary y-axis** (Eixo Y secundário), **Legend**, **Small multiples**, Tooltips. Várias medidas no Y = série estática; campo na Legenda = série dinâmica (não dá para ter os dois). | "Como o número evoluiu ao longo do tempo? Há sazonalidade?" | Eixo com categorias sem ordem natural *(boa prática)*. Previsão e anomalias exigem **uma única série e eixo X contínuo** | [Line charts](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-line-chart) |
| **Área / Área empilhada / Área 100% empilhada** | Mesmas caixas da linha (doc antiga chama o X de **Axis**) | "Qual o volume ao longo do tempo / quanto cada parte contribui para o total acumulado?" | Mais de 3 séries sobrepostas (a Microsoft recomenda linha para comparar tendência e treemap para comparar volume). Detalhe: clicar numa área **não** filtra os outros visuais (ela só recebe filtro) | [Area chart](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-basic-area-chart) |
| **Linha e coluna agrupada / Linha e coluna empilhada** (Combo) | **X-axis** (eixo compartilhado), **Column y-axis** (Eixo Y da coluna), **Line y-axis** (Eixo Y da linha), Legenda da coluna *(nome não verificado)*, Tooltips | "Realizado (colunas) versus meta ou % (linha)"; duas medidas de escalas diferentes no mesmo eixo X | As duas medidas não têm relação *(boa prática)*. O eixo Y secundário aparece/some sozinho conforme as escalas se sobrepõem | [Combo chart](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-combo-chart) |
| **Faixa** (Ribbon chart) | **X-axis**, **Legend**, **Y-axis** | "Quem está em 1º lugar em cada período e como o ranking mudou?" (a maior fica sempre em cima) | Quando o valor exato importa mais que a posição — não tem rótulos no eixo Y, precisa de rótulos de dados | [Ribbon chart](https://learn.microsoft.com/en-us/power-bi/visuals/desktop-ribbon-charts) |
| **Cascata** (Waterfall / bridge) | **Category** (Categoria), **Breakdown** (Detalhamento), **Y-axis**, Tooltips. "Máximo de detalhamentos" no formato (padrão mostra os 5 maiores; o resto vira "Outros") | "Como saí do valor inicial ao final? Quais aumentos e quedas explicam a diferença?" | Categorias sem soma lógica *(boa prática)*. Cores de aumento/redução/total vêm de `good`/`bad`/`neutral` do tema | [Waterfall](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-waterfall-charts), [Custom themes](https://learn.microsoft.com/en-us/power-bi/create-reports/report-themes-create-custom) |

### 3.2 Parte do todo

| Visual | Caixas | Pergunta | Não usar quando | Fonte |
|---|---|---|---|---|
| **Pizza** (Pie) | **Legend**, **Values**, Tooltips (aceita hierarquia na Legenda → drill) | "Qual a fatia de cada parte no total?" | Muitas fatias: a Microsoft fala em **3–6 fatias**. Formatação condicional não é oficialmente suportada | [Pie and donut](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-pie-donut-chart) |
| **Rosca** (Donut) | Iguais à pizza + **Valor central** (só na rosca; mostra o total ou uma medida escolhida) | Mesma da pizza, com o total no centro | Mesmas da pizza; valor central não pode ser movido e some se não couber | [Pie and donut](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-pie-donut-chart) |
| **Treemap** (Mapa de árvore) | **Category**, **Details** (Detalhes), **Values**, Tooltips | "Quem são os maiores contribuintes numa hierarquia grande?" | Precisa comparar valores parecidos com precisão *(boa prática)*. **Saturação de cor e Detalhes não podem ser usados juntos** | [Treemap](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-treemaps) |
| **Funil** (Funnel) | **Category**, **Values**, Tooltips. Dica nativa mostra % do primeiro estágio e % do estágio anterior | "Onde perco gente no processo sequencial (lead → contrato)?" | Etapas que não são sequenciais; a Microsoft sugere **ao menos 4 estágios** e o primeiro maior que o último | [Funnel](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-funnel-charts) |

### 3.3 Distribuição e relação

| Visual | Caixas | Pergunta | Não usar quando | Fonte |
|---|---|---|---|---|
| **Dispersão / Bolhas / Dot plot** (Scatter) | **Values** (o que define cada ponto — use um ID), **X Axis**, **Y Axis**, **Legend**, **Size** (vira bolhas), Tooltips. Categoria no X vira *dot plot*. Eixo de reprodução (*Play axis*): **não verificado** na página atual | "As duas medidas andam juntas? Há grupos e pontos fora da curva?" | Mais de **10.000 pontos** (máximo); se aparecer um ponto só, faltou um campo único em *Values* | [Scatter](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-scatter) |
| **Gantt (versão prévia)** | Não verificado (página não lida) | "Duração e progresso de tarefas no tempo" | — | [Visão geral](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualizations-overview) |

### 3.4 Tabelas

| Visual | Caixas | Pergunta | Não usar quando | Fonte |
|---|---|---|---|---|
| **Tabela** (Table) | **Columns** (Colunas) | "Quais são os valores exatos, linha a linha?" Tem totais, ordenação, copiar célula/seleção, **totais personalizados** (Soma, Média, Mín, Máx, Contagem distinta, Contagem, Nenhum) e largura de coluna (Ajustar ao conteúdo / Crescer para caber / Largura fixa) | O público precisa ver padrão/tendência, não número *(boa prática)*. O tamanho de célula é calculado pelas primeiras 20 colunas e 50 linhas | [Tables](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-tables) |
| **Matriz** (Matrix) | **Rows** (Linhas), **Columns** (Colunas), **Values** (Valores) | "Tabela dinâmica: valor por duas dimensões com subtotais e drill" (ícones **+/-**, *Auto expand*, cabeçalhos de linha congelados) | Poucos dados que caberiam num gráfico *(boa prática)*. Cruzar realce com seleção em níveis diferentes de tabelas diferentes gera erro | [Matrix](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-matrix-visual), [Interactions](https://learn.microsoft.com/en-us/power-bi/create-reports/service-reports-visual-interactions) |

### 3.5 Mapas

| Visual | Caixas | Pergunta | Não usar quando | Fonte |
|---|---|---|---|---|
| **Azure Maps** | **Location**, **Latitude**, **Longitude**, **Legend**, **Size**, **Tooltips**. Camadas: bolha, coluna 3D, mapa de calor, preenchido, marcador, caminho, referência, pizza, *clustering* | "Onde estão as coisas e quanto vale cada lugar?" | Usuários na China, Coreia ou nuvem de governo (sem suporte); mais de **30.000 pontos**; precisa ser habilitado pelo admin; não sai em exportação/assinatura | [Azure Maps visual](https://learn.microsoft.com/en-us/azure/azure-maps/power-bi-visual-get-started) |
| **Mapa** (bolhas, Bing) | **Location**, **Legend**, **Latitude**, **Longitude**, **Size**, Tooltips. Vários campos em Location = geo-hierarquia com drill | Igual ao Azure Maps | **Descontinuação agendada** — migrar para Azure Maps | [Map tips](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-map-tips-and-tricks) |
| **Mapa coroplético** (Filled map, Bing) | **Location** (obrigatório), **Legend**, **Latitude**, **Longitude**, **Tooltips** | "Como o indicador varia por estado/país?" (sombreado claro→escuro) | Mesma descontinuação do Bing; nomes ambíguos (Paris/FR vs Paris/TX) sem segunda coluna de local | [Filled map](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-filled-maps-choropleths) |
| **Mapa de formas** (Shape map, versão prévia) | **Location**, **Color saturation** (Saturação de cor), **Legend** (só funciona com Saturação preenchida) | "Comparar regiões por cor — inclusive mapas próprios (TopoJSON/GeoJSON: planta baixa, territórios)". Tem mapa embutido do **Brasil por estado** | Mais de **1.500 pontos** | [Shape map](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-shape-map) |
| **ArcGIS for Power BI** (Esri) | Não verificado | Análise espacial avançada | Não sai em assinaturas | [Mapas](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-map-visualizations-overview) |

### 3.6 Cartões, KPIs, medidores e metas

| Visual | Caixas | Pergunta | Não usar quando | Fonte |
|---|---|---|---|---|
| **Cartão** (novo, padrão desde nov/2025) | **Values** (várias medidas = vários cartões), **Categories** (um bloco por categoria; o cabeçalho filtra outros visuais). Formato: Callout, **Rótulos de referência** (com Detalhe), Imagem/Imagem do callout (inclusive SVG vindo de medida), layout de vários cartões, *Fit to space*. Preenchimento padrão 12 px; **Unidades de exibição = Auto** mostra 12K/1,2M (troque para "Nenhum" para número cheio) | "Qual é o número principal agora (e como ele está contra a referência)?" | Quando a pessoa precisa ver a tendência e não há imagem/referência *(boa prática)* | [Card](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-card) |
| **Cartão (legado)** e **Multicartão/Cartão de várias linhas (legado)** | Legado: **não verificado** nesta pesquisa. Acesso: Visualizações → "…" → **Restaurar visuais padrão** | Igual, em relatórios antigos | Novos relatórios (use o novo Cartão) | [Card](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-card) |
| **KPI** | **Value** (Valor), **Trend axis** (Eixo de tendência), **Target** (Destino/meta) | "Estou à frente ou atrás da meta? Quanto falta?" Formato: Direção (**Alto é bom**), ícones (✓ verde / ! vermelho), Distância até a meta | Sem coluna de meta no modelo. **O KPI não tem opção de ordenar** — ordene antes de converter | [KPI](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-kpi) |
| **Medidor** (Gauge, radial) | **Value**, **Minimum value**, **Maximum value**, **Target value**, Tooltips. Sem mínimo/máximo, o Power BI usa **0 e o dobro do valor atual** | "Qual a saúde de um único número em relação à meta?" | Comparar vários itens (ocupa muito espaço por um número só) *(boa prática)* | [Gauge](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-radial-gauge-charts) |
| **Metas / Métricas / Scorecard** (Goals visual) | Não verificado | "Acompanhar métricas e scorecards com status colorido" | — | [Visão geral](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualizations-overview) |

### 3.7 Segmentações (slicers)

| Visual | Caixas / estilos | Pergunta | Não usar quando | Fonte |
|---|---|---|---|---|
| **Segmentação** (Slicer visual, "clássica") | Campo único; estilos **lista vertical, bloco, lista suspensa, seletor de data** (inclui **data relativa** que "anda" sozinha); seleção única/múltipla, **"Selecionar tudo"** (que na verdade **não filtra**; desmarcar itens vira filtro "não é") | "Deixar o filtro mais usado visível e fácil" | Filtros raros ou complexos — use o painel Filtros | [Slicers](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-slicers) |
| **Segmentação de botões** (Button slicer) | Botões em grade com imagens/ícones; **não suporta hierarquia** (com parâmetro de campo mostra só o 1º campo) | Filtro bonito com poucas opções | Muitos valores | [Slicers](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-slicers), [Field parameters](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-field-parameters) |
| **Segmentação de lista** (List slicer) | Lista ou suspensa com imagens/rótulos, hierarquia, busca, formatação condicional, "pílulas" de seleção | Lista longa com busca | — | [Slicers](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-slicers) |
| **Segmentação de entrada** (Input slicer) | Texto/número livre com operador (contém, começa com…); usado em fluxos de *translytical task flows* | "Filtrar digitando" | Precisa colar listas (não aceita colar em lote) | [Slicers](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-slicers) |

Recursos comuns: borracha no cabeçalho limpa a seleção; **colar até 2.000 valores** (Ctrl+V) em Slicer/List/Button; busca (Ctrl+F); "Mostrar selecionados primeiro"; por padrão **segmentações filtram outras segmentações**. Fonte: [Slicers](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-slicers).

### 3.8 Visuais de IA

| Visual | Caixas | Pergunta | Não usar quando | Fonte |
|---|---|---|---|---|
| **Árvore de decomposição** | **Analyze** (Analisar — medida ou agregação), **Explain by** (Explicar por — dimensões), Tooltips. "+" escolhe a próxima dimensão; **divisões de IA** (lâmpada): *Valor alto* / *Valor baixo*, modo Absoluto/Relativo; níveis podem ser **bloqueados** | "Por que este número está assim? Por onde ele se decompõe?" | Mais de 50 níveis / 5.000 pontos (top 10 por nível); SSAS on-premises; divisões de IA não funcionam em Publicar na Web, AAS, Report Server | [Decomposition tree](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-decomposition-tree) |
| **Principais influenciadores** (Key influencers) | **Analyze**, **Explain by**, **Expand by** (define o nível de análise sem virar influenciador). Abas **Principais influenciadores** e **Principais segmentos** | "O que faz o NPS/nota/churn ser baixo?" (regressão logística/linear + árvore de decisão; p-valor 0,05; amostra de 10.000 pontos) | DirectQuery, conexão ao vivo com AAS/SSAS, Publicar na Web; menos de ~100 observações no estado analisado | [Key influencers](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-influencers) |
| **Narrativa** (Smart narrative) | Sem caixas; modos **Copilot** (licença) e **Personalizado** (texto com **valores dinâmicos**). Até 4 resumos por visual / 16 por página; ícone opcional "Narrativa inteligente" no cabeçalho do visual | "Me explique em texto o que esta página mostra" | Tabelas, matrizes, R/Python, visuais personalizados; não fixa em dashboard | [Smart narrative](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-smart-narrative) |
| **P e R** (Q&A) | Caixa de pergunta em linguagem natural, sugestões, ícone de converter em visual padrão, engrenagem (ferramentas de Q&A) | "Pergunte em português/inglês e receba um gráfico" | **Em descontinuação** (dez/2026 ou fev/2027 conforme a página) — use Copilot | [Q&A](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-q-and-a) |
| **Detecção de anomalias** | Não é um visual: é opção da aba **Análise** do gráfico de linha | "Teve pico ou queda fora do esperado?" | Mais de uma série ou eixo não contínuo | [Analytics pane](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-analytics-pane) |

### 3.9 Outros visuais nativos

| Visual | Caixas | Para quê | Limitações | Fonte |
|---|---|---|---|---|
| **Relatório paginado** | **Parameters** (Parâmetros) | Embutir relatório "pixel perfeito" (exporta até 1.000.000 de linhas para Excel pela barra do visual) | Exige capacidade Premium/Fabric F64+ para publicar; não entra em assinatura/exportação; limite de 30.000 valores por campo | [Paginated report visual](https://learn.microsoft.com/en-us/power-bi/visuals/paginated-report-visual) |
| **Power Apps** | Campos do painel Dados (nome exato da caixa **não verificado**) | Aplicativo embutido que recebe o contexto de filtro | Ver página do Power Apps | [Power Apps visual](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-powerapp) |
| **Power Automate** | **Power Automate Data** | Botão que dispara um fluxo com os dados filtrados | Máx. 1.000 registros; não funciona em Publicar na Web, inserido (embedded) nem exportação | [Power Automate visual](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-automate-visual) |
| **Visual R** / **Visual Python** | **Values** (vira o *dataframe* `dataset`; agregação padrão "não resumir") | Gráficos estatísticos sob medida | 150.000 linhas, 5 min, 72 DPI, saída 2 MB; não origina filtro cruzado (só recebe) | [R visuals](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-r-visuals) |
| **Imagem** | Upload, URL, OneLake ou campo de dados | Logo, imagem dinâmica | — | [Visão geral](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualizations-overview) |
| **Caixa de texto e formas** | — (texto pode ter valores ligados a dados) | Títulos, explicações, retângulos/setas | — | [Visão geral](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualizations-overview) |
| **Botões e navegadores** | — | Navegar, aplicar indicador, drill-through, URL, aplicar/limpar segmentações (ver §4.5) | — | [Buttons](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-buttons) |

---

## 4. Interações

### 4.1 Filtro cruzado × realce cruzado, e "Editar interações"

- **Padrão:** clicar num ponto de um visual **filtra ou realça** todos os outros da página. **Filtro cruzado** esconde o que não tem relação; **realce cruzado** mantém tudo e **esmaece** o resto (o pedaço realçado aparece "dentro" da barra). Clicar no vazio ou de novo no item desfaz. **Ctrl+clique** seleciona vários.
- **Linha, dispersão e mapa só podem ser filtrados, não realçados.**
- Para mudar: selecione o visual de origem → **Formatar → Editar interações** → em cada outro visual aparecem os ícones **Filtrar**, **Realçar** e **Nenhum**. A escolha é salva no relatório.
- **Drill não afeta outros visuais por padrão**; mude em **Formatar → Aplicar filtros de drill down a → Página inteira** (no Service: "Drilling filters other visuals").
- A predefinição **Redução de consultas** (guia Otimizar) desliga filtro e realce cruzados e põe botão Aplicar no painel Filtros.

Fontes: [Visual interactions](https://learn.microsoft.com/en-us/power-bi/create-reports/service-reports-visual-interactions), [Column charts](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-column-charts), [Funnel](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-funnel-charts), [Optimize ribbon](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-optimize-ribbon).

### 4.2 Drill (hierarquias)

Com hierarquia no eixo (ex.: Ano > Trimestre > Mês) aparecem **quatro ícones** acima ou abaixo do visual:

1. **Drill up** (seta para cima) — sobe um nível.
2. **Ativar drill down** (seta para baixo) — liga o modo; aparece "Modo de drill ativado: clique num ponto"; clicar num ponto desce **só nele**.
3. **Ir para o próximo nível** (seta dupla) — desce **todos** os pontos de uma vez (perde o pai).
4. **Expandir tudo um nível abaixo** (garfo) — desce mantendo o agrupamento pelo pai (rótulo concatenado).

Fontes: [Column charts](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-column-charts), [Line charts](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-line-chart), [Map tips](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-map-tips-and-tricks).

### 4.3 Drill-through (detalhamento) e entre relatórios

- Página de destino recebe o campo na caixa **Drill-through** (painel Visualizações) → o Power BI **cria sozinho um botão Voltar**.
- No visual de origem: **botão direito no ponto → Drill-through → nome da página**. O campo precisa existir no visual de origem e **não pode estar agregado**.
- Também dá para usar **botão com ação Drill-through** (fica desabilitado sem contexto).
- **Entre relatórios:** só no Service, mesmo workspace, nomes e tipos de campo idênticos, habilitar "Drill-through entre relatórios" no relatório de destino.

Fonte: [Drillthrough](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-drillthrough).

### 4.4 Indicadores (bookmarks) + painel Seleção

Um indicador guarda: **página atual, filtros, segmentações (tipo e estado), seleção/realce, ordenação, posição do drill, visibilidade (painel Seleção), foco/Spotlight**. Opções por indicador: **Dados**, **Exibição**, **Página atual**, **Todos os visuais / Visuais selecionados**. **Não guarda a posição** dos visuais. Há **grupos**, **Exibir** (apresentação de slides) e, no Service, **indicadores pessoais** para quem só lê. Acrescentar uma segmentação depois limpa a segmentação nos indicadores existentes.
Fonte: [Bookmarks](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-bookmarks).

### 4.5 Botões e navegadores

- **Tipos de botão** (Inserir → Botões): setas, Voltar, Informações, Ajuda, P e R, Indicador, Em branco, **Navegador** (de páginas / de indicadores), **Aplicar todas as segmentações**, **Limpar todas as segmentações**.
- **Ações:** Voltar, Indicador, Drill-through, Navegação de página, Navegação de indicador, P e R, URL da Web, Aplicar/Limpar todas as segmentações, Função de dados (prévia).
- **Estados:** Padrão, Ao passar o mouse, Ao pressionar, Desabilitado, Carregando. No Desktop, **Ctrl+clique** para testar.
- **Navegador de páginas:** sincroniza sozinho com nomes, ordem e página atual; opções para mostrar páginas ocultas/de dica. **Navegador de indicadores:** usa um grupo de indicadores; "Permitir desmarcar". Layout **Horizontal / Vertical / Grade**, estado **Selecionado** formatável. Destino de navegação pode ser **condicional** (medida/segmentação).
- No Fluent 2 o botão usa a **1ª cor de dados do tema**; predefinições Padrão, Contorno, Transparente, Ícone e texto; navegador Padrão ou **Guia**.

Fontes: [Buttons](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-buttons), [Navigators](https://learn.microsoft.com/en-us/power-bi/create-reports/button-navigators), [Visual defaults](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-reports-visual-defaults).

### 4.6 Dicas de ferramenta de página de relatório

Página nova → **Configurações da tela → Tipo: Dica de ferramenta** → **Informações da página → Dica de ferramenta: Ativado** → arrastar campos para **Campos de dica de ferramenta**. Ou, no visual: **Formatar → Dicas de ferramenta → Página**: escolher a página (**Auto** volta ao padrão). A dica **não é interativa**, não é lida por leitores de tela, não funciona em dashboards nem com R/Python; em gráfico de linha mostra **uma dica para todas as linhas**.
Fonte: [Report tooltips](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-tooltips).

### 4.7 Sincronizar segmentações

Exibir → **Sincronizar segmentações** → por página: **Sincronizar** (a seleção vale ali) e **Visível** (aparece ali). Sincronizar sem mostrar ainda filtra. Segmentações diferentes podem formar **grupo** (Opções avançadas → mesmo nome; sincronizar alterações de campo e/ou de filtro).
Fonte: [Slicers](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-slicers).

### 4.8 Painel Filtros

Níveis **visual / página / todas as páginas / drill-through**. Campos do próprio visual viram filtros automáticos; dá para filtrar por campo que **não está** no visual. **Básico** (lista com caixas), **Avançado** (condições "é maior que", "contém"…), **Top N**, **data relativa**. Filtros podem ser **bloqueados** ou **ocultos**. No Service, os filtros do leitor **persistem** entre sessões; **Redefinir para o padrão** volta ao que o autor salvou.
Fontes: [Add filter](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-report-add-filter), [Report editor](https://learn.microsoft.com/en-us/power-bi/create-reports/service-the-report-editor-take-a-tour).

### 4.9 Modo de foco, Spotlight, tela inteira

- **Modo de foco:** ícone no cabeçalho do visual; ocupa a tela toda **mantendo o painel Filtros**; sai com **Voltar ao relatório**.
- **Spotlight** (Service): "…" → **Spotlight**: o visual fica em destaque e os outros quase transparentes; é salvo em indicadores.
- **Tela inteira:** Exibir → Tela inteira (sem menus; navegação aparece no rodapé ao mover o mouse).
- **Cores de alto contraste** (Service): Exibir → Cores de alto contraste (#1, #2, preto, branco).

Fontes: [Report view](https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-report-view), [Spotlight](https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-spotlight).

### 4.10 "Mostrar como tabela" e "Ver registros"

- **Mostrar como tabela** (Desktop: guia Dados/Drill → **Tabela visual**; botão direito ou "…"): mostra o **visual em cima e a tabela embaixo** (ou lado a lado, alternando no canto); **< Voltar ao relatório**.
- **Mostrar ponto de dados como tabela** (Desktop: **Tabela de ponto de dados**; o antigo "Ver registros"): todas as linhas por trás de **um ponto**. Não funciona quando o ponto é uma medida.
- Sem suporte em: Cartão, KPI, Principais influenciadores, P e R, Narrativa, Métricas, Paginado, Power Apps, ArcGIS, Power Automate.
- Atalho acessível: **Alt+Shift+F11** abre uma tabela amigável para leitor de tela.

Fontes: [Show data](https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-show-data), [Acessibilidade](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-accessibility-creating-reports).

### 4.11 Exportar dados

"…" → **Exportar dados**. No Desktop só **.csv** (resumido). No Service: **Dados com o layout atual**, **Dados resumidos**, **Dados subjacentes** (exige permissão de *build*). Limites: **.xlsx 150.000 linhas** (matriz: 150.000 interseções), **.xlsx com conexão ao vivo 500.000**, **.csv 30.000** (sem subtotais). A 1ª linha do Excel lista os **filtros aplicados**. Textos que começam com `= @ + -` ganham `'` na frente no CSV. O autor controla em **Configurações de relatório → Exportar dados**; o admin pode sobrepor.
Fonte: [Export data](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-export-data).

### 4.12 Ordenar eixo

"…" → **Ordenar eixo** → escolher campo → **Classificar em ordem crescente/decrescente** (marca de seleção indica o ativo). Atenção: o **KPI não tem ordenação** depois de convertido.
Fontes: [Waterfall](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-waterfall-charts), [KPI](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-kpi).

### 4.13 Formatação condicional

- Onde: botão **fx** ao lado da cor (gráficos) ou seta do campo → **Formatação condicional** (tabela/matriz).
- **Tipos (tabela/matriz):** Cor de fundo, Cor da fonte, **Barras de dados**, **Ícones** (direcionais, formas, indicadores, classificações), **URL da Web**.
- **Estilos:** **Gradiente** (mínimo/máximo + cor do meio opcional; tratamento de vazios), **Regras** (se valor ≥ … e < …, por **Número** ou **Percentual** do intervalo — para percentuais, use decimais e "Número"), **Valor do campo** (medida que devolve `#hex`, `rgb()`, nome CSS ou **nome de cor do tema**: `good`, `bad`, `neutral`, `maxColor`…).
- Funciona em valores e totais, **não em cabeçalhos**; sobrepõe cor manual; **não pode ir no arquivo de tema**.

Fontes: [Conditional table formatting](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-conditional-table-formatting), [Column charts](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-column-charts), [Custom themes](https://learn.microsoft.com/en-us/power-bi/create-reports/report-themes-create-custom).

### 4.14 Parâmetros de campo e parâmetros hipotéticos

- **Parâmetro de campo:** Modelagem → Novo parâmetro → **Campos**. Gera tabela DAX `{("Nome", NAMEOF('T'[Col]), 0), …}` e uma segmentação que **troca a medida ou a dimensão** do gráfico. Botão direito → "Mostrar valores do campo selecionado" vira segmentação hierárquica. Não funciona com visuais de IA, Q&A, medidas implícitas, nem como campo de drill-through/dica.
- **Parâmetro hipotético (what-if):** Modelagem → Novo parâmetro → **Intervalo numérico** (Nome, Tipo de dados, Mínimo, Máximo, Incremento, padrão; "Adicionar segmentação a esta página"). Cria a tabela e uma medida `… Value`. Máx. **1.000 valores** únicos.

Fontes: [Field parameters](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-field-parameters), [What-if](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-what-if).

### 4.15 Pequenos múltiplos

Caixa **Small multiples** em barras, colunas, linha e área; grade padrão (doc antiga: 2×2, até 6×6; **Fluent 2: começa em 1×4 ou 4×1**); eixos sincronizados (Y compartilhado, ou "Ajustar à escala"). Sem suporte: zoom, linha de tendência, previsão, rótulos de total empilhado.
Fontes: [Small multiples](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-small-multiples), [Line charts](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-line-chart), [Visual defaults](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-reports-visual-defaults).

### 4.16 Painel Análise (linhas de referência)

| Linha | Visuais suportados (resumo) |
|---|---|
| **Linha de tendência** | Área, colunas agrupadas, linha, linha e coluna agrupada (eixo de tempo), dispersão |
| **Linha constante X / Y** | Área, barras/colunas (agrupadas, empilhadas, 100%), linha, faixa, dispersão; Y também em **cascata** |
| **Mín / Máx / Média / Mediana / Percentil** | Área, barras e colunas agrupadas, linha, dispersão (percentil só com dados importados ou AS 2016+) |
| **Sombreamento de simetria** (e linha de proporção) | Dispersão |
| **Barras de erro** (por campo ou %, banda de erro na linha) | Barras/colunas agrupadas, linha, linha e coluna agrupada |
| **Previsão** (comprimento, intervalo de confiança…) | **Só linha** |
| **Anomalias** (sensibilidade, "Explicar por", faixa esperada) | **Só linha** |

Cada linha tem nome, cor, transparência, estilo, posição (frente/trás) e rótulo de dados; pode haver várias do mesmo tipo.
Fonte: [Analytics pane](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-analytics-pane).

### 4.17 Personalizar visuais (para quem só lê)

Habilitar em **Configurações de relatório → Personalizar visuais** (e por página/visual em Ícones de cabeçalho). O leitor pode trocar tipo de visual, trocar medida/dimensão, pôr/tirar legenda, comparar medidas, mudar agregação; salva em **indicador pessoal**; "Redefinir para o padrão" desfaz. Perspectivas (criadas no TMDL) limitam os campos oferecidos.
Fonte: [Personalize visuals](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-personalize-visuals).

### 4.18 Comentários e assinaturas (Service)

- **Comentários:** no relatório, dashboard ou visual ("…" → Adicionar comentário), com **@menção**; o 1º comentário da conversa **guarda o estado de filtros como indicador**. Limites: 2.000 caracteres, 100 conversas por item.
- **Assinaturas:** e-mail com imagem e link (ou PDF/PPT do relatório inteiro em Premium/PPU, até 20 páginas/25 MB); frequência horária, diária, semanal, mensal ou **após atualização dos dados**; até 24 assinaturas por item; "Incluir minhas alterações" guarda filtros/segmentações/drill.

Fontes: [Comments](https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-comment), [Subscribe](https://learn.microsoft.com/en-us/power-bi/collaborate-share/end-user-subscribe).

---

## 5. Sistema de design

### 5.1 Camadas do tema

1. **Tema base** (mantido pela Microsoft): **Fluent 2** (padrão de novos relatórios), **Classic 2026**, **Classic 2018**. No PBIR, o tema base aparece com um nome de versão, ex.: `"baseTheme": { "name": "CY24SU06", "type": "SharedResources" }`.
2. **Tema personalizado** (JSON importado ou ajustado no painel Tema) — sobrepõe o base.
3. **Formatação manual do visual** — vence os dois; **Redefinir para o padrão** volta ao tema (e apaga formatação condicional e ações de botão!).

Temas embutidos na galeria: **Redefinir para o padrão, Bloom, Dark, Divergent, Frontier, Innovate, Soft dark, Tidal, Copilot default** (Dark e Soft dark usam a paleta **Versa**). Paletas no painel Tema: **Versa, Sunset, Accessible Default, Electric** (hex dessas paletas **não publicados** nas páginas lidas).
Fontes: [Visual defaults](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-reports-visual-defaults), [Report themes](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-report-themes), [PBIR](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report).

### 5.2 A paleta de 10 cores (a "cara" do Power BI)

A Microsoft **não publica** o JSON do tema base Fluent 2. O que a documentação oficial publica é este exemplo de tema, cujas cores são as mesmas que a página de gráfico de colunas usa como padrão (ela chama `#D64550` de **"Theme color 8"** e cita o azul padrão `#118DFF`). Ou seja: **é a paleta padrão clássica que todo mundo reconhece**, mas **trate-a como "a do exemplo oficial"**, não como garantia de que o Fluent 2 usa exatamente essas.

| # | Hex | Nome usual |
|---|---|---|
| 1 | `#118DFF` | azul |
| 2 | `#12239E` | azul-marinho |
| 3 | `#E66C37` | laranja |
| 4 | `#6B007B` | roxo-escuro |
| 5 | `#E044A7` | rosa |
| 6 | `#744EC2` | violeta |
| 7 | `#D9B300` | amarelo-mostarda |
| 8 | `#D64550` | vermelho |
| 9 | `#197278` | verde-azulado |
| 10 | `#1AAB40` | verde |

Cores semânticas do mesmo exemplo: **good `#1AAB40`**, **neutral `#D9B300`**, **bad `#D64554`** (repare: 1 dígito diferente do `#D64550` da paleta), **maximum `#118DFF`**, **center `#D9B300`**, **minimum `#DEEFFF`**, **null `#FF7F48`**.
Cores estruturais do exemplo: **firstLevelElements/foreground `#252423`**, **secondLevelElements `#605E5C`**, **thirdLevelElements/backgroundLight `#F3F2F1`**, **fourthLevelElements `#B3B0AD`**, **background `#FFFFFF`**, **secondaryBackground `#C8C6C4`**, **tableAccent `#118DFF`**.
Como as séries ganham cor: na **ordem em que aparecem** no visual (1ª série = cor 1). Esgotadas as cores, o Power BI gera variações de matiz/saturação.
Fontes: [Custom themes](https://learn.microsoft.com/en-us/power-bi/create-reports/report-themes-create-custom), [Report themes](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-report-themes), [Column charts](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-column-charts).

### 5.3 Tipografia padrão (classes de texto)

| Classe (JSON) | Padrão | Onde aparece |
|---|---|---|
| `callout` | **DIN**, `#252423`, **45 pt** | valor do cartão, indicador do KPI |
| `title` | **DIN**, `#252423`, **12 pt** | títulos de eixo, título do multicartão, cabeçalho da segmentação |
| `largeTitle` | 14 pt | título do visual |
| `header` | **Segoe UI Semibold**, `#252423`, 12 pt | cabeçalhos dos influenciadores |
| `label` | **Segoe UI**, `#252423`, **10 pt** | valores e cabeçalhos de tabela/matriz |
| `semiboldLabel` | Segoe UI Semibold | — |
| `largeLabel` | 12 pt | rótulos do multicartão |
| `smallLabel` | 9 pt | rótulos de linha de referência, busca da segmentação |
| `lightLabel` | `#605E5C` | legenda, texto de botão, rótulos do eixo de categoria |
| `boldLabel` | Segoe UI Bold | totais e subtotais |
| `largeLightLabel` | `#605E5C`, 12 pt | categoria do cartão, rótulos do medidor |
| `smallLightLabel` | `#605E5C`, 9 pt | rótulos de dados, eixo de valores |

Fonte: [Custom themes](https://learn.microsoft.com/en-us/power-bi/create-reports/report-themes-create-custom). (O exemplo de cartão Fluent 2 da Microsoft usa a pilha `DIN, "DIN Alternate", "DIN Next", "Segoe UI", Tahoma, Arial, sans-serif` em SVG — [Card](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-card).)

### 5.4 Tela, fundo, cabeçalho do visual

- **Tela:** 16:9 é o tipo padrão; 1280×720 é uma das opções 16:9; **no Fluent 2, páginas novas = 1920×1080** e plano de fundo/papel de parede em **tons de cinza**. **Papel de parede** (*wallpaper*) = área fora da página; **Plano de fundo** = a página. Fontes: [Display settings](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-report-display-settings), [Visual defaults](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-reports-visual-defaults).
- **Fluent 2 nos visuais:** títulos e subtítulos ligados, títulos de eixo desligados, **mais preenchimento e cantos arredondados**, linha suave por padrão, predefinição "Rótulos de dados" que tira o eixo. Fonte: [Visual defaults](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-reports-visual-defaults).
- **Ícones do cabeçalho do visual** (confirmados nas páginas lidas): ícones de **drill** (4), **Modo de foco**, **Filtro** (ícone de funil), **Mais opções (…)**, **borracha** nas segmentações, **Narrativa inteligente** (opcional), **Personalizar visual**, **Analisar este visual** (com o Analisador de desempenho gravando). São ligados/desligados em **Formatar → Geral → Ícones de cabeçalho**. A lista completa oficial (com avisos/erros, fixar, copiar como imagem) **não foi verificada** — a página dedicada retornou 404. Fontes: [Column charts](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-column-charts), [Report view](https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-report-view), [Smart narrative](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-smart-narrative), [Personalize](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-personalize-visuals), [Performance analyzer](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-performance-analyzer).

### 5.5 Estrutura do JSON de tema

Único campo obrigatório: `name`. Quatro blocos: **cores do tema**, **cores estruturais**, **classes de texto**, **estilos de visual**. O *schema* oficial fica em [microsoft/powerbi-desktop-samples → Report Theme JSON Schema](https://github.com/microsoft/powerbi-desktop-samples/tree/main/Report%20Theme%20JSON%20Schema) (arquivos `reportThemeSchema-2.1xx.json`, um por versão mensal; o mais novo listado é 2.159, out/2026).

```json
{
  "$schema": "reportThemeSchema.json",
  "name": "Custom Theme",
  "dataColors": ["#118DFF", "#12239E", "#E66C37", "#6B007B", "#E044A7",
                 "#744EC2", "#D9B300", "#D64550", "#197278", "#1AAB40"],
  "good": "#1AAB40", "neutral": "#D9B300", "bad": "#D64554",
  "maximum": "#118DFF", "center": "#D9B300", "minimum": "#DEEFFF", "null": "#FF7F48",
  "firstLevelElements": "#252423", "secondLevelElements": "#605E5C",
  "thirdLevelElements": "#F3F2F1", "fourthLevelElements": "#B3B0AD",
  "background": "#FFFFFF", "secondaryBackground": "#C8C6C4", "tableAccent": "#118DFF",
  "textClasses": {
    "callout": { "fontSize": 45, "fontFace": "DIN", "color": "#252423" },
    "title":   { "fontSize": 12, "fontFace": "DIN", "color": "#252423" },
    "header":  { "fontSize": 12, "fontFace": "Segoe UI Semibold", "color": "#252423" },
    "label":   { "fontSize": 10, "fontFace": "Segoe UI", "color": "#252423" }
  },
  "visualStyles": {
    "*": { "*": { "*": [{ "wordWrap": true }],
                  "categoryAxis": [{ "gridlineStyle": "dotted" }] } },
    "scatterChart": { "*": { "bubbles": [{ "bubbleSize": -10 }] } }
  }
}
```

`visualStyles` segue `<tipoDeVisual> → <predefinição> → <cartão de formatação> → [{ propriedade: valor }]`; `"*"` = "todos" (todos os visuais / estilo padrão / todos os cartões). Uma predefinição com nome (ex.: `"Demo Preset 1"`) aparece no menu **Estilo** do painel Formatar. Cores em propriedades vão como `{ "solid": { "color": "#FFFFFF" } }`. Formatação condicional **não** pode ir no tema.
O nome das cores no DAX (para formatação por "Valor do campo"): `background`, `backgroundDark`, `backgroundLight`, `backgroundNeutral`, `foreground`, `foregroundNeutralSecondary`, `foregroundNeutralTertiary`, `disabledText`, `hyperlink`, `visitedHyperlink`, `mapPushpin`, `shapeStroke`, `tableAccent`, `good`, `neutral`, `bad`, `maxColor`, `midColor`, `minColor`, `nullColor`.
Fonte: [Custom themes](https://learn.microsoft.com/en-us/power-bi/create-reports/report-themes-create-custom).

> Nosso tema atual (`powerbi/tema_robo.json`, "Robô de Planilhas · Dark Premium") já segue essa estrutura — o painel web pode ler o mesmo arquivo.

### 5.6 Acessibilidade (o que a Microsoft pede)

- **Contraste mínimo 4,5:1** entre texto e fundo (WCAG 2.1, 1.4.3).
- **Não usar só cor** para informar: use **marcadores com formas diferentes** em linha/área/combo/dispersão.
- Evitar pares difíceis para daltônicos: verde+vermelho, verde+marrom, azul+roxo, verde+azul, verde-claro+amarelo, azul+cinza, verde+cinza, verde+preto.
- **Texto alternativo** em todo visual que informa algo (máx. **250 caracteres**; pode ser dinâmico via fx).
- **Ordem de tabulação** no painel Seleção; tirar formas decorativas da ordem.
- Títulos sem siglas; rótulos de dados com moderação ("teste de apertar os olhos").
- **Alto contraste:** o Desktop detecta o modo do Windows; o Service tem Exibir → Cores de alto contraste.
- Teclado: **Shift+?** mostra atalhos; **Alt+Shift+F11** abre a tabela acessível; não pôr informação importante só em dica de ferramenta.

Fonte: [Acessibilidade](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-accessibility-creating-reports), [Report view](https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-report-view).

---

## 6. Formato de arquivo

### 6.1 PBIX × PBIP

- **PBIX:** um arquivo único (binário) com relatório + modelo + dados.
- **PBIP (Power BI Project):** **Arquivo → Salvar como → .pbip**; vira **pasta com arquivos de texto** (bons para Git/diff/CI-CD). Dá para voltar a PBIX pelo mesmo "Salvar como" (não há conversão por código). Limites: caminho de 260 caracteres no Windows, salvar em UTF-8 **sem BOM**, quebra de linha CRLF, sem rótulos de confidencialidade.

```text
Projeto/
├── AdventureWorks.Report/
├── AdventureWorks.SemanticModel/
├── .gitignore          ← **/.pbi/localSettings.json  e  **/.pbi/cache.abf
└── AdventureWorks.pbip ← só aponta para a pasta do relatório (opcional)
```

Fonte: [PBIP overview](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview).

### 6.2 Pasta do relatório e PBIR

```text
AdventureWorks.Report/
├── .pbi/localSettings.json          (local, ignorado no Git)
├── CustomVisuals/                   (visuais privados .pbiviz)
├── StaticResources/RegisteredResources/  (temas, imagens)
├── definition.pbir                  (OBRIGATÓRIO: aponta o modelo)
└── definition/                      (formato PBIR)
    ├── version.json
    ├── report.json                  (filtros e formatação de relatório, tema)
    ├── reportExtensions.json        (medidas do relatório)
    ├── bookmarks/
    │   ├── bookmarks.json
    │   └── [nome].bookmark.json
    └── pages/
        ├── pages.json               (ordem e página ativa)
        └── [nomeDaPagina]/
            ├── page.json
            └── visuals/
                └── [nomeDoVisual]/
                    ├── visual.json
                    └── mobile.json  (layout móvel do visual)
```

Nomes de pasta: por padrão um identificador de 20 caracteres (ex.: `90c2e07d8e84e7d5c026`); pode renomear para algo legível usando só letras, dígitos, `_` ou `-` (reinicie o Desktop). Limites do serviço: 1.000 páginas, 1.000 visuais por página, 300 MB. **Atenção:** `visual.json` pode conter **valores de dados** (ex.: um filtro `'Empresa' = 'Contoso'`).
Fonte: [PBIR](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report). Schemas: [microsoft/json-schemas → fabric/item/report/definition](https://github.com/microsoft/json-schemas/tree/main/fabric/item/report/definition).

**`definition.pbir` (exemplo oficial):**

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
  "version": "4.0",
  "datasetReference": { "byPath": { "path": "../Sales.Dataset" } }
}
```

**`report.json` (trecho do exemplo oficial):**

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.0.0/schema.json",
  "themeCollection": {
    "baseTheme": { "name": "CY24SU06", "reportVersionAtImport": "5.55", "type": "SharedResources" }
  },
  "annotations": [ { "name": "defaultPage", "value": "c2d9b4b1487b2eb30e98" } ]
}
```

**`page.json` (esqueleto montado a partir do schema `page/2.0.0`):** obrigatórios `$schema`, `name`, `displayName`, `displayOption` (`FitToPage` | `FitToWidth` | `ActualSize`); `height`/`width` em pixels; opcionais `filterConfig`, `objects`, `visibility` (`AlwaysVisible` | `HiddenInViewMode`), `type` (`Drillthrough` | `Tooltip`), `visualInteractions`.

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
  "name": "visao_geral",
  "displayName": "Visão geral",
  "displayOption": "FitToPage",
  "height": 720,
  "width": 1280
}
```

**`visual.json` (esqueleto montado a partir dos schemas `visualContainer/2.4.0` e `visualConfiguration/2.2.0`):** obrigatórios `$schema`, `name` (máx. 50 caracteres), `position` (`x`, `y`, `width`, `height`; opcionais `z`, `tabOrder`, `angle`) e `visual` (com `visualType` obrigatório). Dentro de `query.queryState`, cada chave é um papel (caixa) com `projections` = lista de `{ field, queryRef, nativeQueryRef?, displayName? }`.

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json",
  "name": "colunas_vendas",
  "position": { "x": 20, "y": 20, "z": 0, "width": 600, "height": 320, "tabOrder": 0 },
  "visual": {
    "visualType": "clusteredColumnChart",
    "query": {
      "queryState": {
        "Category": { "projections": [ { "field": { "...": "ver semanticQuery schema" }, "queryRef": "Vendas.Mes" } ] },
        "Y":        { "projections": [ { "field": { "...": "ver semanticQuery schema" }, "queryRef": "Vendas.Total" } ] }
      }
    },
    "drillFilterOtherVisuals": true
  }
}
```

> **Não verificado:** os nomes exatos dos papéis (`Category`, `Y`, …) por tipo de visual e o conteúdo interno de `field` (definido em outro schema, `semanticQuery`). Use "Copiar nome do objeto" + abrir o PBIP no VS Code para ver um visual real.

### 6.3 Pasta do modelo semântico e TMDL

```text
AdventureWorks.SemanticModel/
├── .pbi/ (localSettings.json, editorSettings.json, cache.abf, unappliedChanges.json)
├── DAXQueries/   (cada aba do DAX query view vira [aba].dax)
├── TMDLScripts/  (cada aba do TMDL view vira [aba].tmdl)
├── definition.pbism   (OBRIGATÓRIO; version 4.0+ aceita TMDL)
├── definition/        (formato TMDL)
│   ├── database.tmdl
│   ├── model.tmdl
│   ├── relationships.tmdl
│   ├── expressions.tmdl
│   ├── dataSources.tmdl
│   ├── functions.tmdl     (funções DAX definidas pelo usuário)
│   ├── tables/  [Tabela].tmdl  (colunas, medidas, partições dentro)
│   ├── roles/   cultures/   perspectives/
├── diagramLayout.json (não editar fora do Desktop)
└── model.bim          (só no formato antigo TMSL)
```

TMDL usa **indentação por tabulação** (estilo YAML), `=` para expressões (DAX/M) e `:` para propriedades; nomes com espaço, ponto, `=`, `:` ou `'` vão entre aspas simples; `///` é descrição. Exemplo mínimo (adaptado do exemplo oficial):

```tmdl
model Model
	culture: pt-BR

table Vendas

	measure 'Total Vendas' = SUM(Vendas[Valor])
		formatString: #,##0

	column Valor
		dataType: decimal
		sourceColumn: Valor
		summarizeBy: sum

	partition Vendas = m
		mode: import
		source =
			let
				Fonte = Csv.Document(File.Contents("vendas.csv"))
			in
				Fonte

relationship 9f1c0d2e-0000-4000-8000-000000000001
	fromColumn: Vendas.'Id Produto'
	toColumn: Produto.'Id Produto'
```

Fontes: [Semantic model folder](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset), [TMDL overview](https://learn.microsoft.com/en-us/analysis-services/tmdl/tmdl-overview).

---

## 7. Power BI Service

| Conceito | O que é | Fonte |
|---|---|---|
| **Workspace** | Área de colaboração onde ficam relatórios, modelos e dashboards; papéis Admin, Member, Contributor, Viewer | [Apps](https://learn.microsoft.com/en-us/power-bi/collaborate-share/service-create-distribute-apps) |
| **Relatório** | Uma ou mais páginas, **um** modelo semântico, filtros/segmentações/drill; feito no Desktop ou no Service | [Dashboards](https://learn.microsoft.com/en-us/power-bi/create-reports/service-dashboards) |
| **Dashboard** | **Uma página** de **blocos fixados** (*tiles*) vindos de vários relatórios/modelos; **não filtra**, **tem alertas**, só existe no Service; clicar no bloco abre o relatório | [Dashboards](https://learn.microsoft.com/en-us/power-bi/create-reports/service-dashboards) |
| **App de workspace** | Pacote publicado a partir do workspace, com navegação, até 25 **audiências** (cada uma vê um conjunto), até 10.000 usuários/grupos; leitor não edita | [Apps](https://learn.microsoft.com/en-us/power-bi/collaborate-share/service-create-distribute-apps) |
| **Comentários / Assinaturas** | Ver §4.18 | [Comments](https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-comment), [Subscribe](https://learn.microsoft.com/en-us/power-bi/collaborate-share/end-user-subscribe) |

---

## 8. Como reproduzimos no nosso painel

**Contexto:** o painel (`robo/painel/estaticos/paineis.js`) recebe de `/api/paineis` **dados já agregados** (+ amostras de linhas) e desenha em **SVG puro**. Já existem: `pbKpis` (cartões com o SQL na dica), `pbLinha` (tendência), `pbBarras` (barras horizontais com **linha de meta** e cor de "ruim"), `pbColunas`, `pbTabela`, `pbCartao`. Não há motor DAX: qualquer filtro só funciona sobre o que veio no JSON.

### 8.1 Viabilidade de cada comportamento

| Comportamento Power BI | Viável? | Como fazer no nosso painel | Limite honesto |
|---|---|---|---|
| **Paleta, fontes, tela 16:9** | Sim | Ler `powerbi/tema_robo.json` (ou a paleta da §5.2) para `dataColors`, `good/neutral/bad`, `textClasses`; cor da série = ordem de aparição | Fontes DIN podem não existir no navegador — usar a pilha `DIN, "DIN Alternate", "Segoe UI", Tahoma, Arial, sans-serif` |
| **Filtro cruzado por clique** | Sim, parcial | Clique numa barra guarda `{campo: valor}` no estado da página; os outros cartões re-renderizam filtrando as **linhas de amostra** ou séries que tenham aquele campo | Só funciona se a API mandar os dados **por aquela dimensão**; agregado pronto não "desagrega" |
| **Realce cruzado** | Sim, parcial | Mesmo estado; em vez de esconder, reduzir opacidade do que não bate (ex.: 0,4) | Realce "dentro" da barra exige o valor parcial vindo pronto da API |
| **Editar interações** (Filtrar/Realçar/Nenhum) | Sim | Mapa `interacoes[origem][destino] = "filtrar" \| "realcar" \| "nenhum"` na definição da página | — |
| **Segmentações** | Sim | `<select multiple>`/botões sobre valores distintos da amostra; "Selecionar tudo" = **sem filtro** (igual ao Power BI) | Valores raros podem não estar na amostra |
| **Painel Filtros** (visual/página/relatório) | Sim | Gaveta lateral recolhível `>>` com três seções; filtros básicos (lista) e Top N | Filtro avançado só sobre colunas que vieram |
| **Dicas de ferramenta** | Sim | `<title>` no SVG (já usamos) ou caixa flutuante com campos extras; "página de dica" = mini-cartão | Não interativa (igual ao Power BI) |
| **Modo de foco** | Sim | Botão no cabeçalho do cartão abre o cartão em sobreposição de tela cheia com "← Voltar ao relatório" | — |
| **Mostrar como tabela** | Sim | Em foco, desenhar o gráfico em cima e `pbTabela` com as mesmas linhas embaixo (alternar vertical/horizontal) | — |
| **Exportar CSV** | Sim | Gerar CSV das linhas do cartão no navegador; 1ª linha "Filtros aplicados: …"; prefixar `'` em textos que começam com `= @ + -` (como o Power BI faz) | Só o que está no navegador |
| **Drill down/up** | Sim, se a API mandar níveis | Hierarquia `Ano > Mês > Dia` como séries aninhadas; os 4 ícones; "próximo nível" vs "expandir" | Cada nível precisa vir pré-agregado |
| **Indicadores via URL** | Sim | Serializar `{pagina, filtros, segmentacoes, foco, drill}` em `location.hash`; "copiar link" = indicador pessoal | Não guarda posição (igual ao Power BI) |
| **Navegador de páginas** | Sim | As abas `paineisAba` já existem — estilizar como o navegador (estado selecionado) | — |
| **Formatação condicional** | Sim | Funções `gradiente(min,max)`, `regras([...])`, `valorDoCampo` aceitando `#hex` **ou** nomes `good/bad/neutral`; barras de dados e ícones na tabela | — |
| **Linhas de referência** | Sim | Constante (meta — já existe em `pbBarras`), média, mediana, mín, máx, percentil calculados no navegador sobre a série; tendência por mínimos quadrados | Previsão e anomalias de verdade exigem modelo — **não fazer** no navegador |
| **Pequenos múltiplos** | Sim | Repetir `pbLinha`/`pbColunas` numa grade com eixo Y compartilhado | Custa espaço; limitar a 6×6 |
| **KPI / Medidor** | Sim | Cartão com seta e cor `good/bad` conforme direção "Alto é bom"; medidor = arco SVG | — |
| **Ordenar eixo** | Sim | Menu "…" → campo → crescente/decrescente | — |
| **Acessibilidade** | Sim | `role="img"` + `aria-label` (já usamos), contraste ≥ 4,5:1, marcadores com formas, ordem de tabulação, tabela acessível | — |
| Árvore de decomposição, Influenciadores, Q&A, Narrativa Copilot, mapas Azure, paginado, Power Apps/Automate | **Não** (ou fora de escopo) | — | Dependem de serviços/modelos da Microsoft |

### 8.2 Ordem de prioridade sugerida

1. **Tema** (ler o JSON de tema; cores por ordem de série; `good/bad`).
2. **Dicas de ferramenta** padronizadas + **acessibilidade** (base para tudo).
3. **Modo de foco + Mostrar como tabela + Exportar CSV** (um botão "…" no cabeçalho de cada cartão; ganho grande, risco baixo).
4. **Segmentações + painel Filtros** (estado único da página).
5. **Filtro/realce cruzado por clique** + "Editar interações" na definição da página.
6. **Indicadores via URL** (o estado do item 4/5 vira `#hash`).
7. **Formatação condicional** e **linhas de referência** (média/mediana/meta).
8. **Drill down/up** (só onde a API já manda hierarquia).
9. **Pequenos múltiplos**, **KPI/medidor**.

---

## 9. O que não consegui verificar

- **Hex da paleta do tema base Fluent 2** (e das paletas Versa, Sunset, Accessible Default, Electric): a Microsoft não publica. A paleta da §5.2 é a do **exemplo oficial** (coincide com o padrão clássico citado pela página de colunas).
- **Lista completa de botões por guia** da faixa de opções (especialmente Página Inicial e **Ajuda**): a página oficial atual não lista mais; só confirmei os botões citados na §2.1.
- **Lista oficial completa dos ícones do cabeçalho do visual**: a página dedicada retornou 404.
- **Caixas exatas** de: barras (horizontal), legenda do combo, eixo de reprodução da dispersão, cartão legado/multicartão, Power Apps, Gantt, Metas, ArcGIS.
- **Nomes dos papéis** (`Category`, `Y`, `Values`…) por tipo de visual no `visual.json` do PBIR e o formato interno de `field`.
- **Data exata da descontinuação do Q&A** (as duas páginas oficiais divergem: dez/2026 × fev/2027).
- **Status Fluent 2 padrão × prévia**: a página em inglês (ago/2026) diz padrão; cópias regionais ainda dizem prévia.

---

## 10. Fontes

Todas acessadas em outubro de 2026.

- Temas: https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-report-themes
- Tema personalizado (JSON): https://learn.microsoft.com/en-us/power-bi/create-reports/report-themes-create-custom
- Padrões visuais / tema base: https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-reports-visual-defaults
- Schema do tema: https://github.com/microsoft/powerbi-desktop-samples/tree/main/Report%20Theme%20JSON%20Schema
- Faixa de opções: https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-ribbon
- Guia Design: https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-design-ribbon
- Guia Otimizar: https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-optimize-ribbon
- Introdução ao Desktop: https://learn.microsoft.com/en-us/power-bi/fundamentals/desktop-getting-started
- Editor de relatórios: https://learn.microsoft.com/en-us/power-bi/create-reports/service-the-report-editor-take-a-tour
- Visão geral dos visuais: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualizations-overview
- Colunas: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-column-charts
- Combo: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-combo-chart
- Cascata: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-waterfall-charts
- Faixa: https://learn.microsoft.com/en-us/power-bi/visuals/desktop-ribbon-charts
- Dispersão: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-scatter
- Pizza e rosca: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-pie-donut-chart
- Treemap: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-treemaps
- Funil: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-funnel-charts
- Linha: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-line-chart
- Área: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-basic-area-chart
- Mapas (visão geral): https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-map-visualizations-overview
- Mapa (dicas/Bing): https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-map-tips-and-tricks
- Mapa coroplético: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-filled-maps-choropleths
- Mapa de formas: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-shape-map
- Azure Maps: https://learn.microsoft.com/en-us/azure/azure-maps/power-bi-visual-get-started
- Cartão: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-card
- KPI: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-kpi
- Medidor: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-radial-gauge-charts
- Segmentações: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-slicers
- Tabela: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-tables
- Matriz: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-matrix-visual
- Árvore de decomposição: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-decomposition-tree
- Principais influenciadores: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-influencers
- Narrativa: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-smart-narrative
- P e R: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-q-and-a
- Power Apps: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-powerapp
- Power Automate: https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-automate-visual
- Relatório paginado (visual): https://learn.microsoft.com/en-us/power-bi/visuals/paginated-report-visual
- Visuais R: https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-r-visuals
- Interações: https://learn.microsoft.com/en-us/power-bi/create-reports/service-reports-visual-interactions
- Drill-through: https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-drillthrough
- Dicas de página: https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-tooltips
- Indicadores: https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-bookmarks
- Botões: https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-buttons
- Navegadores: https://learn.microsoft.com/en-us/power-bi/create-reports/button-navigators
- Filtros: https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-report-add-filter
- Foco / exibição: https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-report-view
- Spotlight: https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-spotlight
- Mostrar como tabela: https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-show-data
- Exportar dados: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-export-data
- Painel Análise: https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-analytics-pane
- Parâmetros de campo: https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-field-parameters
- Parâmetros hipotéticos: https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-what-if
- Pequenos múltiplos: https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-small-multiples
- Personalizar visuais: https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-personalize-visuals
- Formatação condicional: https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-conditional-table-formatting
- Tamanho de página: https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-report-display-settings
- Acessibilidade: https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-accessibility-creating-reports
- Layout móvel: https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-create-mobile-optimized-report-mobile-layout-view
- Analisador de desempenho: https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-performance-analyzer
- Exibição de modelo: https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-relationship-view
- Exibição de tabela: https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-data-view
- DAX query view: https://learn.microsoft.com/en-us/power-bi/transform-model/dax-query-view
- TMDL view: https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-tmdl-view
- PBIP: https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview
- PBIR (pasta do relatório): https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report
- Pasta do modelo semântico: https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset
- TMDL: https://learn.microsoft.com/en-us/analysis-services/tmdl/tmdl-overview
- Schemas PBIR: https://github.com/microsoft/json-schemas/tree/main/fabric/item/report/definition
- Dashboards: https://learn.microsoft.com/en-us/power-bi/create-reports/service-dashboards
- Apps: https://learn.microsoft.com/en-us/power-bi/collaborate-share/service-create-distribute-apps
- Comentários: https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-comment
- Assinaturas: https://learn.microsoft.com/en-us/power-bi/collaborate-share/end-user-subscribe
