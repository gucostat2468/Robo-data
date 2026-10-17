# Parte 2 — Banco de dados PostgreSQL (ELT), consultas e backup

Neste projeto, **ELT** quer dizer *Extract, Load, Transform* (Extrair, Carregar, Transformar), nessa ordem. O robô **extrai** os dados das planilhas, **carrega** tudo no PostgreSQL (primeiro a cópia fiel, na camada `bruto`, depois a versão limpa e com tipos certos, na camada `tratado`) e só então a **transformação de negócio** acontece **dentro do banco**, em SQL, na camada `analitico` (pasta `modelos_sql/`). É diferente do ETL clássico, em que tudo seria transformado antes de entrar no banco. A vantagem para você, analista: a regra do NPS, do churn etc. fica escrita uma única vez no banco, e o Power BI, o Excel e o Python passam a ler o mesmo número. Além disso, o original fica guardado no `bruto`, e assim você consegue refazer qualquer cálculo sem precisar da planilha.

> **Glossário rápido (termos que vão aparecer sempre)**
> - **PostgreSQL**: o programa de banco de dados (o "servidor") onde as tabelas ficam guardadas.
> - **Banco de dados** (*database*): um "arquivo lógico" dentro do PostgreSQL. Aqui ele se chama `robo_dados` por padrão.
> - **SQL**: a linguagem usada para conversar com o banco ("me dê as linhas tal", "crie a tabela tal").
> - **Schema**: uma "pasta" dentro do banco que agrupa tabelas. Aqui temos `bruto`, `tratado`, `analitico` e `robo`.
> - **Tabela**: uma planilha que mora no banco, com colunas de tipo fixo (número, data, texto).
> - **View (visão)**: uma "consulta salva com nome". Ela não guarda dados; toda vez que alguém lê a view, o SQL dela roda de novo sobre as tabelas.

---

## robo/banco.py

- **Para que serve**: é o "almoxarifado" do robô. Recebe as tabelas já limpas pelo pipeline e grava no PostgreSQL em camadas: o original em `bruto`, o tratado em `tratado`, e roda os seus modelos SQL em `analitico`. Também anota cada carga numa tabela de controle (`robo.lotes`) e cada erro/aviso em `robo.ocorrencias`, que alimentam o painel e as consultas de monitoramento. Tudo isso é feito com regras de segurança: nada é apagado com DROP, cada arquivo entra inteiro ou não entra, e a contagem de linhas é conferida antes de confirmar.
- **Onde entra no fluxo**:
  - **Quem chama**: principalmente `robo/pipeline.py`, na função `_carregar_banco` (linhas 211–248 daquele arquivo), que, dentro de uma transação, chama `criar_banco_se_preciso`, `conectar`, `inicializar`, `carregar_bruto`, `carregar_tratado`, `reconciliar`, `executar_modelos` e `registrar_lote`. Também usam a classe `Banco`: o painel (`robo/painel/servidor.py`: `resumo`, `testar`, `executar_modelos`, `pasta_modelos`), a linha de comando (`robo/comandos.py`, função `_comando_banco`), `robo/consultas.py` (via `conectar`), `robo/backup.py` (via `_parametros` e `conectar`), `robo/analise.py`, `robo/ti.py` e um teste em `robo/rh.py` (que testa `reconciliar` com uma conexão falsa).
  - **Quem ele chama**: a biblioteca `psycopg` (o "driver", isto é, o programa que fala com o PostgreSQL), `robo/limpeza.py` (`_texto_de`, `normalizar_nome_coluna`) e `robo/modelagem.py` (`tabela_calendario`).

### Docstring do módulo (linhas 1–16)

- Linhas 1–9: o texto explica a **arquitetura medalhão**, o nome de mercado para organizar dados em camadas de qualidade crescente:
  - `bruto`: o dado **exatamente** como veio, tudo como texto, mais a linha de origem. Recebe até os arquivos reprovados, para servir de auditoria.
  - `tratado`: o resultado da limpeza, com tipos corretos (número, data...).
  - `analitico`: as views e tabelas que **você** escreve em SQL. É o "T" do ELT.
  - `robo`: o schema de controle, com a tabela `lotes`.
- Linhas 11–15: as três regras de segurança. (1) Tudo de um arquivo acontece numa **transação**, um "pacote" de comandos que o banco trata como uma coisa só: ou todos valem, ou nenhum vale. (2) Tabelas nunca levam DROP (o comando que apaga a tabela inteira, com estrutura). Colunas novas são adicionadas e tipos só são "alargados". (3) Reprocessar o mesmo arquivo não duplica dados (modo `por_arquivo`).

### Imports (linhas 18–33)

- Linha 18: `from __future__ import annotations` permite escrever dicas de tipo modernas (`str | None`) em versões mais antigas do Python.
- Linhas 20–25: bibliotecas padrão. `json` transforma listas e dicionários em texto JSON, `logging` escreve no log, `math` serve para checar `NaN` ("não é número", o vazio dos números no pandas), `date`/`datetime` são datas, `Decimal` é número decimal exato e `Path` são caminhos de pastas. Observação: `date` e `Decimal` são importados, mas não são usados neste arquivo.
- Linhas 27–28: `numpy` e `pandas`, as bibliotecas de tabelas em memória (o `DataFrame` é a "planilha" do pandas).
- Linhas 30–31: funções do próprio robô. `_texto_de` converte qualquer valor em texto sem o ".0" que o Excel põe em inteiros. `normalizar_nome_coluna` transforma "Data de Admissão" em `data_de_admissao`. `tabela_calendario` gera a dimensão de datas.
- Linha 33: `log` é o "caderno de anotações" do robô (o logger chamado `"robo"`).

### Constantes (linhas 35–43)

- Linha 35: `MODOS_CARGA` lista os quatro jeitos de gravar no `tratado`:
  - `por_arquivo`: apaga o que veio antes **deste mesmo arquivo** e grava de novo.
  - `substituir`: esvazia a tabela inteira e grava.
  - `mesclar`: apaga só as linhas cujas **chaves** chegaram de novo e grava. Uma **chave** é a coluna (ou o conjunto de colunas) que identifica uma linha de forma única, como `id_resposta`.
  - `anexar`: só acrescenta, sem apagar nada.
- Linhas 37–43: `ALARGAMENTOS` é a tabela de "promoções de tipo" permitidas. `bigint` é o inteiro grande do PostgreSQL, `double precision` é o número com casas decimais, `date` é a data e `timestamp without time zone` é a data com hora. Exemplo: em janeiro a coluna `valor` veio só com inteiros (`bigint`) e em fevereiro veio com centavos (`double precision`). O banco "alarga" a coluna para decimal, sem perder nada. O caminho contrário (decimal virar inteiro) não é feito: o par `("double precision", "bigint")` também resulta em `double precision`, ou seja, a coluna continua decimal.

### ErroBancoIndisponivel (linhas 46–47)

- É um tipo de erro próprio (**exceção** é o jeito do Python de avisar "deu problema"). Ele representa um problema **temporário**: banco desligado, senha errada, rede fora. O pipeline captura esse erro (pipeline.py, linha 313) e **adia** o arquivo, que espera e é tentado de novo depois, em vez de ser reprovado. Faz sentido: a planilha não tem culpa se o servidor está fora do ar.

### ErroBancoNaoExiste (linhas 50–51)

- É um caso particular do erro anterior, porque "herda" dele: o PostgreSQL está no ar, mas o banco `robo_dados` ainda não foi criado. Ele existe separado porque `criar_banco_se_preciso` precisa distinguir "não existe, então eu crio" de "está fora do ar, então espero".

### ErroCargaDados (linhas 54–55)

- Representa um problema **nos dados ou na estrutura**, por exemplo texto numa coluna que no banco é numérica. Nesse caso o arquivo é **reprovado** (não adianta tentar de novo: a planilha precisa ser corrigida).

### _psycopg (linhas 58–64)

- Linhas 58–62: importa o `psycopg` e o submódulo `sql` (que monta comandos SQL com nomes protegidos) **só quando precisa**. Assim, quem não usa banco não precisa ter a biblioteca instalada.
- Linhas 63–64: se a biblioteca não estiver instalada, levanta `ErroBancoIndisponivel` com uma instrução prática ("Rode instalar.bat novamente"). O arquivo é adiado, e não reprovado.

### tipo_pg (linhas 67–77)

Esta função descobre qual tipo de coluna do PostgreSQL combina com uma coluna do pandas.
- Linhas 68–69: verdadeiro/falso vira `boolean`.
- Linhas 70–71: inteiro vira `bigint` (inteiro de 64 bits, que comporta números enormes; por isso o robô escolhe sempre o maior, para não estourar com CPFs ou IDs longos).
- Linhas 72–73: número com casas decimais vira `double precision`.
- Linhas 74–76: datas. Se **todas** as datas preenchidas estiverem à meia-noite (`v == v.dt.normalize()`), a coluna vira `date` (só a data). Se alguma tiver hora, vira `timestamp without time zone`. Exemplo: `15/03/2026` vira `date`, e `15/03/2026 14:32` vira `timestamp`. Uma coluna de datas totalmente vazia também vira `date`.
- Linha 77: todo o resto vira `text`.

### _valor_pg (linhas 80–98)

Converte cada célula do pandas para um valor que o `psycopg` sabe enviar ao banco. Isso é necessário porque o pandas usa tipos próprios (`numpy.int64`, `NaT`, `NA`) que o driver não reconhece.
- Linhas 82–85: qualquer tipo de vazio (`None`, `pd.NA`, `pd.NaT`, `NaN`) vira `None`, que no banco é `NULL` (célula vazia).
- Linhas 86–91: números e booleanos do numpy viram os equivalentes do Python puro (`float`, `int`, `bool`).
- Linhas 92–95: datas. Se a coluna no banco for `date`, a hora é descartada (`.date()`). Se for `timestamp`, a data/hora é mantida. É aqui que o "tipo final" devolvido por `_garantir_tabela` importa: se a coluna foi alargada para `timestamp`, as datas novas são enviadas como data e hora.
- Linhas 96–97: se a coluna é texto, mas o valor não é texto (por exemplo, o número `123.0`), ele é convertido por `_texto_de` (vira `"123"`).
- Linha 98: os demais valores passam como estão.

### class Banco (linhas 101–499)

É a classe (o "molde" de um objeto com dados e funções) que concentra tudo o que o robô faz no PostgreSQL. A cada arquivo, o pipeline cria um `Banco` novo (pipeline.py, linha 216).

### Banco.__init__ (linhas 102–107)

- Linha 103: guarda a seção `banco:` do `config.yaml` em `self.cfg`.
- Linhas 104–105: define os nomes dos schemas. Por padrão são `bruto`, `tratado`, `analitico` e, para a chave `controle`, o schema `robo`. O trecho `**(cfg_banco.get("schemas") or {})` permite trocar esses nomes no config (o que vier no config sobrescreve o padrão).
- Linhas 106–107: descobre a pasta dos modelos SQL (padrão `modelos_sql`). Se o caminho não for absoluto, ele é considerado a partir da pasta do projeto.

### Banco.habilitado (linhas 109–111)

- É uma **propriedade**: lê-se como um campo (`banco.habilitado`), mas é calculada na hora. Devolve `True` se `habilitado: true` estiver no config.

### Banco._parametros (linhas 114–128)

Monta o "endereço" de conexão.
- Linhas 115–119: a senha vem do config. Se existir `senha_variavel_ambiente` e essa variável de ambiente do Windows estiver preenchida, a senha da variável tem prioridade. Assim você não precisa deixar a senha escrita no arquivo.
- Linhas 120–128: devolve um dicionário com servidor (`localhost`), porta (`5432`, a padrão do PostgreSQL), nome do banco (padrão `robo_dados`, ou o recebido no parâmetro `banco`), usuário (`postgres`), senha, tempo máximo para conectar (5 segundos, para o robô não ficar travado esperando) e `application_name`, que faz o robô aparecer com o nome `robo_planilhas` nas ferramentas de monitoramento do PostgreSQL.

### Banco.conectar (linhas 130–138)

- Linhas 131–133: abre uma **conexão** (o "telefonema" aberto entre o Python e o banco) com os parâmetros acima.
- Linhas 134–137: se a conexão falhar, a mensagem do PostgreSQL é examinada, em inglês ou em português. Se ela disser que o banco não existe, o erro levantado é `ErroBancoNaoExiste`. Caso contrário, é `ErroBancoIndisponivel`.
- Linha 138: a mensagem técnica é traduzida para uma frase amigável por `_explicar_erro_conexao` (linhas 502–513).

### Banco.criar_banco_se_preciso (linhas 140–153)

- Linhas 143–146: tenta conectar no banco do robô. Se conseguir, ele já existe, e a função devolve `False` ("não precisei criar").
- Linhas 147–148: se o erro for "não existe", segue em frente. Qualquer outro erro (senha, servidor desligado) sobe para quem chamou.
- Linhas 149–151: conecta no banco `postgres`, que **sempre existe** numa instalação do PostgreSQL, liga o `autocommit` e roda `CREATE DATABASE`. O `autocommit` é necessário porque o PostgreSQL não aceita criar um banco dentro de uma transação. **Commit** é a confirmação definitiva de uma transação, e `autocommit` significa "cada comando se confirma sozinho". `sql.Identifier(nome)` coloca o nome entre aspas de forma segura, o que impede que um nome estranho "quebre" o comando.
- Linhas 152–153: registra no log e devolve `True`.

### Banco.inicializar (linhas 155–186)

Garante que a estrutura mínima existe. Pode ser chamada várias vezes sem efeito colateral, graças ao `IF NOT EXISTS`.
- Linhas 157–158: cria os quatro schemas, se ainda não existirem.
- Linhas 159–172: cria `robo.lotes`, com **uma linha por carga** (lote). Colunas: `lote_id` (o identificador da carga, que no pipeline é o nome que o arquivo terá no arquivo morto), `arquivo`, `status` (`sucesso`/`reprovado`), `processado_em`, as contagens de linhas, erros e avisos, `tabelas` (uma lista de textos, `text[]`), `mensagem` e `ocorrencias` (`jsonb`, um campo que guarda JSON). `lote_id` é a **chave primária** (*PRIMARY KEY*): a coluna que não pode se repetir nem ficar vazia, e que identifica cada linha. `timestamptz` é data/hora com fuso. `DEFAULT now()` preenche sozinho com o momento da gravação.
- Linhas 173–186: cria `robo.ocorrencias`, com **uma linha por erro ou aviso** (nível, tabela, coluna, mensagem, quantidade, exemplos). Por que duplicar o que já está no `jsonb` de `lotes`? Porque, com uma linha por ocorrência, a pergunta "quais erros mais se repetem?" vira um `GROUP BY` simples (veja a consulta `02_erros_mais_frequentes.sql`).

### Banco.testar (linhas 188–197)

Usada pelo botão "testar conexão" do painel e pelo comando `testar`.
- Linhas 190–193: cria o banco se precisar, conecta, inicializa a estrutura e pergunta a versão do servidor (`SHOW server_version`). Detalhe: ao sair do `with`, o psycopg confirma (*commit*) a transação, e por isso os schemas criados ficam gravados.
- Linhas 194–195: devolve `ok: True`, a versão, se o banco foi criado agora e uma mensagem amigável.
- Linhas 196–197: em caso de problema de conexão, devolve `ok: False` com a explicação, sem derrubar o painel.

### Banco._colunas_existentes (linhas 200–204)

- Linhas 201–204: consulta o `information_schema`, o "catálogo" do próprio PostgreSQL que descreve todas as tabelas e colunas, e devolve `{nome_da_coluna: tipo}` de uma tabela, na ordem das colunas. Se a tabela não existir, o resultado é um dicionário vazio. Os `%s` são **parâmetros**: os valores vão separados do comando, e o banco nunca os confunde com SQL.

### Banco._garantir_tabela (linhas 206–238)

Este é o coração da regra "nunca DROP". A função cria a tabela ou adapta a que já existe, e devolve os tipos finais de cada coluna.
- Linhas 209–210: lê as colunas atuais e prepara o nome completo `schema.tabela`.
- Linhas 211–214: se a tabela não existe, monta `CREATE TABLE tabela (col1 tipo1, col2 tipo2, ...)` e devolve os tipos pedidos.
- Linha 215: parte dos tipos que já existem no banco.
- Linhas 216–221: para cada coluna do arquivo, se ela **não existe** no banco, roda `ALTER TABLE ... ADD COLUMN` e anota no log. Exemplo: a planilha de março ganhou a coluna "Unidade". A coluna é criada, e as linhas antigas ficam com ela vazia.
- Linhas 222–223: se o tipo é igual ao do banco, ou se a coluna do banco é `text` (texto aceita qualquer coisa), não há nada a fazer.
- Linhas 224–233: se o par (tipo atual, tipo novo) está em `ALARGAMENTOS`, altera o tipo da coluna (`ALTER COLUMN ... TYPE`) quando o novo for diferente do atual. Se o banco recusar (o motivo mais comum é uma view em `analitico` depender da coluna), levanta `ErroCargaDados` com essa dica.
- Linhas 234–237: qualquer outra combinação é um **conflito real**. Exemplo: no banco, `nota_nps` é `bigint`, e no arquivo novo veio `text` porque alguém digitou "dez". O arquivo é reprovado, com a sugestão de corrigir a planilha ou forçar o tipo com `tipos:` no `config.yaml`.
- Linha 238: devolve os tipos finais. Eles são usados por `_valor_pg` para converter cada valor corretamente.

### Banco._copiar (linhas 240–251)

Grava um DataFrame inteiro com **COPY**, o comando de carga em massa do PostgreSQL. Em vez de mandar um `INSERT` (o comando que insere uma linha) para cada linha, o COPY abre um "cano" e despeja todas as linhas de uma vez. Para 100 mil linhas, isso é dezenas de vezes mais rápido.
- Linhas 242–243: tabela vazia não grava nada e devolve 0.
- Linhas 244–246: monta `COPY schema.tabela (col1, col2, ...) FROM STDIN` (`STDIN` quer dizer "os dados vêm pelo cano, enviados pelo Python").
- Linha 247: pega o tipo de cada coluna (o padrão é `text`).
- Linhas 248–250: abre o cano e escreve linha a linha, convertendo cada célula com `_valor_pg`. O `astype(object)` evita que o pandas converta os valores de novo.
- Linha 251: devolve quantas linhas foram enviadas.

### Banco._apagar (linhas 253–255)

- Linha 255: roda `DELETE FROM schema.tabela WHERE <condição>` com parâmetros. Exemplo de uso: `_arquivo_origem = %s`, para apagar as linhas que vieram do mesmo arquivo. Este é o mecanismo do "reprocessar não duplica".

### Banco.carregar_bruto (linhas 258–286)

Grava a cópia fiel (tudo em texto) de cada aba em `bruto.<base>` (ou `bruto.<base>_<aba>`, quando há várias abas).
- Linhas 260–263: prepara o schema, a lista de tabelas gravadas e o dicionário `esperado_bruto` (quantas linhas cada tabela **deveria** receber, usado depois na reconciliação), e verifica se há mais de uma aba.
- Linha 265: com várias abas, o nome da tabela vira `base_nomedaaba` normalizado. Com uma só, vira apenas `base`.
- Linhas 266–272: normaliza os nomes das colunas e evita duplicados (uma segunda coluna `nome` vira `nome_x`). A condição `n.startswith("_")` existe para que uma coluna da planilha não colida com as colunas de controle do robô, que começam com `_` (veja o defeito relatado no final deste guia).
- Linha 273: converte **cada célula em texto** (vazios viram `NULL`). Por que tudo texto? Porque o bruto é a prova do que chegou: se "01/02/2026" foi digitado assim, é assim que ele fica, sem interpretação.
- Linhas 274–278: acrescenta as colunas de auditoria. `_linha_origem` é o número da linha na planilha (índice do DataFrame), e as demais são `_aba`, `_arquivo_origem`, `_lote_id` e `_carregado_em` (momento da gravação).
- Linhas 279–281: todas as colunas são `text`, exceto `_linha_origem` (`bigint`) e `_carregado_em` (`timestamp`). Depois, a tabela é criada ou adaptada.
- Linha 282: apaga o que já existia **deste mesmo arquivo** no bruto, para que um reenvio não duplique.
- Linhas 283–285: grava com COPY, anota quantas linhas eram esperadas e registra o nome da tabela gravada.
- Linha 286: devolve a lista, por exemplo `["bruto.pesquisa_nps"]`.

### Banco.carregar_tratado (linhas 288–347)

Grava as tabelas limpas, com tipos certos, no schema `tratado`. Quando existe um modelo estrela, ela também cuida das **dimensões** (tabelas de cadastro, como `dim_curso`) e dos **fatos** (tabelas de eventos, como `fato_nps`).
- Linhas 290–293: escolhe o modo de carga. A ordem de prioridade é `destino.modo` da regra, depois `modo_carga_padrao` do config e, por fim, `por_arquivo`. Um modo desconhecido reprova o arquivo.
- Linha 294: lê a lista de colunas-chave (usada no modo `mesclar`), com os nomes normalizados.
- Linha 295: lê do modelo quais tabelas são dimensões (`dimensoes:`).
- Linhas 297–300: copia as tabelas (para não mexer no original do pipeline) e zera os registros de controle: as linhas esperadas no tratado e a lista de **chaves estrangeiras**. Uma chave estrangeira é a coluna de um fato que aponta para a chave de uma dimensão (por exemplo, `fato_nps.id_curso` aponta para `dim_curso.id_curso`).
- Linhas 302–311: **passo 1, dimensões.** Para cada dimensão, `_mesclar_dimensao` grava só os membros novos e devolve um "de-para" `{id_do_arquivo: id_definitivo}`. Em seguida, em cada outra tabela que tenha a coluna-chave da dimensão (a primeira coluna dela), os ids do arquivo são trocados pelos ids definitivos. O tipo `Int64` é um inteiro que aceita vazio. Por que isso é necessário? Exemplo: no arquivo de março, "Direito" recebeu o id 1, mas no banco "Direito" já é o id 7 desde janeiro. Sem a troca, o fato de março apontaria para o curso errado. Assim, "o mesmo curso mantém o mesmo id para sempre" (comentário da linha 302).
- Linhas 312–314: a dimensão de calendário recebe tratamento próprio (`_mesclar_calendario`).
- Linha 317: verifica se existe só **uma** tabela que não é dimensão (o caso mais comum: planilha simples).
- Linhas 318–320: **passo 2, fatos e tabelas simples.** As dimensões e o calendário já foram tratados e são pulados.
- Linhas 321–326: escolhe o nome da tabela. Com modelo, usa o nome definido nele (ex.: `fato_nps`). Com uma tabela só, usa `destino.tabela` da regra, se houver, ou o nome-base do arquivo. Com várias abas, usa `base_nomedaaba`.
- Linhas 327–330: acrescenta `_arquivo_origem` (se ainda não existir) e `_lote_id`, que permitem saber de que arquivo e de que carga veio cada linha.
- Linha 331: cria ou adapta a tabela usando os tipos descobertos por `tipo_pg`.
- Linhas 332–334: no modo `substituir`, roda `TRUNCATE`, que esvazia a tabela inteira de uma vez (mantém a estrutura, ao contrário do DROP).
- Linhas 335–336: no modo `por_arquivo`, apaga só as linhas do mesmo arquivo.
- Linhas 337–340: no modo `mesclar`, exige que a chave exista nas colunas e apaga as linhas cujas chaves vieram de novo (`_apagar_por_chave`). No modo `anexar`, nenhum desses blocos roda: o robô só acrescenta.
- Linha 341: grava com COPY.
- Linha 342: anota as linhas esperadas para a reconciliação.
- Linhas 343–345: anota cada ligação fato → dimensão, para a reconciliação conferir a integridade.
- Linhas 346–347: registra e devolve as tabelas gravadas.

Como tudo isso roda **dentro da mesma transação** aberta pelo pipeline (pipeline.py, linha 222), um erro no meio (por exemplo, no passo 2) desfaz também o passo 1. O banco nunca fica com "metade" de um arquivo.

### Banco.reconciliar (linhas 349–373)

É a conferência do "DBA" (o administrador do banco, personagem Dora no projeto). Ela roda **dentro da transação, antes do commit**: se algo não bater, ainda dá para desfazer tudo.
- Linha 354: junta a lista de alvos, que são as tabelas do bruto (com as linhas esperadas registradas em `carregar_bruto`) e as do tratado (registradas em `carregar_tratado`).
- Linhas 355–361: para cada tabela, conta no banco `SELECT count(*) ... WHERE _lote_id = <este lote>` e compara com o esperado. Exemplo: o pandas tinha 1.250 linhas, mas o banco tem 1.249. Isso entra na lista de divergências.
- Linhas 362–370: confere a **integridade referencial**: procura linhas do fato deste lote cuja chave (preenchida) não encontra par na dimensão (um `LEFT JOIN` em que o lado da dimensão vem vazio). Essas linhas são as "órfãs". Exemplo: uma resposta de NPS que aponta para o curso 99, que não existe em `dim_curso`.
- Linhas 371–372: se houver qualquer divergência, levanta `ErroCargaDados`. O pipeline captura o erro, a transação é desfeita (**rollback**: o banco volta exatamente ao estado de antes) e o arquivo é reprovado.
- Linha 373: se tudo bateu, devolve a lista do que foi conferido, que vai para o relatório.

Por que conferir antes do commit? Depois do commit, os dados errados já estariam visíveis para o Power BI e seria preciso limpá-los à mão. Antes do commit, um único rollback resolve.

### Banco._apagar_por_chave (linhas 375–389)

Implementa o modo `mesclar`: apaga do banco as linhas cujas chaves chegaram de novo, para depois gravar a versão nova.
- Linhas 377–379: cria uma **tabela temporária** `_robo_chaves`, com as mesmas colunas-chave e os mesmos tipos da tabela real, mas sem dados (`WITH NO DATA`). Ela some sozinha no commit (`ON COMMIT DROP`).
- Linha 380: lê os tipos das colunas para converter os valores.
- Linhas 381–384: envia, via COPY, as chaves **distintas** do arquivo para a tabela temporária.
- Linhas 385–388: apaga da tabela real todas as linhas cuja chave aparece na temporária (`DELETE ... USING`). `IS NOT DISTINCT FROM` é um "igual" que também considera dois vazios como iguais (o `=` comum diria que `NULL = NULL` é "desconhecido").
- Linha 389: remove a tabela temporária na hora, para que uma segunda tabela no mesmo arquivo possa criar outra com o mesmo nome.

Por que não um `DELETE ... WHERE id IN (lista)`? Com 50 mil chaves, a lista ficaria gigante. COPY mais junção é o jeito eficiente.

### Banco._mesclar_dimensao (linhas 391–418)

Mantém os ids das dimensões estáveis entre cargas.
- Linhas 394–396: a primeira coluna é o id, e as demais formam a **chave natural** (o que identifica o membro "no mundo real": por exemplo, curso + modalidade). Depois, garante que a tabela exista.
- Linhas 397–399: lê tudo o que já existe na dimensão.
- Linhas 401–403: função interna `chave_natural`, que transforma os valores numa tupla comparável, com vazios virando `None` e os tipos convertidos como no banco. Sem essa conversão, `numpy.int64(5)` e `5`, ou um `Timestamp` e uma `date`, poderiam não "casar".
- Linhas 405–406: monta o dicionário `chave natural → id existente` e calcula o próximo id livre (o maior existente + 1).
- Linhas 407–415: para cada linha do arquivo, se a chave natural é nova, ela recebe o próximo id e entra na lista de novos. Em todos os casos, o de-para `id_do_arquivo → id_definitivo` é anotado.
- Linhas 416–418: grava só os membros novos e devolve o de-para.

### Banco._mesclar_calendario (linhas 420–431)

- Linha 422: garante a tabela `dim_calendario`.
- Linhas 423–428: calcula o período coberto, que é o menor e o maior valor entre as datas do arquivo novo **e** as que já estão no banco.
- Linha 429: gera o calendário completo desse período com `tabela_calendario`. Pelo código de `modelagem.py`, ele vai de 1º de janeiro do primeiro ano a 31 de dezembro do último ano.
- Linhas 430–431: esvazia a tabela e grava o calendário completo. Por que não acrescentar só os dias novos? Porque o calendário é inteiramente derivado das datas mínima e máxima: regenerá-lo é simples e garante que não haja buracos nem dias duplicados.

### Banco.executar_modelos (linhas 433–448)

Aqui acontece o "T" do ELT: os seus arquivos `.sql` da pasta `modelos_sql/` são executados.
- Linhas 435–436: se a pasta não existir, não faz nada.
- Linhas 438–440: percorre os `.sql` em **ordem alfabética** (por isso os nomes começam com números, como `00_`, `10_`: um modelo que depende de outro deve vir depois) e **pula** os que começam com `_` (é assim que `_exemplo_nps_mensal.sql` fica desativado).
- Linha 441: lê o arquivo com `utf-8-sig`, o que tolera o "BOM", uma marca invisível que o Bloco de Notas do Windows às vezes coloca no início do arquivo.
- Linhas 442–446: executa dentro de `conn.transaction()`. Como já existe uma transação aberta, isso cria um **savepoint** (um "ponto de restauração" dentro da transação). Se o modelo falhar, o erro diz exatamente qual arquivo falhou, e ele vira `ErroCargaDados`, que desfaz a carga inteira do arquivo.
- Linhas 447–448: registra e devolve os modelos executados.

Os modelos rodam **depois de cada carga bem-sucedida** e dentro da mesma transação. Assim, a camada analítica nunca fica desatualizada em relação ao tratado.

### Banco.registrar_lote (linhas 450–471)

Anota a carga nas tabelas de controle.
- Linhas 452–461: faz um `INSERT ... ON CONFLICT (lote_id) DO UPDATE`, o chamado *upsert*: se o lote ainda não existe, insere. Se já existe (mesmo `lote_id`), atualiza status, contagens, mensagem e ocorrências, e renova `processado_em`. As ocorrências são convertidas em texto JSON (`json.dumps`) para caber na coluna `jsonb`. Os parâmetros nomeados (`%(lote_id)s`) vêm do dicionário `dados`, montado por `_dados_lote` no pipeline.
- Linhas 462–463: apaga as ocorrências antigas deste lote, para não acumular duplicatas se o lote for registrado de novo. Isso acontece de fato no caminho de reprovação do pipeline, que registra o lote numa nova transação.
- Linhas 464–466: monta uma tupla por ocorrência de nível `ERRO` ou `AVISO` (as `INFO` ficam de fora), juntando os exemplos com `" | "`.
- Linhas 467–471: insere todas de uma vez com `executemany`.

### Banco.resumo (linhas 474–499)

Alimenta a tela de banco do painel e o comando de resumo.
- Linhas 476–478: conecta, garante a estrutura e confirma (`commit`).
- Linhas 479–482: lista os objetos (tabelas e views) das camadas `bruto`, `tratado` e `analitico`.
- Linhas 484–490: para cada **tabela** (`BASE TABLE`), conta as linhas. Para views, deixa `linhas` vazio, porque contar uma view significaria rodar o SQL dela, o que pode ser lento. O tipo é traduzido para "tabela" ou "visão".
- Linhas 491–494: lê as 15 cargas mais recentes de `robo.lotes`.
- Linhas 495–499: devolve tudo num dicionário que o painel transforma em tela.

### _explicar_erro_conexao (linhas 502–513)

Traduz as mensagens técnicas do PostgreSQL (em inglês ou português) para orientações práticas:
- Linhas 504–505: senha recusada. Indica conferir em Configurações > Banco.
- Linhas 506–507: o banco não existe.
- Linhas 508–509: o usuário (*role*) não existe.
- Linhas 510–512: conexão recusada ou tempo esgotado. Pergunta se o PostgreSQL está ligado e ensina o caminho nos Serviços do Windows.
- Linha 513: qualquer outro caso devolve a mensagem original, com o prefixo "Falha ao conectar".

**Erros que este arquivo evita**
- **Carga pela metade**: cada arquivo entra numa transação única. Se qualquer passo falhar, nada fica gravado no tratado (o pipeline grava, numa nova transação, só o bruto e o lote reprovado, para auditoria).
- **Duplicar dados ao reenviar o mesmo arquivo**: o modo `por_arquivo` apaga antes as linhas do mesmo `_arquivo_origem` (no tratado e no bruto).
- **Perder histórico por DROP acidental**: nenhuma tabela é apagada, colunas novas são adicionadas e tipos só são alargados.
- **Texto entrando em coluna numérica em silêncio**: o conflito de tipo reprova o arquivo com uma mensagem clara.
- **Contagem que não bate e fatos órfãos**: a reconciliação, antes do commit, compara as linhas esperadas com as gravadas e verifica a integridade fato → dimensão.
- **Ids de dimensão trocando a cada carga**: o de-para por chave natural mantém o mesmo id para o mesmo membro.
- **Robô "reprovando" planilha boa só porque o banco estava fora do ar**: erros de conexão viram `ErroBancoIndisponivel`, e o arquivo é adiado.
- **Comandos SQL quebrados por nomes estranhos e injeção de SQL**: os nomes passam por `sql.Identifier` e os valores por parâmetros `%s`.

---

## robo/consultas.py

- **Para que serve**: é a "biblioteca de perguntas de negócio" do painel. Ela lista os arquivos `.sql` da pasta `consultas_sql/`, lê o cabeçalho de cada um (título, pergunta, como ler, o que a consulta requer) e executa a consulta escolhida em modo **somente leitura** e com tempo limite. Assim você pode clicar em "NPS mensal" no painel sem risco de alterar dados e sem travar o banco.
- **Onde entra no fluxo**:
  - **Quem chama**: o servidor do painel (`robo/painel/servidor.py`, linhas 588–613), que usa `listar`, `ler`, `executar` e `explicar_erro`.
  - **Quem ele chama**: `robo/config.py` (`RAIZ_PROJETO`) e, em `executar`, o objeto `Banco` recebido como parâmetro (método `conectar`).

### Docstring do módulo (linhas 1–11)

- Linhas 3–7: mostram o formato do cabeçalho. Cada `.sql` começa com linhas de comentário (`--` em SQL é comentário, ignorado pelo banco): `-- titulo:`, `-- pergunta:`, `-- como_ler:` e `-- requer:`.
- Linha 9: você pode criar as suas consultas copiando um arquivo. Subpastas viram categorias.
- Linha 10: a execução é somente leitura e tem tempo limite.

### Imports (linhas 13–19)

- Linha 15: `re` serve para expressões regulares (padrões de texto, como "linha que começa com `-- titulo:`").
- Linha 16: `time` mede a duração da consulta.
- Linha 17: `Path` para caminhos.
- Linha 19: `RAIZ_PROJETO` é a pasta raiz do projeto.

### Constantes (linhas 21–23)

- Linha 21: a pasta padrão das consultas é `<projeto>/consultas_sql`.
- Linha 22: `RE_CAMPO` reconhece linhas como `-- titulo: NPS geral`, sem diferenciar maiúsculas de minúsculas e tolerando espaços, e captura o nome do campo e o valor.
- Linha 23: `LIMITE_LINHAS = 1000` é o máximo de linhas enviadas ao painel. Uma tabela com 2 milhões de linhas travaria o navegador.

### _categoria (linhas 26–27)

- Linha 27: transforma o nome da pasta em categoria, tirando o número do começo. Exemplo: `03 NPS` vira `NPS`. Se sobrar vazio, usa o nome original. O número no nome da pasta existe só para ordenar as categorias.

### _cabecalho (linhas 30–38)

- Linhas 31–35: percorre as linhas do arquivo. Quando a linha casa com o padrão, guarda o campo (em minúsculas) e o valor.
- Linhas 36–37: na primeira linha que não está vazia e não é comentário (ou seja, quando o SQL de verdade começa), para de procurar. Isso evita confundir um comentário no meio do SQL com o cabeçalho.
- Linha 38: devolve o dicionário de campos.

### listar (linhas 41–58)

- Linhas 42–43: se a pasta não existe, devolve uma lista vazia.
- Linhas 45–47: procura `.sql` em todas as subpastas (`rglob`), em ordem, e pula os que começam com `_` (rascunhos ou desativados).
- Linha 48: o `id` da consulta é o caminho relativo, com barras normais (ex.: `03 NPS/01_nps_geral_com_margem_de_erro.sql`).
- Linha 49: lê o cabeçalho.
- Linhas 50–57: monta o item. A categoria vem da pasta (arquivos soltos na raiz ficam em "Minhas consultas"). O título vem do cabeçalho ou, na falta dele, do nome do arquivo com os `_` trocados por espaços.

### caminho_seguro (linhas 61–65)

- Linhas 62–64: transforma o `id` recebido do painel num caminho real e confere três coisas: (1) o arquivo está **dentro** da pasta de consultas, (2) termina em `.sql` e (3) existe. Isso impede que alguém peça, por exemplo, `../../config.yaml` e leia ou execute um arquivo fora da biblioteca (o ataque conhecido como *path traversal*).

### ler (linhas 68–71)

- Linha 69: valida o caminho.
- Linha 70: procura, na listagem, os metadados (título etc.) dessa consulta.
- Linha 71: devolve os metadados, o texto SQL completo e o caminho do arquivo (para o painel mostrar o código).

### executar (linhas 74–91)

- Linha 76: lê o SQL a partir do caminho validado.
- Linha 77: dispara o cronômetro.
- Linhas 78–79: conecta e abre uma transação.
- Linha 80: `SET TRANSACTION READ ONLY` marca a transação como somente leitura. A partir daí, o PostgreSQL recusa `INSERT`, `UPDATE`, `DELETE`, `CREATE` etc.
- Linha 81: `SET LOCAL statement_timeout = '60s'` faz o banco cancelar qualquer comando que passe de 60 segundos. O `LOCAL` faz a regra valer só para esta transação.
- Linha 82: executa a consulta.
- Linha 83: pega os nomes das colunas do resultado (se o comando não devolve linhas, a lista fica vazia).
- Linha 84: busca no máximo `limite + 1` linhas. A linha extra serve só para saber se havia mais do que o limite.
- Linha 85: `rollback` ao final, para garantir que nada fica pendente.
- Linhas 86–91: devolve as colunas, até 1.000 linhas, a indicação `truncado` (se havia mais) e a duração em segundos.

### explicar_erro (linhas 94–106)

Traduz os erros mais comuns para o painel:
- Linhas 96–101: "não existe" (*does not exist*). Extrai o nome da tabela ou coluna que faltou e explica que a consulta precisa do que está em `requer`: carregue a planilha correspondente ou edite os nomes no `.sql`. Este é o erro mais comum, porque as consultas de exemplo usam nomes como `tratado.fato_nps`, que só existem se você carregou uma planilha com esse modelo.
- Linhas 102–103: tentativa de alterar dados, bloqueada pelo modo somente leitura.
- Linhas 104–105: passou de 60 segundos. Sugere filtrar um período menor.
- Linha 106: qualquer outro erro devolve a mensagem original.

**Erros que este arquivo evita**
- **Alterar ou apagar dados sem querer** ao rodar uma consulta pelo painel (transação somente leitura).
- **Consulta pesada travando o banco** (corte em 60 segundos) **e o navegador** (máximo de 1.000 linhas).
- **Ler ou executar arquivos fora da pasta de consultas** (`caminho_seguro`).
- **Mensagens de erro incompreensíveis** (`explicar_erro` diz o que falta e o que fazer).
- **Confundir comentário do SQL com cabeçalho** (a leitura do cabeçalho para no início do SQL).

---

## robo/backup.py

- **Para que serve**: faz uma cópia de segurança do PostgreSQL uma vez por dia (por padrão) e guarda as últimas 7, numa pasta do seu computador. Se o PostgreSQL der problema, se alguém apagar uma tabela ou se o disco do banco corromper, você tem de onde recuperar os dados. Usa o `pg_dump` (a ferramenta oficial de cópia) quando ele está disponível. Se não estiver, exporta todas as tabelas para CSV compactado.
- **Onde entra no fluxo**:
  - **Quem chama**: `robo/painel/controle.py` (linhas 139–143), que chama `backup.rotina(cfg)` numa tarefa em segundo plano disparada no máximo uma vez por hora (`>= 3600` segundos, linha 130), junto com a rotina de estratégia. `rotina` decide se já está na hora de fazer o backup.
  - **Quem ele chama**: `robo/banco.py` (`Banco`, `_parametros`, `conectar`), o programa externo `pg_dump` e `robo/canal.py` (`Canal.postar`, para avisar no canal da equipe).

### Docstring do módulo (linhas 1–13)

- Linhas 3–7: os dois métodos. (1) `pg_dump`: cópia completa (estrutura e dados) num arquivo `.dump`, restaurável com `pg_restore`. (2) Alternativa em Python: CSV compactado (`.csv.gz`) de todas as tabelas, mais um `manifesto.json` com as contagens. Guarda os dados, mas não a estrutura.
- Linhas 9–10: os backups ficam em `logs/backups/<data_hora>/`. A configuração é `backup: {habilitado, manter, intervalo_horas}`.
- Linhas 11–12: o comando para restaurar. `--clean --if-exists` apaga os objetos antes de recriá-los a partir da cópia.

### Imports (linhas 15–25)

- Linhas 17–25: `glob` procura arquivos por padrão (como `C:\Program Files\PostgreSQL\*\bin\pg_dump.exe`), `gzip` compacta, `json` grava o manifesto e o `ultimo.json`, `logging` escreve no log, `os` lê as variáveis de ambiente, `shutil` localiza programas e apaga pastas, `subprocess` roda o programa externo `pg_dump`, `datetime`/`timedelta` fazem contas com datas e `Path` trata caminhos.

### Constantes (linhas 27–29)

- Linha 27: o logger do robô.
- Linha 28: `PADRAO` define o backup ligado, manter 7 cópias e intervalo de 24 horas.
- Linha 29: `SCHEMAS` lista os schemas exportados no modo CSV: `bruto`, `tratado`, `analitico`, `robo` e `analise` (este último é criado por `robo/analise.py`).

### _c (linhas 32–33)

- Linha 33: junta o padrão com a seção `backup:` do config. O que estiver no config prevalece.

### pasta (linhas 36–37)

- Linha 37: devolve a pasta dos backups (`<pasta de logs>/backups`).

### localizar_pg_dump (linhas 40–46)

- Linhas 41–43: primeiro procura o `pg_dump` no PATH (a lista de pastas onde o Windows procura programas).
- Linhas 44–45: se não achar, procura nas pastas de instalação padrão do PostgreSQL no Windows e ordena pela versão (o pedaço `16` em `...\PostgreSQL\16\bin`), convertida em número para que 16 venha depois de 9.
- Linha 46: escolhe a versão **mais nova**, porque um `pg_dump` mais novo consegue copiar servidores mais antigos, mas não o contrário. Se não achar nenhum, devolve `None`.

### ultimo (linhas 49–53)

- Linhas 50–53: lê `ultimo.json`, que é o resultado do último backup. Se o arquivo não existir ou estiver corrompido, devolve `None` em vez de quebrar.

### fazer_backup (linhas 56–91)

Faz o backup na hora. Pela documentação da função, "nunca levanta exceção": o resultado é que diz o que aconteceu.
- Linhas 58–59: se o banco está desligado no config, não há o que copiar.
- Linhas 60–62: cria um `Banco` e lê os parâmetros de conexão.
- Linhas 63–66: cria uma pasta com o carimbo de data/hora (ex.: `20261017_093000`) e marca o início.
- Linhas 68–70: se achou o `pg_dump`, o arquivo de destino será `robo_dados.dump`.
- Linha 71: passa a senha pela variável `PGPASSWORD`. Assim ela não aparece na linha de comando, que outros programas conseguem ver.
- Linhas 72–73: roda o `pg_dump` com servidor, porta, usuário, `-F c` (o formato "custom", compactado e próprio para o `pg_restore`), o arquivo de saída e o nome do banco. O tempo máximo é de 1 hora.
- Linhas 74–75: se o `pg_dump` terminou com erro, o problema é levantado com até 400 caracteres da mensagem.
- Linhas 76–77: em caso de sucesso, monta o resultado com o método, o arquivo e o tamanho em MB.
- Linhas 78–79: sem `pg_dump`, usa a exportação em CSV.
- Linhas 80–83: em qualquer falha, **apaga a pasta incompleta** (um backup pela metade é pior do que nenhum, porque dá falsa segurança), anota o motivo e registra no log.
- Linhas 84–85: acrescenta a data/hora, a pasta (só se deu certo) e a duração.
- Linhas 86–87: grava o resultado em `ultimo.json`, que serve para o painel e para a `rotina` saber quando foi o último backup.
- Linhas 88–90: se deu certo, faz o rodízio (apaga os antigos) e registra no log.
- Linha 91: devolve o resultado.

### _exportar_csv (linhas 94–112)

O plano B, quando não há `pg_dump`.
- Linhas 96–99: conecta e lista todas as tabelas reais (`BASE TABLE`; views não, porque são só SQL) dos schemas de `SCHEMAS`.
- Linhas 100–105: para cada tabela, abre um arquivo `.csv.gz` e usa `COPY ... TO STDOUT WITH (FORMAT csv, HEADER true)`, o COPY no sentido inverso: o banco despeja a tabela em CSV com cabeçalho. Os blocos recebidos são gravados direto no arquivo compactado, sem carregar a tabela inteira na memória.
- Linhas 106–107: conta as linhas e anota no manifesto. Isso permite, ao restaurar, conferir se nada se perdeu.
- Linha 108: grava `manifesto.json`.
- Linhas 109–112: calcula o tamanho total e devolve o resultado, com uma observação de que a estrutura das tabelas não foi guardada.

### _rodizio (linhas 115–119)

- Linha 116: lê quantos backups manter (mínimo 1, para nunca apagar todos).
- Linhas 117–119: ordena as pastas de backup pelo nome (o carimbo `AAAAMMDD_HHMMSS` faz a ordem alfabética coincidir com a cronológica) e apaga todas, menos as últimas `manter`.

### rotina (linhas 122–138)

- Linhas 124–126: se o backup ou o banco estiverem desligados, não faz nada.
- Linhas 127–129: se o último backup **deu certo** e foi feito há menos de `intervalo_horas` (24 h), não faz nada. Repare que, se o último **falhou**, essa condição não segura, e o backup é tentado de novo na próxima chamada (que, pelo `controle.py`, acontece a cada hora, mais ou menos).
- Linha 130: faz o backup.
- Linhas 131–135: posta no canal da equipe, como a personagem "dba", uma mensagem de sucesso (método, tamanho, duração) ou um **alerta** de falha.
- Linhas 136–137: se o canal falhar, ignora. O aviso é um bônus e não pode estragar o backup.
- Linha 138: devolve o resultado.

**Erros que este arquivo evita**
- **Perder tudo se o PostgreSQL quebrar ou alguém apagar dados**: sempre existem até 7 cópias diárias.
- **Disco lotando de backups**: o rodízio mantém só os últimos N.
- **Falsa sensação de segurança com cópia pela metade**: a pasta de um backup que falhou é apagada e a falha vira alerta no canal.
- **Senha exposta na linha de comando**: ela vai pela variável `PGPASSWORD`.
- **Ficar sem backup por não ter o `pg_dump`**: a exportação em CSV é o plano B, com manifesto para conferência.
- **Backup repetido a cada hora**: a `rotina` respeita o intervalo, mas tenta de novo logo depois de uma falha.

---

## modelos_sql/00_vw_cargas.sql

**Para que serve**: cria a view `analitico.vw_cargas`, pronta para o Power BI montar um painel de monitoramento das cargas do robô (quantas por dia, quantas reprovadas etc.). Ela é executada por `Banco.executar_modelos` depois de cada carga bem-sucedida. O prefixo `00_` faz com que ela rode primeiro.

- Linhas 1–5: cabeçalho de comentários. Explica que o arquivo é executado depois de cada carga e como achar a view no Power BI (Obter dados > Banco de dados PostgreSQL > `analitico.vw_cargas`).
- Linha 6: `CREATE OR REPLACE VIEW` cria a view ou, se ela já existir, substitui a definição. É isso que permite rodar o mesmo arquivo a cada carga sem erro de "já existe".
- Linhas 7–17: as colunas, que vêm de `robo.lotes`. Duas merecem atenção:
  - Linha 12: `processado_em::date` converte a data/hora em só data (o `::` é o "converter para" do PostgreSQL). Isso facilita agrupar por dia no Power BI.
  - Linha 17: `array_to_string(tabelas, ', ')` transforma a lista de tabelas (`text[]`) num texto separado por vírgulas, porque o Power BI não lida bem com colunas do tipo lista.
- Linha 18: lê de `robo.lotes`.

## modelos_sql/_exemplo_nps_mensal.sql

**Para que serve**: um **exemplo desativado** (o `_` no início faz `executar_modelos` ignorá-lo) de como colocar a regra de negócio do NPS no banco. Para ativar, renomeie para `10_nps_mensal.sql` e ajuste os nomes de tabelas e colunas (linha 3).

- Linhas 1–7: comentários. Linhas 5–6: "Este é o 'T' do ELT": a regra do NPS fica num só lugar, e todo relatório lê o mesmo número.
- Linha 8: cria ou substitui a view `analitico.vw_nps_mensal`.
- Linha 10: `date_trunc('month', f.data_resposta)::date` "arredonda" cada data para o primeiro dia do mês (15/03/2026 vira 01/03/2026). Isso é o que permite agrupar por mês.
- Linha 11: o nome do curso, vindo da dimensão.
- Linha 12: `count(*)` é o total de respostas do grupo.
- Linhas 13–15: `count(*) FILTER (WHERE ...)` conta só as linhas que atendem à condição. Promotores têm nota ≥ 9, neutros têm 7 ou 8 e detratores têm ≤ 6.
- Linhas 16–17: NPS = 100 × (promotores − detratores) ÷ respostas, arredondado com 1 casa. O `100.0` (com ponto) força a conta decimal. Com `100`, o PostgreSQL faria divisão inteira e 37,5 viraria 37.
- Linha 18: a tabela de fatos `tratado.fato_nps`, com o apelido `f`.
- Linha 19: `JOIN ... USING (id_curso)` junta cada resposta ao seu curso pela coluna em comum `id_curso`. Respostas sem curso correspondente ficam de fora (é um JOIN "interno").
- Linha 20: `GROUP BY 1, 2` agrupa pela 1ª e pela 2ª coluna do SELECT (mês e curso).

---

## consultas_sql/ — biblioteca de consultas de negócio

Todos os arquivos seguem o cabeçalho lido por `consultas.py` (`titulo`, `pergunta`, `como_ler`, `requer`) e são executados pelo painel em modo somente leitura. As consultas das categorias 03 a 06 usam nomes de tabela de exemplo (`tratado.fato_nps`, `tratado.fato_csat`, `tratado.clientes`, `tratado.vendas`, `tratado.funil`). Se as suas tabelas tiverem outros nomes, edite o `.sql`. As da categoria 01 usam as tabelas de controle, que o robô cria sozinho.

Dois recursos de SQL aparecem em quase todas as consultas:
- **CTE** (`WITH nome AS (...)`): uma "subconsulta com nome", como uma tabela auxiliar temporária que existe só durante a consulta.
- **Função de janela** (`... OVER (...)`): faz contas que "olham para outras linhas" sem agrupar, como o mês anterior (`lag`), o total geral (`sum(...) OVER ()`) e o ranking (`rank`).

### 01 Monitoramento do robô

- **`01_cargas_por_dia.sql`**: quantos arquivos o robô processou por dia e quantos foram reprovados. Agrupa `robo.lotes` por `processado_em::date`, conta o total e, com `FILTER`, os `sucesso` e os `reprovado`. Também calcula o % de aprovação e soma as linhas publicadas. Uma queda brusca na aprovação costuma indicar mudança de layout na origem.
- **`02_erros_mais_frequentes.sql`**: quais problemas mais se repetem nas planilhas. Lê `robo.ocorrencias` só no nível `ERRO` e agrupa por mensagem e coluna (vazio vira "—"). Conta os arquivos afetados (`count(DISTINCT arquivo)`), as vezes, as células afetadas e a última ocorrência, e ordena pelos que atingem mais arquivos.
- **`03_reprovados_recentes.sql`**: quais arquivos foram reprovados e por quê. Filtra `robo.lotes` com `status = 'reprovado'` e mostra os 100 mais recentes, com a contagem de erros e avisos e o resumo da mensagem.
- **`04_linhas_descartadas_por_arquivo.sql`**: quanto de cada planilha foi descartado na limpeza (duplicadas, linhas de total, vazias). Para os lotes com sucesso, calcula `linhas_entrada − linhas_saida` e o percentual. `nullif(linhas_entrada, 0)` evita divisão por zero (transforma 0 em vazio). Ordena do maior descarte para o menor.
- **`05_tamanho_das_tabelas.sql`**: quanto espaço e quantas linhas cada tabela ocupa. Lê o catálogo de estatísticas `pg_stat_user_tables` (a contagem `n_live_tup` é aproximada) e o tamanho total em disco (`pg_total_relation_size`, formatado com `pg_size_pretty` em "12 MB"), para os schemas `bruto`, `tratado`, `analitico` e `robo`.

### 02 Qualidade dos dados

- **`01_completude_por_coluna.sql`**: qual o percentual de preenchimento de cada coluna de uma tabela. O truque: `to_jsonb(t)` transforma cada linha num objeto JSON, e `jsonb_each` o "desmonta" em pares (coluna, valor). Isso dá uma linha por célula, que é agrupada por coluna, contando os valores `null`. Funciona para qualquer tabela: basta trocar o `FROM`.
- **`02_duplicidades_por_chave.sql`**: existe o mesmo `id_resposta` repetido **entre arquivos diferentes**? Agrupa `tratado.fato_nps` por `id_resposta` e mantém só os que aparecem mais de uma vez (`HAVING count(*) > 1`), listando os arquivos com `string_agg`. Complementa o robô, que só bloqueia duplicidade dentro do mesmo arquivo.
- **`03_volume_por_arquivo_de_origem.sql`**: quantas linhas e qual período de datas veio em cada arquivo. Agrupa por `_arquivo_origem` e mostra a menor e a maior `data_resposta` e o último `_processado_em`. Períodos sobrepostos sugerem duplicidade, e buracos sugerem meses faltando.
- **`04_outliers_iqr.sql`**: há valores muito fora do padrão (ex.: venda de R$ 1 milhão digitada errado)? A CTE `quartis` calcula Q1 e Q3 de `valor` com `percentile_cont`. A consulta principal lista as vendas abaixo de Q1 − 1,5×IQR ou acima de Q3 + 1,5×IQR (IQR = Q3 − Q1), mostrando os limites ao lado.

### 03 NPS

- **`01_nps_geral_com_margem_de_erro.sql`**: qual é o NPS e quão confiável ele é. A CTE `base` calcula n, a proporção de promotores (média de `(nota >= 9)::int`, que vale 1 ou 0) e a de detratores. Depois calcula os percentuais, o NPS e a margem de erro de 95%: 1,96 × √((p_prom + p_det − (p_prom − p_det)²) ÷ n), a fórmula da variância do NPS.
- **`02_nps_mensal_com_variacao.sql`**: como o NPS evolui mês a mês. A CTE `mensal` calcula respostas e NPS por mês (`date_trunc`). A consulta final usa `lag(nps) OVER (ORDER BY mes)` para pegar o NPS do mês anterior e calcular a variação em pontos.
- **`03_nps_por_curso_e_modalidade.sql`**: quais cursos e modalidades puxam o NPS para cima ou para baixo. Junta `fato_nps` com `dim_curso`, calcula o NPS por curso e modalidade e marca como "base pequena" os grupos com menos de 30 respostas, ordenando do maior NPS para o menor.
- **`04_distribuicao_das_notas.sql`**: como as notas de 0 a 10 se distribuem. Agrupa por nota, classifica cada uma em Promotor, Neutro ou Detrator com `CASE` e calcula o % de cada nota sobre o total com `sum(count(*)) OVER ()` (o total geral, ao lado de cada linha).
- **`05_teste_diferenca_ultimos_dois_meses.sql`**: a variação do último mês é real ou é ruído? Calcula as proporções por mês, numera os meses do mais recente para o mais antigo (`row_number`) e calcula a variância de cada um. Depois junta o mês 1 com o mês 2, calcula a diferença e o erro padrão (√(var₁ + var₂)) e o z = diferença ÷ erro padrão. Com |z| ≥ 1,96, a diferença é "Significativa (95%)".
- **`06_detratores_para_contato.sql`**: quem são os detratores dos últimos 30 dias, para a operação retornar o contato (*closed loop*). Filtra nota ≤ 6 e `data_resposta` a partir da data mais recente da base menos 30 dias. Usa `LEFT JOIN` com `dim_curso` para não perder respostas sem curso e ordena pelas piores notas e pelas mais recentes.
- **`07_nps_por_uf.sql`**: em quais estados a experiência é melhor ou pior. Uma CTE calcula o NPS por UF e outra o NPS geral. O `CROSS JOIN` (junta "todos com todos": aqui, cada UF com a única linha do geral) permite calcular a diferença de cada UF em relação ao geral, e `rank()` cria a posição no ranking.

### 04 CSAT e CES

- **`01_csat_geral_e_por_canal.sql`**: qual a satisfação com o atendimento em cada canal. Calcula a nota média e o CSAT (% de notas 4 e 5, o *top-2-box*) por canal. O `GROUP BY ROLLUP (canal)` acrescenta uma linha de total geral, em que `canal` vem vazio e o `coalesce` a rotula como "TOTAL".
- **`02_ces_por_canal.sql`**: em qual canal o cliente tem mais dificuldade para resolver o problema. Por canal, calcula o CES médio (escala de 1 a 7, maior é melhor), o % fácil (notas 5 a 7) e o % difícil (notas 1 a 3), ordenando do pior CES para o melhor.
- **`03_csat_mensal.sql`**: a satisfação está melhorando? Agrupa por mês e mostra as respostas e o CSAT (% de notas ≥ 4), para acompanhar a tendência junto com o volume.
- **`04_pareto_motivos_de_insatisfacao.sql`**: quais poucos motivos explicam a maior parte da insatisfação. Conta os insatisfeitos (notas ≤ 2) por motivo (vazio vira "Não informado") e calcula o % de cada motivo e o **% acumulado**, com uma soma corrida (`sum(...) OVER (ORDER BY insatisfeitos DESC ... ROWS UNBOUNDED PRECEDING)`). Os motivos até cerca de 80% do acumulado são a prioridade.

### 05 Clientes, retenção e churn

- **`01_base_ativa_e_churn_mensal.sql`**: quantos clientes entram, saem e qual o churn por mês. A CTE `limites` descobre o primeiro e o último mês da base, e `generate_series` cria uma linha por mês. Depois, cruzando cada mês com cada cliente, conta os ativos no início do mês, os novos e os cancelados, e calcula o ativo no fim do mês e o churn % (cancelados ÷ ativos no início).
- **`02_retencao_por_coorte.sql`**: dos clientes que entraram em cada mês (coorte, a "safra"), quantos % continuam ativos após N meses. Para cada cliente, gera uma linha por mês, da entrada até o último mês da base (`CROSS JOIN LATERAL generate_series`). Calcula o "mês de vida" (0, 1, 2...) e conta quem ainda está ativo até o fim daquele mês. O resultado se lê como uma matriz coorte × mês de vida.
- **`03_tempo_de_vida_por_plano.sql`**: quanto tempo, em média, um cliente fica em cada plano. Para clientes ativos, usa como "hoje" a data mais recente da base. Calcula a média e a mediana (`percentile_cont(0.5)`) de dias até a saída, divididos por 30,4 para virar meses. A mediana é preferida porque sofre menos com extremos.
- **`04_churn_por_plano.sql`**: qual plano perde mais clientes. Por plano, conta os clientes, os cancelados (`data_saida` preenchida) e o % de churn acumulado, ordenando do maior para o menor.

### 06 Vendas e funil

- **`01_receita_mensal_e_crescimento.sql`**: como a receita evolui e quanto cresce mês a mês. Agrupa as vendas por mês (quantidade e soma do valor) e calcula o ticket médio (receita ÷ vendas) e o crescimento %, comparando com o mês anterior via `lag`.
- **`02_curva_abc_produtos.sql`**: quais produtos concentram a receita. Soma a receita por produto e calcula a participação acumulada, do maior para o menor (soma corrida ÷ total). Classifica como A (até 80%), B (até 95%) ou C (o restante, a "cauda longa").
- **`03_segmentacao_rfm.sql`**: quais clientes são campeões, quais estão em risco e quais estão hibernando. Por cliente, calcula a recência (dias desde a última compra, em relação à data mais recente da base), a frequência e o valor total. `ntile(5)` dá notas de 1 a 5 em quintis (5 = melhor; na recência, quem comprou há menos tempo). Um `CASE` combina R e F em segmentos (Campeões, Leais, Novos/promissores, Em risco, Hibernando, Precisam de atenção).
- **`04_conversao_do_funil.sql`**: onde se perdem mais leads no funil. A CTE `ordem` define as etapas e sua ordem com `VALUES` (lead, contato, proposta, matrícula), que você pode ajustar. Conta os leads distintos por etapa (`LEFT JOIN`, para que uma etapa sem leads apareça com 0) e calcula a conversão desde o início (`first_value`) e a conversão em relação à etapa anterior (`lag`). A menor taxa é o gargalo.
- **`05_conversao_por_origem.sql`**: qual canal de aquisição traz leads que mais convertem em matrícula. Por `origem`, conta os leads distintos e os que chegaram à etapa `matricula` e calcula a taxa de conversão, ordenando pela taxa e depois pelo volume.

---

## Possíveis defeitos notados durante a leitura (não corrigidos)

Esta seção só registra observações. Nenhum código foi alterado.

1. **`robo/banco.py`, linhas 268–270 (`carregar_bruto`), laço infinito.** O laço `while n in vistos or n.startswith("_"): n = f"{n}_x"` nunca termina quando o nome normalizado começa com `_`, porque acrescentar `_x` no **final** não muda o começo. Isso acontece de verdade: no modo padrão `abas: primeira`, quando a planilha tem várias abas com o mesmo cabeçalho, `leitura.py` (linha 227) acrescenta a coluna `_aba_origem` às brutas. `normalizar_nome_coluna("_aba_origem")` devolve `_aba_origem` (verifiquei rodando a função), e o robô travaria nesse arquivo. O mesmo vale para qualquer cabeçalho de planilha que comece com `_`. No mesmo cenário, o índice das abas empilhadas vira texto (`"Fev!12"`), e a linha 274 o grava em `_linha_origem`, que é `bigint` (linha 280). O COPY falharia ali mesmo que o laço terminasse.
2. **`consultas_sql/04 CSAT e CES/01_csat_geral_e_por_canal.sql`, linhas 6, 12 e 13.** No `ORDER BY canal NULLS LAST`, o PostgreSQL entende `canal` como a coluna de saída com esse apelido (o `coalesce(...)`, que nunca é vazio). Por isso o "TOTAL" é ordenado em ordem alfabética entre os canais, e não fica no fim. Além disso, se houver respostas com canal vazio, elas também aparecem rotuladas como "TOTAL", confundindo-se com a linha do total geral.
3. **`robo/consultas.py`, linhas 79–85, somente leitura contornável.** O SQL do arquivo é executado inteiro com `conn.execute(texto)`. Um `.sql` com várias instruções que inclua um `COMMIT;` encerraria a transação somente leitura, e os comandos seguintes poderiam alterar dados. O risco é baixo, porque os arquivos são seus e locais, mas a promessa da docstring ("o banco recusa qualquer alteração") não é absoluta. A linha 85 (`conn.rollback()`) roda depois de o bloco `with conn.transaction()` já ter encerrado a transação, e na prática não tem efeito.
4. **Nomes de schema fixos versus schemas configuráveis.** `Banco.__init__` (linhas 104–105) permite renomear os schemas pelo config, mas `backup.py` (linha 29), `modelos_sql/00_vw_cargas.sql` (linhas 6 e 18) e as consultas (por exemplo, `05_tamanho_das_tabelas.sql`, linha 11) usam os nomes fixos. Se você renomear um schema, o backup em CSV deixará tabelas de fora e os modelos e consultas quebrarão. Além disso, `05_tamanho_das_tabelas.sql` não inclui o schema `analise` e, por ler `pg_stat_user_tables`, não mostra as views.
5. **Consultas que assumem colunas do tipo `date`.** `tipo_pg` (linha 76) cria `timestamp` quando alguma data tem hora. Nesse caso, `06_detratores_para_contato.sql` (linha 14: `max(data_resposta) - 30`) falha, porque não se subtrai um inteiro de um timestamp. `03_tempo_de_vida_por_plano.sql` (linhas 12–13) também falha, porque a diferença vira um intervalo (*interval*) e o `round`/`::numeric` não aceitam esse tipo.
6. **`robo/backup.py`, `fazer_backup` (linhas 60–65), e `rotina` (linha 128).** A docstring diz "nunca levanta exceção", mas a criação do `Banco`, o `_parametros()` (que faz `int(porta)`) e o `mkdir` ficam **fora** do `try`. Em `rotina`, um `ultimo.json` sem `data_hora` ou com outro formato levantaria um erro. O `controle.py` captura essas falhas e só registra no log, mas o alerta no canal não seria enviado.
7. **Detalhes menores em `robo/banco.py`.** `date` e `Decimal` (linhas 23–24) são importados e não usados. Em `carregar_tratado` (linhas 309–310), um id de fato que não esteja no de-para da dimensão vira `NULL` em silêncio, e a reconciliação (linha 364) ignora chaves vazias, de modo que essa perda não seria barrada. Em `_mesclar_dimensao` (linha 406), o próximo id é calculado em memória (máximo + 1): se duas cargas rodassem ao mesmo tempo na mesma dimensão, poderiam gerar o mesmo id.
8. **`robo/consultas.py`, `caminho_seguro`/`executar`.** `listar` esconde os arquivos que começam com `_`, mas `ler` e `executar` aceitam executá-los se o `id` for informado diretamente. É uma inconsistência pequena, sem risco.
