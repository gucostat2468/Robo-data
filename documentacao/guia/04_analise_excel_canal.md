# Parte 4 — Análise (2º andar), Sala Excel (3º andar), canal da equipe, calculadora e central de dados

Esta parte cobre o que acontece **depois** que uma planilha foi aprovada e publicada pelo 1º andar (engenharia de dados):

| Arquivo | Em uma frase |
|---|---|
| `robo/analise.py` | Os 5 analistas que calculam NPS/CSAT/CES com margem de erro, testam diferenças entre segmentos e comparam cargas. |
| `robo/excel.py` | A Sala Excel, que monta um `.xlsx` só com fórmulas vivas e uma aba que confere cada fórmula contra o Python. |
| `robo/canal.py` | O "chat" da equipe: entende suas mensagens sem internet, posta acontecimentos, sprints, boletins e ideias. |
| `robo/calculos.py` | A calculadora do canal: transforma "nps por região onde canal = App" em um cálculo real sobre as bases publicadas. |
| `robo/central.py` | A central de dados do painel: números do dia/período por área, lidos do histórico do robô. |
| `conhecimento/*.md` | Manuais em texto que o canal consegue ler e citar. |

Alguns termos que aparecem o tempo todo (explicados uma vez aqui):

- **DataFrame (`df`)**: uma tabela na memória do Python (biblioteca *pandas*), com linhas e colunas, como uma aba de Excel.
- **Série (`pd.Series`)**: uma única coluna de um DataFrame.
- **Função (`def`)**: um bloco de código com nome que recebe entradas e devolve um resultado — como uma fórmula do Excel que você mesmo escreveu.
- **Classe (`class`)**: um "molde" que junta dados e funções que trabalham juntos. Cada objeto criado a partir dela (por exemplo, uma `Analise`) guarda os próprios dados em `self`.
- **Dicionário (`{}`)**: lista de pares "chave → valor", como um PROCX de duas colunas.
- **Lista (`[]`)**: sequência ordenada de itens.
- **`import`**: traz para o arquivo ferramentas escritas em outro arquivo ou biblioteca.
- **Exceção**: um erro que interrompe o código; `try/except` é o "SEERRO" do Python — tenta, e se der erro faz outra coisa.

---

## robo/analise.py

- **Para que serve**: é o 2º andar. Depois que uma base é aprovada, cinco "analistas" (Bia, Caio, Davi, Eva e Fábio) fazem um raio-X das colunas, calculam NPS/CSAT/CES com margem de erro, dizem quais diferenças entre segmentos são reais (e não acaso), comparam a carga atual com as anteriores da mesma base e escrevem um resumo executivo. O princípio é "certo antes de sofisticado": estatística clássica e explicável, base pequena nunca vira conclusão.
- **Onde entra no fluxo**: é chamado por `robo/pipeline.py` (linhas 379–381) logo depois da publicação, pela função `analisar`. Tudo aqui está dentro de `try`: a análise **nunca** reprova nem atrasa a publicação. Gera `Bases-Relatorios/<base>_analise.xlsx`, `logs/analises/<id>.json` (lido pelo painel) e, com PostgreSQL ligado, tabelas no schema `analise`. Funções daqui (`converter_escalas`, `detectar_indicadores`, `papel_coluna`, `chave_base`) também são reaproveitadas por `excel.py` e `calculos.py`.

### Cabeçalho (docstring) (linhas 1–19)

- Linhas 1–9: o texto entre `"""` é uma **docstring** — um comentário longo que documenta o arquivo. Lista os cinco analistas e o papel de cada um.
- Linhas 11–15: os princípios: regras clássicas, base pequena não vira destaque, correção de Holm contra falsos positivos, e "a análise nunca reprova".
- Linhas 17–18: onde ficam as saídas.

### Imports (linhas 21–34)

- Linha 21: `from __future__ import annotations` permite escrever tipos como `dict | None` em versões mais antigas do Python. Não muda o comportamento.
- Linhas 23–29: bibliotecas padrão do Python: `fnmatch` (compara nomes com curingas tipo `id_*`), `json` (ler/gravar arquivos JSON — texto estruturado em chaves e valores), `logging` (registrar mensagens no log), `math` (raiz quadrada, `erfc`), `re` (expressões regulares — padrões de busca em texto, como um "localizar" turbinado), `datetime` (data e hora) e `Path` (caminhos de arquivos).
- Linhas 31–32: `numpy` (cálculo numérico) e `pandas` (tabelas).
- Linha 34: duas funções do próprio robô: `normalizar_nome_coluna` (transforma "Região do Cliente" em `regiao_do_cliente`) e `sem_acento`.
- Linha 36: `log` é o "diário" onde o robô escreve avisos e erros.

### ANALISTAS (linhas 38–54)

Lista com cinco dicionários, um por analista: `id`, `nome`, `papel`, `cor` (usada no painel) e `descricao`. Não calcula nada; é usada pelo painel e pelo canal para mostrar quem é quem.

### PADRAO_ANALISE (linhas 56–64)

Configurações padrão (podem ser trocadas no `config.yaml`):

- Linha 57: `habilitado` — análise ligada.
- Linha 58: `base_minima: 30` — grupos com menos de 30 respostas não viram destaque.
- Linha 59: `confianca: 0.95` — 95% de confiança.
- Linha 60: `max_categorias: 30` — coluna com mais de 30 valores diferentes não é tratada como segmento.
- Linha 61: `max_segmentos: 10` — no máximo 10 colunas de segmento.
- Linha 62: `variacao_alerta_pct: 30` — variação de 30% (volume ou média) gera alerta no monitoramento.
- Linha 63: `analistas_desligados` — lista de analistas que você quer pular.

### MESES (linhas 66–67)

Conjunto de nomes de meses (completos e abreviados, sem acento). Serve para `chave_base` descobrir que `nps_setembro.xlsx` e `nps_outubro.xlsx` são a mesma base.

### _z_critico (linhas 71–72)

- Linha 72: devolve o **valor crítico z** da confiança pedida: 90% → 1,645; 95% → 1,96; 99% → 2,576. Qualquer outro valor cai em 1,96. O valor z é "quantos desvios-padrão" você precisa andar para cobrir aquela confiança na curva normal (a curva em forma de sino).

### _p_valor (linhas 75–76)

- Linha 76: transforma um z em **p-valor bicaudal** (a chance de ver uma diferença desse tamanho, para cima ou para baixo, se na verdade não houvesse diferença nenhuma). Usa `erfc(|z|/√2)`, que é a fórmula exata da curva normal. Se o z não for um número válido, devolve 1 (= "nenhuma evidência").
- Exemplo: z = 1,96 → p ≈ 0,05; z = 3,11 → p ≈ 0,0019.

### holm (linhas 79–89)

A **correção de Holm-Bonferroni** evita "achar" diferenças por sorte quando se fazem muitas comparações. Se você testa 20 segmentos a 95%, em média 1 aparece "significativo" por puro acaso.

- Linha 81: ordena as comparações do menor p-valor para o maior (guarda as posições originais).
- Linhas 82–83: `m` = número de comparações; começa marcando todas como "não significativas".
- Linhas 84–88: percorre em ordem. A comparação na posição `k` (começando em 0) só é significativa se `p ≤ alfa / (m − k)`. Na primeira que falhar, para (`break`) — todas as seguintes ficam não significativas.
- Linha 89: devolve a lista de verdadeiro/falso na ordem original.

**Exemplo** (alfa = 0,05; 4 comparações com p = 0,004; 0,018; 0,02; 0,03):

| ordem | p | limite = 0,05 / (4 − k) | resultado |
|---|---|---|---|
| 1º (k=0) | 0,004 | 0,05/4 = 0,0125 | significativo |
| 2º (k=1) | 0,018 | 0,05/3 ≈ 0,0167 | **falha → para** |
| 3º | 0,02 | — | não significativo |
| 4º | 0,03 | — | não significativo |

Sem a correção, as quatro seriam "significativas" (todas < 0,05). Com Holm, só uma é.

### _r (linhas 92–93)

- Linha 93: arredonda um número para `casas` decimais; se for vazio, infinito ou "NaN" (*Not a Number*, o "vazio numérico" do Python), devolve `None` (vazio). Evita que um `NaN` apareça no relatório como número.

### papel_coluna (linhas 97–122)

Decide o **papel** de cada coluna: auditoria, vazia, id, data, categoria, número, texto livre ou texto. Esse papel define o que cada analista faz com ela.

- Linhas 98–99: coluna que começa com `_` (ex.: `_arquivo_origem`, criada pelo robô) é "auditoria".
- Linhas 100–102: tira os vazios; se não sobrou nada, "vazia".
- Linhas 103–104: se o nome casa com algum padrão de identificador do `config.yaml` (ex.: `id_*`), é "id".
- Linhas 105–108: tipo data → "data"; verdadeiro/falso → "categoria".
- Linhas 109–114: conta valores distintos. Se é numérica: se todos são inteiros, todos diferentes entre si e há mais de 20 linhas, é "id" (parece matrícula); senão, "numero".
- Linhas 115–117: para texto: todos diferentes, mais de 20 linhas e textos curtos (média < 25 caracteres) → "id" (ex.: código de protocolo).
- Linhas 118–119: texto longo (média > 30 caracteres) ou muitos valores com espaços na maioria → "texto_livre" (comentários abertos).
- Linhas 120–122: até `max_categorias` valores distintos → "categoria" (ex.: região, canal); senão, "texto".

### _escala (linhas 125–126)

Devolve o menor e o maior valor da série. Usado para conferir se uma coluna "cabe" em 0–10, 1–5 etc.

### detectar_indicadores (linhas 129–152)

Reconhece quais colunas são NPS, CSAT e CES **pelo nome e pela faixa de valores**.

- Linhas 132–136: as regras. Cada tipo tem um padrão de nome e uma faixa aceitável:
  - NPS: nome com `nps`, `recomend`, `indicaria` ou `likelihood` e valores entre 0 e 10.
  - CSAT: `csat` ou `satisf`, valores entre 1 e 10.
  - CES: `ces`, `esforco`, `facilidade` ou `effort`, valores entre 1 e 7.
  - O trecho `(^|_)` exige que a palavra esteja no início do nome ou depois de um `_` (evita casar no meio de outra palavra).
- Linhas 138–143: se você **forçou** a coluna no `config.yaml` (`forcados`), ela é usada direto, desde que exista e seja numérica — e o robô nem procura por nome (`continue`).
- Linhas 144–146: percorre as colunas, só as de papel "numero" e que ainda não foram usadas por outro indicador.
- Linhas 147–151: se o nome bate com o padrão, confere se os valores são inteiros e estão na faixa; se sim, adota a coluna e para de procurar aquele tipo.
- Linha 152: devolve algo como `{"nps": "nota_nps", "csat": "satisfacao_geral"}`.

### ESCALAS_TEXTO (linhas 155–164)

Tabelas de tradução de **escalas escritas por extenso** em nota de 1 a 5 (5 = melhor), comparadas sem acento e em minúsculas:

- Linhas 157–159: escala de satisfação ("muito satisfeito" = 5 … "muito insatisfeito" = 1; "neutro"/"indiferente" = 3).
- Linhas 160–161: escala de qualidade ("ótimo/excelente/muito bom" = 5, "bom" = 4, "regular/razoável" = 3, "ruim" = 2, "péssimo/muito ruim" = 1). Também conta como CSAT.
- Linhas 162–163: escala de esforço (CES): "muito fácil" = 5 … "muito difícil" = 1.

### converter_escalas (linhas 167–188)

Transforma uma coluna de texto que é uma escala conhecida numa nova coluna numérica `<coluna>_nota`.

- Linha 170: três dicionários de saída: `novas` (colunas criadas), `origem` (nota → texto de origem), `tipos` (csat/ces → coluna nota).
- Linhas 171–174: percorre as colunas, pulando as numéricas, as de data e as de auditoria.
- Linha 175: normaliza cada valor: tira acento, põe em minúsculas, tira espaços, pontos e exclamações das pontas, e troca espaços repetidos por um só. "  Satisfeito! " vira "satisfeito".
- Linhas 176–177: com menos de 5 respostas preenchidas, nem tenta.
- Linhas 178–180: testa cada escala. Só aceita se **pelo menos 90%** dos valores forem traduzidos e houver **pelo menos 3 níveis diferentes** (evita confundir uma coluna "Sim/Não" com escala).
- Linhas 181–185: cria a coluna `_nota` (inteiro que aceita vazio, `Int64`), alinhada às linhas originais; registra a origem e o tipo (o primeiro de cada tipo vence, `setdefault`). Para na primeira escala que serviu.
- Linhas 186–188: se nada foi convertido, devolve a tabela original; senão, a tabela com as colunas novas acrescentadas.

**Exemplo**: coluna `satisfacao_geral` com 10 respostas: 3× "Muito satisfeito", 4× "Satisfeito", 2× "Neutro", 1× "Insatisfeito". Todas (100%) estão no mapa da linha 157, e há 4 níveis (5, 4, 3, 2) ≥ 3. Nasce `satisfacao_geral_nota` com 5,5,5,4,4,4,4,3,3,2 e ela vira o CSAT da base. A nota 4 e 5 (top-2-box) somam 7 de 10 → CSAT = 70%.

### calcular_indicador (linhas 192–209)

O coração dos números de pesquisa.

- Linhas 193–196: tira os vazios, converte em número, conta `n`. Sem resposta → `None`.
- Linhas 197–202 (**NPS**):
  - `p` = proporção de notas ≥ 9 (promotores); `d` = proporção ≤ 6 (detratores).
  - NPS = 100 × (p − d).
  - **Variância do NPS** (linha 199): `p + d − (p − d)²`. É a "dispersão" de uma nota que vale +1 (promotor), 0 (neutro) ou −1 (detrator).
  - **Margem de erro** (linha 200): `100 × z × √(variância / n)`.
  - Também devolve % promotores, % neutros, % detratores e a média da nota.
- Linhas 203–209 (**CSAT e CES**):
  - Linha 203: descobre a escala pelo maior valor: até 5 → 1 a 5; até 7 → 1 a 7; senão 1 a 10.
  - Linha 204: o **corte**. CSAT: `escala − 1` (top-2-box: 4–5, 6–7 ou 9–10). CES: em escala 7 ou 10, `escala − 2` (5–7 em escala de 7); em escala 5, `escala − 1` (4–5).
  - Linhas 205–206: `p` = proporção acima do corte; variância de proporção = `p × (1 − p)`.
  - Linhas 207–209: devolve nome ("CSAT (top-2-box)" ou "CES (% fácil)"), n, valor em %, margem, variância, média e escala.

**Exemplo de margem do NPS**: 200 respostas, 100 promotores (p = 0,50) e 40 detratores (d = 0,20).
- NPS = 100 × (0,50 − 0,20) = **30**.
- Variância = 0,50 + 0,20 − (0,30)² = 0,70 − 0,09 = 0,61.
- Margem = 100 × 1,96 × √(0,61 / 200) = 100 × 1,96 × 0,0552 ≈ **±10,8 pontos**.
- Leitura: o NPS "real" está entre 19,2 e 40,8 com 95% de confiança.

**Exemplo de margem do CSAT**: 150 respostas, 105 notas 4 ou 5 → p = 0,70. Margem = 100 × 1,96 × √(0,70 × 0,30 / 150) = 100 × 1,96 × 0,0374 ≈ **±7,3 pontos**.

### class Analise (linhas 213–463)

Um objeto `Analise` representa **uma tabela** sendo analisada. Os métodos `fazer_...` são os analistas.

#### __init__ (linhas 214–240)

O "construtor": roda uma vez quando a análise é criada.

- Linha 216: primeiro converte as escalas escritas (veja `converter_escalas`).
- Linhas 217–219: guarda tabela, nomes, configuração (padrão + o que veio do config) e o z crítico.
- Linha 220: calcula o papel de cada coluna.
- Linhas 221–223: detecta NPS/CSAT/CES por nome; se não achou CSAT/CES por nome mas há escala escrita convertida, usa a coluna `_nota`.
- Linhas 224–225: se você forçou segmentos no config, usa só esses (os que existem).
- Linhas 226–229: senão, segmentos = colunas de papel "categoria" com pelo menos 2 valores, que não sejam o próprio indicador nem as colunas de escala (texto ou nota), limitado a `max_segmentos`.
- Linhas 230–233: cria observações do tipo "Escala escrita 'x' convertida em nota de 1 a 5 ('x_nota')" e começa a lista `observacoes` com elas.
- Linhas 234–240: tabelas vazias que cada analista vai preencher (`perfil`, `indicadores`, `destaques`, `relacoes`, `alertas`), o resumo e a "foto" para o monitoramento.

#### fazer_perfil — Bia (linhas 243–262)

- Linhas 244–248: para cada coluna, pega a série e a versão sem vazios.
- Linhas 249–250: monta o básico: papel, total de linhas, preenchidos, % preenchido e nº de valores distintos.
- Linhas 251–255: coluna numérica ganha média, mediana, desvio-padrão (quanto os valores se afastam da média), mínimo, percentis 25 e 75 (o valor abaixo do qual estão 25% / 75% das respostas) e máximo.
- Linhas 256–257: coluna de data ganha a primeira e a última data (dd/mm/aaaa).
- Linhas 258–260: categoria/texto ganha os 5 valores mais comuns com o % de cada um, ex.: `Sul (40%); Sudeste (35%)`.
- Linha 262: vira a tabela `perfil`.

#### fazer_indicadores — Caio (linhas 265–285)

- Linha 267: lê a base mínima (30).
- Linhas 268–274: para cada indicador detectado, calcula o geral e grava uma linha "segmento = Total". Arredonda os números com 1 casa e marca `base_pequena` se n < 30. A variância não vai para a tabela (é só uso interno).
- Linhas 275–282: para cada coluna de segmento e cada grupo (ex.: regiao = Sul), recalcula o indicador só com aquelas linhas e marca `base_pequena`.
- Linhas 283–284: se não achou nenhum indicador, registra uma observação com a dica de nomes (`nota_nps`, `csat`, `ces`).
- Linha 285: vira a tabela `indicadores`.

**Base mínima na prática**: um grupo com 22 respostas aparece na tabela, mas com `base_pequena = True`; o Fábio avisa "mostre no Power BI com aviso de base pequena", e o Davi nem testa esse grupo (abaixo).

#### fazer_estatistica — Davi (linhas 288–343)

Primeira parte: **cada segmento contra o restante** (teste z).

- Linhas 289–293: os "alvos" são os indicadores; se não há indicador, compara a **média** das até 6 primeiras colunas numéricas.
- Linhas 294–298: para cada alvo, cada segmento (com ≥ 2 valores) e cada grupo dentro dele.
- Linhas 299–300: `dentro` = notas do grupo (ex.: Sul); `fora` = notas de todos os outros grupos que têm o segmento preenchido.
- Linhas 301–302: se qualquer um dos lados tem menos que a base mínima, **não testa** (pula).
- Linhas 303–306: alvo "media": diferença de médias; erro-padrão `ep = √(var_dentro/n_dentro + var_fora/n_fora)`.
- Linhas 307–311: alvo indicador: calcula o indicador dos dois lados; `ep = 100 × √(var_a/n_a + var_b/n_b)` usando as variâncias do NPS ou da proporção. Este é o **teste z de duas proporções** (no caso do NPS, de duas "médias de +1/0/−1").
- Linhas 312–313: se o erro-padrão deu zero (todo mundo deu a mesma nota), pula.
- Linhas 314–317: `z = (a − b) / ep`; guarda medida, grupo, n, valores, diferença, z e p-valor.
- Linhas 318–321: aplica Holm a **todas** as comparações juntas, com alfa = 1 − 0,95 = 0,05.
- Linhas 322–324: escreve a leitura: "ACIMA/ABAIXO do restante — diferença real" ou "dentro do esperado pelo acaso"; arredonda o p-valor para 4 casas.
- Linhas 325–326: ordena: significativos primeiro, depois pelo tamanho de |z|.

**Exemplo do teste z**: Sul tem 100 respostas (60% promotores, 10% detratores → NPS 50; variância 0,70 − 0,25 = 0,45). O restante tem 300 respostas (45% e 20% → NPS 25; variância 0,65 − 0,0625 = 0,5875).
- ep = 100 × √(0,45/100 + 0,5875/300) = 100 × √(0,0045 + 0,00196) = 100 × 0,0804 ≈ 8,04.
- z = (50 − 25) / 8,04 ≈ 3,11 → p ≈ 0,0019.
- Se houver, digamos, 10 comparações, o limite de Holm para a primeira é 0,05/10 = 0,005. Como 0,0019 < 0,005, Sul fica "ACIMA do restante — diferença real".

Segunda parte: **relações entre variáveis numéricas** (correlação).

- Linhas 328–331: pega todas as colunas numéricas e forma todos os pares (a, b) sem repetir.
- Linhas 332–334: usa só linhas com os dois preenchidos; pula se houver menos que a base mínima ou se uma coluna for constante.
- Linha 335: **correlação de Pearson** `r` (de −1 a +1: quanto as duas sobem/descem juntas).
- Linhas 336–341: só registra se |r| ≥ 0,3. Força: ≥ 0,7 forte; ≥ 0,5 moderada; senão "fraca a moderada". Sentido: mesma direção (r > 0) ou opostas. Marca se envolve um indicador (candidata a "driver" — fator que move o NPS).
- Linhas 342–343: ordena pela força (|r|).

#### tirar_foto — Eva (linhas 346–364)

A "foto" é um resumo da carga atual guardado para comparar com a próxima.

- Linhas 347–348: data, arquivo, nº de linhas.
- Linhas 349–358: para cada coluna (menos auditoria): papel e % vazio; se numérica, média e desvio; se categoria, a lista (até 200) dos valores que apareceram.
- Linhas 359–362: valor, variância, n e nome de cada indicador.
- Linhas 363–364: guarda e devolve.

#### fazer_monitoramento — Eva (linhas 366–415)

- Linha 367: usa a foto atual (tira se ainda não tirou).
- Linhas 369–372: primeira carga da base → só uma observação; sem alertas.
- Linhas 373–374: compara com a **última** carga; limite de variação = 30%.
- Linhas 376–377: função interna `add` para acrescentar um alerta (nível, tipo, coluna, mensagem).
- Linhas 379–383: **volume**: variação % de linhas. Ex.: 200 → 300 linhas = +50% ≥ 30% → alerta "atenção".
- Linhas 384–388: colunas que **sumiram** (atenção: mudou o layout?) e colunas **novas** (informativo).
- Linhas 389–392: junta todas as categorias já vistas em **todas** as cargas anteriores.
- Linhas 393–396: para colunas presentes nas duas: se o % de vazios subiu 10 pontos ou mais → atenção.
- Linhas 397–400: se a média mudou 30% ou mais → atenção. Ex.: média de idade 30 → 40 = +33%.
- Linhas 401–404: valores de categoria **nunca vistos** antes (só se a coluna já tinha histórico) → informativo, com até 6 exemplos ("novo ou erro de digitação?").
- Linhas 405–414: **indicadores**: diferença entre a carga atual e a anterior, com o mesmo erro-padrão do teste z. Se |diferença / ep| ≥ 1,96 → "mudança significativa" (atenção); senão "variação dentro da margem de erro (não é mudança real)" (informativo).
- Linha 415: vira a tabela `alertas`.

**Exemplo entre cargas**: setembro NPS 30 (n = 200, variância 0,61); outubro NPS 36 (n = 250, 52% promotores e 16% detratores → variância 0,68 − 0,1296 = 0,5504).
- ep = 100 × √(0,5504/250 + 0,61/200) = 100 × √(0,0022 + 0,00305) ≈ 7,25.
- diferença = +6; 6 / 7,25 ≈ 0,83 < 1,96 → **"variação dentro da margem de erro"**. Ou seja: não comemore +6 pontos ainda.

#### fazer_resumo — Fábio (linhas 418–463)

Monta frases simples, na ordem:

- Linhas 419–421: "Base X — arquivo Y: N registros e K colunas" (milhar com ponto).
- Linhas 422–426: período, se houver coluna de data.
- Linhas 427–432: cada indicador geral com margem e n; no NPS, também % promotores e detratores.
- Linhas 433–439: até 6 diferenças significativas (com Holm).
- Linhas 440–442: se nenhuma é significativa, avisa: "evite comunicar ranking entre grupos".
- Linhas 443–446: até 3 correlações, sempre com "Correlação não prova causa".
- Linhas 447–451: quantos alertas de atenção/informativos e os 4 primeiros de atenção.
- Linhas 452–456: colunas com menos de 80% de preenchimento ("não sustente conclusões só nelas").
- Linhas 457–461: quantos grupos com base pequena.
- Linhas 462–463: as observações acumuladas (inclusive falhas de analistas).

### chave_base (linhas 467–476)

Dá um nome estável à base para agrupar ondas.

- Linhas 469–471: se a regra do config define a tabela de destino, usa esse nome.
- Linhas 472–473: se a regra tem um padrão de arquivo (ex.: `nps_*.xlsx`), usa o padrão sem os curingas.
- Linhas 474–476: senão, quebra o nome do arquivo por `_` e joga fora números, meses, `v2`, anos de 4 dígitos, `t1`, `s2`. `nps_outubro_2026_v2.xlsx` → `nps`.

### _historico_fotos (linhas 479–486)

Lê `logs/analises/historico_<base>.json` (lista de fotos anteriores). Se não existe ou está corrompido, devolve lista vazia.

### _guardar_foto (linhas 489–491)

Acrescenta a foto nova e guarda só as **24 últimas** (`[-24:]`).

### analisar (linhas 494–540)

Ponto de entrada chamado pelo pipeline.

- Linha 496: junta configurações: padrão → `analise` do config → `analise` da regra do arquivo (a mais específica vence).
- Linhas 497–498: se desligado, não faz nada.
- Linhas 499–502: analistas desligados, nome da base e pasta do histórico.
- Linhas 504–509: `sinal` avisa o painel em que etapa está (`analise:perfil`…); se o aviso falhar, ignora.
- Linhas 511–516: para cada tabela não vazia, cria uma `Analise`. Se houver mais de uma tabela, a base vira `<base>_<tabela>`.
- Linhas 517–519: as 5 etapas na ordem. O monitoramento recebe as fotos anteriores.
- Linhas 520–528: roda cada etapa dentro de `try`. Se um analista quebrar, os outros continuam e a falha vira observação no relatório.
- Linhas 529–533: guarda a foto no histórico (falha só vai para o log).
- Linhas 535–540: grava as saídas e devolve ao painel: base, arquivo, resumo e os registros de indicadores e destaques (usados depois pela manchete do gerente e pelos checklists).

### _gravar (linhas 543–574)

- Linhas 544–551: monta as abas do `_analise.xlsx`: resumo, perfil, indicadores, destaques, relacoes, alertas (com a coluna `tabela`).
- Linhas 552–559: grava em `Bases-Relatorios/<base>_analise.xlsx`. Se o arquivo estiver aberto no Excel (`PermissionError`), avisa e segue sem ele.
- Linhas 560–568: grava o JSON do painel (`logs/analises/<id>.json`) com papéis, indicadores detectados, segmentos e até 300 linhas de cada aba.
- Linhas 569–573: se o banco está ligado, grava no PostgreSQL (falha vira aviso).

### _gravar_banco (linhas 577–627)

- Linhas 579–582: importa ferramentas de SQL (linguagem dos bancos de dados) e a conexão do robô.
- Linhas 583–596: define quais colunas cada tabela do schema `analise` terá e o tipo de cada uma (inteiro, verdadeiro/falso, número decimal ou texto).
- Linhas 597–598: abre uma **transação** (tudo ou nada) e cria o schema `analise` se não existir.
- Linhas 599–606: para cada tabela: cria se não existe (com `lote_id`, `base`, `arquivo`, `analisado_em`), **apaga** as linhas deste mesmo lote (permite reprocessar sem duplicar) e pula se não há dados.
- Linhas 607–623: converte cada valor para o tipo certo (vazio/NaN vira `NULL`).
- Linhas 624–627: insere todas as linhas de uma vez (`executemany`), com nomes de tabela/coluna escapados com segurança (`sql.Identifier`).

**Erros que este arquivo evita**
- Comunicar "Sul é melhor que Norte" quando a diferença é acaso (teste z + Holm).
- Tirar conclusão de grupo com menos de 30 respostas (base mínima).
- Comemorar ou alarmar por variação de NPS que está dentro da margem de erro entre ondas.
- Não perceber mudança de layout (coluna sumiu), aumento de vazios ou categoria digitada errada.
- Ignorar uma pesquisa porque a nota veio escrita ("Muito satisfeito") e não em número.
- Tratar coluna de matrícula ou comentário aberto como segmento.
- Uma falha de análise derrubar uma publicação já aprovada.

---

## robo/excel.py

- **Para que serve**: é o 3º andar, a "Sala Excel". Para cada base aprovada, monta um arquivo Excel em que **todo número é uma fórmula viva** sobre a aba Dados (nada colado): plano tabular (frequências e NPS por segmento), indicadores com margem de erro e, se houver vendas, uma visão de trade marketing. Cada fórmula é recalculada em Python e comparada dentro do próprio arquivo, na aba Conferência; o Resumo diz no topo se está tudo OK.
- **Onde entra no fluxo**: chamado por `robo/pipeline.py` (linhas 396–399), depois da análise, com `gerar_entrega`. Gera `Bases-Relatorios/<base>_excel.xlsx`. Depois, a revisão da equipe (no pipeline) marca `revisao_ok`.

> Observação importante sobre os nomes das fórmulas: o código grava as fórmulas em inglês e com vírgula (`COUNTIFS(...,...)`), que é o formato interno do arquivo `.xlsx`. Ao abrir num Excel em português, você verá `CONT.SES(...;...)`. Equivalências usadas aqui: COUNTIFS = CONT.SES, COUNTIF = CONT.SE, COUNT = CONT.NÚM, SUMIFS = SOMASES, SUM = SOMA, IF = SE, IFERROR = SEERRO, ISNUMBER = ÉNÚM, SQRT = RAIZ, MAX = MÁXIMO, ABS = ABS.

### Cabeçalho (linhas 1–15)

- Linhas 1–10: apresenta a equipe: Ricardo (supervisor, Conferência), Pedro (plano tabular), Lúcia (indicadores), Tânia (trade), Gabriel (Resumo e formatos).
- Linhas 12–14: a garantia de qualidade: cada número recalculado em Python e comparado com a fórmula; o Excel recalcula ao abrir.

### Imports (linhas 17–33)

- Linhas 19–25: bibliotecas padrão e pandas.
- Linhas 26–29: **openpyxl**, a biblioteca que escreve arquivos `.xlsx`: `Workbook` (pasta de trabalho), estilos (`Font`, `PatternFill`, `Border`…), `get_column_letter` (1 → "A", 27 → "AA") e `CalcProperties` (configuração de cálculo).
- Linha 31: `sem_acento`.
- Linha 33: o log.

### EQUIPE_EXCEL (linhas 35–48)

Os cinco especialistas com `id`, `nome`, `papel`, `cor` e `descricao`. Os `id`s são usados como "etapas" no painel.

### PADRAO_EXCEL (linha 50)

`habilitado`; `max_linhas: 300_000` (acima disso não gera — o Excel ficaria pesado); `max_categorias: 30`; `max_segmentos: 6`; `top_trade: 50` (quantos itens mostrar por dimensão no Trade).

### RE_MEDIDA e RE_DIMENSAO (linhas 52–53)

Padrões de nome:
- Linha 52: colunas de **medida** de trade: valor, venda(s), receita, faturamento, sell_out, sell_in, preço, quantidade, qtd, volume, unidades, gmv.
- Linha 53: colunas de **dimensão**: loja, pdv, canal, região, uf, estado, cidade, categoria, marca, sku, produto, rede, cliente, vendedor, bandeira, fornecedor.
- O `(^|_)…(_|$)` exige a palavra inteira dentro do nome (`valor_venda` casa; `avaliacao` não).

### Estilos (linhas 55–61)

Cores (azul do cabeçalho, verde claro do status, cinza), fonte branca em negrito, negrito e borda fina cinza.

### _criterio (linhas 64–69)

Monta o **critério** de um CONT.SES/SOMASES que casa *exatamente* com o valor.

- Linha 66: no Excel, `*` e `?` são curingas e `~` é o "escape". Então troca `~` por `~~`, `*` por `~*` e `?` por `~?`. Assim a categoria "Loja*Centro" não vira "qualquer coisa que comece com Loja".
- Linhas 67–68: se o valor começa com `<`, `>` ou `=`, o Excel entenderia como comparação; por isso põe `=` na frente (`"=>50 anos"` significa "igual a '>50 anos'").
- Linha 69: põe entre aspas (dobrando aspas internas, regra do Excel).

### _igual_excel (linhas 72–75)

Reproduz em Python a regra de igualdade do CONT.SES: compara texto **sem diferenciar maiúsculas** ("SUL" = "sul"); vazios nunca casam. Aqui o Python também tira espaços das pontas (`strip`). Essa máscara é usada para calcular o "valor esperado" de cada fórmula.

### class Entrega (linhas 78–363)

#### __init__ (linhas 79–88)

- Linha 80: tabela com índice limpo (0, 1, 2…), para a linha N do Python ser a linha N+2 do Excel.
- Linhas 81–82: guarda base, arquivo, papéis, indicadores e configuração.
- Linhas 83–84: cria a pasta de trabalho e liga `fullCalcOnLoad`: o Excel **recalcula tudo ao abrir** (o openpyxl escreve fórmulas, mas não calcula resultados).
- Linha 85: lista de conferências: (descrição, célula, valor esperado).
- Linhas 86–88: nº de linhas, mapa coluna → letra, e lista das etapas concluídas.

#### _faixa (linhas 91–93)

Devolve a faixa absoluta de uma coluna na aba Dados, ex.: `Dados!$C$2:$C$1201` (cabeçalho na linha 1, dados da 2 até n+1). O `$` trava a referência.

#### _conferir (linhas 95–96)

Registra uma conferência: "esta célula deve dar este número".

#### _cabecalho (linhas 98–102)

Escreve uma linha de títulos com fundo azul, fonte branca em negrito, centralizado, com quebra de texto e borda.

#### _larguras (linhas 104–107)

Define a largura de colunas, ex.: `{"A": 34}`.

#### aba_dados (linhas 110–132) — aba **Dados**

- Linhas 111–112: a primeira aba vira "Dados".
- Linhas 113–116: guarda a letra de cada coluna e escreve o cabeçalho.
- Linhas 117–119: escreve cada linha; vazios viram células vazias e datas do pandas viram datas do Excel.
- Linhas 120–124: **segurança**: se um texto da origem começa com `=`, o openpyxl o marcaria como fórmula; aqui ele volta a ser texto. Isso impede "injeção de fórmulas" (um comentário malicioso como `=HYPERLINK(...)` virar fórmula ativa).
- Linhas 125–130: largura entre 10 e 40 conforme o nome; colunas de data com formato `dd/mm/yyyy`.
- Linhas 131–132: congela a linha 1 e liga o autofiltro.

#### segmentos (linhas 135–139)

Escolhe colunas de segmento para o plano tabular: papel "categoria", entre 2 e 30 valores distintos, textos com menos de 200 caracteres; no máximo 6.

#### aba_plano_tabular (linhas 141–198) — aba **Plano tabular** (Pedro)

- Linhas 142–144: sem segmentos, não cria a aba.
- Linhas 145–147: título e instrução.
- Linhas 148–149: coluna de NPS (se houver) e linha inicial 4.
- Linhas 150–155: para cada segmento: títulos "Categoria, Base (n), % da base" e, se há NPS, "Promotores, Detratores, NPS, Base pequena?".
- Linhas 156–161: lista os valores distintos (sem espaços nas pontas, em ordem alfabética) e pula repetições que diferem só em maiúsculas — igual ao CONT.SES, que não diferencia.
- Linhas 162–164: calcula em Python quantas linhas casam (valor esperado).
- Linhas 165–168: coluna A = categoria; coluna B = `=CONT.SES(Dados!faixa_segmento; "Sul")` — a **base** do grupo; registra a conferência.
- Linhas 169–170: coluna C = `=SE($B$TOTAL=0; 0; B5/$B$TOTAL)` — % da base. Como ainda não se sabe em que linha ficará o Total, grava o marcador `{TOTAL}` (as chaves duplas `{{TOTAL}}` na f-string viram `{TOTAL}` literal).
- Linhas 171–177: se há NPS: D = `=CONT.SES(segmento; "Sul"; nota; ">=9")` (promotores), E = `=CONT.SES(segmento; "Sul"; nota; "<=6")` (detratores).
- Linhas 178–180: F = NPS = `(D − E) / n_resp × 100`, em que `n_resp` = `CONT.SES(segmento; "Sul"; nota; ">=0")`, isto é, quem deu nota. Se ninguém deu nota, fica vazio.
- Linha 181: G = `=SE(n_resp<30; "sim"; "não")` — **base pequena**.
- Linhas 182–185: conferências de promotores, detratores e NPS.
- Linhas 186–190: linha **Total**: B = `=SOMA(B início : B fim)`; C = soma dos %.
- Linhas 191–193: agora que a linha do Total é conhecida, troca `{TOTAL}` pelo número real em todas as fórmulas de %.
- Linha 194: confere o Total contra o nº de linhas com o segmento preenchido.
- Linhas 195–198: pula 3 linhas para o próximo segmento; larguras, congela até a linha 3, registra a etapa.

**Exemplo**: segmento `regiao`, categoria "Sul": 120 linhas (B), 115 com nota, 60 promotores (D), 20 detratores (E). F = (60 − 20) / 115 × 100 = **34,8**. G = "não" (115 ≥ 30). Se o total preenchido for 400, C = 120/400 = 30,0%.

#### aba_indicadores (linhas 201–249) — aba **Indicadores** (Lúcia)

- Linhas 202–208: sem indicadores, não cria. Título, instrução e cabeçalho na linha 4.
- Linhas 209–213: NPS: Python calcula n, promotores e detratores.
- Linhas 214–221: as 7 linhas (5 a 11), cada uma com fórmula, formato e valor esperado:
  - B5 `=CONT.NÚM(faixa)` — respostas;
  - B6 `=CONT.SE(faixa; ">=9")` — promotores;
  - B7 `=CONT.SE(faixa; "<=6")` — detratores;
  - B8 `=SE(B5=0; 0; B6/B5)` — % promotores;
  - B9 `=SE(B5=0; 0; B7/B5)` — % detratores;
  - B10 `=(B8−B9)*100` — **NPS**;
  - B11 `=SE(B5=0; 0; 1,96*RAIZ((B8+B9−(B8−B9)^2)/B5)*100)` — **margem de erro**, a mesma fórmula do `analise.py`.
- Linhas 222–223: textos de leitura da coluna C.
- Linhas 224–229: escreve e registra cada conferência.
- Linha 230: destaca o NPS (B10) em negrito maior.
- Linhas 231–237: CSAT: escala pelo máximo (5/7/10) e corte = escala − 1 (top-2-box).
- Linhas 238–247: pula uma linha e escreve: respostas `=CONT.NÚM`, satisfeitos `=CONT.SE(faixa; ">=4")` e CSAT = satisfeitos / respostas, cada um conferido.
- Linhas 248–249: larguras e etapa.

Repare: CES não ganha linha nesta aba (só NPS e CSAT).

#### colunas_trade (linhas 252–256)

Medidas = colunas numéricas cujo nome casa com `RE_MEDIDA`; dimensões = categoria/texto cujo nome casa com `RE_DIMENSAO` e com textos < 200 caracteres.

#### aba_trade (linhas 258–303) — aba **Trade** (Tânia)

- Linhas 259–261: precisa de pelo menos uma medida e uma dimensão.
- Linhas 262–264: título e instrução.
- Linhas 265–266: escolhe a medida de **valor** (nome com valor/venda/receita/faturamento/sell/gmv; senão a primeira) e, se houver, uma de **quantidade**.
- Linhas 267–273: para até 3 dimensões: título "loja × valor" e cabeçalho (com quantidade e preço médio quando há quantidade).
- Linhas 274–276: agrupa em Python sem diferenciar maiúsculas/espaços, soma o valor e ordena do maior para o menor; total geral.
- Linhas 278–286: para os 50 maiores: B = `=SOMASES(Dados!valor; Dados!loja; "L1")`, conferido.
- Linhas 287–290: C = **share** = `=SE(SOMA(valor)=0; 0; B/SOMA(valor))`, conferido contra soma do grupo ÷ total geral.
- Linhas 291–297: se há quantidade: D = `=SOMASES(qtd; loja; "L1")` (conferido) e E = **preço médio** = `B / D` (faturamento ÷ unidades — nunca a média simples dos preços).
- Linhas 298–300: se há mais de 50 itens, nota "(mostrando os 50 maiores de N)".
- Linhas 301–303: espaço entre blocos, larguras, etapa.

**Exemplo**: loja L1 vendeu R$ 50.000 em 2.000 unidades; total da base R$ 200.000. Share = 25,0%; preço médio = R$ 25,00.

#### aba_conferencia (linhas 306–320) — aba **Conferência** (Ricardo)

Como a Conferência compara com o Python:

- Linhas 307–310: título, explicação e cabeçalho "#, O que é conferido, Valor da fórmula, Valor esperado, Status".
- Linhas 311–314: uma linha por conferência registrada.
- Linha 315: C = `=SEERRO('Plano tabular'!B5; "#ERRO")` — **puxa o resultado da fórmula** da célula conferida.
- Linha 316: D = o número que o **Python** calculou, gravado como valor fixo (arredondado em 10 casas).
- Linha 317: E = `=SE(ÉNÚM(C); SE(ABS(C−D) <= 0,0001*MÁXIMO(1; ABS(D)); "OK"; "ERRO"); "ERRO")`. Ou seja: aceita uma diferença de até 0,01% do valor (ou 0,0001 para números pequenos). Se a fórmula der erro ou texto, é "ERRO".
- Linhas 318–320: larguras, congela, etapa.

**Exemplo**: NPS do Sul. Fórmula dá 34,7826087; Python gravou 34,7826087. Diferença ≈ 0, limite = 0,0001 × 34,78 ≈ 0,0035 → OK. Se alguém apagasse uma linha da aba Dados, a fórmula mudaria e o status viraria ERRO.

#### aba_resumo (linhas 322–351) — aba **Resumo** (Gabriel)

- Linha 323: cria o Resumo como **primeira** aba.
- Linha 324: última linha das conferências (4 + quantidade).
- Linhas 325–330: B3 = `=SE(CONT.SE('Conferência'!E5:E_última; "OK") = total; "✔ Todas as N conferências OK"; "✖ Há divergências — não use, avise o supervisor")`.
- Linhas 331–335: arquivo de origem, registros, data de geração e supervisor.
- Linhas 336–347: guia das abas que de fato existem nesta entrega.
- Linhas 348–351: dica "clique em qualquer número e veja a fórmula", larguras, etapa.

#### gerar (linhas 353–363)

- Linhas 354–359: monta as abas nesta ordem (Dados primeiro, porque as outras dependem das letras das colunas; Conferência e Resumo por último, porque dependem das conferências registradas).
- Linhas 360–362: salva primeiro num arquivo temporário `~robo_tmp_...` e só depois troca pelo definitivo — nunca fica um arquivo pela metade.
- Linha 363: devolve caminho, nº de conferências, abas e etapas.

### gerar_entrega (linhas 366–399)

- Linhas 368–370: junta configuração; se desligado ou sem tabela, sai.
- Linhas 371–373: usa **só a primeira tabela**; pula se vazia ou com mais de 300 mil linhas.
- Linhas 374–376: reaproveita as funções do `analise.py` e converte escalas escritas.
- Linhas 377–383: como o pipeline passa `papeis=None` e `indicadores=None`, recalcula papéis e detecta indicadores (sem colunas forçadas) e adota as escalas convertidas.
- Linhas 384–385: garante um papel para toda coluna.
- Linhas 386–392: cria a `Entrega` e sinaliza ao painel as 5 etapas.
- Linhas 393–394: gera `Bases-Relatorios/<base>_excel.xlsx`.
- Linhas 395–399: arquivo aberto no Excel → aviso; qualquer outro erro → log; devolve `None`. Nunca derruba o pipeline.

**Erros que este arquivo evita**
- Número colado que ninguém consegue auditar: tudo é fórmula sobre a aba Dados.
- Fórmula que diverge do cálculo oficial sem ninguém perceber (aba Conferência + status no Resumo).
- Categoria com `*`, `?` ou começando com `=`/`>` contada errado no CONT.SES (`_criterio`).
- Texto malicioso começando com `=` virando fórmula ativa.
- Preço médio calculado como média simples de preços.
- Arquivo de entrega corrompido pela metade (gravação via temporário).

---

## robo/canal.py

- **Para que serve**: é o "chat" interno da empresa-robô, **100% offline** (sem internet e sem IA externa). Você escreve uma mensagem e um roteador em Python decide quem responde: um dado real do robô (status, erros, sprint, banco), um verbete da base de conhecimento (Excel, Power BI, pesquisa, trade), um trecho dos manuais `.md`, a calculadora de amostra ou a calculadora sobre as bases. Também posta automaticamente os acontecimentos (aprovações, reprovações, análises, entregas Excel), o relatório da sprint de 15 dias, o boletim diário e as ideias da Iara.
- **Onde entra no fluxo**: o painel chama `Canal(cfg).perguntar(...)` quando você envia uma mensagem e `sincronizar()` periodicamente (`robo/painel/controle.py` linha 126 e `robo/painel/servidor.py`). Outras partes (backup, TI, estratégia) usam `postar` para escrever no canal. Arquivos: `logs/canal/mensagens.jsonl` e `logs/canal/estado.json`.

### Cabeçalho (linhas 1–11)

Explica o método: (1) normaliza o texto, (2) pontua intenções e verbetes pelas palavras-chave, (3) a maior pontuação responde; se nada bate com segurança, diz "não entendi".

### Imports (linhas 13–23)

`json`, `math`, `re`, `threading` (para a trava que impede duas gravações ao mesmo tempo), `unicodedata` (para tirar acentos), datas e caminhos; e `historico` do robô (o registro de todas as execuções).

### _num_br (linhas 26–31)

Converte números gravados no histórico com vírgula decimal ("0,3" → 0,3; "1.234,5" → 1234,5). Se não der, devolve 0.

### CANAIS (linhas 33–43)

Os canais do chat (geral, engenharia, análise, excel, liderança, banco, rh, ideias, ti) com o nome de exibição.

### EQUIPE_CANAL (linhas 45–55)

Nina (assistente que roteia mensagens), Iara (ideias) e Helena (RH), todas do 4º andar.

### DONO, DIAS_SPRINT, _trava (linhas 57–59)

- Linha 57: você, com id `dono`.
- Linha 58: sprint de 15 dias.
- Linha 59: `Lock` é um "cadeado": só uma mensagem é gravada por vez, evitando números de mensagem repetidos.

### normalizar (linhas 63–66) — primeiro passo para entender a mensagem

- Linha 64: põe em minúsculas e decompõe letras acentuadas ("é" vira "e" + acento separado).
- Linha 65: remove os acentos separados.
- Linha 66: troca por espaço tudo que não for letra, número ou um destes sinais: `% . , = ( ) - /`; depois junta espaços repetidos.
- Exemplo: `"Ricardo, como faço um PROCX?"` → `"ricardo, como faco um procx"`.

### _pasta (linhas 69–72)

Garante que a pasta `logs/canal` existe.

### _num (linhas 75–76)

Formata inteiro com ponto de milhar: 12345 → "12.345".

### pessoas (linhas 79–99)

Monta o "crachá" (nome, papel, canal) de todo mundo que pode falar: agentes nativos da engenharia (linha 85), analistas com prefixo `analise_` (linha 87), Sala Excel (88), supervisores (89), equipe do canal (91), quadro de gestão (96), TI (97) e você (98). Ajusta canais específicos (banco, dba, ideias, rh). Os imports estão dentro da função para evitar "importação circular" (dois arquivos que precisam um do outro ao mesmo tempo).

### class Canal (linhas 103–244)

#### __init__ (linhas 104–108)

Guarda a configuração e os caminhos de `mensagens.jsonl` e `estado.json`.

#### estado (linhas 111–115) e salvar_estado (linhas 117–120)

- `estado` lê o JSON de estado (contador de mensagens, execuções já postadas, início das sprints, último boletim). Se não existe ou está corrompido, devolve vazio.
- `salvar_estado` grava num `.tmp` e depois troca (gravação segura).

#### ler (linhas 123–135)

Lê o arquivo **JSONL** (um JSON por linha). Linha corrompida (ex.: computador desligou no meio) é pulada, sem derrubar o canal.

#### postar (linhas 137–150)

- Linha 138: canal inválido vira "geral".
- Linha 139: pega o crachá do autor.
- Linhas 140–143: com a trava, incrementa o contador `seq` (o número da mensagem).
- Linhas 144–146: monta a mensagem: id, data/hora, canal, autor, nome, papel, tipo (mensagem, pergunta, resposta, acontecimento, sprint, boletim…), texto e extras.
- Linhas 147–149: acrescenta uma linha ao arquivo e salva o estado.

#### listar (linhas 152–169)

Filtra mensagens por canal (o "geral" mostra tudo), autor, tipo, busca (sem acento), últimos N dias e "depois do id X"; devolve as últimas 300.

#### perguntar (linhas 172–179)

- Linha 173: corta a mensagem em 2.000 caracteres.
- Linha 176: posta sua pergunta.
- Linhas 177–178: chama `responder` e posta cada resposta ligada à sua pergunta, com a intenção detectada.

#### sincronizar (linhas 182–205)

- Linhas 184–186: pega as execuções já postadas e as 300 últimas do histórico, da mais antiga para a mais nova.
- Linhas 187–189: na primeira vez, só as 10 mais recentes (não inunda o canal com o passado).
- Linhas 190–199: para cada execução nova, gera as mensagens de quem trabalhou (`_mensagens_execucao`) e posta como "acontecimento".
- Linhas 200–202: guarda até 2.000 ids já postados.
- Linhas 203–205: dispara a sprint automática e o boletim automático.

#### inicio_sprints (linhas 208–217)

A data da primeira sprint: a já gravada no estado; senão, a data do primeiro arquivo do histórico (ou hoje), que fica gravada.

#### sprint_de (linhas 219–223)

Em qual sprint cai um dia: `n = dias desde o início // 15` (divisão inteira).
- Exemplo: início 01/01, hoje 20/01 → 19 dias → 19 // 15 = 1 → **sprint 2**, de 16/01 a 30/01.

#### _sprint_automatica (linhas 225–229)

Se estamos na sprint 2 ou mais e a anterior ainda não foi reportada, publica o relatório **fechado** da sprint anterior.

#### publicar_sprint (linhas 231–244)

- Linhas 232–236: descobre a sprint atual, calcula início e fim da sprint pedida.
- Linha 237: se não foi dito, é "parcial" quando é a sprint em andamento.
- Linhas 238–239: gera as falas e posta cada uma no canal da pessoa.
- Linhas 240–243: se fechada, grava `ultima_sprint_reportada`.

### _mensagens_execucao (linhas 248–283)

Transforma uma execução em falas das pessoas:

- Linhas 252–256: **sucesso**: a Publicação diz quantas linhas foram publicadas (e se foi também ao PostgreSQL).
- Linhas 257–260: a Limpeza diz quantas linhas tirou.
- Linhas 261–267: o gerente de análise posta a manchete; o relator posta até 3 frases do resumo.
- Linhas 268–270: o coordenador de análise cita ressalvas.
- Linhas 271–275: Ricardo "assina" a entrega Excel com o nº de conferências.
- Linhas 276–282: **reprovado**: quem barrou (supervisor, DBA ou validação, conforme a mensagem de erro) diz o principal motivo e que o arquivo está em Bases-Erros.

### _periodo (linhas 287–290)

Execuções do histórico entre duas datas, e os detalhes de até 500 delas.

### relatorio_sprint (linhas 293–364)

Cada pessoa fala no formato **Feito · Bom · Travou · Backlog**.

- Linhas 295–301: separa aprovados e barrados, monta o título "Sprint 3 (01/02 a 15/02, parcial)".
- Linhas 303–308: função interna `fala` que monta a frase só com as partes preenchidas.
- Linhas 310–314: período sem arquivos: Nina diz isso e sugere conferir o OneDrive; Iara traz ideias.
- Linhas 316–323: conta os motivos de erro mais frequentes (troca números por "N" para agrupar "linha 12" e "linha 40" como o mesmo motivo); taxa de aprovação.
- Linhas 325–334: Recepção (recebidos, aprovados, %), Limpeza (linhas tratadas e removidas), Validação (barrados, motivos mais frequentes e backlog de corrigir na origem).
- Linhas 335–343: Banco e DBA (o que carregaram) ou, sem banco, o passo a passo para ligar.
- Linhas 344–348: Supervisor (conferidos/barrados) e Coordenadora de engenharia (liberações).
- Linhas 349–352: Coordenador de análise (análises e ressalvas).
- Linhas 353–357: Ricardo (entregas Excel e conferências).
- Linhas 358–362: Helena (resultado do processo seletivo técnico).
- Linhas 363–364: ideias da Iara no fim.

**Exemplo de taxa**: 40 arquivos, 34 aprovados → 34/40 × 100 = 85% de aprovação.

### ideias (linhas 368–396)

Lista de ideias, cada uma com **Motivo** (o dado) e **Primeiro passo**, em ordem de impacto:

- Linhas 370–373: sem histórico informado, lê as 300 últimas execuções.
- Linhas 375–377: banco desligado → ligar o PostgreSQL.
- Linhas 378–381: mais de 20% reprovados → atacar a causa.
- Linhas 382–385: mais de 2 arquivos sem regra específica → criar regras no `config.yaml`.
- Linhas 386–389: há alertas de monitoramento de "atenção" → revisá-los.
- Linhas 390–395: três ideias fixas: painel no Power BI, padronizar nomes de arquivo, e, com 6 meses de histórico, testar previsão de churn com regressão logística.

### _ideias_falas (linhas 399–401)

Pega as 3 primeiras ideias e transforma numa fala da Iara no canal "ideias".

### CONHECIMENTO (linhas 406–530) — a base de conhecimento

Lista de **verbetes**, cada um com `chaves` (palavras sem acento que disparam o verbete), `autor` (quem responde) e `texto` (resposta didática). Grupos:

- Linhas 407–474: Excel — PROCX/PROCV, ÍNDICE+CORRESP, SOMASES, CONT.SES, tabela dinâmica, Power Query, SEERRO e erros (#N/D, #DIV/0!), duplicados, texto para colunas, formatação condicional, congelar painéis, lista suspensa, datas, função SE/SES, atalhos, referência absoluta.
- Linhas 475–485: Power BI — DAX (medida de NPS com CALCULATE e DIVIDE) e modelo estrela.
- Linhas 486–509: pesquisa — NPS, CSAT, CES, significância (teste z + Holm, base 30), margem de erro, questionário.
- Linhas 510–524: trade marketing — sell-in/sell-out, share, positivação/ruptura, preço médio/ticket.
- Linhas 525–529: gráficos e layout de dashboard.

### INTENCOES (linhas 532–543)

Palavras-chave das **intenções** sobre o trabalho do robô: status, erros, sprint, ideias, banco, equipe, ajuda, amostra e saudação. Algumas são radicais ("reprovad", "sugest", "evolu") para pegar variações.

### PALAVRAS_VAZIAS (linhas 546–548)

Palavras comuns demais para servir de pista ("como", "para", "voce", "fazer", "preciso"…). São ignoradas na busca nos manuais `.md`.

### _secoes_markdown (linhas 551–573) — manuais .md

- Linhas 553–557: lista os `.md` da pasta de agentes (o nome do arquivo é o autor, ex.: `excel_supervisor.md`).
- Linhas 558–560: lista os `.md` da pasta `conhecimento/` (exceto os que começam com `_`); o autor é a Nina.
- Linhas 561–566: lê até 300 arquivos, até 200 mil caracteres cada.
- Linhas 567–572: corta o texto em **seções** a cada título `#`, `##` ou `###`; cada seção vira {arquivo, autor, título, corpo}.

### _buscar_markdown (linhas 576–587)

- Linha 577: termos da sua mensagem com 4+ letras que não são palavras vazias.
- Linhas 580–586: para cada seção, conta os termos encontrados: **3 pontos** se o termo está no título, **1** se só no corpo. Só vale se achar **pelo menos 2 termos diferentes**. Guarda a seção com mais pontos.

**Exemplo**: "qual a boa prática para chave única?" → termos {"qual", "pratica", "chave", "unica"} ("para" é vazia; "boa" tem 3 letras). Na seção "Qualidade de dados: limpeza" do `boas_praticas.md`, "qual" aparece no título ("qualidade" contém "qual") = 3 e "chave" no corpo = 1 → 4 pontos com 2 termos. Outras seções podem pontuar mais; vence a maior.

### _pontuar (linhas 590–600) — pontuação de intenções e verbetes

- Linha 592: separa a mensagem em palavras.
- Linhas 593–595: chave com espaço ou com sinal (ex.: "tabela dinamica", "cont.ses") vale **3 pontos** se aparece no texto.
- Linhas 596–597: chave de uma palavra que aparece como **palavra inteira** vale **2**.
- Linhas 598–599: chave com 5+ letras que aparece **dentro** de outra palavra (radical) vale **1** ("reprovad" em "reprovados").

**Exemplo**: "quantos arquivos foram reprovados?" → intenção "erros": "reprovad" é radical dentro de "reprovados" → 1 ponto.

### _numeros (linhas 603–604)

Extrai números do texto no formato brasileiro: "2.000" → 2000; "5,5" → 5,5.

### responder (linhas 607–657) — o roteador

A ordem de decisão:

1. Linhas 609–613: normaliza e verifica se você **chamou alguém pelo nome** ("Ricardo, …", "@Dora …"). Guarda essa pessoa em `chamado`.
2. Linhas 615–618: pontua todas as intenções e todos os verbetes; pega o melhor de cada.
3. Linhas 620–622: **calculadora de amostra/margem**: se a mensagem tem intenção "amostra" (ou a palavra "margem") **e** tem números, calcula na hora.
4. Linhas 623–631: **calculadora das bases**: se a mensagem não começa com "como", "o que", "qual a diferenca" ou "por que", tenta `calculos.calcular`. Se reconhecer um pedido, responde com o cálculo; se der erro, responde honestamente com o erro.
5. Linhas 632–639: **manuais .md**: se uma seção fez 4+ pontos e mais que o melhor verbete e a melhor intenção, responde citando "Do manual X — título: …" (corta em 1.200 caracteres).
6. Linhas 640–643: **verbete**: se o verbete fez mais pontos que a intenção (ou ≥ 2 e a intenção é só ajuda/saudação/equipe), responde o verbete.
7. Linhas 644–648: **intenção**: chama a função de resposta correspondente (`_RESPOSTAS`). Se você chamou alguém pelo nome e a intenção era só status/saudação, quem responde é a pessoa chamada.
8. Linhas 649–650: só chamou alguém pelo nome → a pessoa se apresenta.
9. Linhas 651–657: nada bateu → "Não tenho certeza do que você precisa — prefiro perguntar a chutar", com sugestões.

**Exemplo completo**: "Ricardo, como faço um procx entre duas planilhas?" → normalizada; `chamado` = Ricardo (excel_supervisor). Intenções: 0. Verbete PROCX: "procx" palavra inteira = 2. Não tem número. Não começa com "como" (começa com "ricardo"), então tenta a calculadora, que não acha operação e devolve nada. Se nenhum manual fizer 4+ pontos acima de 2, vence o verbete PROCX (2 > 0) e Ricardo responde. (É exatamente o que a prova técnica da linha 839 confere.)

### _resposta_pessoal (linhas 660–668)

A pessoa chamada se apresenta: nome, cargo e duas responsabilidades da ficha de RH.

### _hoje (linhas 671–674)

Execuções de hoje: todas, aprovadas e reprovadas.

### _r_status (linhas 677–687)

Coordenadora de engenharia: "Hoje: N recebidos, X aprovados com Y linhas, Z barrados" (e o último barrado), ou "ainda não chegou nenhuma planilha".

### _r_erros (linhas 690–702)

Validação: os 3 últimos barrados com data e a primeira mensagem de ERRO de cada; orienta corrigir na origem ou usar Reprovados → Reprocessar.

### _r_sprint (linhas 705–712)

Nina: período da sprint atual e as 3 primeiras falas da parcial; sugere "Rodar sprint" para o relatório completo.

### _r_ideias (linhas 715–718)

Iara: as 3 ideias de maior impacto.

### _r_banco (linhas 721–732)

DBA: se o banco está desligado, o passo a passo para ligar (porta 5432, banco `robo_dados`, variável `ROBO_PG_SENHA`); se ligado, onde está e como as cargas são reconciliadas.

### _r_equipe (linhas 735–749)

Helena: total de pessoas por andar e quem foi reprovado nas provas; como contratar.

### _r_ajuda (linhas 752–753)

Reaproveita a resposta de "não entendi" (chama `responder("xyzzy")`, que nunca bate em nada), mas com intenção "ajuda".

### _r_saudacao (linhas 756–758)

"Oi! " + o status do dia.

### _r_amostra (linhas 761–766)

Quando você fala de amostra mas sem números: explica o que informar e a regra de bolso (95%, público grande): ±5 → 385; ±3 → 1.068; ±10 → 97; 30 por segmento (ideal 100).

### _calculo_amostral (linhas 769–796) — a calculadora de amostra

- Linhas 770–774: procura a **margem** (número seguido de `%`, "pontos", "p.p." ou "pp"); os outros números são candidatos a população.
- Linhas 775–783: **sem margem, mas com "respostas", "entrevist" ou "com "**: calcula a margem de erro para aquele n, no pior caso p = 50%: `e = 1,96 × √(0,25 / n)`. Para NPS, mostra até o dobro.
  - Exemplo: "margem de erro com 400 respostas" → e = 1,96 × √(0,25/400) = 1,96 × 0,025 = **±4,9 pontos**; NPS até **±9,8**.
- Linhas 784–785: margem ausente ou fora de 0–50% → explicação genérica.
- Linha 786: **amostra para público grande**: `n0 = 1,96² × 0,25 / margem²`.
- Linhas 787–792: com população informada, aplica a **correção para população finita**: `n = n0 / (1 + (n0 − 1) / N)`.
- Linhas 793–796: arredonda para cima e lembra da folga de ~10% e da base por segmento.

**Exemplo**: "amostra para margem de 5% numa base de 2000 clientes" → n0 = 3,8416 × 0,25 / 0,0025 = 384,16; n = 384,16 / (1 + 383,16/2000) = 384,16 / 1,1916 ≈ 322,4 → **323 respostas** (conferido pela prova da linha 862).

### _RESPOSTAS (linhas 799–800)

Mapa intenção → função de resposta.

### boletim_diario (linhas 804–814)

- Linhas 805–807: execuções do dia; sem nenhuma, "nenhum arquivo recebido".
- Linhas 808–811: aprovados, barrados, linhas publicadas e quantos passaram do prazo (SLA, padrão 120 segundos, configurável em `quadro.sla_segundos`).
- Linhas 812–814: frase final com prioridade de amanhã.

### _boletim_automatico (linhas 817–824)

Uma vez por dia (se o boletim de ontem ainda não saiu e o canal já sincronizou ao menos uma vez), a gerente de operações posta o boletim de **ontem** no canal geral.

### provas_canal (linhas 828–865)

"Provas técnicas" que o RH roda para conferir que o canal funciona, usando uma pasta temporária:

- Linhas 831–838: configuração falsa mínima (logs na pasta temporária, banco desligado).
- Linhas 839–847: perguntas de teste (PROCX, texto sem sentido, amostra), ideias, e um histórico de um arquivo para testar o boletim.
- Linhas 848–853: testa a regra de contratação da Helena: júnior em habilidade de risco alto é barrado; de risco baixo, aprovado.
- Linhas 855–865: o resultado: Nina encaminha Excel ao Ricardo e diz "não entendi" para "asdf"; Iara propõe ligar o banco e toda ideia tem motivo e primeiro passo; amostra 5% em 2.000 = 323; boletim com números certos.

**Erros que este arquivo evita**
- Responder com "chute": sem pontuação suficiente, diz que não entendeu.
- Inventar números: status, erros, sprint e boletim vêm do histórico real.
- Mensagens perdidas ou com número repetido (trava e gravação segura).
- Uma linha corrompida derrubar o canal inteiro.
- Inundar o canal com o passado ao ligá-lo pela primeira vez.
- Calcular amostra "de cabeça": a fórmula com correção para população finita é aplicada.

---

## robo/calculos.py

- **Para que serve**: é a calculadora do canal. Você pede em português ("nps por região onde canal = App", "soma de vendas por região e canal", "quais colunas tem a base nps") e ela encontra a base publicada, as colunas (mesmo com nome aproximado), aplica filtros, agrupa e calcula — tudo local, sobre Bases-Tratadas.
- **Onde entra no fluxo**: é chamada por `canal.responder` (linhas 623–631 do `canal.py`) antes dos verbetes. Se a mensagem não for um pedido de cálculo, devolve `None` e o canal segue o roteamento normal.

### Cabeçalho (linhas 1–14)

Exemplos de pedidos e o "dicionário" de entendimento: operação, `de <coluna>`, `por <coluna> [e <coluna>]`, `onde <coluna> =/>/< <valor>` e `na base <nome>`.

### Imports (linhas 16–26)

`difflib` (compara textos parecidos e tolera erro de digitação), `math`, `re`, `Path`, pandas, `historico`, `normalizar_nome_coluna` e `sem_acento`.

### OPERACOES (linhas 28–42)

Lista **em ordem de prioridade**: correlação, mediana, desvio, média, soma, mínimo, máximo, distintos, percentual, contagem, NPS, CSAT. Cada uma tem palavras que a disparam e quem responde. Média/soma vêm antes de NPS de propósito: em "média de nota nps", o pedido é média e "nps" é parte do nome da coluna. "Mediana" vem antes de "média" para "mediana" não ser lida como "média".

### _CACHE (linha 43)

Memória das tabelas já lidas (não relê o Excel a cada pergunta).

### _norm (linhas 46–47)

Sem acento, minúsculas, espaços simples.

### bases_publicadas (linhas 51–70)

- Linhas 55–57: percorre o histórico do mais recente para o mais antigo, só sucessos.
- Linhas 58–61: dá o nome de base (`chave_base`); se a base já foi vista, fica com a versão mais recente.
- Linhas 62–66: pega os arquivos de saída `.xlsx`/`.csv` da execução (ou, em execuções antigas, monta o caminho em Bases-Tratadas pelo nome).
- Linhas 67–69: só conta se o arquivo ainda existe.

### carregar_base (linhas 73–92)

- Linhas 75–77: o primeiro arquivo da base; a chave do cache inclui a data de modificação (se o arquivo mudar, relê).
- Linhas 79–80: CSV: detecta o separador sozinho.
- Linhas 82–85: Excel: lê todas as abas e escolhe a **fato** (a primeira aba que não é `dim_`, `dicionario_dados` nem `log_qualidade`).
- Linhas 86–89: junta (como um PROCX em massa, `merge`) cada dimensão `dim_` (menos calendário) cuja primeira coluna existe na fato — assim dá para segmentar por curso, região etc.
- Linhas 90–92: limpa o cache se passar de 20 tabelas; devolve a tabela e o nome do arquivo.

### _achar_coluna (linhas 96–106)

Encontra a coluna citada:
- Linhas 97–101: normaliza ("Região" → `regiao`) e tenta igual.
- Linhas 102–104: tenta "contém" (em qualquer direção) e escolhe a de tamanho mais parecido: `regiao` acha `regiao_cliente`.
- Linhas 105–106: tenta parecida com 70% de semelhança (erro de digitação: `regaio`).

### _valor (linhas 109–114)

Converte o valor de um filtro: se parece número ("1.000", "8", "7,5"), vira número; senão, fica texto sem aspas.

### interpretar (linhas 117–152) — como o pedido é entendido

- Linhas 118–124: procura "na/da/do/no/em base|arquivo|planilha X"; acha a base mais parecida (60%) e **remove esse trecho** do texto (para "nps" no nome da base não ser lido como pedido de NPS).
- Linhas 125–131: acha a **operação**: a primeira de `OPERACOES` cuja palavra aparece como palavra inteira. Sem operação → não é cálculo.
- Linha 132: estrutura do pedido: operação, autor, base, métrica, por, filtros.
- Linhas 133–140: **filtros**: tudo depois de "onde", "quando", "com", "para" ou "filtrando". Separa várias condições por " e ". Cada condição é `coluna sinal valor`, com sinais `>=`, `<=`, `!=`, `=`, `>`, `<` ou por extenso ("igual a", "maior que", "menor que", "diferente de"). Remove o trecho do texto.
- Linhas 141–144: **agrupamento**: tudo depois de "por", separado por " e " ou vírgula. Remove o trecho.
- Linhas 145–151: **métrica**: na correlação, "entre A e B"; senão, o que vem depois de "de/do/da/dos/das".

**Exemplo — "nps por região onde canal = App"**:
1. Normalizado: `nps por regiao onde canal = app`.
2. Sem "na base …".
3. Operação: nenhuma das anteriores aparece; "nps" aparece → op = **nps**, quem responde = Caio (`analise_indicadores`).
4. Filtro: `canal = app` → (`canal`, `=`, `app`). Sobra `nps por regiao`.
5. Por: `regiao`. Sobra `nps`.
6. Métrica: não há "de …" → vazia (o NPS vai achar a coluna sozinho).
7. Resultado: `{op: nps, por: [regiao], filtros: [(canal, =, app)], metrica: []}`.

### _fmt (linhas 156–161)

Formata número no padrão brasileiro com 2 casas: 1234.5 → "1.234,50". Vazio → "—".

### _nps (linhas 164–170)

Mesmo NPS do `analise.py`: NPS, n e margem 95% (`100 × 1,96 × √((p + d − (p − d)²)/n)`). O `max(…, 0)` protege contra arredondamento negativo.

### _csat (linhas 173–178)

CSAT top-2-box pela escala detectada (5/7/10) e o n.

### calcular (linhas 181–274) — como o pedido é calculado

- Linhas 183–189: "quais bases existem" → lista as bases com o último arquivo e data.
- Linhas 190–193: "quais colunas…" é tratado à parte; senão interpreta; se não é cálculo, devolve `None`.
- Linhas 194–196: sem base publicada → avisa.
- Linhas 197–201: base pedida (ou, em "quais colunas tem a base X", a parecida com 50%).
- Linhas 202–203: base pedida não existe → lista as que existem.
- Linhas 204–217: **sem base no pedido**: percorre da mais recente para a mais antiga e escolhe a primeira que tem **todas** as colunas citadas (e, para NPS/CSAT sem métrica, uma coluna de indicador). Se nenhuma tem, explica.
- Linhas 218–223: carrega a base; ignora colunas de auditoria (`_`); responde "quais colunas" com o tipo de cada uma.
- Linhas 225–232: acha as colunas de métrica e de "por"; o que não achar vai para `nao_achei`.
- Linhas 233–249: aplica cada **filtro**: número contra coluna numérica usa a comparação pedida; texto compara sem acento e sem maiúsculas (igual ou diferente). Guarda a descrição do filtro.
- Linhas 250–254: coluna não encontrada → sugere as 2 mais parecidas e lista as disponíveis.
- Linhas 256–258: NPS/CSAT sem métrica → acha a coluna pelo nome (`_coluna_indicador`).
- Linhas 259–261: operação numérica sem coluna → pergunta "De qual coluna?" e lista as numéricas.
- Linhas 262–267: coluna de texto em operação numérica → explica e sugere contagem/percentual.
- Linhas 268–269: filtro não deixou nenhuma linha → avisa.
- Linhas 271–274: executa e monta o texto: título — "Base X (arquivo), N linha(s), filtro: …" e a tabela.

**Continuação do exemplo**: a base mais recente com `regiao` e `canal` e uma coluna de NPS é escolhida. Filtra as linhas com `canal` igual a "app" (sem diferenciar maiúsculas). Acha `nota_nps`. Agrupa por `regiao` e devolve algo como:
```
NPS de nota_nps por regiao — Base nps (nps_outubro.xlsx), 812 linha(s), filtro: canal = app.
Sudeste: 42,10 (±6,30, n=410)
Sul: 35,00 (±9,80, n=200)
Norte: 18,18 (±31,20, n=22) ⚠ base pequena
```

### _coluna_indicador (linhas 277–281)

Primeira coluna numérica com "nps"/"recomend" (para NPS) ou "csat"/"satisf"/"atendimento" (para CSAT) no nome, que não comece com `id_` ou `_`.

### _milhar (linhas 284–285) e _tipo (linhas 288–293)

Milhar com ponto; tipo legível da coluna (data, número, texto).

### _executar (linhas 296–346)

- Linhas 297–298: coluna principal e lista de linhas do resultado.
- Linhas 299–306: **correlação** de Pearson entre duas colunas, com força (≥ 0,7 forte; ≥ 0,4 moderada; ≥ 0,2 fraca; abaixo, praticamente nenhuma), o lembrete "correlação não prova causa" e o n.
- Linhas 308–321: função interna `calc` que calcula a operação num pedaço da tabela: NPS (com margem, n e "⚠ base pequena" se n < 30), CSAT, contagem de linhas, distintos, ou média/mediana/soma/mínimo/máximo/desvio.
- Linhas 323–325: nome amigável da operação.
- Linhas 326–336: **percentual**: com "por" e coluna, faz uma tabela cruzada (% de cada valor da coluna dentro de cada grupo, até 15 grupos); senão, a distribuição % da coluna (até 15 valores, incluindo vazios).
- Linhas 337–339: título; sem "por", calcula no total.
- Linhas 340–346: com "por", agrupa, ordena os grupos do maior para o menor, mostra até 15 ("… e mais N grupo(s)").

**Erros que este arquivo evita**
- Calcular sobre base não conferida: só usa Bases-Tratadas.
- Ler "nps" no nome da base como pedido de NPS, ou "média de nota nps" como NPS.
- Responder com coluna errada em silêncio: se não acha, diz e sugere as parecidas.
- Fazer média de texto: explica e sugere contagem/percentual.
- Mostrar NPS de grupo pequeno sem aviso.

---

## robo/central.py

- **Para que serve**: monta os números da tela "Central de dados" do painel: quantos arquivos chegaram, foram aprovados ou barrados, por quê e por quem, a tendência dos últimos 14 dias e um resumo por andar (engenharia, análise, Sala Excel, governança, TI).
- **Onde entra no fluxo**: o painel chama `central.montar(cfg, dias)` (`robo/painel/servidor.py` linha 512) a cada atualização (a cada 3 segundos). Só lê: `logs/historico.csv`, `logs/execucoes/<id>.json` e `logs/analises/*.json`.

### Cabeçalho e imports (linhas 1–14)

Docstring explicando as fontes e o cache; imports de `json`, `re`, datas, `Path` e `historico`.

### _num_br (linhas 17–22)

Igual ao do `canal.py`: número com vírgula decimal → número.

### _CACHE (linha 24)

Guarda o resumo de cada execução já lida (o painel atualiza a cada 3 s; sem cache, releria centenas de arquivos).

### _resumo_execucao (linhas 27–52)

- Linhas 28–30: se já está no cache, devolve; senão lê o detalhe da execução.
- Linhas 31–34: separa ERROS e AVISOS; o motivo principal é o primeiro erro.
- Linhas 35–39: **quem barrou**, pela mensagem do erro: Supervisor, DBA, Equipe, Coordenadora, Leitura (arquivo aberto, codificação, sem aba com dados) ou Auditoria (regras).
- Linhas 40–49: monta o resumo: nº de erros e avisos, motivo, quem barrou, até 3 exemplos, manchete e base da análise, nº de ressalvas, conferências Excel e se a revisão Excel passou, achados de cada pessoa do quadro, até 3 avisos.
- Linhas 50–52: só guarda no cache se a execução foi encontrada.

### _janela (linhas 55–56)

Data inicial do período: para `dias = 7`, hoje menos 6 dias (hoje conta).

### montar (linhas 59–139)

- Linha 60: limita o período a 1–90 dias.
- Linhas 61–65: execuções no período, aprovadas e reprovadas; função `soma`.
- Linhas 67–74: **série diária** dos últimos 14 dias (aprovados e reprovados por dia), sempre, para mostrar tendência.
- Linhas 76–85: resumo de até 500 execuções; conta os **motivos** (números viram "N" para agrupar) e **quem barrou**.
- Linhas 87–93: por pessoa do quadro: quantas conferências fez e quantos achados.
- Linhas 95–97: até 15 análises com manchete.
- Linha 98: alertas de monitoramento do período.
- Linha 99: entregas Excel com conferências.
- Linhas 100–104: última ronda da TI (se falhar, vazio).
- Linha 105: achados de LGPD (dados pessoais) da pessoa `gov_pleno_lgpd`.
- Linhas 107–115: **totais**: recebidos, aprovados, reprovados, adiados, taxa de aprovação (%), linhas publicadas e removidas, avisos, erros e tempo médio.
- Linhas 116–123: série, até 25 erradas (com motivo e exemplos), 15 acertos, 8 motivos mais frequentes, ranking de quem barrou.
- Linhas 124–135: **áreas** 1 a 5: engenharia, análise (bases analisadas, com ressalva, alertas), Sala Excel (entregas, conferências, divergências), governança (dados pessoais) e TI (saudável, última ronda, até 5 alertas).
- Linhas 136–138: pessoas ordenadas por andar e por mais achados; análises; até 10 alertas.

**Exemplo de taxa e tempo médio**: no período, 50 recebidos e 46 aprovados → taxa = 100 × 46/50 = 92,0%. Se os 46 aprovados somam 552 segundos, tempo médio = 12,0 s.

### _alertas_monitoramento (linhas 142–155)

- Linhas 143–145: lista os JSON de análise (`logs/analises/2*.json`, ou seja, os nomeados pelo id da execução — o histórico de fotos, `historico_*.json`, fica de fora), do mais novo para o mais antigo, até 100.
- Linhas 146–147: ao chegar num arquivo anterior ao período, para.
- Linhas 148–151: lê o JSON (corrompido é pulado).
- Linhas 152–154: guarda só os alertas de nível "atenção", com base, arquivo e mensagem.

**Erros que este arquivo evita**
- Painel lento por reler centenas de arquivos a cada 3 segundos (cache).
- Mesmo motivo de erro aparecendo como dezenas de motivos diferentes só porque muda o número da linha.
- Um JSON corrompido ou a TI fora do ar derrubarem a tela inteira.
- Período absurdo (0 ou 10.000 dias) travar o painel.

---

## conhecimento/boas_praticas.md (resumo)

Manual de boas práticas da "empresa", lido pelo canal (`_secoes_markdown` corta em seções por título; a Nina cita a seção que melhor bate com sua pergunta). Seções:

- **Princípios**: certo antes de rápido (quatro olhos), nada some em silêncio, erro é informação, honestidade com o dono, tudo local.
- **Engenharia (ingestão e estrutura)**: só processar arquivo parado (OneDrive), nunca alterar o original, rastrear arquivo/aba/linha, tratar `#REF!`/`#DIV/0!`/`#N/D` como erro, achar o cabeçalho real, cabeçalho em duas linhas, mescladas, abas iguais empilhadas, sinônimos declarados.
- **Qualidade (limpeza e validação)**: nomes padronizados, números e datas em vários formatos, códigos como texto, tirar linhas de total, chave de duplicidade, regras no `config.yaml`, qualquer erro reprova o arquivo inteiro, conciliação de linhas.
- **Power BI e banco**: modelo estrela, 1 para muitos, integridade referencial, calendário, medidas DAX; camadas bruto/tratado/analítico, uma transação por arquivo, reconciliação antes do commit, senha em variável de ambiente.
- **Análise e pesquisa**: indicador sempre com n e margem; base mínima 30 (30–100 = tendência); Holm; significativo ≠ importante; correlação ≠ causa; NPS/CSAT/CES; escala escrita vira nota 1–5; não ponderar sem plano; boas práticas de questionário.
- **Trade, Excel, visualização, ciência de dados, LGPD e operação**: share no mesmo recorte; preço médio = faturamento ÷ unidades; fórmula viva e aba Conferência; PROCX; leitura em Z; evitar pizza com mais de 3 fatias; treino/teste separados; dados pessoais só quando necessário; texto com "=" nunca vira fórmula; sprint de 15 dias e regras de promoção.

## conhecimento/glossario_pesquisa.md (resumo)

Glossário curto com três verbetes, também lidos pelo canal:

- **Base mínima de respostas**: nada de segmento com menos de 30 respostas; entre 30 e 100, tendência; acima de 100, margem do NPS perto de ±10 pontos.
- **Ponderação de amostra**: dar pesos para a amostra parecer com a população; só com plano definido antes da coleta, informando base ponderada e não ponderada.
- **Top-2-box**: % nas duas notas mais altas da escala (ex.: 4 e 5 de 1 a 5); forma padrão de reportar CSAT.
