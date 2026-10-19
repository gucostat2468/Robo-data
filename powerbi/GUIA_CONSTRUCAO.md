# Guia de construção: painel Power BI "Robô de Planilhas"

Este guia leva você do zero ao painel pronto, clique a clique: conexão, limpeza, modelo estrela, DAX, 5 abas com design executivo, validação e publicação.

> **Nota honesta antes de começar.** Este kit **não traz um arquivo `.pbix`**. O Power BI Desktop só roda no Windows, e o kit foi produzido num ambiente Linux sem ele. Por isso não foi possível gerar nem abrir um `.pbix` para conferir.
>
> O que foi validado de verdade:
> - as views do schema `bi` rodando no PostgreSQL (Neon);
> - as contagens batendo entre Neon, CSV e Excel (tabela na seção 9);
> - os números das telas, recalculados a partir dos mesmos dados.
>
> O que **não** foi executado: as medidas DAX e o código M foram escritos seguindo a documentação, mas não rodaram dentro do Power BI. Por isso a seção 9 traz números-âncora. Se o seu painel mostrar os mesmos números, está certo.

---

## Resumo Executivo

**O painel responde a uma pergunta por aba:**

| Aba | Pergunta de negócio | Para quem |
|---|---|---|
| 1. Visão Executiva | Como a empresa está agora, em um olhar? | Diretoria |
| 2. Treino & Evolução | Os funcionários estão aprendendo, e onde ainda erram? | Heads e coordenação |
| 3. Pessoas & Andares | Quem são, onde estão e como cada andar evolui? | Gestão de pessoas |
| 4. Conversas & Mentorias | Quem ajuda quem, e isso funciona? | Coordenação |
| 5. Operação & Rotinas | As rotinas automáticas estão saudáveis? | TI / Operações |

**Retrato dos dados de hoje** (instantâneo de 19/10/2026, 17:25):
- 726 tentativas de treino, com **98,6% de acerto**;
- todos os 88 funcionários treinaram;
- nível médio de 2,40 numa escala de 1 a 5;
- 7 subidas de nível e nenhuma queda;
- no **nível 4 o acerto cai para 84,8%**: é ali que o treino ensina;
- 30 conversas e 10 mentorias, das quais só 2 fechadas, uma amostra pequena demais para concluir;
- 160 execuções de rotina com 2 erros, os dois em `memoria_pg`.

**O que tem nesta pasta:**

| Arquivo | Para que serve |
|---|---|
| `estrela_neon.sql` | Cria o modelo estrela (schema `bi`) no PostgreSQL. Já aplicado no Neon. |
| `dados/*.csv` + `dados/modelo_estrela.xlsx` | As mesmas 12 tabelas em arquivo, para quem não quer conectar no banco. |
| `power_query.m` | Todas as consultas M, com tipos e limpeza. Um único parâmetro troca entre banco e Excel. |
| `medidas.dax` | O catálogo de cerca de 50 medidas, comentado linha a linha. |
| `tema_robo.json` | O tema de cores e fontes: visuais transparentes e paleta validada. |
| `telas/0X_*.png` | As maquetes 1920x1080 com números reais. Mostram como cada aba deve ficar. |
| `telas/0X_*_fundo.png` | Os fundos para aplicar no Power BI: a moldura, sem números. |
| `exportar_estrela.py`, `gerar_telas.py` | Os geradores. Rode de novo para atualizar tudo (seção 11). |

---

## Explicação Técnica

### Por que um modelo estrela?

O modelo estrela tem dois tipos de tabela:
- **Fatos**: o que aconteceu. Uma linha é um evento, como uma tentativa, uma conversa ou uma execução. São tabelas longas e estreitas.
- **Dimensões**: quem, o quê, onde e quando. Uma linha é uma coisa, como uma pessoa, uma competência ou um dia. São tabelas curtas e largas.

Os filtros saem das dimensões e descem para as fatos, **sempre em uma direção só**. É o desenho que o motor do Power BI (VertiPaq) foi feito para calcular rápido. Ele também evita os dois erros clássicos de iniciante: números repetidos em todas as linhas e totais que não batem.

```
                      dim_andar (6)
                          │ 1
                          ▼ *
dim_competencia (15) ── dim_funcionario (88) ──┐
   │ 1                       │ 1               │
   │                         ▼ *               │
   ├──────────────► fato_treino (726) ◄────────┼── dim_nivel (5)
   ├──────────────► fato_evolucao_nivel (399)  │
   ├──────────────► fato_nivel_atual (392)  ◄──┤   (foto de hoje, sem data)
   ├──────────────► fato_mentorias (10) ◄──────┤   aprendiz_id = ativa · mentor_id = INATIVA
   └──────────────► fato_rh_movimentos (0)     │
                    fato_interacoes (30) ◄─────┘   de_id = ativa · para_id = INATIVA
                    fato_rotinas (160)          (não tem pessoa: só data)

dim_data (2 dias) ──► coluna "data" de todas as fatos que têm data
```

### Decisões de modelagem (e o porquê de cada uma)

1. **Andar é o andar ATUAL da pessoa.** O caminho é `dim_andar → dim_funcionario → fatos`, um "floco de neve" curto. Assim, filtrar "3º andar" filtra as pessoas do 3º andar em todas as abas de uma vez.
   - `fato_treino` também tem o andar no momento da tentativa. O Power Query renomeia essa coluna para `andar_na_tentativa` e ela fica oculta, para ninguém usá-la por engano.
   - Uma pessoa saiu do organograma (`tina_contatos`, 8 tentativas). Ela cai no **andar 0, "Fora do quadro atual"**, em vez de virar "(Em branco)".
2. **Duas pessoas na mesma fato** (de/para nas conversas, mentor/aprendiz nas mentorias). O Power BI só permite **uma relação ativa** entre duas tabelas.
   - Ficam ativas `de_id` e `aprendiz_id`.
   - Ficam inativas (tracejadas) `para_id` e `mentor_id`. As medidas `[Conversas Recebidas]` e `[Mentorias Dadas]` ligam a relação inativa com `USERELATIONSHIP`.
   - **Alternativa:** duplicar a dimensão (`dim_mentor`), o que se chama "dimensão com papel" (role-playing). Ela é mais simples de usar em segmentação, mas tem custo: mais uma tabela e o risco de alguém filtrar a errada.
3. **Calendário próprio (`dim_data`).** Ele cobre do primeiro ao último dia com dados, sem buracos.
   - Fica marcado como tabela de datas.
   - Desligue o "Data/hora automática" do Power BI: ele cria uma tabela escondida por coluna de data e pesa o arquivo.
4. **Toda conta é medida, nenhuma é coluna calculada.**
   - As colunas novas, como rótulos legíveis ("Achou outra coisa" em vez de "achou_outra_coisa"), nascem no **Power Query**: limpeza no Power Query, cálculo no DAX.
   - Os flags 0/1 (`acertou`, `errou`, `ajudou`, `fechada`, `com_erro`) já vêm prontos das views. Somar um 0/1 equivale a contar, e é o jeito mais rápido.
5. **As fatos são views, e não cópias.** No PostgreSQL, `bi.fato_*` são views sobre o schema `robo`. Elas mostram sempre o dado atual e não duplicam nada.
   - O organograma e o catálogo de competências vivem no código do robô. Por isso viram as tabelas carregadas `bi.dim_funcionario_base` e `bi.dim_competencia_base`.

### Relações (para criar no passo 5)

| De (lado 1) | Para (lado *) | Cardinalidade | Direção do filtro | Ativa? |
|---|---|---|---|---|
| dim_andar[andar] | dim_funcionario[andar] | 1 : * | Única | Sim |
| dim_funcionario[funcionario_id] | fato_treino[funcionario_id] | 1 : * | Única | Sim |
| dim_funcionario[funcionario_id] | fato_evolucao_nivel[funcionario_id] | 1 : * | Única | Sim |
| dim_funcionario[funcionario_id] | fato_nivel_atual[funcionario_id] | 1 : * | Única | Sim |
| dim_funcionario[funcionario_id] | fato_rh_movimentos[funcionario_id] | 1 : * | Única | Sim |
| dim_funcionario[funcionario_id] | fato_mentorias[aprendiz_id] | 1 : * | Única | Sim |
| dim_funcionario[funcionario_id] | fato_mentorias[mentor_id] | 1 : * | Única | **Não** |
| dim_funcionario[funcionario_id] | fato_interacoes[de_id] | 1 : * | Única | Sim |
| dim_funcionario[funcionario_id] | fato_interacoes[para_id] | 1 : * | Única | **Não** |
| dim_competencia[competencia_id] | fato_treino, fato_mentorias, fato_evolucao_nivel, fato_nivel_atual, fato_rh_movimentos [competencia_id] | 1 : * | Única | Sim |
| dim_nivel[nivel] | fato_treino[nivel], fato_mentorias[nivel], fato_nivel_atual[nivel] | 1 : * | Única | Sim |
| dim_data[data] | fato_treino, fato_interacoes, fato_mentorias, fato_rotinas, fato_evolucao_nivel, fato_rh_movimentos [data] | 1 : * | Única | Sim |

**Nenhuma relação é bidirecional e nenhuma é muitos-para-muitos.** Se o Power BI sugerir "Ambas", troque para "Única". A relação bidirecional cria caminhos ambíguos, deixa o modelo lento e produz números que ninguém consegue explicar.

---

## Passo a Passo

### Passo 0: preparar o Power BI Desktop (5 minutos, uma vez)

1. Instale o **Power BI Desktop** pela Microsoft Store (procure "Power BI Desktop"; é grátis).
2. Abra o programa e feche a tela de boas-vindas.
3. Clique em **Arquivo** → **Opções e configurações** → **Opções**.
4. Na lista da esquerda, em **ARQUIVO ATUAL**, clique em **Carregamento de Dados**.
5. **Desmarque** "Data/hora automática" e "Detectar automaticamente novas relações após o carregamento dos dados". Nós vamos criar as relações à mão, do jeito certo.
6. Ainda na lista da esquerda, em **ARQUIVO ATUAL**, clique em **Configurações regionais** → Localidade para importação: **Português (Brasil)**.
7. Clique em **OK**.
8. Ajuste o tamanho da tela:
   1. Clique numa área vazia da página.
   2. No painel **Visualizações**, clique no ícone de pincel (**Formatar sua página de relatório**).
   3. Abra **Configurações da tela** → Tipo: **Personalizado** → Largura **1920**, Altura **1080**.
   4. Os fundos têm exatamente esse tamanho. Com isso, 1 pixel do fundo vale 1 unidade do Power BI.

### Passo 1: escolher a origem dos dados

| Situação | Origem | Vantagem | Desvantagem |
|---|---|---|---|
| Quer o painel **ao vivo**, atualizando com a empresa na nuvem | **PostgreSQL (Neon)** | O dado é sempre o atual, sem copiar arquivo | Precisa da senha do `robo_leitura` e de internet |
| Quer **treinar** o Power BI ou está sem acesso ao banco | **Excel** (`dados/modelo_estrela.xlsx`) | Funciona offline, é imediato | É uma foto de 19/10 17:25 e não atualiza sozinha |

**Recomendação:** comece pelo Excel para aprender o caminho. Depois troque o parâmetro `Origem` para PostgreSQL; nenhuma outra consulta muda.

### Passo 2A: conectar no PostgreSQL (Neon)

1. Pegue o **Hostname** do Neon:
   1. No painel do Neon, abra o projeto e clique em **Connect**.
   2. Na Connection string, copie o trecho entre `@` e `/`, por exemplo `ep-xxxx.sa-east-1.aws.neon.tech`.
2. No Power BI: **Página Inicial** → **Obter dados** → **Mais...** → digite `PostgreSQL` → selecione **Banco de dados PostgreSQL** → **Conectar**.
3. Preencha **Servidor** com o hostname e **Banco de dados** com `Roboplanilhas`. Em **Modo de Conectividade de Dados**, escolha **Importar**.
   - **Por que Importar e não DirectQuery:** com Importar, os dados ficam comprimidos dentro do arquivo e o painel responde na hora.
   - Com DirectQuery, cada clique vai ao Neon. O plano grátis do Neon "dorme" quando ninguém usa, então cada clique esperaria ele acordar.
4. Clique em **OK**. Na janela de credenciais, escolha **Banco de dados** na esquerda.
5. Preencha **Nome de usuário** `robo_leitura` e a **senha**. A senha está com o dono do projeto e **nunca vai no arquivo**: o Power BI a guarda no cofre do Windows.
6. Clique em **Conectar**. Se aparecer um aviso de criptografia, a conexão **deve** ser criptografada (o Neon exige SSL). Não aceite "conectar sem criptografia".
7. O **Navegador** abre com a lista de schemas e tabelas. **Não clique em Carregar ainda.** Clique em **Transformar Dados**. Nós vamos montar as consultas pelo arquivo `power_query.m`, que é mais limpo.

> **Como validar:** no Navegador, expanda `bi` e clique em `fato_treino`. A prévia mostra colunas como `tentativa_id`, `data_hora` e `acertou`. Se `bi` não aparecer, o usuário não tem permissão: veja Erros Comuns.

### Passo 2B: alternativa pelo Excel

1. Copie a pasta `powerbi/dados/` para o seu computador.
2. Clique com **Shift + botão direito** em `modelo_estrela.xlsx` → **Copiar como caminho**.
3. No Power BI: **Página Inicial** → **Transformar dados**. O Editor do Power Query abre.
4. Siga o passo 3 e, no parâmetro `CaminhoExcel`, cole o caminho **sem as aspas**. No parâmetro `Origem`, escolha `Excel`.

### Passo 3: montar as consultas no Power Query

**O que é:** o Power Query é a "cozinha" do Power BI. É ali que você limpa, tipa e prepara os dados antes de eles entrarem no modelo. Cada clique vira uma etapa gravada, e a etapa roda de novo sozinha a cada atualização.

1. No Editor do Power Query, vá em **Página Inicial** → **Gerenciar Parâmetros** → **Novo Parâmetro** e crie os quatro parâmetros do bloco 1 do `power_query.m`:

   | Nome | Tipo | Valor |
   |---|---|---|
   | `Origem` | Texto | Valores sugeridos: **Lista de valores** → `PostgreSQL` e `Excel` |
   | `Servidor` | Texto | o hostname do Neon |
   | `Banco` | Texto | `Roboplanilhas` |
   | `CaminhoExcel` | Texto | o caminho do xlsx (pode ficar como está se você usar só o banco) |

   Clique em **OK**.
2. Para **cada** bloco `// ---------- CONSULTA: <nome>` do arquivo (comece por `fxTabelaBI`, depois as dimensões, depois as fatos, por último `_Medidas`):
   1. **Página Inicial** → **Nova Fonte** → **Consulta Nula**.
   2. **Exibição** → **Editor Avançado** → apague o texto que aparece → cole o bloco inteiro, de `let` até a última linha depois do `in` → **Concluído**.
   3. No painel **Consultas** (à esquerda), clique com o botão direito na consulta nova → **Renomear** → digite o nome exato (por exemplo `fato_treino`).
3. Clique com o botão direito em `fxTabelaBI` → **desmarque "Habilitar carga"**. Ela é só uma ajudante e não deve virar tabela no modelo.
4. **Confira cada consulta:** clique nela e olhe o painel **Etapas Aplicadas**, à direita. Clique em cada etapa e veja a prévia mudar. É assim que você aprende o que cada linha do M faz.
   - **Tipos**: o ícone no cabeçalho de cada coluna muda (`123` para inteiro, `ABC` para texto, calendário para data).
   - **SemEspacos / TextoLimpo**: tira espaços e quebras de linha invisíveis, que duplicariam categorias.
   - **ErroLegivel / TipoRotulo / SituacaoRotulo**: cria rótulos para pessoas lerem; o código cru continua disponível.
   - **SemDuplicados**: garante uma linha por chave nas dimensões. Sem isso, a relação 1:* não pode ser criada.
   - **SemColunasTecnicas**: remove colunas que nenhum visual usa. Menos colunas significa arquivo menor e atualização mais rápida.
5. Clique em **Página Inicial** → **Fechar e Aplicar**. As 13 tabelas carregam: 12 do modelo mais `_Medidas`.

> **Como validar:** no painel **Dados**, à direita, devem existir `dim_andar`, `dim_competencia`, `dim_data`, `dim_funcionario`, `dim_nivel`, as sete `fato_*` e `_Medidas`. Ao passar o mouse em `fato_treino`, o total é de 726 linhas no instantâneo de 19/10. Com a nuvem ativa, esse número cresce.

**Impacto na performance:**
- **Com PostgreSQL**, a navegação `Fonte{[Schema="bi",Item=...]}` permite **dobra de consulta** (query folding). As etapas viram SQL e rodam no Neon. Clique com o botão direito numa etapa: se "Exibir Consulta Nativa" estiver habilitado, a etapa foi dobrada.
- `Text.Clean` e as colunas condicionais quebram a dobra. Isso é aceitável aqui, porque as tabelas têm centenas de linhas e não milhões.

### Passo 4: preparar as tabelas (exibição de Modelo)

1. Na barra da esquerda, clique no 3º ícone, **Exibição de modelo**, que tem o desenho de caixinhas ligadas.
2. **Marcar a tabela de datas:**
   1. Clique na tabela `dim_data`.
   2. No menu superior, clique em **Ferramentas de tabela** → **Marcar como tabela de datas** → coluna `data` → **OK**.
   3. Aparece um "Validado com êxito".
3. **Ordenar textos pela ordem lógica.** Sem isso, "Coordenador" vem antes de "Estagiário" por ordem alfabética.
   - Em `dim_funcionario`, selecione a coluna `nivel_cargo` → **Ferramentas de coluna** → **Classificar por coluna** → `nivel_cargo_ordem`.
   - Faça o mesmo com `dim_andar[andar_rotulo]` e `dim_andar[andar_curto]` (por `andar`), `dim_nivel[nivel_nome]` e `dim_nivel[nivel_curto]` (por `nivel`), e `dim_data[mes_nome]` (por `mes`).
4. **Ocultar o que confunde quem monta visual.** Clique com o botão direito na coluna → **Ocultar na exibição de relatório**:
   - todas as colunas `*_id` das fatos: a pessoa deve usar o nome, que vem da dimensão;
   - `fato_treino[andar_na_tentativa]`;
   - os flags 0/1 (`acertou`, `errou`, `ajudou`, `fechada`, `com_erro`): eles são usados por medidas, não diretamente;
   - `_Medidas[Coluna1]`.
5. **Resumo padrão.** Selecione `nivel` (em todas as tabelas), `andar`, `hora` e `nivel_cargo_ordem` → **Propriedades** → **Resumir por: Nenhum**. Sem isso, o Power BI soma o nível ("nível 4.012") quando você arrasta a coluna para um visual.

### Passo 5: criar as relações

1. Ainda na Exibição de modelo, vá em **Página Inicial** → **Gerenciar relações** → **Novo...**
2. Para cada linha da tabela de relações (Explicação Técnica):
   1. Escolha a tabela do lado 1 (a dimensão) e clique na coluna-chave.
   2. Escolha a tabela do lado * (a fato) e clique na coluna correspondente.
   3. Confira **Cardinalidade: Um para muitos (1:*)** e **Direção do filtro cruzado: Única**.
   4. Para `mentor_id` e `para_id`, **desmarque** "Tornar esta relação ativa".
   5. Clique em **OK**.
3. Arraste as caixas no diagrama para ficar como a estrela do desenho: dimensões em cima e nas laterais, fatos no centro. O Power BI não exige isso, mas quem herdar o arquivo agradece.

> **Como validar:**
> - No diagrama, as relações inativas aparecem **tracejadas**.
> - Cada linha tem "1" na ponta da dimensão e "*" na ponta da fato.
> - Nenhuma seta é dupla.

### Passo 6: criar as medidas

1. Garanta que a tabela `_Medidas` existe (ela veio do Power Query).
2. **Jeito rápido:**
   1. Na barra da esquerda, clique em **Exibição de consulta DAX** (o ícone com o símbolo "DAX").
   2. Cole o arquivo `medidas.dax` inteiro e clique em **Executar**.
   3. Embaixo aparece uma linha com as âncoras: Tentativas 726, Taxa de Acerto 0,986 e assim por diante. Confira com a seção 9.
   4. Clique em **Atualizar modelo com alterações** para gravar as medidas.
3. **Jeito manual** (se a sua versão não tiver a exibição de consulta DAX):
   1. Selecione `_Medidas` no painel **Dados** → **Ferramentas de tabela** → **Nova medida**.
   2. Cole cada medida começando pelo nome (`Tentativas = COUNTROWS ( fato_treino )`) e pressione **Enter**.
4. **Formatos** (a consulta DAX não grava formato):
   1. Clique na medida → **Ferramentas de medida** → **Formato**.
   2. Siga o comentário `formato:` de cada uma. Taxas usam **Porcentagem**, 1 casa decimal. Contagens usam **Número inteiro** com separador de milhar.
5. Depois de existir ao menos uma medida, oculte `Coluna1`. A `_Medidas` sobe para o topo da lista com ícone de calculadora.

**Medidas que todo mundo deve entender primeiro** (as demais seguem o mesmo raciocínio e estão comentadas no arquivo):

- **`[Taxa de Acerto] = DIVIDE ( [Acertos], [Tentativas] )`**
  - **Contexto de filtro:** numa barra do "1º andar", os filtros vão de `dim_andar` para `dim_funcionario` e de lá para `fato_treino`. Sobram só as tentativas do 1º andar, e a medida divide acertos por tentativas **daquele recorte**.
  - **Total:** o total recalcula sobre todas as tentativas. Ele **não** é a média das taxas dos andares, e esse é o comportamento correto.
- **`[% do Erro por Tipo]`:** `ALL ( fato_treino[tipo_erro] )` remove **só** o filtro do tipo de erro no denominador. Por isso as fatias somam 100% dentro do andar ou período que o usuário escolheu.
- **`[Mentorias Dadas]`:** `USERELATIONSHIP` acende a relação tracejada `mentor_id` só durante o cálculo. Fora dele, quem manda é a relação ativa (`aprendiz_id`).
- **`[Ranking por Nível]`:**
  - **Contexto de linha:** o `RANKX` percorre cada funcionário de `ALLSELECTED ( dim_funcionario )`. A **transição de contexto** transforma a linha em filtro e calcula o nível médio dela.
  - Somar `tentativas / 1.000.000` desempata sem mudar a ordem principal.
- **`[Δ Acerto (p.p.)]`:** diferença de taxas se mede em **pontos percentuais**. Cair de 99,2% para 98,2% é −1,0 p.p., e não "−1%".

### Passo 7: aplicar o tema e os fundos

1. **Tema:** **Exibição** → no grupo Temas, clique na setinha ▾ → **Procurar temas** → escolha `tema_robo.json`.
   - O tema deixa todos os visuais **transparentes e sem título**, porque os títulos e cartões já estão desenhados no fundo.
   - Ele também aplica a paleta validada para daltonismo e para o fundo escuro.
2. **Fundo de cada página:**
   1. Clique numa área vazia da página.
   2. No painel **Visualizações**, clique no pincel (**Formatar página**).
   3. Abra **Tela de fundo** (atenção: **não** é "Papel de parede", que é só a moldura cinza de fora).
   4. Em **Imagem**, clique em **Procurar** e escolha `telas/01_visao_executiva_fundo.png`.
   5. Ajuste da imagem: **Normal**. "Ajustar" e "Preencher" distorcem a imagem.
   6. **Transparência: 0%**.
3. Repita em cada página com o fundo dela. Renomeie as abas (botão direito na aba → **Renomear página**) para: `Visão Executiva`, `Treino & Evolução`, `Pessoas & Andares`, `Conversas & Mentorias`, `Operação & Rotinas`.
4. Abra a maquete com números (`telas/01_visao_executiva.png`) ao lado, numa segunda tela ou no celular. Ela é o "gabarito" de onde vai cada visual.

> **Por que fundo desenhado e não formas do Power BI:**
> - Cada forma do Power BI é um visual a mais para renderizar.
> - Um PNG de cerca de 80 KB substitui 20 ou 30 formas.
> - A moldura fica milimetricamente alinhada (grade de 8 px, margens de 24, espaços de 16, cantos arredondados de 14).

### Passo 8: montar cada aba

**Posições:** o tamanho e a posição de cada visual ficam em **Formatar visual** → **Geral** → **Propriedades** → **Tamanho** e **Posição**. Use os números abaixo. Na tela de 1920x1080, eles coincidem com os cartões do fundo.

**Regra geral para todos os visuais:**
- título **desligado** (o título está no fundo);
- fundo **desligado**;
- rótulos de dados **ligados** só onde a maquete mostra número.

#### Elementos comuns a todas as abas

| Elemento | Visual | Campo | Posição (X, Y, Largura, Altura) |
|---|---|---|---|
| Navegação | 5 **botões em branco** (Inserir → Botões → **Em branco**), um sobre cada item do menu desenhado no fundo; em cada um: Formatar → **Ação** ligada → Tipo **Navegação de página** → Destino = a aba. Sem texto e sem preenchimento: o fundo já desenha o menu e o item ativo. | — | 16, 88 / 136 / 184 / 232 / 280 (Y de cada um), 200 × 44 |
| Filtro Período | **Segmentação de dados** (estilo "Entre") | `dim_data[data]` | 16, 388, 200, 44 |
| Filtro Andar | Segmentação (Lista suspensa) | `dim_andar[andar_rotulo]` | 16, 460, 200, 44 |
| Filtro Competência | Segmentação (Lista suspensa) | `dim_competencia[competencia]` | 16, 532, 200, 44 |
| Filtro Nível | Segmentação (Lista suspensa) | `dim_nivel[nivel_nome]` | 16, 604, 200, 44 |
| "Atualizado em" | **Cartão** (novo), texto 10 pt cor #A1A1AA, alinhado à esquerda | `[Atualizado em]` (a pílula do fundo já traz a bolinha verde; o texto vem da medida) | 1700, 40, 190, 26 |

**Sincronizar os filtros entre as abas:**
1. **Exibição** → **Sincronizar segmentações**.
2. Selecione cada segmentação e marque todas as páginas nas colunas "Sincronizar" e "Visível".
3. Assim, escolher "3º andar" na aba 1 vale também na aba 3.

#### Aba 1: Visão Executiva (gabarito: `telas/01_visao_executiva.png`)

**Fluxo de leitura em Z:**
1. KPIs, à esquerda e em cima: o "como estamos".
2. Tendência e comparação por andar: o "onde".
3. Diagnóstico por nível e por erro: o "por quê".
4. Destaques de pessoas: o "quem".
5. Frases de insight: o "e daí".

| # | Visual | Campos | Por que este visual | Posição |
|---|---|---|---|---|
| 1 | Cartão (novo) | Valor `[Tentativas]`; rótulo de referência `[Rótulo Δ Tentativas]` com cor fx `[Cor Δ Tentativas]` | O número mais importante tem de ser o maior elemento da tela | 330, 116, 230, 84 |
| 2 | Cartão (novo) | `[Taxa de Acerto]` + `[Rótulo Δ Acerto]` / `[Cor Δ Acerto]` | idem | 661, 116, 230, 84 |
| 3 | Cartão (novo) | `[Pessoas que Treinaram]` + `[% do Quadro que Treinou]` | Cobertura: todo mundo está treinando? | 992, 116, 230, 84 |
| 4 | Cartão (novo) | `[Nível Médio]` + `[Rótulo Evolução]` | Evolução em um número | 1323, 116, 230, 84 |
| 5 | Cartão (novo) | `[Conversas]` + `[Mentorias]` | A empresa conversa? | 1654, 116, 230, 84 |
| 6 | **Gráfico de linhas** | Eixo X `fato_treino[data_hora]` com hierarquia desligada, agrupado por hora (clique com o botão direito no campo → "Nova hierarquia" ou use `data` + `hora`); Y `[Tentativas]` | Ritmo ao longo do tempo pede linha, porque a linha mostra continuidade. Nunca use pizza para tempo. | 270, 300, 990, 350 |
| 7 | **Barras horizontais** | Eixo Y `dim_andar[andar_rotulo]`; X `[Taxa de Acerto]`; cor fx `[Cor Acerto vs Meta]`; linha constante X = 0,95 (painel **Análise** → Linha constante) | Barras horizontais comparam categorias de nome longo sem cortar o texto | 1303, 300, 580, 350 |
| 8 | **Colunas** | X `dim_nivel[nivel_curto]`; Y `[Taxa de Acerto]`; cor fx `[Cor Acerto vs Meta]` | São poucas categorias e têm ordem natural (1 a 5), por isso colunas. A cor denuncia o nível 4. | 270, 742, 470, 196 |
| 9 | **Barras horizontais** | Y `fato_treino[tipo_erro_rotulo]`; X `[Erros]`; filtro do visual: `tipo_erro_rotulo` não é "(sem erro)" | Ranking de causas, do maior para o menor | 786, 742, 470, 196 |
| 10 | **Tabela** | `dim_funcionario[nome]`, `dim_funcionario[cargo]`, `[Nível Médio]`, `[Taxa de Acerto]`; filtro **N superior** 5 por `[Nível Médio]` | Nomes pedem tabela, porque um gráfico com 88 nomes é ilegível | 1303, 742, 580, 196 |
| 11 | 3 Cartões (novo) | `[Insight Acerto]` e textos | O "e daí" para quem só lê a frase | 256, 968, 1640, 44 |

#### Aba 2: Treino & Evolução (gabarito: `telas/02_treino_evolucao.png`)

| Visual | Campos | Por que |
|---|---|---|
| 4 Cartões | `[Taxa de Acerto]`, `[Subidas de Nível]`, `[Nível Médio]`, `[Tempo Médio por Tentativa (s)]` | Os 4 sinais de aprendizagem |
| Barras horizontais (cartão grande à esquerda) | Y `dim_competencia[competencia]`; X `[Taxa de Acerto]`; rótulo de dados ligado; dica de ferramenta `[Tentativas]`; linha constante 0,95 | 15 competências com nomes longos, por isso barras horizontais. Ordene por `[Taxa de Acerto]` crescente para os problemas ficarem visíveis: "Achar os perfis" tem 50% com 2 tentativas e "Achar o conhecimento certo" tem 94,2% com 156. |
| Colunas | X `dim_nivel[nivel_curto]`; Y `[Tentativas]` | Mostra onde a empresa está na escada de dificuldade |
| Linhas | X hora; Y `[Taxa de Acerto]`; linha constante 0,95 | Mostra se o acerto se mantém ao longo do dia. O eixo Y começa em 80%, **e isso precisa estar escrito** no subtítulo do fundo, para não exagerar a variação. |

> **Atenção, n baixo:** "Achar os perfis" tem 50% de acerto com **2 tentativas**. Não é conclusão, é sinal. Coloque `[Tentativas]` na dica de ferramenta para quem passar o mouse ver o tamanho da base.

#### Aba 3: Pessoas & Andares (gabarito: `telas/03_pessoas_andares.png`)

| Visual | Campos | Por que |
|---|---|---|
| 4 Cartões | `[Funcionários no Quadro]`, `[Pessoas que Treinaram]` + `[% do Quadro que Treinou]`, `[Nível Médio]`, `[Subidas de Nível]` | Quadro × engajamento |
| Tabela "Andares" | `dim_andar[andar_curto]`, `dim_andar[andar_nome]`, `[Funcionários no Quadro]`, `[Pessoas que Treinaram]`, `[Tentativas]`, `[Taxa de Acerto]`, `[Nível Médio]`; filtro do visual: `dim_andar[andar]` ≠ 0 | 5 linhas × 7 números: a tabela é mais precisa que qualquer gráfico |
| Colunas "Nível médio por andar" | X `dim_andar[andar_curto]`; Y `[Nível Médio]`; cor por andar (Colunas → Cor → cada barra com a cor da paleta, na mesma ordem) | **A cor segue o andar em todo o painel:** 1º violeta, 2º verde-azulado, 3º âmbar, 4º rosa, 5º azul |
| Tabela "Ranking" | `[Ranking por Nível]`, `dim_funcionario[nome]`, `[cargo]`, `dim_andar[andar_curto]`, `[Nível Médio]`, `[Tentativas]`, `[Taxa de Acerto]`; classificar por `[Ranking por Nível]` crescente; N superior 9 | Quem lidera, com desempate transparente |
| Barras horizontais "Quadro por nível de cargo" | Y `dim_funcionario[nivel_cargo]` (já ordenado por `nivel_cargo_ordem`); X `[Funcionários no Quadro]` | Estrutura da pirâmide da empresa |

#### Aba 4: Conversas & Mentorias (gabarito: `telas/04_conversas_mentorias.png`)

| Visual | Campos | Por que |
|---|---|---|
| 4 Cartões | `[Conversas]`, `[Mentorias]` (rótulo: fechadas e abertas), `[% Mentorias que Ajudaram]` com rótulo `[Aviso Mentorias]` e cor fx `[Cor Aviso Mentorias]`, `[Mentores Diferentes]` | O cartão de efetividade **avisa sozinho** quando a amostra é pequena (hoje: 2 fechadas) |
| Barras horizontais | Y `fato_interacoes[tipo_rotulo]`; X `[Conversas]` | Que tipo de conversa domina |
| Barras horizontais | Y `fato_mentorias[situacao_rotulo]`; X `[Mentorias]`; cores: aberta em âmbar, não ajudou em vermelho, ajudou em verde | Estado das mentorias. É **status**, por isso as cores reservadas de status. |
| Barras horizontais "Quem mais ensinou" | Y `dim_funcionario[nome]`; X `[Mentorias Dadas]`; N superior 5 | Usa a relação **inativa** `mentor_id` via `USERELATIONSHIP`. Com `[Mentorias]` no lugar, o gráfico mostraria aprendizes, não mentores. |
| Tabela "Conversas mais recentes" | `fato_interacoes[data_hora]`, `dim_funcionario[nome]` (quem enviou), `fato_interacoes[tipo_rotulo]`, `fato_interacoes[texto]`; classificar por data_hora decrescente; **Formatar → Valores → Quebra automática de texto: ligado** | Texto livre só cabe em tabela. O "para quem" precisa de `dim_funcionario` duplicada ou de `LOOKUPVALUE`; veja Próximos Passos. |

#### Aba 5: Operação & Rotinas (gabarito: `telas/05_operacao_rotinas.png`)

| Visual | Campos | Por que |
|---|---|---|
| 4 Cartões | `[Execuções]`, `[Taxa de Sucesso das Rotinas]` (cor fx `[Cor Sucesso Rotinas]`, meta 99%), `[Execuções com Erro]`, `[Rotinas Diferentes]` | Saúde em 4 números |
| Barras horizontais | Y `fato_rotinas[rotina]`; X `[Execuções]` | Volume por rotina |
| Tabela "Saúde de cada rotina" | `rotina`, `[Execuções]`, `[Execuções com Erro]`, `[Tempo Médio da Rotina (s)]`, `[Taxa de Sucesso das Rotinas]`; **formatação condicional** (botão direito no campo → Formatação condicional → Cor da fonte → Valor do campo → `[Cor Sucesso Rotinas]`) | O olho vai direto ao `memoria_pg`, com 87,5% |

#### Por que não há aba de RH

`fato_rh_movimentos` está **vazia**: nenhuma promoção formal foi registrada. Um gráfico vazio passa a ideia de que o relatório está quebrado.

A tabela, as relações e a medida `[Movimentos de RH]` já estão prontas. Quando entrar o primeiro movimento, crie a aba 6 com:
- um Cartão de `[Movimentos de RH]`;
- Barras por `fato_rh_movimentos[tipo]`;
- uma Tabela com nome, de nível, para nível, proposto por e validado por.

### Passo 9: interações, dicas e acabamento

1. **Editar interações:** selecione o gráfico de andares → **Formatar** → **Editar interações**. Nos cartões KPI, escolha **Filtrar**, não "Realçar": realçar num cartão não faz sentido.
2. **Dica de ferramenta:** em todo gráfico de taxa, arraste `[Tentativas]` para **Dicas de ferramenta**. Quem lê vê o tamanho da base sem poluir o gráfico.
3. **Rótulos com contagem por extenso.** Escreva "726 tentativas" e nunca "n=726".
4. **Teste no modo leitura:** **Exibição** → **Modo de leitura**. Clique em cada filtro, em cada barra e em cada botão de navegação.

### Passo 10: publicar

1. **Página Inicial** → **Publicar** → entre com a conta do trabalho → escolha o workspace → **Selecionar**.
2. No serviço (app.powerbi.com), abra o workspace → modelo semântico **Robô de Planilhas** → **...** → **Configurações** → **Credenciais da fonte de dados** → **Editar credenciais**. Escolha Básico, usuário `robo_leitura`, a senha e nível de privacidade **Organizacional**.
3. **Atualização agendada:** na mesma tela, ligue a atualização e escolha os horários. Os turnos da nuvem rodam a cada 2 h, então 4 a 8 atualizações por dia é o suficiente.
4. O Neon é um serviço na internet, então **não precisa de gateway**. Se o serviço pedir gateway, confira se o servidor foi digitado com o hostname completo.

---

## 9. Validação: os números que o seu painel TEM de mostrar

Os valores são do instantâneo de **19/10/2026 17:25** (Excel, ou Neon naquele momento). **Com a nuvem rodando, o PostgreSQL cresce a cada turno.** Para conferir com o banco ao vivo, rode `python powerbi/exportar_estrela.py` com a memória mais nova e compare com o Excel novo.

### Contagens das tabelas (reconciliadas: Neon = CSV = Excel)

| Tabela | Linhas | Tabela | Linhas |
|---|---|---|---|
| dim_funcionario | 88 | fato_treino | 726 |
| dim_competencia | 15 | fato_interacoes | 30 |
| dim_andar | 6 | fato_mentorias | 10 |
| dim_nivel | 5 | fato_rh_movimentos | 0 |
| dim_data | 2 | fato_rotinas | 160 |
| | | fato_evolucao_nivel | 399 |
| | | fato_nivel_atual | 392 |

### Âncoras por medida

| Medida | Valor esperado |
|---|---|
| Tentativas | 726 |
| Taxa de Acerto | 98,6% (716 acertos, 10 erros) |
| Pessoas que Treinaram | 88 |
| Funcionários no Quadro | 87 |
| Nível Médio | 2,40 |
| Subidas / Quedas de Nível | 7 / 0 |
| Tentativas últimas 8 h × anteriores | 435 × 249 → Δ +74,7% |
| Acerto últimas 8 h × anteriores | 98,2% × 99,2% → Δ −1,0 p.p. |
| Tempo Médio por Tentativa | 0,11 s |
| Erros por tipo | achou outra coisa 7 · não encontrou 2 · grupos errados 1 |
| Conversas | 30 (pedido de ajuda 11 · mentoria 10 · troca 6 · retorno 2 · resposta 1) |
| Mentorias | 10 (8 abertas · 2 não ajudaram · 0 ajudaram) |
| Execuções / com erro | 160 / 2 (ambos em `memoria_pg`, que fica com 87,5% de sucesso) → 98,8% |

### Acerto por nível

| Nível | Tentativas | Acerto |
|---|---|---|
| 1 | 119 | 100% |
| 2 | 262 | 100% |
| 3 | 278 | 100% |
| 4 | 66 | 84,8% |
| 5 | 1 | 100% |

### Por andar atual da pessoa

| Andar | Tentativas | Acerto | Pessoas | Nível médio |
|---|---|---|---|---|
| 1º Engenharia de Dados | 160 | 98,8% | 18 | 2,17 |
| 2º Analytics e Ciência de Dados | 139 | 98,6% | 16 | 2,24 |
| 3º Sala Excel e BI | 89 | 97,8% | 10 | 2,61 |
| 4º Operações | 165 | 98,8% | 22 | 2,54 |
| 5º TI | 165 | 98,8% | 21 | 2,62 |
| Fora do quadro atual | 8 | 100% | 1 | — |

### Topo do ranking

| Posição | Pessoa | Cargo | Nível |
|---|---|---|---|
| 1 | Otávio | Head da Sala de Casos | 5,0 |
| 2 em diante | André, Eduardo, Felipe, Henrique, Juliana… | | 4,0 (desempate por tentativas) |

### Checklist antes de mostrar a alguém

- [ ] A contagem de cada tabela bate com as contagens acima.
- [ ] Os cartões batem com as âncoras por medida.
- [ ] Cada filtro foi testado sozinho e combinado (por exemplo: 4º andar + Nível 4 deve dar menos de 66 tentativas, só as do 4º andar).
- [ ] O total das tabelas é o recálculo, não a soma das linhas.
- [ ] As taxas aparecem com 1 casa decimal e os níveis com 2.
- [ ] Os recortes com base pequena estão sinalizados: mentorias (2 fechadas), "Achar os perfis" (2 tentativas), nível 5 (1 tentativa).
- [ ] O modo de leitura foi conferido como o gestor vai ver.

---

## Boas Práticas

- **Uma pergunta por página** e no máximo 8 a 12 visuais. Cada visual é uma consulta ao motor, e mais visuais deixam a página mais lenta e mais confusa.
- **O número mais importante é o maior elemento da tela**, sempre em cima e à esquerda (leitura em Z).
- **Cor tem função.**
  - **Identidade:** as 5 cores dos andares, sempre a mesma cor para o mesmo andar.
  - **Status:** verde, âmbar e vermelho, e **só** para status, nunca como "a 4ª série".
  - A paleta foi validada para daltonismo e contraste no fundo escuro #27272A.
- **Nunca use eixo duplo.** Duas medidas de escala diferente vão em dois gráficos.
- **O eixo de taxa que não começa em zero precisa dizer isso** (aba 2, acerto por hora, eixo a partir de 80%).
- **Limpeza no Power Query, cálculo no DAX, regra de negócio no banco** (as views `bi`). Quem mudar a regra muda num lugar só.
- **Documente as medidas:** em **Propriedades** → **Descrição** de cada medida, cole a 1ª linha do comentário do `medidas.dax`. A descrição aparece quando alguém passa o mouse na medida.
- **Segurança:** o `.pbix` publicado não contém senha. **Não** compartilhe o `.pbix` com "Exportar dados" liberado para quem não deveria ver nomes de funcionários.

## Erros Comuns

| Sintoma | Causa quase certa | Correção |
|---|---|---|
| O mesmo número em todas as barras | Falta a relação, ou ela está inativa | Passo 5: confira a linha cheia (ativa) entre a dimensão do eixo e a fato da medida |
| "Quem mais ensinou" mostra os aprendizes | Usou `[Mentorias]` em vez de `[Mentorias Dadas]` | Troque a medida |
| Nível 4.012 em vez de 2,40 | A coluna `nivel` foi arrastada com "Soma" | Use a medida `[Nível Médio]` ou defina Resumir por: Nenhum |
| Ordem Coordenador, Diretor, Especialista… | Ordenação alfabética | Classificar por coluna → `nivel_cargo_ordem` |
| Linha "(Em branco)" no gráfico de andar | `dim_andar` sem a linha 0 (SQL antigo) | Rode de novo `estrela_neon.sql` (já corrigido) ou filtre `andar ≠ 0` |
| "Não é possível comparar Integer com Text" | A chave foi tipada diferente nas duas tabelas | Confira as etapas "Tipos" do `power_query.m` |
| `bi` não aparece no Navegador | `robo_leitura` sem permissão no schema | O dono roda de novo `estrela_neon.sql`; ele termina com `GRANT ... TO robo_leitura` |
| Erro "Endpoint ID is not specified" | Driver antigo sem SNI, que o Neon usa para achar o banco | Atualize o Power BI Desktop. Em último caso, use como senha `endpoint=<id-do-endpoint>;<senha>`, onde o id é o `ep-xxxx` do hostname. |
| A atualização demora 5 a 10 s na primeira vez | O Neon grátis "dorme" e acorda na 1ª consulta | Normal. Não use DirectQuery por causa disso. |
| A medida dá erro de sintaxe com "," | Editor configurado para ";" | Troque `,` por `;` nos argumentos |
| O fundo fica borrado ou deslocado | Ajuste "Ajustar" ou "Preencher", ou página diferente de 1920x1080 | Ajuste **Normal** e página 1920x1080 (Passo 0, item 8) |
| Visual com fundo branco sobre o fundo escuro | O tema não foi aplicado, ou o visual foi criado antes do tema | Formatar → Geral → Efeitos → Plano de fundo: desligado; ou use o Pincel de formatação |

## Próximos Passos

1. **Quando houver semanas de histórico,** troque a comparação "8 h × 8 h" por semana contra semana anterior:
   ```
   CALCULATE ( [Taxa de Acerto], DATEADD ( dim_data[data], -7, DAY ) )
   ```
   Isso só funciona porque `dim_data` está marcada como tabela de datas.
2. **"Para quem" nas conversas:** crie `dim_destinatario` como referência de `dim_funcionario` (Power Query → botão direito → **Referência**) e ligue-a a `fato_interacoes[para_id]` como relação ativa. Isso é uma dimensão com papel, que é mais simples de usar em segmentação do que o `USERELATIONSHIP`.
3. **Aba de RH,** assim que `fato_rh_movimentos` tiver linhas (veja "Por que não há aba de RH").
4. **Segurança por linha (RLS),** se o painel for aberto para os heads. Em **Modelagem** → **Gerenciar funções**, crie uma função por andar com o filtro `dim_andar[andar] = 1`. Cada head vê só o próprio andar.
5. **Modelo (.pbit):** depois de montar, salve em **Arquivo** → **Exportar** → **Modelo do Power BI**. O `.pbit` guarda o modelo, as medidas e o layout sem os dados, e é o arquivo certo para versionar e compartilhar.

### Atualizar tudo depois

```bash
# 1) Tabelas em arquivo (CSV + Excel) + SQL do modelo, a partir da memória mais nova da empresa
python powerbi/exportar_estrela.py logs/trabalho.db

# 2) Maquetes e fundos (leem os CSV recém-gerados; precisam do Playwright + Chromium)
python powerbi/gerar_telas.py

# 3) Só se o organograma ou o catálogo mudou no código: aplicar o SQL no banco
#    Neon → SQL Editor → cole powerbi/estrela_neon.sql → Run. Pode rodar de novo quantas vezes quiser:
#    o script recria as views e as tabelas *_base, e não toca no schema robo.
```

No Power BI: **Página Inicial** → **Atualizar**. Se a origem for Excel, primeiro substitua o `modelo_estrela.xlsx` pelo novo, no mesmo caminho.
