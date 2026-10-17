# Parte 1 — Entrada e tratamento das planilhas

Este guia explica, arquivo por arquivo e praticamente linha por linha, o "primeiro andar" do Robô de Planilhas: tudo o que acontece desde o momento em que você solta uma planilha na pasta **Bases-Limpeza** até ela aparecer tratada em **Bases-Tratadas** (ou reprovada em **Bases-Erros**).

**O caminho que um arquivo percorre.** Tudo começa quando você roda `python -m robo ...`: o Python abre `robo/__main__.py`, que só repassa o pedido para `robo/comandos.py`. Ali o comando digitado é interpretado e as configurações são carregadas por `robo/config.py` (que lê o `config.yaml`, cujo modelo é `config.exemplo.yaml`). No modo do dia a dia, `robo/monitor.py` fica olhando a pasta de entrada; quando um arquivo novo para de mudar (o OneDrive terminou de sincronizar) e não está aberto no Excel, ele chama `robo/pipeline.py`, o "maestro" do processamento. O maestro chama, em ordem: `robo/leitura.py` (abre a planilha e acha o cabeçalho), `robo/limpeza.py` (padroniza nomes, textos, tipos, remove totais e duplicadas), `robo/validacao.py` (confere as regras de qualidade), `robo/modelagem.py` (monta fato/dimensões para o Power BI, se pedido) e `robo/escrita.py` (grava o Excel/CSV tratado). Durante todo o caminho, cada passo é anotado em um `Relatorio` (`robo/relatorio.py`); no final, o resultado é guardado no histórico (`robo/historico.py`). Uma vez por dia, `robo/manutencao.py` apaga backups e logs muito antigos.

> **Como ler os intervalos de linhas:** "Linhas 10–12" significa as linhas 10 a 12 do arquivo, como aparecem em qualquer editor de código (VS Code, Bloco de Notas++ etc.).

---

## robo/__main__.py

- **Para que serve:** é a "porta da frente" do robô. Quando você digita `python -m robo monitorar`, o Python procura dentro da pasta `robo` um arquivo chamado `__main__.py` e o executa. Ele não faz trabalho nenhum sozinho: apenas chama a função principal da linha de comando.
- **Onde entra no fluxo:** é chamado pelo próprio Python (comando `python -m robo`). Ele chama `principal()` de `robo/comandos.py`.

### Import (linha 1)

- Linha 1: `from robo.comandos import principal`. Um **import** é a instrução que "traz" para este arquivo algo que foi escrito em outro arquivo (um **módulo**). Aqui ele traz a **função** `principal` — uma função é um bloco de código com nome, que pode ser executado ("chamado") quando necessário, como uma macro do Excel.

### Bloco de execução (linhas 3–4)

- Linha 3: `if __name__ == "__main__":` é a forma padrão do Python dizer "só execute o que vem abaixo se este arquivo foi iniciado diretamente" (e não apenas importado por outro arquivo).
- Linha 4: chama `principal()` e entrega o número que ela devolve para `SystemExit`. `SystemExit` encerra o programa informando ao Windows um **código de saída**: 0 = deu tudo certo; qualquer outro número = houve problema. Isso permite que um agendador de tarefas ou um `.bat` saiba se o robô terminou bem.

**Erros que este arquivo evita**
- Executar o robô sem passar pela leitura correta dos comandos.
- Perder o código de saída (o Agendador de Tarefas do Windows conseguiria "achar" que deu certo quando não deu).

---

## robo/comandos.py

- **Para que serve:** é o "balcão de atendimento" da linha de comando. Ele entende o que você pediu (`monitorar`, `varrer`, `processar`, `diagnosticar`, `status`, `manutencao`, `app`, `banco`, `atalhos`, `inicializacao`), prepara o registro de log (o "diário" do robô) e chama a parte certa do sistema.
- **Onde entra no fluxo:** é chamado por `robo/__main__.py`. Ele chama `robo/config.py` (carregar configurações), `robo/monitor.py` (vigiar a pasta), `robo/pipeline.py` (processar um arquivo), `robo/manutencao.py` (limpeza de arquivos antigos) e, sob demanda, `robo/banco.py`, `robo/painel/servidor.py` e `robo/painel/sistema.py` (que não fazem parte desta Parte 1).

### Texto de documentação (linhas 1–9)

- Linhas 1–9: é uma **docstring** — um texto entre três aspas no topo do arquivo que não é executado; serve só de manual. Lista os comandos principais e o que cada um faz. Repare na diferença importante: `processar` grava e move o arquivo; `diagnosticar` só analisa, sem gravar nem mover nada.

### Imports (linhas 11–24)

- Linha 11: `from __future__ import annotations` permite escrever as "anotações de tipo" (as dicas do tipo `argv: list[str] | None`) de forma moderna mesmo em versões mais antigas do Python. Não muda o comportamento.
- Linhas 13–18: bibliotecas que já vêm com o Python:
  - `argparse`: lê os comandos e opções digitados no terminal.
  - `csv`: lê/escreve arquivos CSV (aqui, para mostrar o histórico no `status`).
  - `logging`: o sistema de registro de mensagens (o "diário" do robô).
  - `sys`: acesso a coisas do próprio Python, como a saída do console.
  - `TimedRotatingFileHandler`: um gravador de log que troca de arquivo automaticamente todo dia.
  - `Path`: representa caminhos de pastas e arquivos de forma segura (sem se preocupar com `\` ou `/`).
- Linhas 20–24: imports do próprio robô: o número da versão (`__version__`), a exceção `ErroConfig` e a função `carregar_config` (config.py), `executar_manutencao` (manutencao.py), `Monitor`, `TravaInstancia` e `eh_candidato` (monitor.py) e `processar_arquivo` (pipeline.py). Uma **exceção** é a forma do Python sinalizar "deu errado": o código "levanta" a exceção e quem estiver preparado a "captura" e decide o que fazer.

### Constante `log` (linha 26)

- Linha 26: cria (ou obtém) o registrador de mensagens chamado `"robo"`. Todos os arquivos do robô usam esse mesmo nome, por isso todas as mensagens caem no mesmo diário.

### configurar_log (linhas 29–41)

Prepara para onde as mensagens do diário vão: arquivo e/ou tela.

- Linha 29: recebe a pasta de logs, se é para ser "verboso" (mais detalhes) e se deve gravar em arquivo.
- Linha 30: define o formato de cada linha: data/hora no padrão brasileiro, nível (INFO, WARNING…) e a mensagem. Exemplo de linha: `17/10/2026 09:30:12 | INFO    | Processando nps_outubro.xlsx`.
- Linha 31: no modo verboso registra até mensagens de depuração (DEBUG); senão, só INFO para cima.
- Linha 32: apaga os destinos antigos, para não duplicar mensagens se a função for chamada duas vezes.
- Linhas 33–37: se é para gravar em arquivo, cria a pasta de logs, cria `robo.log` com troca à meia-noite (`when="midnight"`), guarda até 60 arquivos antigos (`backupCount=60`, ou seja, ~2 meses) e grava em UTF-8 (para acentos saírem certos).
- Linhas 38–41: se existe um console (tela preta), também mostra as mensagens nele. O comentário explica o porquê do `if`: quando o robô roda escondido com `pythonw`, não existe console, e tentar escrever nele daria erro.

### _imprimir_resultado (linhas 44–55)

Mostra na tela o resultado de `processar` ou `diagnosticar`. O `_` no começo do nome é uma convenção: "função de uso interno deste arquivo".

- Linhas 45–46: pula uma linha e imprime o relatório completo em texto (o mesmo conteúdo do `_ERROS.txt`).
- Linhas 47–53: se há tabelas tratadas, imprime uma "prévia": para cada tabela, o nome, quantas linhas e colunas, o tipo de cada coluna (`dtypes`) e as 5 primeiras linhas (`head(5)`). As tabelas são **DataFrames** — a estrutura do pandas que funciona como uma aba de Excel na memória (linhas, colunas, cabeçalho). `r.tabelas` é um **dicionário**: uma coleção de pares "chave → valor", como um PROCV pronto (aqui, nome da tabela → DataFrame).
- Linhas 54–55: lista os arquivos gerados (`r.saidas` é uma **lista**, ou seja, uma sequência ordenada de itens).

### _status (linhas 58–74)

Implementa o comando `status`.

- Linha 59: imprime o nome e a versão.
- Linhas 60–61: para cada pasta configurada, imprime `OK` se existe ou `--` se não existe, junto com o caminho.
- Linhas 62–65: monta a "fila": nomes dos arquivos em Bases-Limpeza que o robô consideraria processar (usa `eh_candidato`, que ignora temporários do Excel/OneDrive). Mostra no máximo 20.
- Linhas 66–67: conta quantos relatórios `*_ERROS.txt` existem em Bases-Erros — ou seja, quantos arquivos reprovados ainda esperam correção.
- Linhas 68–74: se existe o histórico `historico_processamentos.csv`, lê o arquivo (separador `;`, pulando o cabeçalho com `[1:]`) e mostra os 10 últimos processamentos: data, status, nome, linhas de saída, erros e avisos (posições 0, 2, 1, 4, 5 e 6 da linha, que batem com a ordem das colunas definida em `historico.py`). O `utf-8-sig` lê corretamente o "BOM", uma marca invisível que o Excel coloca no começo de CSVs UTF-8.

### _comando_banco (linhas 77–97)

Implementa `python -m robo banco testar|modelos|resumo`.

- Linha 78: importa o módulo do banco só agora (import "preguiçoso"): quem nunca usa PostgreSQL não precisa nem carregar essa parte.
- Linha 79: cria o objeto `Banco` com as configurações da seção `banco`.
- Linhas 80–83: `testar`: tenta conectar e imprime OK/ERRO com a mensagem; devolve 0 ou 1.
- Linhas 84–89: `modelos`: abre uma conexão e uma **transação** (um "pacote" de operações no banco que ou é confirmado inteiro, ou é desfeito inteiro), prepara a estrutura do banco e executa os modelos SQL da pasta `modelos_sql`. Imprime quais rodaram.
- Linhas 90–93: qualquer outra ação (na prática, `resumo`): lista as tabelas do banco com schema, nome, tipo e número de linhas.
- Linha 94: devolve 0 (sucesso).
- Linhas 95–97: se o banco estiver fora do ar ou recusar dados, imprime o erro e devolve 1, em vez de "quebrar" com uma mensagem técnica.

### principal (linhas 100–194)

É o coração da linha de comando.

- Linhas 101–103: cria o leitor de comandos (`ArgumentParser`) e duas opções gerais: `--config` (outro caminho de `config.yaml`) e `-v/--verboso`.
- Linha 104: diz que haverá subcomandos e que um deles é obrigatório.
- Linhas 105–120: declara cada subcomando. Destaques: `app` aceita `--sem-janela` (liga só em segundo plano, usado na inicialização do Windows) e `--porta`; `processar` e `diagnosticar` exigem o nome do arquivo; `inicializacao` aceita só `ligar`, `desligar` ou `status`; `banco` aceita só `testar`, `modelos` ou `resumo` (`choices` recusa qualquer outra palavra).
- Linha 121: lê o que foi digitado. `argv` permite que testes automatizados chamem a função passando os comandos como lista.
- Linhas 123–137: `atalhos` e `inicializacao` (coisas do Windows). Importa o módulo `sistema` do painel e: cria os atalhos (linha 127), mostra se o robô inicia com o Windows (linha 129) ou liga/desliga isso (linhas 131–133). Qualquer falha vira a mensagem "Não foi possível" e código 1. Esses comandos vêm antes do carregamento do `config.yaml` de propósito: não dependem dele.
- Linhas 139–149: `app` (o painel gráfico). Primeiro liga o log na pasta `logs` do projeto (linha 142), porque nesta hora ainda pode não existir `config.yaml`. Depois tenta carregar a configuração (linha 144); se a pasta de logs configurada for outra, reconfigura o log para ela (linhas 145–146). Se a configuração der erro, ignora (linhas 147–148): o painel vai mostrar a tela de configuração inicial. A linha 149 inicia o painel.
- Linhas 151–155: para todos os outros comandos, carrega a configuração. Se falhar (`ErroConfig`), imprime a mensagem no canal de erro e sai com código 2.
- Linhas 157–158: liga o log. O comentário explica: `status` e `diagnosticar` não gravam em `robo.log` para não "brigar" pelo arquivo com um robô que já esteja rodando.
- Linhas 160–162: `status` → chama `_status` e sai com 0.
- Linhas 163–166: `diagnosticar` → processa com `gravar=False` (nada é gravado ou movido), imprime e devolve 1 se houve erros.
- Linhas 167–171: `processar` → cria as pastas, processa de verdade, imprime e devolve 0 só se o status for "sucesso".
- Linhas 172–176: `banco` → `_comando_banco`; `manutencao` → executa e imprime o resumo (quantos arquivos apagados por pasta).
- Linha 178: a partir daqui sobram `monitorar` e `varrer`; cria as pastas.
- Linha 180: `with TravaInstancia(...)` impede que dois robôs rodem ao mesmo tempo (detalhes em `monitor.py`). O `with` garante que a trava seja liberada ao sair, mesmo se houver erro.
- Linha 181: cria o monitor.
- Linhas 182–186: `varrer` → um único ciclo forçado (sem esperar a sincronização), conta quantos deram sucesso, imprime o resumo e devolve 0 só se todos deram certo.
- Linhas 187–190: `monitorar` → roda sem parar; se você apertar Ctrl+C (`KeyboardInterrupt`), registra "Robô encerrado pelo usuário" em vez de mostrar um erro feio.
- Linhas 191–193: se a trava não puder ser obtida (já existe outro robô), registra o erro e sai com código 3.
- Linha 194: fim normal, código 0.

**Erros que este arquivo evita**
- Dois robôs processando a mesma pasta ao mesmo tempo (trava de instância).
- O comando `status`/`diagnosticar` disputando o arquivo de log com o robô em execução.
- Mensagens técnicas incompreensíveis quando a configuração está errada (vira "ERRO DE CONFIGURAÇÃO" com código 2).
- Diagnóstico que, sem querer, moveria ou gravaria arquivos.

---

## robo/config.py

- **Para que serve:** reúne todas as "preferências" do robô. Ele tem valores padrão para tudo, lê o seu `config.yaml` por cima desses padrões e descobre sozinho onde está a pasta Bases-Limpeza dentro do OneDrive. Também escolhe qual "regra por arquivo" vale para cada planilha (por exemplo, a regra `nps_*` para `nps_outubro.xlsx`).
- **Onde entra no fluxo:** é chamado por `comandos.py` (`carregar_config`) e o objeto `Config` resultante é passado para `monitor.py`, `pipeline.py`, `manutencao.py` e praticamente todo o resto. Ele não chama outros módulos do robô.

### Docstring e imports (linhas 1–10)

- Linha 1: descrição do arquivo.
- Linhas 5–8: `copy` (fazer cópias profundas de dicionários), `fnmatch` (comparar nomes com curingas como `nps_*`), `os` (variáveis de ambiente do Windows) e `Path`.
- Linha 10: `yaml`, biblioteca externa que lê arquivos YAML (o formato do `config.yaml`, baseado em indentação).

### Constantes de caminhos e nomes (linhas 12–16)

- Linha 12: `RAIZ_PROJETO` = a pasta do projeto. `__file__` é o caminho deste arquivo (`.../robo/config.py`); `.parent.parent` sobe duas pastas. Assim o robô sabe onde está instalado, não importa de onde você o chamou.
- Linha 13: o `config.yaml` padrão fica na raiz do projeto.
- Linhas 15–16: os nomes oficiais das pastas de entrada e saída. Uma **constante** é um valor fixo com nome em MAIÚSCULAS, para não espalhar o mesmo texto pelo código.

### PADROES (linhas 18–104)

Um grande dicionário com o valor padrão de cada configuração. Se o `config.yaml` não falar nada sobre um item, vale o que está aqui.

- Linhas 19–31 (`pastas`): entrada, saída, erros, originais e relatórios em `"auto"` (descoberta automática); logs na pasta `logs` do projeto; definições de agentes e habilidades personalizadas em pastas do projeto.
- Linhas 32–36 (`monitoramento`): olhar a pasta a cada 5 segundos; o arquivo precisa ficar 10 segundos sem mudar para ser considerado "pronto" (sincronização do OneDrive terminada).
- Linhas 37–41 (`leitura`): por padrão lê a primeira aba com dados; procura o cabeçalho nas 20 primeiras linhas.
- Linhas 42–53 (`limpeza`):
  - remove duplicadas e linhas de total; tenta descobrir tipos automaticamente;
  - `limiar_conversao: 0.95` — uma coluna só vira número/data se pelo menos 95% dos valores preenchidos puderem ser convertidos. Exemplo: 100 notas, 97 numéricas e 3 escritas "não respondeu" → vira número (e o robô avisa que esvaziou as 3);
  - `valores_nulos` — textos que significam "vazio" (`-`, `N/A`, `null`, `sem informação`, `s/i`...);
  - `erros_excel: "erro"` — `#REF!`, `#DIV/0!` etc. reprovam o arquivo (a alternativa `anular` esvazia a célula e só avisa);
  - `padroes_identificador` — nomes de coluna (com curingas) que sempre ficam como texto, para não perder zeros à esquerda: `id`, `cpf*`, `cep*`, `telefone*`, `matricula*`, `codigo*`, `ra`, `rg`...
- Linhas 54–64 (`saida`): grava `.xlsx`, sem sufixo, sobrescrevendo (sem versionar), aba chamada `dados`, com colunas de auditoria; CSV com `;` e vírgula decimal (padrão brasileiro).
- Linhas 65–80 (`banco`): PostgreSQL desligado por padrão, com dados de conexão, nome da variável de ambiente da senha, se grava a camada "bruto", pasta dos modelos SQL, modo de carga e tempo limite de 5 s para conectar.
- Linhas 81–92 (`analise` e `excel`): parâmetros do 2º e 3º andares (análise automática e Sala Excel), cobertos em outras partes do guia.
- Linhas 93–97 (`painel`): porta 8765, liga o robô ao abrir, notificações ligadas.
- Linhas 98–102 (`manutencao`): guarda originais e relatórios por 180 dias e logs por 60 dias.
- Linha 103: `regras` começa como lista vazia.

### ATRIBUTO_PASTA (linha 108)

- Linha 108: tradução entre o nome usado no `config.yaml` e o nome usado no código. O único que muda é `saida`, que no código se chama `tratadas` (`cfg.tratadas`). O comentário da linha 107 explica isso.

### ErroConfig (linhas 111–112)

- Linhas 111–112: cria uma exceção própria, `ErroConfig`. Uma **classe** é um "molde" para criar objetos; aqui o molde herda tudo de `Exception` e não acrescenta nada (`pass`). Ter um tipo de erro só para configuração permite que `comandos.py` capture exatamente esse caso e mostre "ERRO DE CONFIGURAÇÃO".

### _mesclar (linhas 115–122)

Junta os padrões com o que você escreveu no `config.yaml`, nível por nível.

- Linha 116: faz uma **cópia profunda** dos padrões, para nunca alterar o dicionário original `PADROES`.
- Linhas 117–121: para cada item do seu arquivo: se o valor é um dicionário e o padrão também é (ex.: a seção `limpeza`), mescla por dentro (a função chama a si mesma — isso se chama **recursão**); caso contrário, o seu valor substitui o padrão.
- Por que isso importa: se você escrever só `limpeza: {remover_duplicadas: false}`, todos os outros itens de `limpeza` continuam com o padrão. Atenção: **listas não são mescladas, são substituídas** — se você escrever `valores_nulos: ["-"]`, a lista padrão inteira deixa de valer.

### _expandir (linhas 125–127)

- Linha 126: transforma o texto do caminho em `Path`, trocando `~` pela sua pasta de usuário e `%VARIAVEL%`/`$VARIAVEL` pelo valor da variável de ambiente.
- Linha 127: se o caminho já é completo (ex.: `C:/Users/...`), usa como está; se é relativo (ex.: `logs`), monta a partir da pasta `base` (a pasta onde está o `config.yaml`).

### raizes_onedrive (linhas 130–145)

Descobre onde o OneDrive está no computador.

- Linhas 133–135: o Windows cria variáveis de ambiente `OneDrive`, `OneDriveCommercial` (corporativo) e `OneDriveConsumer` (pessoal). Se existirem, entram como candidatas.
- Linhas 136–138: também procura na sua pasta de usuário qualquer pasta que comece com `OneDrive` (ex.: `OneDrive - Cogna`), em ordem alfabética.
- Linhas 139–144: remove repetidos (comparando sem diferenciar maiúsculas, porque no Windows `C:\Users\A` e `c:\users\a` são o mesmo lugar) e descarta o que não for pasta.
- Linha 145: devolve a lista de raízes encontradas.

### localizar_pasta (linhas 148–164)

Procura uma pasta pelo nome até 4 níveis abaixo das raízes do OneDrive.

- Linha 150: põe o nome procurado em minúsculas, para não diferenciar `Bases-Limpeza` de `bases-limpeza`.
- Linha 151: percorre as raízes (as informadas ou, se nenhuma, as do OneDrive).
- Linhas 152–154: usa uma "fila" de pastas a visitar, começando pela raiz (nível 0). Esse jeito de procurar (nível por nível) se chama **busca em largura**: acha primeiro a pasta mais "rasa".
- Linhas 155–156: achou o nome? Devolve a pasta.
- Linhas 157–158: se já está no nível máximo, não desce mais.
- Linhas 159–162: lista as subpastas (ignorando as ocultas, que começam com `.`); se não tiver permissão para abrir uma pasta, pula sem travar.
- Linha 163: coloca as subpastas no fim da fila, com nível + 1.
- Linha 164: não achou em lugar nenhum → devolve `None` ("nada").

### Classe Config (linhas 167–256)

É o objeto que carrega todas as configurações já resolvidas.

#### __init__ (linhas 168–172)
- `__init__` é a função que roda quando um objeto é criado. Guarda os dados mesclados, a pasta base e o caminho do arquivo, e já resolve todas as pastas (linha 172). Ou seja: se a pasta de entrada não for encontrada, o erro aparece logo na criação, não no meio de um processamento.

#### __getitem__ (linhas 175–176)
- Permite escrever `cfg["regras"]` como se `cfg` fosse um dicionário.

#### Propriedades de atalho (linhas 178–204)
- Cada `@property` cria um "atalho" de leitura: `cfg.limpeza` é o mesmo que `cfg.dados["limpeza"]`. Existem para `limpeza`, `leitura`, `saida`, `monitoramento`, `banco`, `painel` e `manutencao`. Deixa o resto do código mais legível.

#### _resolver_pastas (linhas 207–233)
- Linhas 208–209: pega a seção `pastas`; se `entrada` estiver vazia, trata como `"auto"`.
- Linhas 210–217: no modo automático, procura `Bases-Limpeza` no OneDrive; se não achar, levanta `ErroConfig` com instrução clara de como informar o caminho manualmente.
- Linhas 218–219: se você informou um caminho, ele é expandido (`_expandir`).
- Linhas 221–227: a "irmã" é a pasta que contém Bases-Limpeza. Os caminhos automáticos das outras pastas ficam lado a lado com ela: `Bases-Tratadas`, `Bases-Erros`, `Bases-Originais` e `Bases-Relatorios`. Exemplo: se a entrada é `C:/Users/ana/OneDrive/CI/Bases-Limpeza`, a saída será `C:/Users/ana/OneDrive/CI/Bases-Tratadas`.
- Linhas 228–230: para cada uma dessas quatro, usa o caminho automático ou o informado, e grava no atributo certo (`setattr` cria `self.tratadas`, `self.erros`, etc., usando a tradução de `ATRIBUTO_PASTA`).
- Linha 231: a pasta de logs é relativa à pasta do `config.yaml`.
- Linhas 232–233: agentes e habilidades são relativos à raiz do projeto. A linha 233 aceita também o nome antigo `skills`, por compatibilidade.

#### criar_pastas (linhas 235–237)
- Cria todas as pastas listadas por `pastas()` (e as intermediárias, `parents=True`); se já existem, não faz nada (`exist_ok=True`).

#### pastas (linhas 239–247)
- Devolve um dicionário "nome amigável → caminho" com as seis pastas principais. É usado pelo `status` e por `criar_pastas`.

#### regra_para (linhas 250–256)
- Linhas 252–255: percorre a lista de regras **na ordem em que aparecem** no `config.yaml`; a primeira cujo `padrao` casar com o nome do arquivo (sem diferenciar maiúsculas, com curingas `*`) é devolvida. Exemplo: padrão `nps_*` casa com `NPS_Outubro.xlsx`.
- Linha 256: nenhuma casou → devolve um dicionário vazio (o arquivo é tratado só com as configurações gerais).

### carregar_config (linhas 259–273)

- Linha 260: usa o caminho informado ou o `config.yaml` da raiz do projeto.
- Linhas 261–265: se o arquivo existe, lê com `yaml.safe_load` (versão "segura", que não executa nada estranho escrito no YAML). Se o arquivo estiver vazio, vira `{}`. A base dos caminhos relativos é a pasta do arquivo.
- Linhas 266–267: se o arquivo não existe, segue só com os padrões e usa a raiz do projeto como base.
- Linhas 268–270: mescla padrões + seu arquivo + (opcional) um dicionário `sobrescrever`, usado por quem chama a função para trocar algo pontualmente (ex.: testes ou o painel).
- Linhas 271–272: se `regras` não for uma lista, recusa com mensagem clara. Isso pega o erro clássico de YAML em que a pessoa esquece o `-` antes de `padrao:`.
- Linha 273: cria e devolve o objeto `Config`.

**Erros que este arquivo evita**
- Ter que escrever o caminho do OneDrive à mão (descoberta automática).
- Configuração incompleta quebrar o robô (tudo tem padrão).
- Pastas de saída espalhadas por lugares diferentes (ficam lado a lado com Bases-Limpeza).
- `regras` escritas no formato errado passarem despercebidas.

---

## robo/monitor.py

- **Para que serve:** é o "porteiro" da pasta Bases-Limpeza. A cada poucos segundos, ele olha a pasta, percebe arquivos novos, espera o OneDrive terminar de sincronizar e o Excel fechar o arquivo, e só então manda processar. Também impede que dois robôs rodem ao mesmo tempo e dispara a manutenção diária.
- **Onde entra no fluxo:** é usado por `comandos.py` (comandos `monitorar` e `varrer`) e pelo painel. Ele chama `pipeline.processar_arquivo` para cada arquivo pronto e `manutencao.executar_manutencao` uma vez por dia.

### Docstring (linhas 1–8)

- Explica a decisão de usar **polling** (olhar a pasta de tempos em tempos) em vez de "eventos" do Windows. O porquê: o OneDrive cria e renomeia arquivos temporários durante a sincronização e esses eventos podem se perder. Também lista as duas condições para processar: o arquivo parou de mudar por X segundos e pode ser aberto (não está aberto no Excel).

### Imports (linhas 10–21)

- Linhas 12–17: `logging`, `os` (saber se é Windows), `threading` (rodar coisas em paralelo e travas), `time` (relógio), `date` (data de hoje) e `Path`.
- Linhas 19–21: `Config`, `executar_manutencao` e, do pipeline, a constante `ADIADO` e a função `processar_arquivo`.

### Constantes (linhas 23–25)

- Linha 23: o diário `"robo"`.
- Linha 25: nomes de arquivos de sistema que nunca são planilhas: `desktop.ini`, `thumbs.db`, `.ds_store` (este último é criado por Macs). Usa um **conjunto** (`{...}`), uma coleção sem repetição muito rápida para perguntar "este nome está aqui?".

### eh_candidato (linhas 28–35)

Responde "este arquivo deve ser considerado?".

- Linha 29: compara tudo em minúsculas.
- Linhas 30–35: só é candidato se: é arquivo (não pasta); não é de sistema; não começa com `~$` (arquivo de bloqueio que o Excel cria quando você abre uma planilha), `~robo_tmp_` (temporário do próprio robô), `.` ou `~`; e não termina com extensões de arquivo incompleto ou atalho (`.tmp`, `.crdownload` do Chrome, `.part`, `.partial`, `.lnk`).

### pode_abrir (linhas 38–44)

- Linhas 40–42: tenta abrir o arquivo em modo leitura+escrita (`rb+`). No Windows, isso falha se o Excel estiver com o arquivo aberto. Conseguiu → `True`.
- Linhas 43–44: falhou por permissão ou outro erro do sistema → `False`.

### Classe Monitor (linhas 47–175)

#### __init__ (linhas 48–61)
- Linhas 49–51: guarda a configuração, o intervalo entre olhadas e o tempo de estabilidade (convertidos para número decimal).
- Linha 53: `_vistos` é a "memória" do porteiro: para cada arquivo, guarda tamanho, data de modificação e **quando essa combinação foi vista pela primeira vez**. É assim que ele sabe há quanto tempo o arquivo está parado.
- Linha 54: data da última manutenção (começa vazia).
- Linha 55: uma trava (`Lock`) para que dois ciclos nunca rodem ao mesmo tempo (ex.: o ciclo automático e o botão "Processar agora" do painel).
- Linhas 56–57: funções opcionais de aviso: uma chamada após cada processamento (painel/notificações), outra a cada etapa (o "escritório 3D" do painel).
- Linhas 58–61: estado para o painel: o arquivo em processamento agora, os arquivos abertos em outro programa, os adiados (com o motivo) e o horário do último ciclo.

#### ciclo (linhas 63–67)
- Uma passada na pasta, protegida pela trava (linha 66). Usa `time.monotonic()` (relógio que só anda para frente, imune a mudanças de horário do Windows) ou um horário informado (útil em testes). `forcar=True` processa sem esperar a estabilidade.

#### _ciclo (linhas 69–130)
- Linhas 70–75: lista os candidatos em ordem alfabética. Se a pasta de entrada sumiu, registra erro e devolve lista vazia (não derruba o robô).
- Linhas 77–81: para cada arquivo, lê tamanho e data de modificação; se não conseguir (arquivo sumiu no meio), pula.
- Linhas 82–83: a "assinatura" é o par (tamanho, modificação); busca a assinatura anterior na memória.
- Linhas 84–92: se o arquivo é novo ou mudou desde a última olhada, reinicia o cronômetro com a nova assinatura. Se for a primeira vez, registra "Novo arquivo detectado" e avisa a etapa "recepcao". Sem `forcar`, para por aqui neste ciclo (`continue` = vá para o próximo arquivo). Com `forcar`, segue em frente usando a assinatura recém-gravada.
- Linhas 93–94: se ainda não se passaram os segundos de estabilidade desde que a assinatura apareceu, espera o próximo ciclo. Exemplo: o OneDrive ainda está baixando um arquivo de 40 MB; o tamanho muda a cada olhada e o cronômetro fica reiniciando até o download terminar.
- Linhas 95–99: se o arquivo está aberto (Excel), anota em `em_uso` e só registra a mensagem na primeira vez (para não encher o log a cada 5 segundos).
- Linhas 100–101: liberado: tira de `em_uso` e marca como "processando".
- Linhas 102–109: chama `processar_arquivo`. Se der um erro inesperado, registra com detalhes, reinicia o cronômetro (nova tentativa após a espera) e segue para o próximo arquivo. O `finally` garante que "processando" volte a vazio em qualquer caso.
- Linhas 110–116: guarda o resultado. Se foi **ADIADO** (ex.: banco fora do ar ou arquivo de saída aberto no Power BI), anota o motivo e "empurra" o cronômetro 50 segundos para o futuro — somados aos 10 s de estabilidade, dá cerca de 1 minuto até nova tentativa. Se não foi adiado, esquece o arquivo (ele já foi movido para Originais ou Erros).
- Linhas 117–121: chama o aviso pós-processamento (painel). Se o aviso falhar, só registra; nunca atrapalha o processamento.
- Linhas 123–127: faxina da memória: esquece arquivos que não existem mais e limpa `em_uso`/`adiados` de nomes que saíram da pasta. O `&=` faz a "interseção" de conjuntos (mantém só o que está nos dois).
- Linhas 128–130: anota a hora do ciclo, roda a manutenção diária (se ainda não rodou hoje) e devolve os resultados.

#### estado_fila (linhas 132–157)
Monta, para o painel, a situação de cada arquivo da pasta.
- Linhas 134–139: pega o relógio e lista os candidatos; se não conseguir ler a pasta, devolve lista vazia.
- Linhas 140–145: para cada arquivo, cria um item com nome, tamanho e estado inicial "detectado".
- Linhas 146–155: decide o estado, nesta prioridade: "processando" → "adiado" (com motivo) → "em_uso" → "aguardando" (com os segundos que faltam para a estabilidade, nunca negativo).
- Linhas 156–157: adiciona à lista e devolve.

#### _manutencao_diaria (linhas 159–166)
- Se a data de hoje é diferente da última manutenção, anota hoje e roda `executar_manutencao`. Falhas são só registradas. Resultado: a manutenção roda no primeiro ciclo de cada dia (inclusive logo ao ligar o robô).

#### rodar (linhas 168–175)
- Linha 169: `parar` é um "sinal" (`Event`) que outra parte do programa (o painel) pode acionar para desligar o robô com elegância.
- Linhas 170–172: registra onde está monitorando e como encerrar.
- Linhas 173–175: enquanto ninguém pediu para parar: um ciclo, depois espera o intervalo. `parar.wait(...)` espera, mas acorda imediatamente se o sinal de parar for dado.

### Classe TravaInstancia (linhas 178–203)

Impede dois robôs rodando ao mesmo tempo (ex.: um ligado pela inicialização do Windows e outro aberto à mão).

- Linhas 181–184 (`__init__`): garante a pasta de logs e define o arquivo-trava `robo.lock`.
- Linhas 186–199 (`__enter__`, que roda ao entrar no `with`):
  - Linha 187: abre (ou cria) o arquivo-trava.
  - Linhas 189–192: no Windows (`os.name == "nt"`), usa `msvcrt.locking` para trancar o primeiro byte do arquivo sem esperar (`LK_NBLCK`).
  - Linhas 193–195: em Linux/Mac, usa `fcntl.flock` com trava exclusiva sem espera.
  - Linhas 196–198: se outro robô já tem a trava, o sistema operacional recusa; o arquivo é fechado e levanta-se um `RuntimeError` com mensagem clara (que `comandos.py` transforma em código de saída 3).
- Linhas 201–203 (`__exit__`, ao sair do `with`): fecha o arquivo, o que libera a trava. Como a trava é do sistema operacional, ela é liberada mesmo se o robô "morrer" de repente.

**Erros que este arquivo evita**
- Processar um arquivo pela metade enquanto o OneDrive ainda sincroniza.
- Brigar com o Excel por um arquivo aberto.
- Processar arquivos temporários ou de sistema (`~$planilha.xlsx`, `desktop.ini`).
- Dois robôs movendo o mesmo arquivo ao mesmo tempo.
- Um erro em um arquivo derrubar o robô inteiro.

---

## robo/pipeline.py

- **Para que serve:** é o "maestro" do processamento de **um** arquivo. Ele chama, em ordem, leitura → limpeza → validação → modelagem, passa pelas conferências de qualidade, carrega no banco (se ligado), grava a planilha tratada e arquiva o original. A regra de ouro é "tudo ou nada": se aparecer qualquer erro, nada é publicado.
- **Onde entra no fluxo:** é chamado por `monitor.py` e por `comandos.py` (`processar` e `diagnosticar`), além do painel. Chama `leitura`, `limpeza`, `validacao`, `modelagem`, `escrita`, `relatorio`, `historico` e, conforme o caso, `agentes`, `producao`, `quadro`, `banco`, `analise`, `excel` e `contratacao` (estes últimos são explicados nas outras partes do guia; aqui descrevemos só como o pipeline os usa).

### Docstring (linhas 1–13)

- Descreve as quatro fases (Extrair, Transformar, Carregar, Arquivar) e duas ideias centrais: a camada "bruto" do banco guarda até arquivos reprovados (para auditoria), enquanto "tratado" e "analitico" só recebem arquivos 100% aprovados; e problemas temporários geram status ADIADO (o arquivo fica em Bases-Limpeza e o robô tenta de novo sozinho).

### Imports (linhas 15–33)

- Linhas 17–22: `logging`, `shutil` (mover arquivos), `time` (cronometrar), `dataclass`/`field` (criar classes de dados com pouco código), `datetime` e `Path`.
- Linha 24: `pandas` (apelidado `pd`), a biblioteca de tabelas.
- Linhas 26–33: os módulos do robô. Note que `leitura` fornece também `EXTENSOES_SUPORTADAS` e `ErroLeitura`.

### Constantes de status (linhas 35–40)

- Linha 35: o diário.
- Linhas 37–40: os quatro resultados possíveis: `sucesso`, `reprovado`, `adiado` e `diagnostico` (este último é o status de quem só testou, sem gravar).

### Resultado (linhas 43–61)

- Uma **dataclass** é uma classe feita só para carregar dados, como uma "ficha". A ficha `Resultado` tem: arquivo, status, relatório, tabelas tratadas, arquivos gerados, tabelas gravadas no banco, linhas de entrada/saída, duração, para onde o original foi, o `id` do processamento, o motivo do adiamento, e os resultados dos andares seguintes (análise, checklists, Excel, conferências do "quadro" de pessoal). O `field(default_factory=dict)` cria um dicionário/lista **novo** para cada ficha (se todos compartilhassem o mesmo, um processamento "vazaria" para o outro).

### _Tratamento (linhas 64–71)

- Ficha interna com o que sai da etapa de tratamento: `brutas` (as abas como foram lidas), `tabelas` (prontas para gravar), `regra` aplicada, `modelo` (fato/dimensões), `linhas_entrada` e `analisaveis` (as tabelas limpas **antes** de virar fato/dimensões, usadas pela análise do 2º andar).

### _conferencias_equipe (linhas 74–94)

Roda as conferências do "quadro de pessoal" (os "funcionários virtuais" do robô, definidos em `robo/quadro.py`) para uma fase e anota os achados no relatório.

- Linha 80: importa o quadro só aqui (import preguiçoso).
- Linhas 81–83: para cada pessoa do quadro nesta fase que tem uma função de conferência, sinaliza ao painel que ela começou.
- Linha 84: executa as conferências da fase.
- Linhas 85–93: transforma cada achado em texto ("Cargo Nome: achado") e decide o nível: estagiário → sempre AVISO "Em observação (não bloqueia)"; se a fase bloqueia (`bloquear=True`) e a pessoa tem poder de bloquear → ERRO "Barrado na conferência da equipe"; caso contrário → AVISO.
- Linha 94: devolve os resultados para guardar na ficha.

### _carimbo (linhas 97–98)

- Devolve a data/hora atual como texto no formato `20261017_093012`. Esse formato ordena corretamente em ordem alfabética, por isso é usado em nomes de arquivo.

### _destino_livre (linhas 101–106)

- Encontra um nome que ainda não existe na pasta: tenta `nome.xlsx`; se existe, `nome_2.xlsx`, `nome_3.xlsx`... Evita sobrescrever um backup antigo.

### _mover (linhas 109–113)

- Garante que a pasta exista, escolhe um nome livre e move o arquivo. Devolve o caminho final.

### nome_base_tabela (linhas 116–118)

- Nome da tabela no banco: o `destino.tabela` da regra, se houver; senão, o nome do arquivo sem extensão. Sempre padronizado (ex.: `NPS Outubro.xlsx` → `nps_outubro`).

### _sinal (linhas 121–127)

- Avisa o painel (o "escritório 3D") que uma etapa começou. Se o aviso falhar, registra só em nível de depuração e **nunca** interrompe o processamento — o painel é um enfeite útil, não pode derrubar o trabalho.

### _CACHE_EQUIPE e obter_equipe (linhas 130–149)

A "equipe de agentes" são passos extras de tratamento definidos por você em YAML (pasta `agentes/`) e em Python (pasta `habilidades_personalizadas/`).

- Linha 130: um **cache** — uma memória para não refazer trabalho caro.
- Linha 135: importa a classe `Equipe`.
- Linhas 137–140: a "assinatura" de uma pasta é a lista (nome, data de modificação) de cada arquivo. Se você editar um agente, a data muda e a assinatura muda.
- Linhas 142–146: se a equipe já foi montada e nenhuma assinatura mudou, reaproveita.
- Linhas 147–149: senão, monta a equipe de novo e guarda. Resultado prático: você pode editar um agente com o robô ligado e ele passa a valer no próximo arquivo, sem reiniciar.

### _tratar (linhas 152–203)

O tratamento propriamente dito (Extrair + Transformar).

- Linhas 153–155: cria a ficha já com a regra do arquivo (via `cfg.regra_para`) e anota qual regra foi aplicada.
- Linhas 157–159: se a extensão não é suportada (ex.: `.pdf`), registra erro e para.
- Linhas 160–166: sinaliza "leitura" e chama `ler_arquivo`. A regra pode trocar o modo de abas (`abas`); senão vale o geral. Se a leitura falhar (`ErroLeitura`: arquivo corrompido, com senha...), vira erro no relatório.
- Linhas 167–169: nenhuma aba com dados → erro.
- Linha 171: soma as linhas de todas as abas lidas (é o "linhas de entrada" do histórico).
- Linha 172: obtém a equipe de agentes.
- Linhas 173–174: o modelo estrela (fato/dimensões) só é aplicado quando há **uma** tabela; com várias abas separadas ele é ignorado.
- Linhas 175–178: para cada aba: o nome da tabela é o `nome_aba` da configuração (padrão `dados`) quando há uma só, ou o nome da própria aba quando há várias. Registra onde estava o cabeçalho e o tamanho. Exemplo: "Aba 'Respostas' lida: cabeçalho na linha 4, 1.250 linhas, 18 colunas".
- Linhas 179–181: se abas com o mesmo cabeçalho foram empilhadas (ex.: Jan, Fev, Mar), registra quais e lembra da coluna `_aba_origem`.
- Linhas 182–184: se abas com estrutura diferente foram deixadas de fora, registra um AVISO (nada é ignorado em silêncio) e sugere `abas: todas`.
- Linhas 185–187: sinaliza "limpeza", roda `limpar_tabela` e depois os agentes da fase "limpeza".
- Linhas 188–191: sinaliza "validacao", roda `validar_tabela` (que só anota erros, não altera a tabela) e depois os agentes das fases "validacao" e "modelagem".
- Linha 192: guarda a tabela limpa em `analisaveis` (antes de virar fato/dimensões).
- Linhas 193–195: sinaliza "modelagem" e chama `modelar`; cada tabela resultante entra em `t.tabelas` com o índice reiniciado (`reset_index(drop=True)`): na saída final não faz sentido manter o número da linha do Excel como índice.
- Linhas 197–202: se as colunas de auditoria estão ligadas, acrescenta em toda tabela que não começa com `dim_` duas colunas: `_arquivo_origem` (nome do arquivo) e `_processado_em` (data/hora sem microssegundos). No Power BI isso permite saber de qual arquivo veio cada linha.
- Linha 203: devolve a ficha.

### _resumo_tabelas (linhas 206–208)

- Para cada tabela, devolve nome, número de linhas e a lista de colunas com o tipo "amigável" (Texto, Número inteiro, Data...). Vai para o histórico detalhado usado pelo painel.

### _carregar_banco (linhas 211–248)

Carga no PostgreSQL, com **uma transação por arquivo**.

- Linhas 214–219: importa o banco, cria o objeto, cria o banco de dados se ainda não existir e calcula o nome-base das tabelas.
- Linha 220: abre a conexão (com `with`, ela é fechada no final de qualquer jeito).
- Linhas 222–235: dentro de uma transação:
  - prepara a estrutura (schemas/tabelas de controle);
  - se configurado, grava a camada **bruto** (o que chegou, mesmo que reprovado);
  - se aprovado: grava a camada **tratado** (respeitando `destino` e `modelo` da regra), sinaliza a "DBA", **reconcilia** (confere no banco, antes de confirmar, se o que foi gravado bate com o esperado) e executa os modelos SQL da camada analítica;
  - registra o "lote" (a ficha da carga) com `_dados_lote`.
- Linhas 236–245: se o banco recusar os dados (`ErroCargaDados`), a transação inteira é desfeita automaticamente. O robô registra o erro e, numa **nova** transação, guarda só o bruto e o lote como reprovado — assim a auditoria não perde o registro do que chegou.
- Linhas 246–248: anota no relatório as tabelas gravadas e devolve a lista.
- Observação: se o banco estiver fora do ar, a exceção `ErroBancoIndisponivel` não é capturada aqui; ela "sobe" para `processar_arquivo`, que adia o arquivo.

### _dados_lote (linhas 251–259)

- Monta a ficha do lote para o banco: id, arquivo, status, linhas de entrada, linhas de saída (só das tabelas que não são `dim_`, e zero se reprovado), contagem de erros e avisos, tabelas gravadas, as mensagens de erro juntas (cortadas em 2.000 caracteres) e todas as ocorrências que não são INFO.

### processar_arquivo (linhas 262–434)

A função principal deste arquivo.

- Linhas 265–268: liga o cronômetro, cria o relatório e registra "Processando..." ou, no diagnóstico, "Testando... (sem gravar nada)".
- Linhas 270–275: roda `_tratar`. Qualquer erro inesperado é capturado, registrado com detalhes e vira um ERRO no relatório, com uma ficha vazia — o robô nunca cai por causa de um arquivo estranho. No diagnóstico, os sinais ao painel são desligados.
- Linhas 277–278: cria a ficha de resultado com status provisório "diagnostico" e conta as linhas de saída (sem as dimensões).
- Linhas 279–281: no diagnóstico, para aqui e devolve. Repare: as conferências de produção (supervisor, quadro, checklist) e a gravação ficam de fora do diagnóstico.
- Linhas 283–287: cria as pastas, gera o carimbo de data/hora e define o **id** do processamento: é o nome que o original terá no "arquivo morto" (Bases-Erros se já há erros; senão `Bases-Originais/AAAA-MM`). Exemplo: `20261017_093012_nps_outubro`. O mesmo id liga o arquivo arquivado, o lote do banco e o histórico do painel.
- Linhas 289–298: **portão de produção** — se até aqui não há erros e há tabelas, o "supervisor" (`producao.conferencia_supervisor`) faz uma conferência independente ("quem faz não é quem aprova"). Se a própria conferência falhar, isso vira erro (por segurança, na dúvida não publica).
- Linhas 300–305: monta o "contexto" com tudo o que os conferentes precisam (arquivo, configuração, regra, tabelas brutas, limpas e finais) e roda a conferência da fase "engenharia" com poder de bloqueio.
- Linhas 307–318: se o banco está habilitado, sinaliza e carrega (antes de gravar arquivos: se o banco recusar, a planilha não é publicada). Banco fora do ar → **ADIADO** (linhas 313–315). Outro erro inesperado → ERRO no relatório (linhas 316–318).
- Linhas 320–332: se não há erros, a "Coordenadora de Engenharia" (`producao.checklist_engenharia`) avalia um checklist com as conferências, a equipe, se o banco está ligado e se a carga gravou algo. Se algum item não estiver OK, cada um vira ERRO; senão, registra "Liberado para produção".
- Linha 333: sinaliza "publicacao".
- Linhas 335–343: `reprovar()` é uma função **dentro** da função (só existe aqui). Ela: marca REPROVADO e zera linhas de saída; recalcula o id para ficar livre em Bases-Erros; move o original para lá; grava ao lado o relatório `<id>_ERROS.txt` (em `utf-8-sig`, para o Bloco de Notas abrir os acentos certos); e registra um aviso no log.
- Linhas 345–350: se não há erros e o formato não é `nenhum`, monta o nome do arquivo de saída (nome original + sufixo + carimbo, se versionar) e grava com `gravar_tabelas`.
- Linhas 351–353: se a gravação der `PermissionError` (o arquivo tratado está aberto no Excel ou Power BI), o arquivo é **ADIADO**.
- Linhas 354–355: avisos da gravação (ex.: virou CSV por ser grande demais) entram no relatório.
- Linhas 356–358: a conferência da fase "publicacao" relê o que foi gravado em disco, com poder de bloqueio.
- Linhas 359–365: se essa releitura acusar erro, apaga os arquivos recém-gravados; se o banco já tinha confirmado a carga, registra um erro pedindo que a DBA confira/remova o lote; e zera a lista de saídas.
- Linhas 367–368: havendo qualquer erro → `reprovar()`.
- Linhas 369–377: senão: recalcula o nome-base (mesma regra das linhas 346–348), marca SUCESSO, move o original para `Bases-Originais/AAAA-MM` com o nome do id, grava o relatório de qualidade e registra o "OK" com destinos, linhas e avisos.
- Linhas 378–394: **2º andar** (análise automática). Como a planilha já foi publicada, nada aqui pode reprovar: qualquer falha só é registrada (linha 394). Se houver análise, roda as conferências da fase "analise" sem bloqueio, o checklist da análise e gera uma "manchete".
- Linhas 395–411: **3º andar** (Sala Excel): gera a entrega com fórmulas; roda a conferência "excel" sem bloqueio; anota se houve divergências. Falhas só são registradas.
- Linhas 412–416: **4º andar** (governança de dados pessoais e catálogo): conferências sem bloqueio.
- Linhas 417–425: "RH": registra observações dos estagiários, avalia o fim de experiências e possíveis "contratações" automáticas, anotando no relatório. Falhas só são registradas.
- Linhas 427–430: fecha o cronômetro; em caso de sucesso, roda a conferência da fase "fim" (sem bloqueio e sem sinais ao painel).
- Linhas 431–434: registra no histórico (`_registrar`), sinaliza "concluido" com status, linhas, erros e se gravou no banco, e devolve o resultado.

### _adiar (linhas 437–442)

- Marca ADIADO, guarda o motivo, mede a duração e registra "Tentarei de novo em instantes". O arquivo **não** é movido: continua em Bases-Limpeza, e o monitor tenta de novo em ~1 minuto. Repare que um adiamento também não passa por `_registrar` (não entra no histórico).

### _registrar (linhas 445–467)

- Linha 446: data/hora atual.
- Linha 447: grava no resumo consolidado de ocorrências (em Bases-Relatorios) todos os erros e avisos deste arquivo.
- Linhas 448–453: acrescenta uma linha no `historico_processamentos.csv`: data, arquivo, status, linhas, erros, avisos, duração (com vírgula decimal, para o Excel brasileiro), saídas e id.
- Linhas 454–467: grava o JSON detalhado `logs/execucoes/<id>.json`, usado pelo painel: tudo da ficha, inclusive o resumo das tabelas (só em caso de sucesso), a análise sem os campos internos (os que começam com `_`), checklists, Excel, quadro e todas as ocorrências.

### _gravar_relatorio_qualidade (linhas 470–481)

- Grava em Bases-Relatorios (fora da pasta que o Power BI lê, para não poluir o modelo) um Excel `<nome>_qualidade.xlsx` com as abas `log_qualidade` (todas as ocorrências), `dicionario_dados` (perfil de cada coluna) e, se houver, `checklist_producao`.
- Linhas 480–481: se esse relatório estiver aberto no Excel, só registra um aviso — não reprova um arquivo já publicado por causa do relatório.

**Erros que este arquivo evita**
- Publicar uma planilha "meio certa" (tudo ou nada).
- Perder um arquivo por problema temporário (banco fora do ar, saída aberta no Power BI → ADIADO).
- Sobrescrever backups (nomes livres com `_2`, `_3`...).
- Um erro inesperado em um arquivo derrubar o robô.
- Publicar no Power BI algo que o banco recusou (o banco é carregado antes dos arquivos).
- Perder a auditoria do que chegou (camada bruto, mesmo para reprovados).

---

## robo/leitura.py

- **Para que serve:** abre a planilha (Excel ou texto), descobre sozinho a codificação e o separador de CSVs, encontra a linha de cabeçalho mesmo quando há títulos acima da tabela, trata células mescladas e empilha abas com o mesmo formato (ex.: uma aba por mês). A decisão mais importante: o índice de cada tabela é o **número da linha no arquivo original**, para que os relatórios digam "linha 57" exatamente como você vê no Excel.
- **Onde entra no fluxo:** é chamado por `pipeline._tratar` (função `ler_arquivo`). Ele usa `limpeza.normalizar_nome_coluna` para comparar cabeçalhos entre abas.

### Docstring (linhas 1–6)

- Descreve os formatos aceitos e a decisão do índice = número da linha do Excel.

### Imports (linhas 8–15)

- `csv` (para detectar separador), `io` (tratar um texto na memória como se fosse arquivo), `Path`, `pandas` e `load_workbook` do **openpyxl** (biblioteca que abre arquivos `.xlsx` diretamente).

### Constantes (linhas 17–23)

- Linhas 17–19: extensões de Excel (`.xlsx`, `.xlsm`, `.xls`), de texto (`.csv`, `.txt`) e a união das duas (`|` une conjuntos).
- Linha 21: codificações testadas, nesta ordem: `utf-8-sig` (UTF-8 com ou sem BOM), `cp1252` (o padrão do Excel brasileiro no Windows ao salvar CSV) e `latin-1`.
- Linha 22: até 30 MB o Excel é aberto "completo" para enxergar células mescladas; acima disso, é aberto em modo leve (mais rápido e econômico, mas sem informação de mesclas).
- Linha 23: separadores aceitos: `;`, `,`, tabulação e `|`.

### ErroLeitura (linhas 26–27)

- Exceção própria para problemas de leitura. O pipeline a captura e transforma em ERRO no relatório.

### _vazio (linhas 30–38)

Decide se um valor é "vazio".

- Linhas 31–32: `None` (nada) é vazio.
- Linhas 33–34: texto só com espaços é vazio (`"   "` → vazio).
- Linhas 35–38: para outros valores, pergunta ao pandas se é "nulo" (NaN, NaT). Se a pergunta não fizer sentido para aquele valor, considera não vazio.

### _decodificar (linhas 41–47)

- Tenta transformar os bytes do arquivo em texto com cada codificação, na ordem. A primeira que funcionar vence. Se nenhuma funcionar, levanta `ErroLeitura`. Por que a ordem importa: um arquivo UTF-8 lido como cp1252 viraria "SÃ£o Paulo"; testando UTF-8 primeiro isso é evitado. (Na prática, `latin-1` aceita qualquer sequência de bytes, então é a "rede de segurança".)

### _detectar_separador (linhas 50–57)

- Linha 51: usa só as 50 primeiras linhas como amostra.
- Linhas 52–53: pede ao "farejador" (`csv.Sniffer`) do Python para descobrir o separador entre os aceitos.
- Linhas 54–57: se o farejador não conseguir, conta quantas vezes cada separador aparece e escolhe o mais frequente; se nenhum aparecer, usa `;` (padrão brasileiro).

### _ler_openpyxl (linhas 60–94)

Leitura dos `.xlsx`/`.xlsm`.

- Linhas 61–70 (docstring): explica **por que não usar o leitor padrão do pandas**: ele transforma células com erro de fórmula (`#REF!`, `#DIV/0!`, `#N/D`) em vazio sem avisar. Lendo pelo openpyxl, essas células chegam como texto e o robô consegue acusá-las. `data_only=True` lê o **resultado** da fórmula (o que aparece na tela), não a fórmula. Abas ocultas são ignoradas. E descreve o tratamento de mesclas.
- Linha 71: decide se abre completo (até 30 MB).
- Linha 72: abre a pasta de trabalho; modo leve (`read_only`) para arquivos grandes.
- Linhas 73–76: para cada aba, pula as que não estão visíveis (ocultas ou "muito ocultas").
- Linha 78: transforma todas as linhas da aba em um DataFrame "cru", sem cabeçalho ainda, com tipo `object` (cada célula mantém exatamente o valor que tinha: texto, número, data).
- Linhas 79–89: se abriu completo e há mesclas, analisa cada intervalo mesclado (convertendo de "linha 1 do Excel" para "posição 0 do Python", por isso o `- 1`):
  - Linhas 83–84: ignora mesclas fora da área com dados.
  - Linha 85: o valor da mescla fica na primeira célula (canto superior esquerdo).
  - Linhas 86–87: mescla **vertical** numa só coluna → repete o valor em todas as linhas. Exemplo: a célula "Sul" mesclada de A5 a A7 → as lojas das linhas 5, 6 e 7 ficam todas com região "Sul" (sem isso, só a linha 5 teria região e as outras ficariam vazias).
  - Linhas 88–89: mescla **horizontal** numa só linha → guarda (linha no padrão Excel, coluna inicial, coluna final, valor) para usar como rótulo de grupo. Exemplo: "Atendimento" mesclado sobre as colunas "Nota" e "Comentário".
  - Mesclas em bloco (várias linhas e várias colunas) não entram em nenhum dos dois casos.
- Linha 90: guarda as mesclas horizontais nos `attrs` do DataFrame (um "bolso" de informações extras que acompanha a tabela).
- Linha 91: guarda a aba pelo título.
- Linhas 93–94: `finally` garante que o arquivo seja fechado, mesmo se der erro (senão o Windows poderia mantê-lo bloqueado).

### _ler_brutos (linhas 97–125)

Escolhe como ler conforme a extensão.

- Linhas 99–104: `.xlsx`/`.xlsm` → `_ler_openpyxl`. Qualquer erro (corrompido, protegido por senha) vira `ErroLeitura` com uma mensagem que explica o que verificar.
- Linhas 105–113: `.xls` (formato antigo) → leitor do pandas com o motor `xlrd`, lendo todas as abas, sem cabeçalho e sem adivinhar tipos (`dtype=object`). Se faltar a biblioteca `xlrd`, a mensagem pede para rodar o `instalar.bat` de novo.
- Linhas 114–124: `.csv`/`.txt` → lê os bytes, decodifica; se o texto for vazio, devolve "nenhuma aba"; detecta o separador e lê tudo como texto (`dtype=str`), sem transformar "NA" em vazio automaticamente (`keep_default_na=False` — quem decide o que é vazio é a limpeza, com a sua lista de `valores_nulos`) e **sem pular linhas em branco** (`skip_blank_lines=False`), para que a contagem de linhas continue batendo com o arquivo. O "nome da aba" de um CSV é o nome do arquivo sem extensão.
- Linha 125: qualquer outra extensão → `ErroLeitura`.

### _localizar_cabecalho (linhas 128–144)

Acha a linha do cabeçalho, ignorando títulos soltos acima da tabela.

- Linha 134: olha só as primeiras N linhas (padrão 20).
- Linhas 135–136: conta quantas células preenchidas cada linha tem e pega o maior número.
- Linhas 137–143: percorre as linhas em ordem; pula as vazias ou com menos de 60% do máximo de células preenchidas; a primeira linha restante em que pelo menos metade das células é **texto** é o cabeçalho.
- Linha 144: se nenhuma linha passar no critério, usa a primeira.
- Exemplo: linha 1 "Pesquisa NPS – Outubro" (1 célula), linha 2 vazia, linha 3 "Gerado em 01/11" (1 célula), linha 4 "ID | Data | Nota | Curso" (4 textos), linha 5 em diante dados. As linhas 1 e 3 têm só 1 célula (menos de 60% de 4) e são puladas; a linha 4 é toda texto → é o cabeçalho.

### _montar_tabela (linhas 147–165)

Transforma a aba crua em tabela com cabeçalho.

- Linha 148: trabalha numa cópia.
- Linha 150: o índice passa a ser 1, 2, 3... — exatamente o número da linha no Excel (linha 1 = primeira linha da aba).
- Linha 151: troca todo valor "vazio" por `pd.NA` (o marcador oficial de vazio do pandas).
- Linha 152: remove linhas totalmente vazias e colunas totalmente vazias. Como o índice já foi fixado antes, a numeração continua a do Excel mesmo removendo linhas.
- Linhas 153–154: aba sem nada → `None`.
- Linhas 155–158: localiza a posição do cabeçalho, descobre o número da linha do Excel correspondente, pega os valores do cabeçalho e separa o "corpo" (tudo abaixo).
- Linhas 159–161: cada nome de coluna vazio vira `coluna_1`, `coluna_2`... (pela posição); os outros têm espaços repetidos e quebras de linha reduzidos a um espaço (ex.: `"Nota\n  NPS"` → `"Nota NPS"`).
- Linha 162: resolve nomes repetidos com `_desempatar`, usando as posições originais das colunas e os rótulos de grupo da linha de cima.
- Linhas 163–165: aplica os nomes, guarda a linha do cabeçalho nos `attrs` e devolve.

### _grupos_acima (linhas 168–175)

- Para cada mescla horizontal que esteja **exatamente na linha acima do cabeçalho** e tenha valor, associa esse valor a cada coluna coberta. Devolve um dicionário "posição da coluna → rótulo do grupo".

### _desempatar (linhas 178–190)

- Linhas 180–182: conta quantas vezes cada nome aparece (sem diferenciar maiúsculas).
- Linhas 183–186: se o nome é repetido e a coluna tem grupo, prefixa o grupo: "Nota" sob "Atendimento" vira "Atendimento Nota"; sob "Produto", "Produto Nota".
- Linhas 187–189: se mesmo assim repetir, a 2ª ocorrência vira "Nota (2)", a 3ª "Nota (3)"...
- Por que isso importa: sem desempate, duas colunas "Nota" causariam confusão em todas as etapas seguintes.

### ler_arquivo (linhas 193–207)

A função pública de leitura.

- Linhas 195–197: se o arquivo não existe, `ErroLeitura`.
- Linha 198: lê as abas cruas.
- Linhas 199–204: monta cada aba; abas sem dados são descartadas.
- Linhas 205–206: no modo `primeira` (padrão), chama `_empilhar_abas_iguais`.
- Linha 207: no modo `todas`, devolve todas as abas separadas.

### _empilhar_abas_iguais (linhas 210–235)

- Linhas 211–215 (docstring): a primeira aba com dados é a principal; as outras com **exatamente** o mesmo cabeçalho são empilhadas embaixo (ex.: Jan, Fev, Mar); as diferentes (instruções, resumos) ficam de fora, mas são listadas para o relatório avisar. Nas abas empilhadas, a "linha" vira `Aba!linha` (ex.: `Fev!12`).
- Linha 216: importa a padronização de nomes da limpeza.
- Linhas 217–219: a "assinatura" de uma aba é a lista de nomes de coluna padronizados (assim "Nota NPS" e "nota nps" contam como iguais).
- Linhas 220–221: separa as abas iguais à primeira das diferentes.
- Linhas 222–231: se há iguais, para cada uma (incluindo a primeira): copia, troca o índice para `Aba!linha`, cria a coluna `_aba_origem` com o nome da aba, e junta todas (`pd.concat`, o "empilhar" do pandas). Guarda a linha do cabeçalho da primeira e a lista de abas empilhadas.
- Linhas 232–233: se não há iguais, fica só a primeira aba (índice continua sendo o número da linha simples).
- Linhas 234–235: guarda a lista das ignoradas e devolve **uma** tabela com o nome da primeira aba.

**Erros que este arquivo evita**
- Erros de fórmula do Excel virarem vazio sem ninguém perceber.
- Acentos estragados em CSV ("SÃ£o Paulo").
- Ler o título do relatório como se fosse o cabeçalho.
- Perder a informação de células mescladas (região, grupo de perguntas).
- Colunas com nomes repetidos.
- Abas de instruções sendo misturadas com dados — e, ao mesmo tempo, abas de dados ignoradas em silêncio.
- Relatório apontando a linha errada (o índice é a linha real do Excel).

---

## robo/limpeza.py

- **Para que serve:** padroniza a tabela lida: acusa erros de fórmula, deixa os nomes das colunas no padrão (`data_de_admissao`), aplica sinônimos/renomeações/remoções da regra, limpa espaços e marcadores de vazio, remove linhas de Total, descobre (ou força) o tipo de cada coluna — número, data ou texto — e remove linhas duplicadas. Tudo fica registrado no relatório.
- **Onde entra no fluxo:** é chamado por `pipeline._tratar` (`limpar_tabela`). Suas funções utilitárias (`normalizar_nome_coluna`, `sem_acento`, `_texto_de`, `_converter`...) também são usadas por `leitura`, `validacao`, `modelagem`, `banco`, `habilidades` e outros. Ele usa `relatorio.Relatorio` para anotar o que fez.

### Docstring (linhas 1–13)

- Lista as 9 etapas, na ordem em que acontecem.

### Imports (linhas 15–25)

- `fnmatch` (curingas), `re` (**regex**, ou expressões regulares: uma "mini-linguagem" para descrever padrões de texto, como "começa com R$ e depois vem um número"), `unicodedata` (separar letras de acentos), `date`/`datetime`, `numpy` (apelido `np`, a biblioteca numérica sobre a qual o pandas é construído), `pandas` e `Relatorio`.

### ERROS_EXCEL (linhas 27–30)

- Conjunto com os textos de erro do Excel em inglês e português, já em minúsculas: `#ref!`, `#div/0!`, `#valor!`, `#nome?`, `#n/d`, `#despejar!` etc.

### FORMATOS_DATA (linhas 32–36)

- Formatos de data aceitos, tentados nesta ordem: brasileiro (`31/12/2025`, com ou sem hora, e com ano de 2 dígitos), ISO (`2025-12-31`, inclusive com `T` entre data e hora), `31-12-2025`, `31.12.2025` e `2025/12/31`. Como o brasileiro vem primeiro, `01/02/2025` é lido como **1º de fevereiro** (nunca 2 de janeiro).

### Expressões regulares (linhas 38–43)

- Linha 38: `_RE_MOEDA` — símbolo de moeda no começo (`R$`, `US$`, `U$S`, `$`, `€`, `£`), seguido de espaços.
- Linha 39: `_RE_NUM_VIRGULA` — número no formato brasileiro: `1.234,56`, `1234,5`, `12` (pontos só como separador de milhar, a cada 3 dígitos).
- Linha 40: `_RE_NUM_PONTO` — formato americano: `1,234.56`, `1234.5`, `12`.
- Linha 41: `_RE_TOTAL` — o texto inteiro é "Total", "Subtotal", "Sub-total", "Total Geral", com ou sem dois-pontos.
- Linha 42: `_RE_COMECA_TOTAL` — o texto **começa** com a palavra "Total" ou "Subtotal" (ex.: "Total Sul", mas também "Total Express").
- Linha 43: `_RE_SUBTOTAL` — começa com "Subtotal"/"Sub-total".

### MESES, datas por extenso e serial do Excel (linhas 45–49)

- Linhas 45–46: dicionário das 3 primeiras letras do mês (português e inglês) → número do mês.
- Linha 47: `_RE_DATA_EXTENSO` — dia + mês por extenso + ano: `05-fev-2025`, `6 de fevereiro de 2025`, `5/fev/25`.
- Linha 48: `_RE_MES_ANO` — mês + ano: `fev/2025`, `fevereiro de 2025`.
- Linha 49: por baixo de uma data, o Excel guarda um número (dias desde 30/12/1899). Só números entre 20.000 e 80.000 (anos ~1954 a ~2119) podem ser considerados datas.

### TIPOS_VALIDOS (linha 51)

- Tipos que você pode forçar na regra: `texto`, `inteiro`, `decimal`, `data`, `datahora`.

### sem_acento (linhas 57–58)

- Decompõe cada letra (ex.: "ã" vira "a" + "~") e descarta os acentos. "Avaliação" → "Avaliacao".

### normalizar_nome_coluna (linhas 61–70)

- Linha 63: tira acento, põe em minúsculas, tira espaços das pontas.
- Linha 64: lembra se o nome começava com `_` (colunas de controle do robô, como `_aba_origem`).
- Linha 65: tudo que não for letra ou número vira `_`, e `_` das pontas são retirados. "Data de Admissão (R$)" → `data_de_admissao_r`.
- Linhas 66–67: se não sobrou nada (ex.: "???"), vira `coluna`.
- Linhas 68–69: se começa com número, ganha `c_` na frente ("2025" → `c_2025`), porque bancos de dados e o Power BI lidam mal com nomes começando por dígito.
- Linha 70: devolve, recolocando o `_` inicial se era coluna de controle.

### _nomes_unicos (linhas 73–88)

- Garante nomes únicos **depois** da padronização. Exemplo: "Nota" e "nota " viram as duas `nota`; a segunda passa a `nota_2`. O laço das linhas 80–82 cuida do caso raro em que `nota_2` já existia de verdade (aí tenta `nota_3`...).

### _eh_numero_nativo (linhas 91–92)

- `True` se o valor já é número de verdade (veio como número da célula do Excel), excluindo Verdadeiro/Falso (que no Python também contam como número).

### _eh_data_nativa (linhas 95–96)

- `True` se o valor já é uma data de verdade (célula formatada como data no Excel).

### _texto_de (linhas 99–105)

- Linhas 101–102: número decimal sem casas (ex.: `123.0`) vira `"123"` — sem o `.0` que apareceria ao transformar em texto.
- Linhas 103–104: data/hora vira texto brasileiro: `31/12/2025` ou, se tiver hora, `31/12/2025 14:30:00`.
- Linha 105: o resto vira texto normalmente.

### numero_de (linhas 108–138)

Converte textos de número escritos "do jeito humano" em número.

- Linhas 110–111: se já é número, devolve como decimal (ou `None` se for vazio/NaN).
- Linhas 112–113: se não é texto, não é número → `None`.
- Linha 114: tira espaços das pontas e troca o espaço "não separável" (aquele que vem de páginas web e do Excel, invisível) por espaço normal.
- Linhas 115–117: `(1.000)` — parênteses, como na contabilidade → negativo.
- Linhas 118–119: sinal de menos antes.
- Linha 120: tira o símbolo de moeda.
- Linhas 121–122: sinal de menos depois da moeda (`R$ -10`).
- Linhas 123–125: `%` no final → marca como percentual e tira o símbolo.
- Linha 126: tira espaços internos (`1 234,56` → `1234,56`).
- Linhas 127–134: confere se o texto bate com o formato esperado (brasileiro ou americano, conforme o parâmetro `decimal`). Se não bater → `None`. Se bater, transforma no formato que o Python entende: no brasileiro, tira os pontos e troca vírgula por ponto (`1.234,56` → `1234.56`); no americano, tira as vírgulas.
- Linhas 135–138: converte, divide por 100 se era percentual (`45%` → `0,45`) e aplica o sinal.
- Exemplos: `"R$ 1.234,56"` → 1234,56; `"(500)"` → -500; `"12,5%"` → 0,125; `"abc"` → `None`.

### data_de (linhas 141–174)

Converte um valor em data.

- Linhas 145–149: se já é data, padroniza para `Timestamp` (o tipo de data do pandas); datas fora do intervalo suportado → `None`.
- Linhas 150–151: com `serial=True`, um número entre 20.000 e 80.000 vira data contando dias a partir de 30/12/1899 (ex.: 45697 → 10/02/2025). A docstring (linhas 142–144) explica o porquê da cautela: isso só é permitido quando a coluna **já tem** datas escritas como texto; um número solto nunca vira data (senão uma coluna de "valor da venda" com 45.000 viraria datas).
- Linhas 152–154: não é texto → `None`; senão tira espaços das pontas.
- Linhas 155–159: tenta cada formato de `FORMATOS_DATA`.
- Linhas 160–168: tira acentos, põe em minúsculas e tenta "dia mês-por-extenso ano"; se não der, "mês ano" (dia vira 1). O mês é reconhecido pelas 3 primeiras letras. Se nada casar → `None`.
- Linhas 169–170: ano de 2 dígitos: abaixo de 70 → 2000+ (`25` → 2025); senão 1900+ (`85` → 1985).
- Linhas 171–174: monta a data; se for impossível (ex.: 31 de fevereiro) → `None`.

### _detectar_decimal (linhas 177–181)

- Conta quantos textos da coluna funcionam como número no formato brasileiro e quantos no americano; usa o americano só se ele ganhar. Empate → vírgula (brasileiro). Exemplo: `"1.234"` funciona nos dois; com empate, vira mil duzentos e trinta e quatro (padrão BR).

### _linhas (linhas 184–185)

- Monta até 5 exemplos "linha X" a partir de uma máscara. (Observação: neste arquivo esta função não é usada; `validacao.py` tem a sua própria versão.)

### _eh_identificador (linhas 188–189)

- `True` se o nome da coluna casa com algum padrão de identificador (`cpf*`, `*_id`, `matricula*`...).

### _como_numero (linhas 195–201)

- Linhas 196–197: converte cada valor com `numero_de` (vazios ficam vazios), mantendo o índice (números de linha). Uma **máscara**, termo que aparece muito daqui em diante, é uma coluna de Verdadeiro/Falso dizendo, linha a linha, quem atende a uma condição.
- Linhas 198–200: se todos os valores preenchidos são inteiros (e menores que 2^53, limite em que o decimal ainda representa inteiros com exatidão), usa o tipo `Int64` (inteiro que aceita vazio). Assim a nota `9` não aparece como `9.0` no Power BI.
- Linha 201: senão, fica decimal.

### _como_data (linhas 204–206)

- Converte cada valor com `data_de` (vazios viram `NaT`, o "vazio" de datas) e guarda como coluna de data.

### _como_texto (linhas 209–210)

- Converte cada valor em texto com `_texto_de`; vazios continuam vazios.

### _converter (linhas 213–228)

Conversão para um tipo **forçado** pela regra.

- Linhas 214–223: `inteiro` ou `decimal` → converte para número. Para `decimal`, força decimal. Para `inteiro`, se houver valor com casas decimais, devolve a coluna decimal mesmo assim (linha 221) para a etapa 7 acusar o erro; senão converte para `Int64`.
- Linhas 224–225: `data` → converte e zera a hora (`normalize`): `31/12/2025 14:30` vira `31/12/2025`.
- Linhas 226–227: `datahora` → mantém a hora.
- Linha 228: qualquer outro (na prática, `texto`) → texto.

### _inferir (linhas 231–268)

Descobre sozinho o tipo de uma coluna (quando a regra não força).

- Linhas 232–234: coluna sem nenhum valor → texto.
- Linhas 235–236: nome de identificador → texto (sempre).
- Linhas 238–241: se algum texto é só dígitos, com mais de 1 caractere, começando com zero (ex.: matrícula `00123`, CEP `01310`), a coluna inteira fica texto — para não perder os zeros à esquerda.
- Linhas 243–244: lê o limiar (95%) e o total de valores preenchidos.
- Linhas 246–249: se todos já são números de verdade → número; se todos já são datas de verdade → data.
- Linhas 251–258: detecta o separador decimal, conta quantos valores viram número. Se ≥ 95%: converte, avisa sobre os valores que foram esvaziados por não serem número, e registra se havia percentuais convertidos.
- Linhas 260–266: tenta data. O `serial` só é ligado se pelo menos um texto da coluna for data escrita (ver `data_de`). Se ≥ 95% viram data: converte e avisa sobre os esvaziados.
- Linha 268: nada disso → texto.
- Exemplo: coluna "Valor" com `R$ 10,00`, `R$ 25,50`, ..., e 2 células `sem valor` entre 100 → 98% numérico → vira número; o relatório avisa "Valores que não são número foram esvaziados" com os exemplos e as linhas.

### _registrar_perdas (linhas 271–276)

- Compara o original com o convertido: quem tinha valor e ficou vazio foi "perdido". Se houver algum, registra AVISO com quantidade e até 5 exemplos (`linha 57: 'sem valor'`).

### limpar_tabela (linhas 282–429)

A função principal: aplica as 9 etapas, nesta ordem.

- Linhas 283–284: trabalha numa cópia e guarda quantas linhas havia.

**Etapa 1 — erros de fórmula (linhas 286–298)**
- Linha 288: para cada coluna, marca as células cujo texto é um erro do Excel.
- Linhas 289–296: se houver, monta exemplos (`linha 12: #REF!`). No modo `anular` registra AVISO; no padrão (`erro`) registra ERRO, que reprova o arquivo.
- Linha 298: nos dois modos, a célula é esvaziada — o comentário explica: assim as próximas etapas enxergam o restante da coluna normalmente (ex.: a detecção de tipo não "estraga" por causa de um `#DIV/0!`).

**Etapa 2 — nomes de colunas (linhas 300–306)**
- Padroniza todos os nomes, garante unicidade e registra (INFO) quais mudaram, ex.: `'Nota NPS' -> nota_nps`.

**Etapa 3a — sinônimos (linhas 308–317)**
- Para cada nome "oficial" da regra: se a coluna oficial já existe, nada a fazer; senão, procura a primeira alternativa que exista no arquivo e renomeia. Exemplo: regra `sinonimos: {nota_nps: [nota, nps, nota_recomendacao]}` → num mês o arquivo veio com "Nota", no outro com "NPS"; os dois viram `nota_nps`.

**Etapa 3 — renomear/remover (linhas 319–330)**
- Linhas 320–325: aplica o `renomear` da regra (nomes de origem e destino são padronizados, então você pode escrever como no Excel). Se alguma coluna a renomear não existir, registra AVISO.
- Linhas 326–330: remove as colunas pedidas em `remover_colunas` que existirem, registrando INFO.

**Etapa 4 — textos e marcadores de vazio (linhas 332–348)**
- Linha 333: prepara a lista de marcadores de vazio sem acento e em minúsculas.
- Linhas 336–344: para cada texto: troca espaço não separável por espaço normal, remove o "espaço de largura zero" (caractere invisível que vem de copiar/colar da web), reduz espaços repetidos a um e tira das pontas. Se o resultado for um marcador de vazio (`-`, `N/A`, `Sem Informação`...), vira vazio e é contado. `nonlocal` permite que a função interna altere o contador da função de fora.
- Linhas 346–348: aplica a todas as células e registra quantos marcadores foram esvaziados.

**Etapa 5 — linhas e colunas vazias (linhas 350–358)**
- Colunas que ficaram totalmente vazias (depois das etapas anteriores) são removidas com AVISO; linhas totalmente vazias são removidas com INFO.

**Etapa 6 — linhas de Total (linhas 360–378)**
- Linha 364: lista as colunas "quase cheias" (≥ 90% preenchidas).
- Linhas 366–373: uma linha é Total se o seu **primeiro valor preenchido** for texto e: (a) for exatamente "Total"/"Subtotal"/"Total Geral", ou começar com "Subtotal"; ou (b) começar com "Total" **e** deixar vazia alguma coluna quase sempre preenchida. O comentário explica o porquê: "Total Express" pode ser nome de loja; numa linha de dados normal, todas as colunas importantes estão preenchidas, então ela não é removida.
- Linhas 374–378: aplica a regra linha a linha; se achar totais, registra AVISO com as linhas e as remove — evitando que, no Power BI, a soma conte o valor em dobro.

**Etapa 7 — tipos (linhas 380–408)**
- Linha 381: lê os tipos forçados pela regra (nomes padronizados, tipos em minúsculas).
- Linhas 382–386: tipo inexistente (ex.: `numero`) → ERRO; coluna da regra que não existe no arquivo → AVISO.
- Linhas 388–404: para cada coluna com tipo forçado válido: detecta o decimal, converte; os valores que tinham conteúdo e não converteram viram ERRO (com exemplos). Se o tipo é `inteiro` e a coluna ficou decimal (tinha casas decimais), outro ERRO mostrando os valores quebrados.
- Linhas 405–406: sem tipo forçado e com `inferir_tipos` ligado → `_inferir`.
- Linhas 407–408: com `inferir_tipos` desligado → tudo texto.
- Diferença importante: tipo **forçado** que falha = ERRO (você garantiu que era aquele tipo); tipo **inferido** que esvazia poucos valores = só AVISO.

**Etapa 8 — maiúsculas/minúsculas (linhas 410–417)**
- Para cada coluna da seção `texto` da regra que existir: aplica `maiusculo`, `minusculo` ou `titulo` (primeira letra de cada palavra maiúscula) apenas nos valores de texto. Ex.: `uf: maiusculo` → "sp" vira "SP".

**Etapa 9 — duplicadas (linhas 419–426)**
- A regra pode ligar/desligar; senão vale o geral. Linhas **idênticas em todas as colunas** são removidas, mantendo a primeira, com AVISO e exemplos. Por ser a última etapa, "  João " e "João" já foram padronizados e contam como iguais.

- Linhas 428–429: registra o resumo ("Limpeza concluída: 1.250 -> 1.243 linhas, 18 colunas") e devolve a tabela.

**Erros que este arquivo evita**
- `#REF!`/`#DIV/0!` chegando ao Power BI.
- Nomes de coluna diferentes a cada mês quebrando o relatório (padronização + sinônimos).
- "N/A", "-", espaços invisíveis contando como valores.
- Linhas de Total somadas em dobro.
- Números como texto (`R$ 1.234,56`), datas como texto (`fev/2025`) e notas com `.0`.
- Perda de zeros à esquerda em CPF, CEP e matrícula.
- Linhas duplicadas inflando contagens.

---

## robo/validacao.py

- **Para que serve:** confere as regras de qualidade definidas por você no `config.yaml` (colunas obrigatórias, campos que não podem ficar vazios, chave única, faixas de valores, lista de valores permitidos, mínimo de linhas). Qualquer ERRO aqui impede a publicação. Ele não altera a tabela: só aponta os problemas com a linha exata.
- **Onde entra no fluxo:** é chamado por `pipeline._tratar` (`validar_tabela`), logo depois da limpeza. Usa `limpeza.normalizar_nome_coluna`/`sem_acento` e anota no `Relatorio`.

### Docstring (linhas 1–10)

- Lista as regras disponíveis, com exemplo de sintaxe de cada uma.

### Imports (linhas 12–19)

- `difflib` (biblioteca do Python para achar textos parecidos — usada para sugerir "você quis dizer..."), `pandas`, funções da limpeza e `Relatorio`.

### _cols (linhas 22–23)

- Padroniza uma lista de nomes de coluna (aceita lista vazia ou ausente). Por isso você pode escrever as regras como no Excel ("Nota NPS") ou já padronizado (`nota_nps`).

### _linhas (linhas 26–27)

- Até 5 exemplos `linha X` das linhas marcadas pela máscara. Como o índice é o número da linha do Excel, o exemplo aponta exatamente onde corrigir.

### validar_tabela (linhas 30–100)

- Linhas 31–33: `minimo_linhas` (padrão 1): se, depois da limpeza, sobrou menos linhas que o mínimo → ERRO. Pega, por exemplo, uma planilha que veio só com cabeçalho.
- Linhas 34–36: sem nenhuma coluna → ERRO e para (as outras checagens não fariam sentido).
- Linhas 38–46 (**colunas obrigatórias**): lista as que faltam. Para cada uma, procura no arquivo um nome parecido (pelo menos 60% de semelhança, ignorando colunas de controle) e sugere: "nota_nps (você quis dizer 'nota_nps_2'? se for, adicione em 'sinonimos' na regra)". O comentário deixa claro: o robô **não** troca sozinho — quem decide é você.
- Linhas 48–56 (**não nulos**): para cada coluna: se ela não existe e ainda não foi acusada como obrigatória ausente, ERRO (evita acusar o mesmo problema duas vezes); se existe, conta as células vazias e registra ERRO com as linhas.
- Linhas 58–68 (**chave única**): se alguma coluna da chave não existe → ERRO. Senão, marca todas as linhas cuja combinação se repete (`keep=False` marca **todas** as cópias, não só a segunda) e registra ERRO com exemplos tipo `linha 12: id_resposta=4521`.
- Linhas 70–89 (**faixas**): para cada coluna com faixa:
  - não existe → ERRO;
  - não é número nem data → ERRO (não dá para comparar "maior que");
  - define a conversão do limite (data ou número), marca quem está abaixo do `min` ou acima do `max` (vazios não contam), e registra ERRO com exemplos. Exemplo: `nota_nps: {min: 0, max: 10}` e a linha 88 tem 11 → "Valores fora da faixa permitida (0 a 10) — linha 88: 11".
- Linhas 91–100 (**valores permitidos**): para cada coluna: não existe → ERRO; senão, compara cada valor preenchido com a lista, sem acento e sem diferenciar maiúsculas; quem não está na lista → ERRO com exemplos. Exemplo: `uf` com "Sao Paulo" quando a lista tem só siglas → `linha 40: 'Sao Paulo'`.

**Erros que este arquivo evita**
- Publicar uma base faltando colunas que o Power BI espera.
- IDs ou notas vazios onde não poderiam estar.
- Respostas duplicadas (mesmo ID duas vezes) inflando o NPS.
- Notas fora da escala (ex.: 11 numa escala 0–10) ou datas absurdas.
- Categorias digitadas errado (UF inválida).
- Base vazia sendo publicada como se fosse válida.

---

## robo/modelagem.py

- **Para que serve:** prepara as tabelas para o Power BI. Sem configuração, devolve a tabela como está. Com a seção `modelo` na regra, monta um **modelo estrela**: uma tabela **fato** (os acontecimentos, ex.: cada resposta) e tabelas **dimensão** (as descrições, ex.: cursos), ligadas por uma chave numérica, além de uma **tabela calendário**. Também gera o **dicionário de dados** (o perfil de cada coluna) usado no relatório de qualidade.
- **Onde entra no fluxo:** é chamado por `pipeline._tratar` (`modelar`), por `pipeline._resumo_tabelas` (`tipo_amigavel`) e por `pipeline._gravar_relatorio_qualidade` (`dicionario_dados`).

### Docstring (linhas 1–13)

- Mostra o formato da seção `modelo` com um exemplo: fato `fato_respostas`, dimensão `dim_curso` com as colunas `curso` e `modalidade` e chave `id_curso`, e calendário a partir de `data_resposta`.

### Imports (linhas 15–20)

- `pandas`, `normalizar_nome_coluna` e `Relatorio`.

### MESES e DIAS (linhas 22–24)

- Nomes em português dos meses e dos dias da semana (segunda primeiro), para a tabela calendário não sair em inglês.

### tipo_amigavel (linhas 27–37)

- Traduz o tipo técnico de uma coluna para português: "Verdadeiro/Falso", "Número inteiro", "Número decimal", "Data" ou "Data e hora" e, para o resto, "Texto".
- Linhas 34–36: para datas, se todas as horas são meia-noite (ou a coluna está vazia), é "Data"; senão, "Data e hora". A ordem dos testes importa: Verdadeiro/Falso vem antes de inteiro.

### dicionario_dados (linhas 40–63)

- Para cada tabela e cada coluna, monta uma linha com: tabela, coluna, tipo amigável, total de linhas, preenchidos, % de vazios (arredondado em 2 casas), valores distintos, mínimo e máximo (só para números e datas) e um exemplo (o primeiro valor preenchido).
- Linha 63: devolve tudo como um DataFrame, que vira a aba `dicionario_dados` do relatório de qualidade.
- Exemplo de linha: `dados | nota_nps | Número inteiro | 1243 | 1240 | 0,24 | 11 | 0 | 10 | 9`.

### tabela_calendario (linhas 66–81)

- Linha 67: pega as datas preenchidas.
- Linhas 68–70: cria um dia por linha, de 1º de janeiro do menor ano até 31 de dezembro do maior ano. Anos completos são o que o Power BI espera de uma "tabela de datas" (funções de inteligência de tempo, como acumulado no ano, dependem disso).
- Linhas 71–80: cria as colunas: ano, trimestre (`T1`...`T4`), número e nome do mês, abreviação (`Jan`), ano-mês (`2025-02`), dia, número do dia da semana (1 = segunda ... 7 = domingo), nome do dia e se é fim de semana (sábado ou domingo).

### _chave (linhas 84–85)

- Transforma uma combinação de valores numa "tupla" (uma lista fixa) trocando qualquer vazio por `None`. Por que: no pandas, "vazio" não é igual a "vazio" numa comparação; trocando por `None`, duas linhas com a mesma combinação (inclusive com vazios) encontram a mesma chave.

### modelar (linhas 88–129)

- Linhas 90–91: sem `modelo` na regra → devolve a tabela original com o mesmo nome (caso mais comum).
- Linhas 93–94: a fato começa como cópia da tabela, com índice 0, 1, 2...
- Linhas 96–116, para cada dimensão:
  - Linhas 97–99: padroniza o nome da dimensão, as colunas e a chave. Se a chave não foi informada, vira `id_` + nome sem `dim_` (ex.: `dim_curso` → `id_curso`).
  - Linhas 100–103: lista vazia ou coluna inexistente → ERRO e pula esta dimensão.
  - Linhas 104–106: se já existe uma coluna com o nome da chave → ERRO (evita sobrescrever um dado real).
  - Linha 107: a dimensão são as combinações distintas das colunas escolhidas (sem combinações totalmente vazias).
  - Linha 108: ordena (comparando como texto, com vazios no fim), para que as chaves sejam estáveis e previsíveis (ex.: cursos em ordem alfabética).
  - Linha 109: cria a chave 1, 2, 3... na primeira coluna.
  - Linha 110: guarda em que posição estava a primeira coluna da dimensão, para colocar a chave no mesmo lugar na fato.
  - Linhas 111–112: monta o "de-para" (combinação → chave) e, para cada linha da fato, procura a chave correspondente. É, literalmente, um PROCV automático.
  - Linhas 113–114: remove da fato as colunas descritivas e insere a coluna de chave no lugar delas.
  - Linhas 115–116: guarda a dimensão e registra quantos registros ela tem e que o relacionamento no Power BI é `id_curso` 1:* (um para muitos).
  - Exemplo: 10.000 respostas com 15 combinações de curso+modalidade → `dim_curso` com 15 linhas e a fato com a coluna `id_curso` (1 a 15) no lugar de `curso` e `modalidade`.
- Linhas 118–126 (calendário): se pedido, a coluna precisa existir na fato **e** ser do tipo data; senão, ERRO. Se tiver ao menos uma data preenchida, cria `dim_calendario` e registra como relacionar.
- Linhas 128–129: o nome da fato é o configurado ou `fato_` + nome da tabela (ex.: `fato_dados`). Devolve a fato e as dimensões.

**Erros que este arquivo evita**
- Dimensões com chaves inconsistentes (o "de-para" é feito por código, não à mão).
- Sobrescrever uma coluna real com a chave criada.
- Calendário com "buracos" de datas (sempre anos completos).
- Nomes de mês/dia em inglês no Power BI.

---

## robo/escrita.py

- **Para que serve:** grava as tabelas tratadas em Excel formatado (cabeçalho colorido, filtro, painel congelado, formatos de data e número, larguras ajustadas) e/ou CSV. A gravação é "atômica": escreve primeiro um arquivo temporário e só no final troca pelo nome definitivo, para o Power BI/OneDrive nunca enxergarem um arquivo pela metade.
- **Onde entra no fluxo:** é chamado por `pipeline.processar_arquivo` (`gravar_tabelas`). Não chama outros módulos do robô.

### Docstring e imports (linhas 1–14)

- Explica a gravação atômica. Imports: `os` (troca de nome atômica), `Path`, `pandas` e, do openpyxl, estilos (`Alignment`, `Font`, `PatternFill`) e `get_column_letter` (transforma 1 → A, 2 → B...).

### Constantes (linhas 16–17)

- Linha 16: 1.048.575 linhas de dados — o limite do Excel é 1.048.576 linhas, e uma é o cabeçalho.
- Linha 17: cor do cabeçalho (azul-escuro).

### _nome_aba (linhas 20–28)

- Linha 21: remove os caracteres proibidos em nome de aba (`[ ] : * ? / \`), corta em 31 caracteres (limite do Excel) e, se sobrar nada, usa `dados`.
- Linhas 22–26: se o nome já foi usado (sem diferenciar maiúsculas), acrescenta `_2`, `_3`... cortando a base para continuar cabendo em 31 caracteres.
- Linhas 27–28: anota como usado e devolve.

### _neutralizar_formulas (linhas 31–37)

- Segurança contra "injeção de fórmula": se um texto da planilha de origem começar com `=` (ex.: `=HYPERLINK("site-malicioso";"Clique")`), o openpyxl o gravaria como fórmula ativa. Aqui, toda célula marcada como fórmula (`"f"`) é remarcada como texto (`"s"`). A saída tratada nunca contém fórmulas ativas.

### _formatar_aba (linhas 40–65)

- Linha 41: neutraliza fórmulas.
- Linha 42: congela a primeira linha (o cabeçalho fica visível ao rolar).
- Linhas 43–44: liga o filtro automático em toda a área com dados.
- Linhas 45–48: cabeçalho em negrito branco, fundo azul-escuro, centralizado verticalmente.
- Linha 49: usa as 500 primeiras linhas como amostra para calcular larguras (rápido, mesmo em bases enormes).
- Linhas 50–64, para cada coluna:
  - datas: formato `dd/mm/yyyy` (largura 12) ou, se houver horas, `dd/mm/yyyy hh:mm` (largura 17), aplicado a cada célula;
  - decimais: formato `#,##0.00` (no Excel brasileiro aparece como `1.234,56`), largura 12;
  - outros (texto e inteiros): largura = tamanho do texto no percentil 90 da amostra + 2 (o percentil 90 ignora os 10% mais longos, para um comentário gigante não deixar a coluna enorme); sem valores, 10.
- Linha 65: a largura final fica entre 10 e 60 e nunca menor que o nome da coluna + 3.

### _gravar_xlsx (linhas 68–80)

- Linha 69: o temporário se chama `~robo_tmp_<nome>` — e o monitor ignora arquivos com esse prefixo (ver `eh_candidato`).
- Linhas 72–76: abre um gravador de Excel; para cada tabela, escolhe um nome de aba válido, grava sem o índice (`index=False`) e formata.
- Linha 77: `os.replace` troca o temporário pelo definitivo de uma vez só (operação atômica do sistema). Se o definitivo estiver aberto no Excel, aqui ocorre o `PermissionError` que o pipeline transforma em ADIADO.
- Linhas 78–80: em qualquer caso, apaga o temporário se ele ainda existir (não deixa lixo na pasta).

### _gravar_csv (linhas 83–90)

- Mesma lógica atômica: grava o CSV temporário com o separador e o decimal configurados, sem índice, em `utf-8-sig` (o Excel abre os acentos corretamente) e datas no formato `2025-12-31 14:30:00`; depois troca pelo definitivo e limpa o temporário.

### gravar_tabelas (linhas 93–115)

- Linhas 95–97: cria a pasta, lê o formato e prepara a lista de avisos.
- Linhas 98–100: se o formato inclui Excel e alguma tabela passa do limite de linhas, avisa e grava **só** CSV (o Excel cortaria os dados).
- Linhas 103–106: `xlsx` ou `ambos` → um único Excel com todas as tabelas, uma por aba.
- Linhas 107–112: `csv` ou `ambos` → um CSV por tabela; com uma só tabela, `<nome>.csv`; com várias, `<nome>__<tabela>.csv` (ex.: `nps_outubro__dim_curso.csv`).
- Linhas 113–114: se nada foi gravado, o formato era inválido → `ValueError` (erro de valor).
- Linha 115: devolve os arquivos gravados e os avisos.

**Erros que este arquivo evita**
- Power BI ou OneDrive lendo um arquivo pela metade.
- Fórmulas maliciosas vindas da origem virando links ativos.
- Bases grandes cortadas no limite do Excel.
- Nomes de aba inválidos travando a gravação.
- Arquivos temporários esquecidos na pasta.

---

## robo/relatorio.py

- **Para que serve:** é o "caderno de ocorrências" de cada arquivo. Cada etapa anota o que fez em três níveis: **ERRO** (bloqueia a publicação), **AVISO** (não bloqueia, mas fica registrado) e **INFO** (documenta uma etapa). O caderno pode virar tabela (para o Excel de qualidade) ou texto legível (o `_ERROS.txt`).
- **Onde entra no fluxo:** é criado em `pipeline.processar_arquivo` e passado para leitura/limpeza/validação/modelagem e conferências. É lido por `pipeline` (decidir aprovar/reprovar), `historico` e `comandos` (imprimir).

### Docstring (linhas 1–6)

- Define o significado dos três níveis.

### Imports e constantes (linhas 8–20)

- `dataclass`/`field`, `datetime`, `Iterable` (dica de tipo: "qualquer coisa que possa ser percorrida") e `pandas`.
- Linhas 16–18: os textos dos níveis.
- Linha 20: no máximo 5 exemplos por ocorrência — suficiente para achar o padrão do problema sem gerar relatórios gigantes.

### Ocorrencia (linhas 23–30)

- A ficha de uma anotação: nível, mensagem, tabela, coluna, quantidade (opcional) e lista de exemplos.

### Relatorio (linhas 33–114)

- Linhas 34–37: o caderno guarda o nome do arquivo, a hora de início (preenchida automaticamente com "agora") e a lista de ocorrências.

#### _add (linhas 39–41)
- Converte os exemplos em texto, guarda só os 5 primeiros e acrescenta a ocorrência.

#### erro, aviso, info (linhas 43–50)
- Atalhos para anotar em cada nível. O `**kw` repassa os detalhes opcionais (tabela, coluna, quantidade, exemplos).

#### erros, avisos, tem_erros (linhas 52–62)
- `erros` e `avisos` filtram as ocorrências do nível; `tem_erros` responde "há pelo menos um erro?" — é essa pergunta que decide se o arquivo é publicado.

#### para_dataframe (linhas 64–76)
- Transforma o caderno em tabela com as colunas nivel, tabela, coluna, mensagem, quantidade e exemplos (separados por `; `). As colunas são declaradas explicitamente (linha 76) para a tabela sair com cabeçalho mesmo sem ocorrências.

#### texto (linhas 78–114)
- Linhas 80–89: cabeçalho com arquivo, data/hora, resultado (APROVADO/REPROVADO), quantidade de erros e avisos.
- Linhas 90–105: três seções, nesta ordem: ERROS, AVISOS e ETAPAS EXECUTADAS (seções vazias não aparecem). Cada item é numerado e mostra `[tabela / coluna]`, `(qtd: N)` e a linha de exemplos.
- Linhas 106–113: se reprovado, acrescenta "O QUE FAZER": corrigir a planilha (que está na mesma pasta), salvar e colocar de novo em Bases-Limpeza; o robô processa sozinho.

Exemplo de trecho do `_ERROS.txt`:
```
1. Células vazias em coluna obrigatória  [dados / nota_nps]  (qtd: 3)
   Exemplos: linha 15; linha 88; linha 203
```

**Erros que este arquivo evita**
- Reprovação sem explicação (sempre há mensagem, local e exemplos).
- Relatórios gigantes e ilegíveis (limite de 5 exemplos).
- Confundir problema grave com observação (níveis separados).

---

## robo/historico.py

- **Para que serve:** guarda a "memória" de todos os processamentos: uma linha por arquivo em `logs/historico_processamentos.csv` (fácil de abrir no Excel ou Power BI), um JSON detalhado por processamento em `logs/execucoes/<id>.json` (usado pelo painel) e um resumo consolidado de erros e avisos de todas as planilhas em `Bases-Relatorios/resumo_ocorrencias.csv`.
- **Onde entra no fluxo:** é chamado por `pipeline._registrar` (gravar) e pelo painel (ler). `comandos._status` lê o CSV diretamente.

### Docstring (linhas 1–8)

- Explica os arquivos e que o `<id>` é o mesmo nome (sem extensão) do original arquivado, ex.: `20261014_093012_nps_outubro` — assim o painel liga o arquivo ao seu relatório.

### Imports e CABECALHO (linhas 10–18)

- `csv`, `json` (formato de texto para dados estruturados), `datetime`, `Path`.
- Linhas 17–18: as colunas do histórico, nesta ordem.

### arquivo_historico e pasta_execucoes (linhas 21–26)

- Devolvem os caminhos do CSV de histórico e da pasta de execuções, para não repetir esses nomes pelo código.

### registrar (linhas 29–42)

- Linha 30: garante a pasta de logs.
- Linhas 32–36: se o histórico já existe, lê a primeira linha; se o cabeçalho for diferente do atual (versão antiga do robô), renomeia o arquivo antigo para `historico_antigo_<data_hora>.csv` e começa um novo — nunca mistura colunas diferentes no mesmo arquivo.
- Linhas 37–42: abre em modo "acrescentar" (`"a"`), escreve o cabeçalho se o arquivo é novo e escreve a linha na ordem do cabeçalho (campos ausentes ficam vazios). `newline=""` evita linhas em branco extras no Windows.

### ler (linhas 45–53)

- Lê todas as linhas como dicionários (coluna → valor), inverte para que as mais recentes venham primeiro e devolve todas ou só as `limite` primeiras.

### salvar_execucao (linhas 56–61)

- Grava o detalhe do processamento em JSON, com acentos legíveis (`ensure_ascii=False`), indentação de 1 espaço e convertendo para texto o que o JSON não entende (datas, caminhos), via `default=str`.

### ler_execucao (linhas 64–70)

- Linhas 65–66: segurança: recusa ids vazios, com `/` ou `\`, ou começando com `.` — impede que alguém peça pelo painel algo como `../../config` e leia arquivos fora da pasta.
- Linhas 67–70: se o JSON existe, lê e devolve; senão, `None`.

### CABECALHO_OCORRENCIAS e ARQUIVO_OCORRENCIAS (linhas 73–75)

- Colunas e nome do resumo consolidado de ocorrências.

### registrar_ocorrencias (linhas 78–102)

- Linhas 80–84 (docstring): o objetivo é descobrir quais problemas mais se repetem e em quais planilhas, filtrando no Excel ou no Power BI.
- Linhas 85–87: pega só ERROs e AVISOs; se não houver, não faz nada.
- Linhas 88–98: acrescenta uma linha por ocorrência, com data, arquivo, status, nível, tabela, coluna, mensagem, quantidade, exemplos (separados por ` | `) e id.
- Linhas 99–102: se o CSV estiver aberto no Excel, registra um aviso no log em vez de travar ("o resumo desta execução ficou só no histórico do painel").

**Erros que este arquivo evita**
- Perder o rastro do que foi processado, quando e com qual resultado.
- Misturar colunas de versões diferentes do histórico.
- Leitura indevida de arquivos fora da pasta pelo painel.
- O robô travar porque o resumo de ocorrências está aberto no Excel.

---

## robo/manutencao.py

- **Para que serve:** faz a "faxina" periódica: apaga backups de originais, relatórios e logs mais antigos que a retenção configurada (padrão 180, 180 e 60 dias). A pasta Bases-Erros **nunca** é limpa automaticamente, porque ali estão arquivos que esperam a sua correção.
- **Onde entra no fluxo:** é chamado por `monitor._manutencao_diaria` (uma vez por dia) e pelo comando `python -m robo manutencao`.

### Docstring e imports (linhas 1–14)

- Explica o propósito e a exceção de Bases-Erros. Imports: `logging`, `time`, `Path`, `Config`; e o diário `"robo"`.

### _limpar (linhas 17–34)

- Linhas 18–19: se a retenção é zero/negativa ou a pasta não existe, não faz nada (zero = "nunca apagar").
- Linha 20: calcula o "limite": agora menos N dias (86.400 segundos por dia).
- Linhas 22–28: percorre a pasta **e todas as subpastas** (`rglob`) atrás dos arquivos que casam com o padrão; apaga os que foram modificados antes do limite e conta. Se um arquivo não puder ser apagado (aberto, sem permissão), pula.
- Linhas 29–33: depois, tenta remover as subpastas, da mais funda para a mais rasa (`reverse=True`); `rmdir` só remove pastas vazias, então pastas com conteúdo ficam. Ex.: `Bases-Originais/2025-03` some quando todos os backups de março/2025 forem apagados.
- Linha 34: devolve quantos arquivos foram apagados.

### executar_manutencao (linhas 37–46)

- Linhas 38–43: limpa Originais e Relatórios (todos os arquivos) e, em Logs, só os arquivos `robo.log.*` (os logs diários antigos — o histórico e os JSONs do painel não são apagados). Lê as retenções da configuração.
- Linhas 44–45: se apagou algo, registra o resumo.
- Linha 46: devolve o resumo (ex.: `{"originais": 12, "relatorios": 3, "logs": 0}`).

**Erros que este arquivo evita**
- O OneDrive enchendo de backups antigos.
- Apagar arquivos reprovados que ainda precisam de correção (Bases-Erros fica de fora).
- Apagar o histórico e os detalhes de execução do painel (em Logs, só `robo.log.*`).

---

## config.exemplo.yaml

- **Para que serve:** é o modelo comentado do arquivo de configuração. O `instalar.bat` copia este arquivo para `config.yaml`, que é o que o robô realmente lê. Aqui você define pastas, tempos, comportamento da limpeza, formato de saída, banco de dados, painel, retenção e as regras por arquivo.
- **Onde entra no fluxo:** é lido (na forma de `config.yaml`) por `config.carregar_config`, que mescla o conteúdo com os `PADROES` de `config.py`. Tudo o que não aparece aqui (por exemplo, `valores_nulos`, `padroes_identificador`, `csv_separador`, as seções `analise` e `excel`) continua valendo pelo padrão do código.

> **YAML em uma frase:** é um formato de texto em que a hierarquia é dada pela **indentação** (espaços à esquerda), `chave: valor` define um item, `- item` define um item de lista e `#` inicia um comentário.

### Cabeçalho (linhas 1–6)

- Comentários: copiar para `config.yaml`, `#` é comentário e o alerta mais importante: a indentação importa e TAB não pode ser usado.

### pastas (linhas 8–18)

- Linhas 9–12: explica o modo `auto` e como informar um caminho manual (com `/` ou `\\` duplicada, porque no YAML uma `\` sozinha pode ser interpretada como caractere especial dentro de aspas).
- Linhas 13–18: todas em `auto`, exceto `logs`, que fica na pasta do projeto — o comentário explica: assim os logs não sincronizam no OneDrive (o que geraria conflitos com o arquivo sendo escrito o tempo todo).

### monitoramento (linhas 20–22)

- Olha a pasta a cada 5 segundos; espera o arquivo ficar 10 segundos parado.

### leitura (linhas 24–26)

- `abas: primeira` (com empilhamento automático de abas iguais) ou `todas`; cabeçalho procurado nas 20 primeiras linhas.

### limpeza (linhas 28–33)

- Remove duplicadas e totais, infere tipos com limiar de 95% e trata erros de fórmula como `erro` (reprova) ou `anular` (esvazia e avisa).

### saida (linhas 35–40)

- Formato (`xlsx`, `csv`, `ambos` ou `nenhum` = só banco), sufixo do nome (ex.: `_tratada`), versionamento, nome da aba e colunas de auditoria (`_arquivo_origem` e `_processado_em`).

### banco (linhas 42–61)

- Linhas 42–50: comentário explicando as camadas no PostgreSQL: `bruto.<tabela>` (original, como texto, para auditoria), `tratado.<tabela>` (limpo e tipado), `analitico.*` (suas views/tabelas SQL da pasta `modelos_sql/`) e `robo.lotes` (controle de cada carga); e a dica de usar a variável de ambiente `ROBO_PG_SENHA` em vez de deixar a senha no arquivo.
- Linhas 51–61: desligado por padrão; dados de conexão; o banco `robo_dados` é criado automaticamente; modo de carga padrão `por_arquivo`.

### painel (linhas 63–66)

- Porta 8765, liga o robô ao abrir e mostra notificações.

### manutencao (linhas 68–71)

- Retenção de 180 dias (originais e relatórios) e 60 dias (logs).

### regras (linhas 73–113)

- Linhas 73–81: explicam que a primeira regra cujo `padrao` casar com o nome do arquivo é aplicada, que `*` significa "qualquer texto" e que nomes de colunas podem ser escritos como no Excel ou padronizados. Para ativar, apague o `[]` e descomente o exemplo.
- Linha 82: `regras: []` — lista vazia (nenhuma regra ativa).
- Linhas 84–107: exemplo completo (comentado) para arquivos `nps_*`: colunas obrigatórias, não nulos, chave única, tipos forçados (`data_resposta: data`, `nota_nps: inteiro`), faixa de 0 a 10, `uf` em maiúsculas, lista de UFs permitidas, destino no banco (tabela `nps`, modo `mesclar` pela chave `id_resposta`) e modelo estrela (fato `fato_nps`, dimensão `dim_curso` com `curso` e `modalidade` e chave `id_curso`, calendário por `data_resposta`).
- Linhas 109–113: exemplo simples para `vendas_*`: renomear "Vlr Total" para `valor_total`, remover `observacao_interna` e exigir `valor_total` preenchido.
- Opções aceitas pelo código mas que não aparecem no exemplo: `sinonimos`, `abas`, `minimo_linhas` e `remover_duplicadas` (por regra).

**Erros que este arquivo evita**
- Configurar sem saber o que cada opção faz (tudo comentado).
- Usar TAB na indentação (alerta logo no topo).
- Deixar a senha do banco exposta (dica da variável de ambiente).
- Escrever regras no formato errado (exemplos prontos para copiar).
