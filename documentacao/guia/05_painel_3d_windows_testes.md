# Parte 5 — Painel, escritório 3D, Windows e testes automáticos

Esta parte do guia explica a "cara" do Robô de Planilhas: o **painel** que você abre com dois cliques, o **escritório 3D** onde os agentes aparecem trabalhando, os **arquivos do Windows** que instalam e ligam o robô, e os **testes automáticos** que garantem que nada quebrou.

Antes de começar, quatro ideias que aparecem o tempo todo:

- **Servidor web local**: um programa que fica "escutando" pedidos e devolvendo páginas ou dados. Aqui ele roda no seu próprio computador, no endereço `127.0.0.1` (que significa "esta máquina"; também chamado de `localhost`). Nenhum outro computador da rede consegue falar com ele.
- **HTTP**: a "língua" que o navegador e o servidor usam para conversar. Cada conversa é um **pedido** (requisição) e uma **resposta**. O pedido tem um **método** — `GET` (quero ler algo) ou `POST` (quero fazer uma ação/enviar algo) — e **cabeçalhos** (etiquetas com informações extras, como "Host" ou "Content-Type").
- **API**: o "cardápio" de pedidos que o servidor aceita. Cada item do cardápio é uma **rota**, um endereço como `/api/estado`. A interface (a página) chama essas rotas para buscar números e executar ações.
- **JSON**: o formato de texto usado para trocar dados, parecido com um dicionário do Python: `{"ligado": true, "fila": []}`.

Mapa do fluxo desta parte:

```
Abrir Robo de Planilhas.vbs ──► python -m robo app ──► servidor.py (iniciar_app)
                                                         │
                     ┌───────────────────────────────────┼───────────────────────────┐
                     ▼                                   ▼                           ▼
              controle.py (liga/pausa o            sistema.py (abre janela,     configuracao.py
              monitor numa thread, guarda          notificações, atalhos,      (edita config.yaml
              log e eventos)                       inicialização do Windows)    sem perder comentários)
                     │
   navegador ◄──── HTTP/JSON ────► rotas /api/... (classe Api)
      │
      ├── inicio.html + painel.js + painel.css      (o painel, 13 páginas)
      └── escritorio.html + escritorio.js + escritorio.css (o prédio 3D)
```

---

## robo/painel/__init__.py

- **Para que serve**: só identifica a pasta `robo/painel` como um "pacote" do Python (um conjunto de módulos que pode ser importado com `from robo.painel import ...`). O texto explica, em linguagem simples, que o painel é um mini servidor web local.
- **Onde entra no fluxo**: é lido automaticamente quando qualquer arquivo faz `import robo.painel...`.

### Docstring (linhas 1–5)
Linhas 1–5: um texto entre aspas triplas (docstring) que descreve o pacote: a interface abre numa janela própria do Edge/Chrome, o servidor fica em 127.0.0.1 e o robô trabalha numa **thread** em segundo plano. *Thread* é uma "linha de execução" paralela: o mesmo programa faz duas coisas ao mesmo tempo (por exemplo, responder ao painel enquanto processa uma planilha).

**Erros que este arquivo evita**: sem ele, `import robo.painel.servidor` poderia falhar em ferramentas que exigem pacotes explícitos.

---

## robo/painel/servidor.py

- **Para que serve**: é o "balcão de atendimento" do robô. Ele sobe um servidor web que só aceita conexões do seu próprio computador, entrega os arquivos da interface (HTML, JavaScript, CSS) e oferece a API que a interface usa para mostrar números, ligar/pausar o robô, enviar e testar planilhas, salvar configurações, conversar no canal, etc. Também concentra as proteções de segurança do painel.
- **Onde entra no fluxo**: o atalho `Abrir Robo de Planilhas.vbs` executa `python -m robo app`; o comando `app` (em `robo/comandos.py`, linha 141–149) chama `iniciar_app` deste arquivo. A partir daí, tudo o que você faz no painel vira um pedido HTTP que chega aqui.

### Docstring (linhas 1–5)
Linhas 1–5: resumo das três proteções principais: só aceita conexões da própria máquina, confere o cabeçalho `Host` contra "DNS rebinding" (um truque em que um site malicioso faz o navegador achar que o endereço dele é 127.0.0.1, para conversar com programas locais) e exige um cabeçalho próprio nas ações `POST`, que páginas de outros sites não conseguem enviar.

### Imports (linhas 7–33)
- Linha 7: `from __future__ import annotations` permite escrever tipos como `dict | None` mesmo em versões de Python que ainda não entendiam isso nativamente.
- Linhas 9–22: bibliotecas padrão do Python. `json` (ler/escrever JSON), `logging` (registro de mensagens), `mimetypes` (descobrir o tipo de um arquivo pela extensão), `re` (expressões regulares — padrões de texto), `shutil` (mover/copiar arquivos), `tempfile` (arquivos e pastas temporários), `threading` (threads e sinais entre elas), `time`, `urllib.parse` (quebrar um endereço em partes) e `urllib.request` (fazer pedidos HTTP), `date/datetime`, `Decimal` (número decimal exato), `BaseHTTPRequestHandler` e `ThreadingHTTPServer` (a base do servidor web: o segundo atende cada pedido numa thread separada) e `Path` (caminhos de arquivo).
- Linha 24: `pandas`, a biblioteca de tabelas, usada aqui para detectar valores vazios e datas.
- Linhas 26–33: partes do próprio robô: a versão (`__version__`) e o `historico` (lê o CSV/JSON de execuções); `RAIZ_PROJETO` (pasta do projeto); `EXTENSOES_SUPORTADAS` (.xlsx, .csv...); `executar_manutencao` (limpeza de arquivos antigos); `TravaInstancia` (impede dois robôs ao mesmo tempo) e `eh_candidato` (diz se um arquivo é uma planilha a processar); os módulos `configuracao` e `sistema` deste pacote; `ControleRobo`; e `processar_arquivo` (o pipeline).

### Constantes (linhas 35–51)
- Linha 35: `log` é o "caderno de registros" chamado `"robo"`, o mesmo usado em todo o projeto.
- Linha 37: `ESTATICOS` aponta para a pasta `estaticos` ao lado deste arquivo, onde ficam HTML, JS, CSS e ícones.
- Linha 38: `LIMITE_UPLOAD` = 300 MB, o maior arquivo que o painel aceita receber.
- Linha 39: `LIMITE_JSON` = 2 MB, o maior corpo de ação em JSON (configurações, textos). Planilhas usam a rota de upload, não esta.
- Linhas 40–45: `CABECALHOS_SEGURANCA`, enviados em toda resposta:
  - `X-Content-Type-Options: nosniff` — o navegador não "adivinha" o tipo do arquivo; usa o que o servidor disse.
  - `X-Frame-Options: DENY` e `Content-Security-Policy: frame-ancestors 'none'` — nenhum site pode exibir o painel dentro de uma moldura (iframe). Isso evita **clickjacking**, o golpe de esconder o painel por baixo de um botão falso para você clicar sem saber.
  - `Referrer-Policy: no-referrer` — ao sair do painel por um link, o endereço do painel não é contado ao outro site.
- Linha 46: `CABECALHO_ACAO = "X-Robo-Painel"`, o cabeçalho obrigatório em todo `POST`.
- Linha 47: `RE_CARIMBO` reconhece o carimbo de data e hora no começo do nome (ex.: `20261017_143000_`), que o robô coloca nos arquivos reprovados.
- Linhas 48–51: `TIPOS_ESTATICOS`, tabela fixa extensão → tipo de conteúdo (o "Content-Type", ou tipo MIME, que diz ao navegador se aquilo é HTML, JavaScript, imagem...).

### class ErroApi (linhas 54–57)
Linhas 54–57: um tipo de erro próprio da API. Guarda a mensagem amigável e o **código de status HTTP** (número que resume a resposta: 200 = deu certo, 400 = pedido errado, 403 = proibido, 404 = não encontrado, 409 = conflito, 413 = grande demais, 415 = formato não suportado, 500 = erro interno, 503 = serviço indisponível). O padrão é 400.

### _fmt (linhas 61–82)
Transforma qualquer valor de célula num texto bonito no padrão brasileiro, para mostrar nas prévias.
- Linhas 62–68: vazio (`None`, `pd.NA`, `pd.NaT` ou qualquer coisa que o pandas considere vazia) vira `""`. O `try/except` existe porque `pd.isna` dá erro com alguns tipos (listas, por exemplo).
- Linhas 69–72: datas com hora viram `dd/mm/aaaa hh:mm`; sem hora, só `dd/mm/aaaa`.
- Linhas 73–75: `Decimal` mantém até 4 casas decimais; a troca `","→"X"→"."` converte o padrão americano `1,234.5` para o brasileiro `1.234,5`.
- Linhas 76–77: verdadeiro/falso viram "Sim"/"Não". (O teste de `bool` vem antes do de `int` porque, no Python, `True` também é um número inteiro.)
- Linhas 78–79: número com vírgula vira texto com 2 casas no padrão brasileiro.
- Linhas 80–82: inteiros ganham separador de milhar com ponto; qualquer outra coisa vira `str(v)`.

### _ficha_curta (linhas 85–90)
Linhas 85–90: recebe a "ficha profissional" de um agente (cargo, nível, metodologias...) e devolve só os campos que o escritório 3D precisa, reduzindo as provas técnicas a três números (acertos, total, aprovado). O operador `|` junta dois dicionários.

### _ocorrencias (linhas 93–95)
Linhas 93–95: aceita tanto um relatório (que tem `.ocorrencias`) quanto uma lista pronta, e converte cada ocorrência (objeto) em dicionário (`__dict__`), que pode virar JSON.

### _nome_original (linhas 98–99)
Linhas 98–99: remove o carimbo de data do começo do nome do arquivo reprovado, devolvendo o nome que você deu.

### _dentro (linhas 102–107)
Linhas 102–107: verifica se um caminho está **dentro** de alguma das pastas permitidas. `resolve()` transforma o caminho no endereço real e absoluto (resolvendo `..` e atalhos), o que impede truques como `Bases-Tratadas/../../Windows/calc.exe`. Se o caminho não puder ser resolvido, a resposta é "não".

### class Api (linhas 111–811)
É o cardápio da API: cada método é a função de uma rota. Todos recebem `q` (os parâmetros da URL, para `GET`) ou `b` (o corpo JSON, para `POST`) e devolvem um dicionário que vira JSON.

#### __init__ (linhas 112–115)
Linhas 112–115: guarda o `ControleRobo` (em `self.c`), a porta e cria `encerrar`, um `threading.Event` — uma "bandeirinha" que uma thread levanta para avisar outra (aqui, para fechar o aplicativo).

#### cfg (linhas 117–121)
Linhas 117–121: `@property` faz `self.cfg` parecer um atributo, mas na verdade roda esta função. Se a configuração não carregou (por exemplo, a pasta Bases-Limpeza não foi encontrada), levanta `ErroApi` com status 409, e a rota responde com a mensagem do problema em vez de quebrar.

#### estado — rota `GET /api/estado` (linhas 124–170)
Alimenta a Visão geral e a barra lateral (chamada a cada 2 segundos).
- Linhas 125–129: monta a base (versão, erro de configuração, se está ligado, desde quando, hora atual). Sem configuração, para aqui.
- Linhas 130–134: lê até 2.000 linhas do histórico e separa as de hoje e as dos últimos 30 dias (comparando o texto `data_hora`).
- Linhas 136–140: duas funções internas: `contar` (quantos registros têm um status) e `soma` (soma um campo numérico só dos sucessos).
- Linhas 142–151: lista os reprovados (sem detalhes, para ser rápido) e monta o quadro das pastas: nome, caminho, se existe e, para entrada e tratadas, quantos arquivos válidos há. Para Bases-Erros a quantidade é a dos reprovados pendentes.
- Linhas 152–170: acrescenta: arquivo em processamento, hora do último ciclo, fila, pastas, indicadores (aprovados, reprovados e linhas de hoje, pendentes, taxa de aprovação de 30 dias arredondada e total), os 8 registros mais recentes, se o banco está ligado e se as notificações estão ligadas.

#### escritorio — rota `GET /api/escritorio` (linhas 172–264)
Alimenta o prédio 3D (chamada a cada 1 segundo).
- Linhas 174–179: lê o parâmetro `desde` (o número do último evento que a página já recebeu) e devolve só os eventos novos (`eventos_desde`), mais o último número. Sem configuração, para aqui.
- Linhas 181–186: histórico de hoje, separado em aprovados (`ok`) e reprovados (`ruim`); `com_banco` são os aprovados que geraram tabelas `tratado.` no PostgreSQL.
- Linhas 187–193: importa a equipe da linha de produção (nativos + seus agentes) e monta a lista com o que o 3D precisa: id, nome, papel, cor, descrição, habilidades ativas, andar 1 e ficha curta.
- Linhas 194–206: lê a configuração da análise; acrescenta os supervisores (DBA com aviso de "prontidão" se o banco estiver desligado) e os analistas do 2º andar (com prefixo `analise_`; ficam "estudando" se a análise estiver pausada).
- Linhas 207–211: acrescenta a Sala Excel (3º andar); `ronda` marca quem anda pelos corredores (o supervisor do Excel).
- Linhas 212–220: acrescenta o quadro de pessoal (plenos, juniores, estagiários de cada andar; coordenadores fazem ronda) e a equipe do canal (4º andar; Helena faz ronda).
- Linhas 221–227: lê a última ronda de TI e acrescenta a equipe de TI no 5º andar.
- Linhas 228–233: regra "ninguém dorme": agente pausado continua ativo, mas "em treinamento"; o agente do banco sem PostgreSQL fica "preparando as tabelas"; todo mundo ganha o campo `prontidao`.
- Linhas 234–263: números do dia por agente (o que aparece na ficha e na lista lateral): recebidos, linhas lidas, linhas descartadas (entrada − saída), barrados, modelados, linhas carregadas no banco, publicados; números da análise, da Sala Excel, das conferências do quadro e da TI ("OK" ou quantidade de alertas). Também resumos de análise, Excel, canal e TI para as TVs.

#### _execucao_resumida (linhas 266–274)
Linhas 266–274: lê o JSON detalhado de uma execução e guarda só a parte do Excel e do quadro (id, ok, quantidade de achados) num **cache** (memória de consulta rápida) dentro do próprio objeto, para não reler o disco a cada segundo.

#### _quadro_hoje (linhas 276–285)
Linhas 276–285: para até 300 execuções de hoje, conta quantas conferências cada pessoa do quadro fez e quantos achados teve, e devolve no formato `{id: {"valor": ..., "rotulo": ...}}`.

#### _canal_hoje (linhas 287–298)
Linhas 287–298: conta as mensagens de hoje do canal, descobre a sprint atual e os dias restantes e pega a última mensagem (cortada em 140 caracteres). Qualquer falha é registrada em nível "debug" e devolve `{}` — o escritório não pode cair por causa do canal.

#### _excel_hoje (linhas 300–309)
Linhas 300–309: soma as entregas da Sala Excel de hoje, as conferências assinadas e o nome do último arquivo entregue.

#### _analises_do_dia (linhas 311–323)
Linhas 311–323: lê os JSONs da pasta `logs/analises`, do mais novo para o mais velho (até 200), e para no primeiro que não é de hoje. Arquivos ilegíveis são pulados.

#### _numeros_analise (linhas 325–337)
Linhas 325–337: a partir das análises do dia, conta colunas descritas, indicadores calculados (segmento "Total"), diferenças significativas, alertas de "atenção" e resumos escritos — um número para cada analista do 2º andar.

#### _analise_hoje (linhas 339–346)
Linhas 339–346: resumo para a TV do 2º andar: bases analisadas, destaques, alertas, último arquivo e até 7 linhas do resumo executivo.

#### historico — rota `GET /api/historico` (linhas 348–350)
Linhas 348–350: devolve até `limite` registros do histórico (padrão 500; o painel pede 1.000).

#### execucao — rota `GET /api/execucao` (linhas 352–356)
Linhas 352–356: devolve o detalhe completo de um processamento pelo `id`. Se não existir (a manutenção pode ter apagado), responde 404 com mensagem clara.

#### _listar_reprovados (linhas 358–379)
- Linhas 359–362: sem pasta Bases-Erros, lista vazia.
- Linhas 363–367: percorre a pasta do mais novo para o mais velho, ignora relatórios `_ERROS.txt` e o que não for planilha; guarda nome, nome original, id e data.
- Linhas 368–377: com detalhes, lê a execução e separa erros e avisos; se o JSON da execução não existir (registro antigo), usa o texto do `_ERROS.txt` (`utf-8-sig` aceita o BOM que o Excel/Bloco de Notas colocam).

#### reprovados — rota `GET /api/reprovados` (linhas 381–382)
Linhas 381–382: devolve a lista completa, com detalhes.

#### log — rota `GET /api/log` (linhas 384–385)
Linhas 384–385: devolve as mensagens do log em memória com número maior que `desde` (a tela Atividade busca só as novas).

#### config — rota `GET /api/config` (linhas 387–408)
- Linhas 389–391: informações básicas: erro, se é Windows, se a inicialização automática está ligada, versão e caminho do `config.yaml` (criado a partir do exemplo, se faltar).
- Linhas 395–396: copia a seção do banco e **troca a senha por `senha_definida: true/false`** — a senha nunca viaja para a página.
- Linhas 397–407: regras resumidas (padrão + nomes das validações), pastas, saída, monitoramento, banco, painel, modelos SQL e manutenção.

#### _pasta_modelos e _modelos_sql (linhas 410–418)
Linhas 410–412: descobre a pasta dos modelos SQL pela classe `Banco`. Linhas 414–418: lista os `.sql`; os que começam com `_` aparecem como desativados.

#### agentes — rota `GET /api/agentes` (linhas 420–449)
Linhas 420–449: devolve tudo o que a tela "Equipe e contratações" precisa: a linha de produção (`equipe.lista()`), analistas, liderança, Sala Excel, quadro de pessoal + canal (cada um com ficha completa do RH), escopos por nível, catálogo de habilidades (com risco e número de provas), erros ao carregar habilidades personalizadas, posições possíveis e a tabela de níveis/áreas do RH.

#### agente_salvar — rota `POST /api/agentes/salvar` (linhas 451–465)
- Linhas 454–455: pega o agente enviado e verifica se ele já tem arquivo `.yaml` (se não, é contratação nova).
- Linhas 456–461: agente novo e não nativo passa pela **contratação** (anuncia no canal e entra como estagiário em experiência); senão, só salva.
- Linhas 462–465: erro de validação do agente vira 400 com a mensagem; sucesso é registrado no log.

#### agente_manual / agente_manual_ler — rotas `POST /api/agentes/manual/salvar` e `GET /api/agentes/manual` (linhas 467–478)
Linhas 467–474: grava o manual em Markdown de um agente. Linhas 476–478: lê o manual pelo `id`.

#### canal — rota `GET /api/canal` (linhas 481–494)
- Linhas 483–486: cria o canal e lê os filtros da URL (canal, autor, tipo, busca, dias, desde, limite).
- Linhas 487–494: devolve as mensagens filtradas, a lista de canais, os autores (com nome e papel) e os dados da sprint de 15 dias.

#### canal_enviar — rota `POST /api/canal/enviar` (linhas 496–501)
Linhas 496–501: recusa mensagem vazia; senão a equipe responde (`perguntar`) no canal indicado (padrão "geral") e as mensagens novas voltam.

#### canal_sprint — rota `POST /api/canal/sprint` (linhas 503–507)
Linhas 503–507: sincroniza os acontecimentos e publica a rodada da sprint (cada pessoa conta o que fez).

#### central — rota `GET /api/central` (linhas 510–512)
Linhas 510–512: monta a Central de dados para 1, 7 ou 30 dias (`dias`).

#### estrategia — rota `GET /api/estrategia` (linhas 514–534)
- Linhas 518–521: lê o backlog, ordena (abertos primeiro, depois maior prioridade) e põe o nome do responsável.
- Linhas 522–534: últimas 12 avaliações e treinamentos, sprint atual, alinhamento por andar, nomes de status, trilhas e a lista de pessoas (sem o "dono"), em ordem alfabética.

#### estrategia_item / estrategia_excluir / estrategia_avaliar / estrategia_treinar / estrategia_sincronizar (linhas 536–562)
- Linhas 536–541 (`POST /api/estrategia/item`): cria ou altera uma prioridade; dados inválidos viram 400.
- Linhas 543–546 (`POST /api/estrategia/excluir`): exclui pelo id.
- Linhas 548–552 (`POST /api/estrategia/avaliar`): aplica as provas técnicas em todos e atualiza o backlog.
- Linhas 554–558 (`POST /api/estrategia/treinar`): roda o treinamento com planilhas difíceis e atualiza o backlog.
- Linhas 560–562 (`POST /api/estrategia/sincronizar`): cria/fecha prioridades automáticas a partir dos dados.

#### boas_praticas — rota `GET /api/boas-praticas` (linhas 564–566)
Linhas 564–566: devolve o texto de `conhecimento/boas_praticas.md` (ou vazio).

#### ti e ti_ronda — rotas `GET /api/ti` e `POST /api/ti/ronda` (linhas 569–575)
Linhas 569–571: última ronda e intervalo configurado. Linhas 573–575: roda uma ronda agora.

#### agente_excluir — rota `POST /api/agentes/excluir` (linhas 577–585)
Linhas 577–585: exclui um agente (o arquivo vai para `agentes/_excluidos`). Tentar excluir um nativo gera `ErroAgente` → 400.

#### consultas e consulta — rotas `GET /api/consultas` e `GET /api/consulta` (linhas 587–596)
Linhas 587–589: lista as consultas SQL prontas e diz se o banco está ligado. Linhas 591–596: lê uma consulta; id inválido (ou fora da pasta) vira 404.

#### consulta_executar — rota `POST /api/consultas/executar` (linhas 598–615)
- Linhas 602–603: banco desligado → 409.
- Linhas 604–613: lê e executa. Consulta inexistente → 404; banco fora do ar → 503; erro de SQL → resposta `ok: false` com explicação em português (`explicar_erro`).
- Linhas 614–615: sucesso: colunas, linhas formatadas por `_fmt`, se foi cortado e a duração.

#### banco_resumo — rota `GET /api/banco/resumo` (linhas 617–628)
Linhas 617–628: com o banco ligado, pede o resumo (tabelas por camada e últimas cargas) e converte a data de cada lote em texto. Banco fora do ar vira `ok: false` com mensagem (não erro HTTP).

#### ligar / pausar / processar_agora — rotas `POST /api/robo/ligar`, `/api/robo/pausar`, `/api/robo/processar-agora` (linhas 631–642)
Linhas 631–637: ligam/pausam o monitor e devolvem o estado. Linhas 639–642: dispara um ciclo imediato; sem configuração → 409.

#### abrir — rota `POST /api/abrir` (linhas 644–667)
Abre uma pasta no Explorador ou um arquivo no programa padrão.
- Linhas 647–650: lista **fechada** de destinos permitidos: as pastas do robô, modelos, projeto, consultas, agentes e habilidades.
- Linhas 651–653: destino conhecido → cria a pasta se faltar.
- Linhas 654–655: "config" → o `config.yaml`.
- Linhas 656–659: "arquivo" → só se estiver **dentro** de uma das pastas permitidas (`_dentro`) e existir; senão 404. É essa proteção que o teste com `C:/Windows/system32/calc.exe` confirma.
- Linhas 660–663: "reprovado" → só o **nome** (`Path(...).name`) é usado, sempre dentro de Bases-Erros; isso impede `../`.
- Linhas 664–667: qualquer outro destino → 400; senão abre com `sistema.abrir_no_sistema`.

#### reprocessar — rota `POST /api/reprovados/reprocessar` (linhas 669–684)
- Linhas 671–673: localiza o arquivo em Bases-Erros (só pelo nome).
- Linhas 674–676: o destino é Bases-Limpeza com o nome original; se já existir um igual esperando, 409.
- Linhas 677–680: move; se o Excel estiver com o arquivo aberto (Windows bloqueia), avisa para fechar.
- Linhas 681–684: apaga o relatório `_ERROS.txt` antigo e registra no log.

#### descartar — rota `POST /api/reprovados/descartar` (linhas 686–700)
Linhas 686–700: em vez de apagar, move o arquivo e seu `_ERROS.txt` para `Bases-Erros/_descartados` (dá para recuperar). Arquivo aberto no Excel → 409.

#### _salvar_upload (linhas 702–708)
Linhas 702–708: usa só o nome final do arquivo (sem pastas), recusa extensão não suportada com 415 e move o arquivo temporário para o destino.

#### testar — rota `POST /api/testar` (upload) (linhas 710–730)
- Linhas 711–714: cria uma pasta temporária, salva o arquivo lá e roda o pipeline com `gravar=False` (nada é gravado, movido ou carregado).
- Linhas 715–724: para cada tabela, monta a prévia: nome, linhas, colunas (com tipo amigável e quantidade de vazios) e as 25 primeiras linhas formatadas.
- Linhas 725–728: veredito: aprovado?, linhas de entrada/saída, duração, regra usada e ocorrências.
- Linhas 729–730: `finally` apaga a pasta temporária, dê certo ou errado.

#### enviar — rota `POST /api/enviar` (upload) (linhas 732–738)
Linhas 732–738: se já existir um arquivo com o mesmo nome em Bases-Limpeza, 409; senão salva lá e registra no log. O monitor processa depois.

#### definir_entrada — rota `POST /api/config/entrada` (linhas 740–749)
Linhas 740–749: limpa espaços e aspas do caminho colado (o "Copiar como caminho" do Windows vem entre aspas), exige que a pasta exista, grava em `pastas.entrada`, recarrega e liga o robô se a preferência mandar.

#### salvar_config — rota `POST /api/config/salvar` (linhas 751–764)
Linhas 751–764: para cada seção/chave enviada, chama `configuracao.definir` (que só aceita chaves da lista `EDITAVEIS`). Senha vazia significa "manter a atual". Chave proibida vira 400. Depois recarrega a configuração.

#### banco_testar — rota `POST /api/banco/testar` (linhas 766–774)
Linhas 766–774: começa pela configuração salva, sobrepõe o que foi digitado (senha vazia mantém a salva) e testa a conexão — sem gravar nada.

#### banco_modelos — rota `POST /api/banco/modelos` (linhas 776–787)
Linhas 776–787: abre conexão e **transação** (bloco "tudo ou nada"), prepara os schemas e executa os modelos SQL. Erro de banco vira `ok: false` com mensagem.

#### manutencao — rota `POST /api/manutencao` (linhas 789–790)
Linhas 789–790: roda a limpeza de arquivos antigos e devolve quantos foram removidos por tipo.

#### inicializacao — rota `POST /api/inicializacao` (linhas 792–796)
Linhas 792–796: liga/desliga o início junto com o Windows; fora do Windows vira 400 com mensagem.

#### atalhos — rota `POST /api/atalhos` (linhas 798–802)
Linhas 798–802: cria os atalhos; qualquer falha vira 400 com a mensagem.

#### recarregar — rota `POST /api/config/recarregar` (linhas 804–806)
Linhas 804–806: relê o `config.yaml` (útil depois de editar à mão).

#### sair — rota `POST /api/sair` (linhas 808–811)
Linhas 808–811: registra no log e cria uma thread que espera 0,3 s e levanta a bandeira `encerrar`. A espera dá tempo de a resposta chegar ao navegador antes de o programa fechar.

### Tabelas de rotas (linhas 814–835)
- Linhas 814–821: `ROTAS_GET`, dicionário endereço → função. `/api/ping` (linha 815) é uma função anônima (`lambda`) que responde `{"app": "robo-planilhas", "versao": ...}` — serve para saber se o robô já está aberto.
- Linhas 822–834: `ROTAS_POST`, as ações.
- Linha 835: `ROTAS_UPLOAD`, as duas rotas que recebem arquivo bruto (`/api/testar`, `/api/enviar`).

Guardar as rotas em dicionários é uma proteção por si só: um endereço que não está na lista simplesmente não existe.

### criar_manipulador (linhas 838–936)
Fabrica a classe que atende cada pedido HTTP, já "presa" à `Api` e à porta.
- Linhas 839–840: os únicos `Host` aceitos são `127.0.0.1:PORTA` e `localhost:PORTA`; as únicas origens aceitas são as mesmas com `http://`.

#### class Manipulador (linhas 842–934)
- Linha 843: nome que o servidor informa nas respostas.
- Linhas 845–846 (`log_message`): silencia a linha de log que o Python escreveria a cada pedido (seriam milhares por hora).

##### _json (linhas 848–857)
Linhas 848–857: converte o dicionário em JSON (`ensure_ascii=False` mantém acentos; `default=str` transforma em texto o que o JSON não entende, como datas), envia status, tipo, `Cache-Control: no-store` (o navegador nunca guarda dados velhos), os cabeçalhos de segurança, o tamanho e o corpo.

##### _host_ok (linhas 859–860)
Linhas 859–860: confere se o cabeçalho `Host` é um dos permitidos. É a defesa contra DNS rebinding: um site malicioso que consiga apontar para 127.0.0.1 ainda enviaria o próprio nome no `Host`, e é recusado.

##### do_GET (linhas 862–868)
Linhas 862–868: `Host` inválido → 403. Separa caminho e parâmetros; se o caminho é uma rota GET, executa; senão tenta entregar um arquivo estático.

##### do_POST (linhas 870–889)
As camadas de proteção das ações, nesta ordem:
- Linhas 871–872: `Host` válido **e** cabeçalho `X-Robo-Painel: 1`. Um formulário ou link de outro site não consegue enviar cabeçalho personalizado sem permissão do servidor (o navegador bloqueia), então ações "às escondidas" ficam impossíveis.
- Linhas 873–875: se veio `Origin` (o site de onde partiu o pedido), ela precisa ser o próprio painel.
- Linhas 876–879: lê o tamanho declarado; rotas de upload vão para `_upload`.
- Linhas 880–881: rota que não existe → 404.
- Linhas 882–884: corpo maior que 2 MB → 413, **sem ler o corpo**, e fecha a conexão (assim ninguém trava o servidor mandando um texto gigante).
- Linhas 885–889: lê e interpreta o JSON (corpo vazio vira `{}`); JSON inválido → 400; senão executa a ação.

##### _upload (linhas 891–907)
- Linhas 892–893: arquivo vazio ou maior que 300 MB → 413.
- Linha 894: o nome do arquivo vem no cabeçalho `X-Nome-Arquivo`, codificado para aceitar acentos (`unquote` desfaz isso).
- Linhas 895–904: cria um arquivo temporário e copia o corpo em blocos de 1 MB (`1 << 20`), sem carregar 300 MB na memória de uma vez; se a conexão acabar antes, para.
- Linhas 905–907: executa a rota e, no `finally`, apaga o temporário (se ainda existir).

##### _executar (linhas 909–916)
Linhas 909–916: roda a função da rota. `ErroApi` vira resposta com o status e a mensagem dele; qualquer outro erro é registrado com o rastreamento completo no log e responde 500 com o tipo e a mensagem do erro. Assim um defeito numa rota nunca derruba o servidor.

##### _estatico (linhas 918–934)
- Linha 919: o endereço vazio ou `/` entrega `inicio.html`.
- Linhas 920–922: **proteção de caminho**: resolve o caminho real e exige que esteja dentro da pasta `estaticos` e seja um arquivo; `/../config.yaml` ou `/../../Windows/...` dá 404.
- Linhas 923–926: lê o arquivo e escolhe o tipo pela tabela fixa (o comentário explica: no Windows o `mimetypes` lê o registro do sistema e pode dizer que `.js` é texto puro, o que impediria o navegador de rodar o escritório 3D).
- Linhas 927–934: envia com `Cache-Control: no-cache` (o navegador confere se há versão nova), os cabeçalhos de segurança, o tamanho e o conteúdo.

Linha 936: devolve a classe pronta.

### ja_rodando (linhas 939–944)
Linhas 939–944: tenta chamar `/api/ping` em até 1,5 s; se a resposta disser `"app": "robo-planilhas"`, já existe um robô aberto. Qualquer erro significa "não".

### iniciar_app (linhas 947–988)
O "ligar o aplicativo".
- Linhas 948–950: cria o controle (que carrega a configuração), decide a porta (parâmetro, `painel.porta` do config ou 8765) e monta o endereço.
- Linhas 951–955: se já houver um robô aberto, só abre a janela de novo e sai — clicar duas vezes no atalho não cria dois robôs.
- Linhas 957–962: pega a **trava de instância** (um arquivo na pasta de logs). Se outro robô (por exemplo, o modo texto) estiver rodando, registra o erro e sai com código 3.
- Linhas 964–970: cria a `Api` e o servidor **amarrado a 127.0.0.1** — essa é a proteção "somente esta máquina": o servidor nem escuta na rede. Porta ocupada → mensagem, solta a trava, código 4.
- Linhas 971–973: `daemon_threads = True` faz as threads de atendimento morrerem junto com o programa; o servidor roda numa thread própria chamada `robo-painel`.
- Linhas 975–978: liga o robô (se a preferência mandar) e abre a janela (exceto no modo `--sem-janela`).
- Linhas 979–988: o programa fica esperando, de segundo em segundo, a bandeira `encerrar` (ou Ctrl+C). Ao sair, pausa o robô, desliga o servidor e solta a trava. Devolve 0 (sucesso).

**Erros que este arquivo evita**:
- Outros computadores da rede ou sites abertos no navegador mexendo no seu robô (127.0.0.1, `Host`, `X-Robo-Painel`, `Origin`).
- O painel ser embutido num site para enganar seus cliques (X-Frame-Options e CSP).
- Ler arquivos fora da pasta da interface ou abrir programas fora das pastas do robô (verificação de caminho e `_dentro`).
- Servidor travado ou sem memória por corpo gigante (limites de 2 MB e 300 MB, cópia em blocos).
- Senha do banco aparecendo na tela (`senha_definida`).
- Dois robôs processando a mesma pasta (ping + trava de instância).
- Um erro numa rota derrubar o painel inteiro (`_executar`).
- Escritório 3D em branco no Windows por tipo errado de `.js` (`TIPOS_ESTATICOS`).

---

## robo/painel/controle.py

- **Para que serve**: é o "interruptor" do robô dentro do painel. Liga e pausa o monitor (que vigia Bases-Limpeza) numa thread separada, roda as rotinas da empresa (canal, estratégia, backup e ronda de TI), guarda as últimas mensagens do log para a tela Atividade, guarda os eventos de cada etapa para o escritório 3D e dispara as notificações do Windows.
- **Onde entra no fluxo**: é criado por `iniciar_app` (servidor.py, linha 948) e usado por quase todas as rotas da `Api` (como `self.c`).

### Docstring e imports (linhas 1–17)
- Linha 1: descrição do módulo.
- Linhas 5–10: `collections` (traz o `deque`, uma lista com tamanho máximo que descarta os itens mais antigos sozinha), `logging`, `threading`, `time`, `datetime`, `Path`.
- Linhas 12–15: `ErroConfig` e `carregar_config` (configuração), `Monitor`, o módulo `sistema` (notificações) e os status do pipeline (`ADIADO`, `REPROVADO`, `SUCESSO`).
- Linha 17: o log `"robo"`.

### class MemoriaLog (linhas 20–41)
Um **handler** de log: uma "saída" extra para onde o `logging` copia cada mensagem (além do arquivo e da tela).
- Linhas 23–27 (`__init__`): guarda até 1.000 registros num `deque`, um contador `sequencia` e uma **trava** (`Lock`) — um cadeado que garante que só uma thread mexa na lista por vez.
- Linhas 29–37 (`emit`): chamado pelo `logging` a cada mensagem; com o cadeado fechado, aumenta o número e guarda número, hora (`dd/mm hh:mm:ss`), nível (INFO, WARNING, ERROR) e texto.
- Linhas 39–41 (`desde`): devolve os registros com número maior que o informado.

### class ControleRobo (linhas 44–181)

#### __init__ (linhas 45–59)
Linhas 45–59: guarda o caminho do config; começa sem configuração, sem monitor e sem thread; cria a bandeira `_parar`, duas travas (uma para ligar/pausar, outra para os eventos), a memória de log e o `deque` de até 400 eventos para o escritório. Na linha 58 pendura a `MemoriaLog` no log `"robo"` e, na 59, carrega a configuração.

#### carregar (linhas 62–73)
Linhas 62–73: tenta carregar o config, criar as pastas e montar o `Monitor`, passando duas funções de retorno (**callbacks** — funções que o monitor chama quando algo acontece): `_apos_processar` (ao terminar um arquivo) e `_registrar_etapa` (a cada etapa). Configuração inválida ou pasta inacessível não derrubam nada: ficam guardadas em `erro_config` e aparecem na tela de boas-vindas.

#### recarregar (linhas 75–80)
Linhas 75–80: lembra se estava ligado, pausa, recarrega e, se estava ligado e a nova configuração é válida, liga de novo.

#### ligado (linhas 83–85)
Linhas 83–85: o robô está ligado se a thread existe e está viva (`is_alive`).

#### ligar (linhas 87–97)
Linhas 87–97: com o cadeado fechado (evita dois cliques simultâneos criarem duas threads), se já estiver ligado ou sem monitor, só devolve o estado. Senão cria uma bandeira nova, cria a thread `robo-monitor` (do tipo **daemon**, que morre junto com o programa) rodando `_laco`, anota a hora e registra no log.

#### pausar (linhas 99–106)
Linhas 99–106: levanta a bandeira `_parar` e espera a thread terminar o que está fazendo por até 120 s (`join`) — assim uma planilha no meio do caminho termina direito. Zera o "ligado desde" e registra.

#### _laco (linhas 108–115)
Linhas 108–115: o coração do robô ligado: enquanto a bandeira não subir, roda um ciclo do monitor (erro inesperado é registrado, mas o laço continua), roda as rotinas e espera o intervalo configurado. `parar.wait(...)` é uma espera que acorda na hora se alguém pedir para parar.

#### _rotinas (linhas 117–154)
Rotinas que não dependem de arquivo novo.
- Linhas 119–121: sem configuração, nada a fazer.
- Linhas 122–128: a cada 60 s, sincroniza o canal da equipe (posta os acontecimentos). `getattr(self, "_ultimo_canal", 0)` lê o atributo ou usa 0 na primeira vez.
- Linhas 129–146: a cada 3.600 s (1 hora), se não estiver rodando, dispara numa thread separada `robo-estrategia` a rotina de estratégia (avaliação/treinamento por sprint) e o backup diário do PostgreSQL; cada uma tem seu próprio `try`, e o `finally` sempre libera a marca "rodando". Ficam em segundo plano porque levam alguns segundos.
- Linhas 147–154: a cada `intervalo_minutos` da TI (padrão 30), roda a ronda de TI.

#### processar_agora (linhas 156–160)
Linhas 156–160: sem monitor, devolve `False`. Senão cria uma thread `robo-agora` que roda um ciclo forçado (sem esperar a sincronização). O monitor tem um cadeado próprio, então isso não colide com o ciclo normal.

#### _registrar_etapa (linhas 163–166)
Linhas 163–166: chamado pelo pipeline a cada etapa; com o cadeado dos eventos, aumenta o número e guarda número, hora, etapa, arquivo e extras (status, linhas, erros...). É daqui que o escritório 3D tira as animações.

#### eventos_desde (linhas 168–170)
Linhas 168–170: devolve os eventos novos a partir de um número.

#### _apos_processar (linhas 173–181)
Linhas 173–181: se as notificações estiverem ligadas: sucesso → "Planilha tratada: X linhas prontas" (com ponto de milhar); reprovado → "Planilha reprovada: N erro(s)"; adiado → nada (resolve-se sozinho).

**Erros que este arquivo evita**:
- O painel congelar enquanto uma planilha é processada (thread separada).
- Duas threads do robô ao mesmo tempo (cadeado em `ligar`).
- Arquivo cortado ao meio ao pausar (`join` espera terminar).
- Um erro num ciclo ou numa rotina desligar o robô (`try/except` no laço).
- Mensagens embaralhadas entre threads (travas na memória de log e nos eventos).
- Memória crescendo sem fim (`deque` com 1.000 logs e 400 eventos).

---

## robo/painel/configuracao.py

- **Para que serve**: deixa o painel alterar o `config.yaml` sem destruir seus comentários e a organização do arquivo. Só mexe na linha `chave: valor` da seção certa e só em configurações de uma lista permitida.
- **Onde entra no fluxo**: usado pelas rotas `/api/config/salvar`, `/api/config/entrada` e `/api/config` do servidor. **YAML** é o formato do `config.yaml`: texto com `chave: valor` e indentação (espaços) indicando hierarquia.

### Docstring e imports (linhas 1–14)
Linhas 1–4: explicam o objetivo (preservar comentários). Linhas 8–14: `re` (padrões de texto), `shutil` (copiar), `Path`, `yaml` (biblioteca PyYAML) e `RAIZ_PROJETO`.

### EDITAVEIS (linhas 16–23)
Linhas 16–23: a **lista branca**: seção → chaves que o painel pode alterar (pasta de entrada; formato e versionamento da saída; espera de estabilidade; campos do banco; ligar ao abrir e notificações). Qualquer outra coisa é recusada.

### garantir_arquivo (linhas 26–30)
Linhas 26–30: usa o caminho informado ou `config.yaml` na raiz; se não existir, copia `config.exemplo.yaml`. Devolve o caminho.

### _escalar (linhas 33–37)
Linhas 33–37: transforma um valor do Python em texto YAML de uma linha só (`default_flow_style=True`), com acentos preservados. O `yaml.safe_dump` às vezes acrescenta `...` (marca de fim de documento) e uma quebra de linha; as linhas 35–37 removem isso. Ex.: `True` vira `true`; um texto com `:` ganha aspas.

### definir (linhas 40–63)
- Linhas 41–42: chave fora da lista branca → `ValueError` (vira 400 no servidor).
- Linhas 43–44: lê o arquivo em linhas e prepara a linha nova com 2 espaços de indentação.
- Linha 45: procura a linha que abre a seção (`secao:` no começo da linha, podendo ter comentário) usando uma **expressão regular** (um padrão de busca de texto); `re.escape` impede que caracteres especiais do nome atrapalhem.
- Linhas 46–47: seção não existe → acrescenta no fim.
- Linhas 49–50: descobre onde a seção termina: a próxima linha não vazia que começa sem espaço e não é comentário.
- Linhas 51–56: procura `chave:` dentro da seção, guardando a indentação original e um eventual comentário no fim da linha (grupo 4); troca só o valor e mantém o comentário.
- Linhas 57–60: se a chave não existe (`for ... else`: o `else` roda quando o laço termina sem `break`), insere depois da última linha "de verdade" da seção.
- Linhas 61–63: junta o texto, **valida com `yaml.safe_load` antes de gravar** (se ficou inválido, dá erro e o arquivo original não é tocado) e grava.

**Erros que este arquivo evita**: perder seus comentários e anotações no `config.yaml`; o painel alterar configurações perigosas que não deveria (lista branca); gravar um `config.yaml` quebrado que impediria o robô de abrir; ficar sem config na primeira execução.

---

## robo/painel/sistema.py

- **Para que serve**: faz a ponte com o Windows: abre pastas e arquivos, mostra notificações no canto da tela, abre o painel numa janela "de aplicativo" (sem barra de endereço), liga/desliga a inicialização automática e cria atalhos. Em outros sistemas faz o possível ou simplesmente ignora.
- **Onde entra no fluxo**: chamado por `servidor.py` (abrir, janela, atalhos, inicialização) e `controle.py` (notificações).

### Docstring e imports (linhas 1–16)
Linhas 1–2: descrição. Linhas 6–14: `os` (variáveis de ambiente e `startfile`), `shutil.which` (procurar um programa), `subprocess` (rodar outros programas), `sys`, `webbrowser` (abrir o navegador padrão), `Path`, `RAIZ_PROJETO`. Linha 16: log.

### Constantes (linhas 18–21)
Linha 18: `EH_WINDOWS` é verdadeiro no Windows (`os.name == "nt"`). Linha 19: nome do atalho. Linha 20: nome do arquivo colocado na pasta de inicialização. Linha 21: `SEM_JANELA`, código do Windows para rodar um programa sem abrir janela preta.

### abrir_no_sistema (linhas 24–31)
Linhas 24–31: no Windows, `os.startfile` abre como se você desse dois cliques (pasta no Explorador, `.xlsx` no Excel). No Mac usa `open`; no Linux, `xdg-open`, se existir.

### _powershell (linhas 34–41)
Linhas 34–41: roda um script do **PowerShell** (a linha de comando avançada do Windows) entregando o texto pela entrada padrão (`-Command -`), sem perfil, sem interação, sem janela e sem mostrar saída. Se `esperar=True`, aguarda até 30 s.

### _ps_texto (linhas 44–45)
Linhas 44–45: coloca um texto entre aspas simples para o PowerShell, dobrando aspas simples internas. Isso impede que um nome de arquivo com `'` "quebre" o script e execute comandos (injeção).

### notificar (linhas 48–64)
Linhas 48–64: fora do Windows não faz nada. No Windows monta um script que usa o sistema de notificações nativo ("toast", modelo com título e texto), insere título e mensagem já protegidos por `_ps_texto` e mostra a notificação em nome do PowerShell (o código longo na linha 59 é o identificador do PowerShell no Windows). Qualquer falha é silenciosa (só log de depuração).

### _navegador_app (linhas 67–76)
Linhas 67–76: procura o Edge e o Chrome nas pastas de programas (`ProgramFiles(x86)`, `ProgramFiles`, `LOCALAPPDATA`); se não achar, tenta pelo PATH. Devolve o caminho ou `None`.

### abrir_janela (linhas 79–88)
Linhas 79–88: no Windows, com Edge/Chrome, abre `--app=URL` em 1360×900 — o painel parece um programa, sem abas nem barra de endereço. Sem isso, abre no navegador padrão.

### pasta_inicializacao (linhas 92–95)
Linhas 92–95: só no Windows: devolve a pasta `Inicializar` do usuário (tudo o que estiver lá abre quando você entra no Windows).

### inicializacao_ligada (linhas 98–100)
Linhas 98–100: está ligada se o arquivo `RoboPlanilhas.vbs` existe nessa pasta.

### definir_inicializacao (linhas 103–114)
Linhas 103–114: fora do Windows, erro explicativo. Para ligar, escreve um pequeno VBScript que roda o lançador `Abrir Robo de Planilhas.vbs` com `/oculto` (sem abrir janela), gravado em UTF-16 para o Windows ler corretamente caminhos com acento. Para desligar, apaga o arquivo. Devolve o estado final.

### criar_atalhos (linhas 117–137)
Linhas 117–137: só no Windows. Monta um script PowerShell que, para a Área de Trabalho e para o Menu Iniciar (Programas), cria `Robô de Planilhas.lnk` apontando para `wscript.exe` com o lançador `.vbs` como argumento, na pasta do projeto, com o ícone `robo.ico` e uma descrição. Todos os textos passam por `_ps_texto`. Espera terminar e devolve os dois locais.

**Erros que este arquivo evita**: janela preta piscando a cada notificação (`SEM_JANELA`); scripts quebrados ou injetados por nomes com aspas (`_ps_texto`); caminhos com acento ilegíveis na inicialização (UTF-16); o programa falhar fora do Windows (verificações de `EH_WINDOWS`).

---
## robo/painel/estaticos/inicio.html

- **Para que serve**: é o "esqueleto" da tela principal do painel: a barra lateral com o menu, a área de conteúdo (preenchida pelo JavaScript), a camada de "soltar arquivos", a gaveta lateral de detalhes, a janela de confirmação e a área de avisos.
- **Onde entra no fluxo**: é o arquivo entregue quando o navegador pede `/` (servidor.py, linha 919). **HTML** é a linguagem que descreve a estrutura de uma página (títulos, botões, caixas).

### Cabeçalho da página (linhas 1–9)
Linha 1: declara que é HTML moderno. Linha 2: idioma pt-BR. Linhas 4–5: acentos em UTF-8 e ajuste para telas pequenas. Linha 6: título da aba. Linha 7: ícone (`robo.svg`). Linha 8: carrega o visual (`painel.css`).

### Barra lateral (linhas 11–40)
- Linha 11: `div.app`, a grade com duas colunas (menu + conteúdo).
- Linhas 13–19: a marca (ícone, "Robô de Planilhas", "ETL & ELT local"; `&amp;` é como se escreve `&` em HTML).
- Linhas 20–35: o menu. Cada link aponta para um **hash** (a parte da URL depois de `#`, como `#historico`), que o JavaScript usa para trocar de página sem recarregar. `data-pagina` diz qual página o link representa; `<i data-icone="...">` é um marcador que o `painel.js` troca pelo desenho do ícone. A exceção é a linha 24, "Escritório 3D", que abre outra página (`escritorio.html`). Na linha 28, o `<b id="badge-reprovados">` é o contador vermelho de reprovados, escondido (`hidden`) até haver pendências.
- Linhas 36–39: o indicador de status no rodapé do menu (bolinha `ponto-status`, texto e subtexto).

### Conteúdo (linha 42)
Linha 42: `main#conteudo`, onde cada página é desenhada.

### Camada de soltar arquivos (linhas 45–58)
Linhas 45–58: aparece quando você arrasta um arquivo para a janela. Tem duas zonas (`soltar-zona`): "Enviar para processamento" (`data-acao="enviar"`) e "Só testar" (`data-acao="testar"`).

### Gaveta, modal e avisos (linhas 60–63)
Linha 60: o fundo escuro atrás da gaveta. Linha 61: a gaveta lateral (`aria-hidden` informa leitores de tela se está visível). Linha 62: o fundo da janela de confirmação. Linha 63: a pilha de avisos (`aria-live="polite"` faz leitores de tela anunciarem as mensagens novas).

### Script (linha 65)
Linha 65: carrega o `painel.js` no fim, quando todos os elementos acima já existem.

**Erros que este arquivo evita**: o JavaScript procurar elementos que ainda não existem (o script vem por último); dependência de internet (nada externo é carregado).

---

## robo/painel/estaticos/painel.js

- **Para que serve**: é o cérebro da tela do painel. Desenha as 13 páginas, busca os dados na API a cada poucos segundos, responde aos cliques (ligar, pausar, reprocessar, salvar configurações, contratar agentes, executar consultas...) e cuida de arrastar e soltar planilhas. Não usa nenhuma biblioteca externa, então funciona sem internet.
- **Onde entra no fluxo**: carregado pelo `inicio.html`; conversa com as rotas `/api/...` de `servidor.py`.

Três conceitos de JavaScript que aparecem o tempo todo:
- **DOM**: a "árvore" de elementos da página que o JavaScript consegue ler e alterar (por exemplo, trocar o conteúdo de `#conteudo`).
- **fetch**: a função do navegador para fazer pedidos HTTP à API.
- **async/await e Promise**: uma *Promise* é a "promessa" de um resultado que chega depois (como a resposta de um pedido); `await` espera essa promessa sem travar a tela; funções `async` podem usar `await`.
- **Template string**: texto entre crases `` `...${valor}...` `` em que `${}` insere valores. O painel monta o HTML de cada página assim e coloca com `innerHTML`.

### Cabeçalho (linhas 1–5)
Linhas 1–4: comentário: sem bibliotecas, funciona offline, conversa com `/api/...`. Linha 5: `"use strict"` liga o modo rigoroso do JavaScript (erros bobos, como usar variável não declarada, viram erro em vez de passar em silêncio).

### ICONES e icone (linhas 8–48)
Linhas 8–47: dicionário nome → desenho SVG (vetor; as linhas `<path>`, `<circle>`, `<rect>` desenham traços num quadro 24×24). Linha 48: `icone(nome, classe)` monta o `<svg>` completo com a classe CSS `icone`; `aria-hidden` esconde o desenho de leitores de tela.

### Utilitários curtos (linhas 51–53)
- Linha 51: `esc` troca `& < > " '` pelos códigos HTML equivalentes. **Todo texto vindo de dados passa por `esc` antes de entrar no HTML**, o que impede que um nome de arquivo como `<script>...` seja executado (ataque chamado XSS).
- Linha 52: `num` formata número no padrão brasileiro (`1.234`) ou mostra "—" se vazio.
- Linha 53: `$` é um atalho para `querySelector` (achar o primeiro elemento que casa com um seletor CSS, como `#conteudo`).

### dataCurta (linhas 55–62)
Linhas 55–62: recebe `"2026-10-17 14:30:00"`; se for hoje, mostra `hoje, 14:30`; senão `17/10/2026 14:30`.

### relativo (linhas 63–70)
Linhas 63–70: transforma um horário (em segundos) em "agora", "há 12 s", "há 3 min" ou "há 2 h".

### tamanho (linhas 71–75)
Linhas 71–75: bytes → "B", "KB" ou "MB" (com vírgula).

### duracao (linhas 76–80)
Linhas 76–80: segundos → "4,2 s" ou "1 min 5 s"; aceita vírgula ou ponto; valor inválido vira "—".

### api (linhas 82–102)
A função que conversa com o servidor.
- Linha 83: o método é POST se houver corpo ou arquivo; senão GET.
- Linha 84: todo POST leva `X-Robo-Painel: 1` (a senha de "sou o painel" que o servidor exige).
- Linhas 85–88: com arquivo, o corpo é o próprio arquivo, o nome vai no cabeçalho `X-Nome-Arquivo` (codificado com `encodeURIComponent` por causa de acentos) e o tipo é "binário genérico".
- Linhas 89–92: com corpo, transforma o objeto em JSON.
- Linhas 93–98: faz o `fetch`; se nem conectar, mostra "Sem conexão com o robô...".
- Linhas 99–101: lê o JSON da resposta (ou `{}`); se o status não for de sucesso, lança erro com a mensagem do servidor.

### avisar (linhas 104–110)
Linhas 104–110: cria um aviso (balão) com ícone conforme o tipo (erro, sucesso, informação), coloca em `#avisos` e remove depois de 7 s (erro) ou 4 s.

### confirmar (linhas 112–124)
Linhas 112–124: mostra uma janela "Tem certeza?" e devolve uma Promise que se resolve com `true` (botão confirmar) ou `false` (cancelar ou clique fora). O botão de confirmar recebe o foco; com `perigo`, fica vermelho.

### comCarregando (linhas 126–131)
Linhas 126–131: enquanto uma tarefa roda, desliga o botão e mostra "Aguarde…" com ícone girando; erro vira aviso vermelho; no fim, devolve o botão ao normal (se ele ainda estiver na tela).

### E — o estado da tela (linhas 134–148)
Linhas 134–148: um único objeto guarda tudo o que a tela sabe: dados gerais, página atual, histórico e filtros, reprovados, teste em andamento, configuração, banco, equipe e agente em edição, consultas, log, organograma, canal e filtros, TI, central, estratégia. As "assinaturas" (`assinaturaHist`, `assinaturaRep`) servem para saber se algo mudou e vale redesenhar.

### STATUS e etiquetaStatus (linhas 150–155)
Linhas 150–154: status → [texto, cor, ícone] (Aprovado/verde, Reprovado/vermelho, Adiado/laranja). Linha 155: monta a etiqueta colorida.

### PAGINAS (linhas 158–172)
Linhas 158–172: o mapa das 13 páginas: título, função que desenha (`render`) e, quando precisa buscar dados antes, função `carregar`.

### irPara (linhas 174–183)
Linhas 174–183: troca de página: página desconhecida vira "inicio"; fecha a gaveta; marca o item ativo no menu; muda o título da aba; desenha logo (para não ficar em branco); se a página precisa de dados, carrega e desenha de novo; volta a rolagem ao topo.

### desenhar (linhas 185–192)
Linhas 185–192: sem dados ainda → "Conectando ao robô…"; com erro de configuração (exceto na Atividade) → tela de boas-vindas; senão desenha a página atual. Na Atividade, rola o log para o fim; no Canal, rola as mensagens para o fim.

### cabecalho (linhas 194–195)
Linhas 194–195: monta o título, o subtítulo e os botões do topo de cada página.

### atualizarEstado (linhas 198–214)
Chamada a cada 2 s.
- Linhas 200–202: busca `/api/estado` e atualiza a barra lateral.
- Linha 203: na primeira vez, ou se a configuração passou de "com erro" para "ok" (ou o contrário), redesenha tudo.
- Linha 204: na Visão geral, redesenha sem atrapalhar quem está digitando.
- Linhas 205–209: nos Reprovados e no Histórico, só recarrega se o número de pendentes ou o registro mais recente mudou.
- Linhas 210–213: se falhar, marca "desconectado" e mostra o erro na lateral.

### desenharSemPerderFoco (linhas 216–223)
Linhas 216–223: se você está com o cursor num campo de texto ou lista da página, não redesenha (perderia o que você digitou); no Histórico, atualiza só as linhas da tabela. Senão, redesenha normalmente.

### atualizarLateral (linhas 225–239)
Linhas 225–239: pinta a bolinha e os textos: vermelho "Sem conexão" (aplicativo encerrado), vermelho "Configuração pendente", verde "Monitorando"/"Processando…" (com "Verificado há X"), ou laranja "Pausado". Também mostra/esconde o contador de reprovados.

### renderBoasVindas (linhas 242–257)
Linhas 242–257: a tela de primeira configuração: explica que a pasta Bases-Limpeza não foi encontrada, mostra o erro, dá 3 passos (Explorador → botão direito → "Copiar como caminho" → colar) e oferece o campo `#campo-entrada` com o botão "Salvar e começar" (ação `salvar-entrada`).

### Página "Visão geral" — ESTADO_FILA e renderInicio (linhas 260–342)
- Linhas 260–266: estado do arquivo na fila → [texto, cor, ícone] (Detectado, Aguardando sincronização, Aberto em outro programa, Processando, Adiado).
- Linhas 271–282: o cartão "herói": ícone, "Monitorando Bases-Limpeza" / "Processando X" / "Robô pausado", última verificação e os botões **Processar agora**, **Pausar** ou **Ligar robô**.
- Linhas 284–295: quatro indicadores (KPIs): aprovados hoje, linhas tratadas hoje, taxa de aprovação de 30 dias e "Aguardando correção" (vermelho e clicável quando há pendências, levando a Reprovados).
- Linhas 297–310: "Na fila agora": lista cada arquivo com tamanho, motivo e etiqueta (com segundos de espera e ícone girando ao processar). Fila vazia mostra uma área para soltar/escolher arquivos.
- Linhas 312–323: "Últimos processamentos": cada item clicável abre o detalhe (`ver-execucao`).
- Linhas 325–338: "Fluxo das pastas": Bases-Limpeza → Robô → Bases-Tratadas / Bases-Erros, cada pasta é um botão que abre no Explorador.
- Linhas 340–341: junta tudo na ordem.

### Página "Reprovados" — carregarReprovados, blocoOcorrencias, renderReprovados (linhas 345–392)
- Linhas 345–350: busca a lista e anota a assinatura.
- Linhas 352–364 (`blocoOcorrencias`): separa erros, avisos e informações; cada ocorrência mostra mensagem, coluna/tabela/quantidade e exemplos (como "linha 7: nove"). Erros vêm primeiro ("impedem a publicação"), avisos depois, e as etapas executadas ficam num bloco recolhível.
- Linhas 366–392 (`renderReprovados`): os 4 passos (abrir no Excel, corrigir, salvar e fechar, reprocessar); se não há pendências, mensagem verde; senão, um cartão por arquivo com os botões **Abrir planilha**, **Já corrigi — reprocessar** e o ícone de lixeira (**descartar**). Registros antigos sem detalhes mostram o texto do relatório.

### Página "Histórico" — carregarHistorico, linhasHistorico, renderHistorico (linhas 395–430)
- Linhas 395–400: busca 1.000 registros.
- Linhas 402–414: filtra por status e busca no nome; monta as linhas (data, arquivo, status, linhas entrada → saída, erros, avisos, duração). Cada linha abre o detalhe.
- Linhas 416–430: botões de filtro (Todos/Aprovados/Reprovados), campo de busca, contador e a tabela; botão para abrir a pasta de logs (o `historico_processamentos.csv` abre no Excel ou Power BI).

### Gaveta de detalhes — abrirGaveta, fecharGaveta, verExecucao (linhas 433–479)
- Linhas 433–437: coloca o conteúdo, abre a gaveta e mostra o fundo escuro.
- Linhas 438–443: fecha, tira o modo "larga", esquece o agente em edição.
- Linhas 445–479 (`verExecucao`): sem id (registro antigo) avisa; senão mostra "Carregando…", busca `/api/execucao`, conta erros e avisos e monta: métricas (lidas, publicadas, erros/avisos, duração), arquivos e destinos (saídas com botão **Abrir**, tabelas do PostgreSQL, original guardado), as colunas de cada tabela com tipo e o bloco de ocorrências.

### Página "Testar planilha" — renderTestar, testarArquivo, enviarArquivos (linhas 482–528)
- Linhas 482–512: enquanto analisa, mostra "Analisando…". Com resultado: veredito "Seria aprovada/reprovada", linhas lidas → tratadas, erros/avisos e regra; botões **Testar outra** e **Enviar para processamento** (ou "Enviar mesmo assim"); ocorrências; prévia das 25 primeiras linhas, com abas se houver várias tabelas. Sem resultado, mostra a área para arrastar/escolher.
- Linhas 514–520 (`testarArquivo`): guarda o arquivo, marca "carregando", vai para a página (mudando o hash), envia para `/api/testar` e redesenha.
- Linhas 522–528 (`enviarArquivos`): envia cada arquivo para `/api/enviar`, um aviso por arquivo, e atualiza o estado.

### Página "Banco de dados" — carregarBanco, CAMADAS, renderBanco (linhas 531–584)
- Linhas 531–535: só busca o resumo se o banco estiver ligado; erro vira `{ok:false, mensagem}`.
- Linhas 537–541: as três camadas do **ELT** (Extrair, Carregar e só depois Transformar dentro do banco): bruto, tratado, analítico, cada uma com cor.
- Linhas 543–584: explicação das camadas; banco desligado → convite para configurar; carregando → aviso; sem conexão → explica que os arquivos ficam "Adiado" sem perda. Com dados: as tabelas de cada camada (com número de linhas ou "visão"), a tabela das últimas cargas (`robo.lotes`, clicáveis) e a dica de como conectar o Power BI (servidor, porta e banco). Botões: pasta de modelos SQL, **Executar modelos agora**, **Atualizar**.

### Página "Equipe e contratações" (linhas 587–790)
- Linha 587: texto de cada posição de trabalho (depois da Limpeza, depois da Auditoria, antes da Modelagem).
- Linhas 589–594 (`carregarAgentes`): busca ao mesmo tempo (`Promise.all`) `/api/agentes` e `/api/escritorio` (esta última dá o organograma completo).
- Linhas 596–598: nomes dos 5 andares e a ordem dos níveis (Gerente → Estagiário).
- Linhas 600–616 (`renderOrganograma`): agrupa as pessoas por andar e por nível; cada andar é um bloco recolhível (o 1º aberto); cada pessoa é um botão (`ver-pessoa`) com avatar, cargo, a quem responde e o placar das provas técnicas.
- Linhas 618–639 (`abrirPessoa`): busca o manual `.md` da pessoa e abre a gaveta larga com nível, área, gestor, provas, descrição, responsabilidades, critérios, metodologias, limites e um campo para escrever o manual (botão **Salvar manual**).
- Linha 641 (`avatar`): círculo colorido com a inicial do nome.
- Linhas 643–670 (`renderAgentes`): botões (pasta de habilidades em Python, ver no escritório 3D, **Contratar**); avisa se alguma habilidade personalizada não carregou; explica a ordem de trabalho; mostra o organograma e, abaixo, a **linha de produção** na ordem real: cada cartão tem número de ordem, avatar, descrição e etiquetas (nativo ou posição, quantidade de habilidades, arquivos que trata, nível, andar, fim da experiência, "contratado pela liderança", "em treinamento", "configuração inválida").
- Linhas 672–752 (`editorAgente`): monta o editor na gaveta.
  - Linhas 675–689 (`campoParam`): cria o campo certo para cada parâmetro de habilidade: chave liga/desliga (booleano), lista de opções (escolha), caixa de texto com `chave=valor` por linha (mapa), número ou texto (as listas aparecem separadas por vírgula).
  - Linhas 690–704: lista as habilidades do agente na ordem de execução, com chave liga/desliga, setas para subir/descer, lixeira, os parâmetros e um bloco "Conhecimento: quando usar e cuidados". Habilidade que não existe no catálogo aparece em vermelho.
  - Linhas 706–712: o catálogo filtrado pela busca, agrupado por categoria.
  - Linhas 714–731: para agentes personalizados, o formulário: nome, função, descrição, quando trabalha, ordem, arquivos que trata, cor, nível (com o risco máximo), andar, cargo, área, mentor (só sêniores, especialistas e coordenadores), manual e a chave "Agente ligado". Para nativos, só a descrição.
  - Linhas 733–751: cabeçalho, problemas de configuração, habilidades (ou aviso de que o agente é de infraestrutura e não usa habilidades), catálogo e botões **Excluir agente**, **Cancelar** e **Salvar agente**.
- Linhas 754–783 (`coletarEditor`): lê de volta tudo o que está nos campos para o objeto `E.editando`: dados do agente e, para cada habilidade, se está ligada e cada parâmetro convertido para o tipo certo (lista separada por vírgula, mapa `chave=valor`, número). Campo vazio remove o parâmetro.
- Linhas 785–789 (`abrirEditor`): faz uma **cópia profunda** do agente (`JSON.parse(JSON.stringify(...))`), para que editar e cancelar não altere o original, e abre a gaveta larga.
- Linha 790 (`redesenharEditor`): redesenha o editor mantendo a posição da rolagem.

### Página "Consultas SQL" (linhas 793–855)
- Linhas 793–798: busca a lista e abre a primeira consulta automaticamente.
- Linhas 800–804: busca uma consulta pelo id e limpa o resultado anterior.
- Linhas 806–817: lista filtrada pela busca (título, pergunta, categoria), agrupada por categoria, com a atual destacada.
- Linhas 819–855: à esquerda a lista; à direita a pergunta de negócio, "como ler", o que precisa existir no banco, o SQL e os botões **Executar** (desligado sem banco), **Copiar SQL** e **Editar arquivo**; abaixo, o resultado (tabela, aviso de corte em 1.000 linhas, duração) ou a mensagem de erro, e a dica de colar o SQL no Power BI.

### Página "Atividade" (linhas 858–885)
- Linhas 858–866: filtro Tudo / Avisos e erros e a caixa do log.
- Linhas 867–872 (`linhasLog`): filtra e monta cada linha com hora, nível traduzido e mensagem.
- Linha 873 (`rolarLog`): rola para o fim se a rolagem automática estiver ligada.
- Linhas 874–885 (`atualizarLog`): a cada 2 s busca só as mensagens novas, guarda no máximo 1.000; na página Atividade, desliga a rolagem automática se você subiu para ler algo antigo (mais de 40 px do fim) e redesenha só a caixa do log.

### Página "Configurações" (linhas 888–1002)
- Linhas 888–890: busca `/api/config`.
- Linhas 892–893 (`chave`): botão em forma de interruptor (`role="switch"`, `aria-checked`).
- Linhas 895–982 (`renderConfig`), por seção:
  - Geral (905–914): ligar ao abrir, notificações (salvam na hora, ação `cfg-chave`), iniciar com o Windows (ação `inicializacao`) e **Criar atalhos** (desligados fora do Windows).
  - Pastas (916–923): cada pasta com botão **Abrir** e o campo para trocar a pasta de entrada.
  - Saída em arquivo (925–936): formato (xlsx, csv, ambos, nenhum), espera de sincronização (2–300 s), "Guardar versões" e **Salvar**.
  - Banco PostgreSQL (938–957): interruptor geral, servidor, porta, banco, usuário, senha (o campo fica vazio; o texto de exemplo diz se já há senha salva), modo de carga, "Guardar camada bruta", **Testar conexão** e **Salvar**.
  - Regras e modelos (959–969): as regras do config e os modelos SQL (ativos/desativados), com botões para editar.
  - Manutenção (971–976): dias de retenção e **Executar manutenção agora**.
  - Aplicativo (978–981): versão e **Encerrar aplicativo**.
- Linhas 984–985: `valor(id)` lê o valor de um campo; `marcado(id)` diz se um interruptor está ligado.
- Linhas 987–994 (`salvarConfig`): envia `{alteracoes}` para `/api/config/salvar`, avisa o resultado, recarrega configuração e estado e redesenha.
- Linhas 996–1002 (`dadosBanco`): junta os campos do banco; a senha só vai se você digitou uma.

### Página "Canal da equipe" (linhas 1006–1052)
- Linhas 1006–1010 (`carregarCanal`): monta os filtros (canal, autor, tipo, dias, busca, limite 300) com `URLSearchParams` (que codifica o texto para a URL) e busca `/api/canal`.
- Linhas 1012–1015: nomes dos tipos de mensagem e as sugestões de perguntas prontas.
- Linhas 1017–1041 (`renderCanal`): título com a sprint; à esquerda os canais; à direita filtros (pessoa, tipo, período, busca), as mensagens (as suas alinhadas de outro jeito, com etiqueta do tipo e do canal de origem quando você está no #geral), as sugestões e a caixa de texto com **Enviar** (Enter envia, Shift+Enter quebra linha).
- Linhas 1043–1052 (`enviarCanal`): usa o rascunho (sugestão clicada) ou o texto digitado, envia para `/api/canal/enviar`, recarrega, rola para o fim e devolve o foco à caixa.

### Página "Central de dados" (linhas 1055–1124)
- Linhas 1055–1057: busca `/api/central?dias=`.
- Linhas 1059–1071 (`barrasDias`): desenha em SVG um gráfico de barras empilhadas por dia (verde aprovadas, vermelho reprovadas, com o dia embaixo e dica ao passar o mouse).
- Linhas 1073–1124 (`renderCentral`): período (Hoje/7/30 dias); seis KPIs (recebidas, aprovadas, reprovadas, taxa, linhas publicadas, tempo médio); gráfico dos últimos 14 dias; "Por que barramos" (barras horizontais por motivo e por quem barrou); um cartão por andar (1º engenharia, 2º análise, 3º Excel, 4º governança/dados pessoais, 5º TI); tabela de planilhas erradas (clicáveis, com motivo e exemplos); manchetes das análises e alertas; acertos recentes; conferências por pessoa.

### Página "Estratégia" (linhas 1127–1244)
- Linhas 1127–1132: busca `/api/estrategia` e, na aba Boas práticas, o texto.
- Linhas 1134–1146 (`markdown`): um conversor de **Markdown** (texto com marcações simples como `# título`, `- item`, `**negrito**`) bem pequeno: primeiro escapa o texto com `esc` (seguro) e só depois troca `**...**` por negrito e `` `...` `` por código; `-` vira lista, `#` vira título, `##` subtítulo, o resto parágrafo.
- Linhas 1148–1149: as cinco abas.
- Linhas 1151–1161 (`renderEstrategia`): botões **Atualizar com os dados** e **Nova prioridade**, título com a sprint e a fórmula "Prioridade = impacto × urgência ÷ esforço", abas e o corpo da aba ativa.
- Linhas 1163–1186 (`estPrioridades`): filtro por andar e um **kanban** (quadro de colunas por situação). Cada cartão mostra prioridade (vermelha ≥ 8, laranja ≥ 4), andar, origem ("dos dados" ou "seu"), título, motivo, responsável e I/U/E, uma lista para mudar a situação, editar e (só nos seus) excluir.
- Linhas 1188–1193 (`estAlinhamento`): por andar, o gerente, itens travados e as prioridades abertas.
- Linhas 1195–1208 (`estAvaliacoes`): botão para aplicar a avaliação técnica, último placar, histórico e a tabela por pessoa (aprovado/reprovado e motivos).
- Linhas 1210–1224 (`estTreinamentos`): botão para rodar o treinamento, último placar e tempo, histórico, a tabela de casos difíceis (problema, quem domina, resultado) e a trilha de cada pessoa.
- Linhas 1226–1244 (`editorItem`): o formulário de uma prioridade (título — só leitura se veio dos dados —, motivo, andar, responsável, impacto, urgência, esforço de 1 a 5, situação) e o histórico do item.

### Página "TI e segurança" (linhas 1247–1265)
- Linhas 1247–1249: busca `/api/ti`.
- Linhas 1251–1265 (`renderTI`): sem ronda, convida a rodar; com ronda: data, intervalo, faixa verde ("Sistema saudável") ou de alerta e a tabela "quem verifica o quê" com OK ou os achados.

### dataBr (linha 1267)
Linha 1267: `"2026-10-17"` → `"17/10/2026"`.

### ACOES — cada botão do painel (linhas 1269–1444)
Os botões não têm código próprio: cada um tem `data-acao="nome"`, e este dicionário diz o que fazer.
- `ir` (1270): muda o hash para a página do botão.
- `ligar` / `pausar` (1271–1272): chamam a rota, atualizam o estado e redesenham.
- `processar-agora` (1273–1277): chama a rota e avisa "Processando a fila agora…" ou "Nenhum arquivo na fila"; atualiza 0,6 s depois.
- `abrir` (1278): envia alvo, caminho e nome para `/api/abrir`.
- `ver-execucao` (1279) e `fechar-gaveta` (1280).
- `reprocessar` (1281–1285): devolve o arquivo à fila e recarrega.
- `descartar` (1286–1291): pede confirmação antes; depois chama a rota.
- `filtro` (1292) e `log-filtro` (1293): trocam o filtro e redesenham.
- `escolher-arquivo` (1294): abre a janela de escolher arquivo no modo testar ou enviar.
- `enviar-testado` (1295): envia o arquivo que acabou de ser testado e volta à Visão geral.
- `aba-teste` (1296): troca a aba da prévia.
- `salvar-entrada` (1297–1304): exige o caminho, envia para `/api/config/entrada`, avisa e volta à Visão geral.
- `cfg-chave` (1305–1309): inverte o interruptor e salva a preferência na hora.
- `alternar-local` (1310): só inverte o interruptor na tela (salva depois, com o botão Salvar).
- `inicializacao` (1311–1315): liga/desliga o início com o Windows e mostra o estado real devolvido.
- `criar-atalhos` (1316).
- `salvar-saida` (1317–1320): formato, versionar e espera (mínimo 2 s).
- `salvar-banco` (1321) e `testar-banco` (1322–1327, mostra o resultado ao lado do botão).
- `executar-modelos` (1328–1332).
- `novo-agente` (1333–1335): abre o editor com um agente em branco (estagiário, 1º andar, posição "limpeza", cor laranja).
- `ver-pessoa` (1336) e `salvar-manual` (1337–1340).
- `canal-ir` (1341), `canal-enviar` (1342), `canal-sprint` (1343–1347), `canal-sugestao` (1348).
- `central-dias` (1349).
- `est-aba`, `est-novo`, `est-editar`, `est-salvar`, `est-excluir` (com confirmação), `est-sincronizar`, `est-avaliar`, `est-treinar` (1350–1379).
- `ti-ronda` (1380).
- `editar-agente` (1381), `abrir-catalogo` (1382), `adicionar-habilidade` (1383–1388), `remover-habilidade` (1389), `mover-habilidade` (1390–1394, troca de lugar com a vizinha). Todos chamam `coletarEditor` antes, para não perder o que você digitou.
- `salvar-agente` (1395–1407): se é novo, cria o id a partir do nome (tira acentos com `normalize("NFD")`, minúsculas, troca símbolos por `_`, não começa com número, até 40 letras); envia os campos e recarrega a equipe.
- `excluir-agente` (1408–1414): confirmação e exclusão.
- `abrir-consulta`, `executar-consulta`, `copiar-consulta` (usa a área de transferência do navegador; se não puder, explica como copiar), `atualizar-banco`, `recarregar-config`, `manutencao` (soma os removidos) (1415–1437).
- `sair` (1438–1443): confirmação; chama `/api/sair` e troca a página por "Robô encerrado".

### Escutadores de eventos (linhas 1446–1481)
Um **escutador** (event listener) é uma função que o navegador chama quando algo acontece (clique, tecla, digitação).
- Linhas 1446–1451: um único escutador de cliques para a página toda: acha o elemento com `data-acao` mais próximo (`closest`), ignora botões desligados e executa a ação. Isso funciona mesmo para botões criados depois.
- Linha 1452: clicar no fundo escuro fecha a gaveta. Linha 1453: Esc fecha a gaveta.
- Linhas 1454–1468 (digitação): busca de habilidade (redesenha só o catálogo), busca de consulta, busca do histórico, rascunho do canal e busca do canal (espera 300 ms sem digitar antes de buscar — evita um pedido por letra).
- Linhas 1469–1478 (mudança em listas): situação de uma prioridade (salva na hora), filtro de andar da estratégia e filtros do canal.
- Linhas 1479–1481: Enter (sem Shift) na caixa do canal envia.

### atualizarMensagens (linhas 1484–1493)
Linhas 1484–1493: redesenha o canal num elemento invisível e copia só a lista de mensagens se mudou, mantendo a rolagem no fim se você já estava no fim. Assim a caixa de texto não perde o que você está escrevendo.

### Arquivos: escolher e arrastar (linhas 1496–1520)
- Linhas 1496–1501 (`escolherArquivo`): cria um `<input type="file">` invisível, aceitando só planilhas; no modo enviar, aceita vários; ao escolher, testa o primeiro ou envia todos.
- Linhas 1503–1506: `contadorArraste` conta entradas e saídas do arrasto (o navegador dispara "entrou/saiu" a cada elemento interno); só arrastos com arquivos mostram a camada `#soltar`.
- Linhas 1507–1511: enquanto arrasta, destaca a zona sob o mouse.
- Linhas 1512–1520: ao soltar, esconde a camada; se caiu na zona "testar", testa o primeiro; na zona "enviar", envia todos; fora das zonas, ignora.

### Início (linhas 1523–1538)
- Linha 1523: troca cada `<i data-icone>` do HTML pelo ícone SVG.
- Linha 1524: quando o hash muda (clique no menu, voltar do navegador), vai para a página.
- Linhas 1525–1538: busca o estado, carrega a configuração (se não há erro), abre a página do hash (ou Visão geral) e liga os relógios: estado a cada 2 s, canal a cada 4 s (só na página Canal), central a cada 3 s (só na Central, sem redesenhar enquanto você mexe num campo) e log a cada 2 s.

**Erros que este arquivo evita**:
- Execução de código vindo de dados (nomes de arquivos, mensagens) — tudo passa por `esc`.
- Ações disparadas sem o cabeçalho do painel (a função `api` sempre o envia nos POST).
- Perder o que você digitou por causa da atualização automática (`desenharSemPerderFoco`, `atualizarMensagens`).
- Clicar duas vezes e disparar a ação duas vezes (`comCarregando` desliga o botão).
- Excluir/descartar/encerrar sem querer (`confirmar`).
- Editar um agente e o cancelamento estragar o original (cópia profunda).
- Pedidos em excesso ao servidor (atualização só quando algo mudou; espera de 300 ms na busca).

---
## robo/painel/estaticos/escritorio.html

- **Para que serve**: é o esqueleto da página do escritório 3D: a área onde a cena é desenhada e as "camadas de interface" por cima dela (topo com botões, lista da equipe, ficha do agente, rodapé com a narração e a ajuda de teclas).
- **Onde entra no fluxo**: abre pelo item "Escritório 3D" do menu (`inicio.html`, linha 24) e carrega o `escritorio.js`.

### Cabeçalho (linhas 1–11)
Linhas 1–7: igual ao painel (idioma, acentos, título "Escritório dos Robôs", ícone). Linhas 8–9: usa o visual do painel **mais** o `escritorio.css`. Linha 10: um **mapa de importação** (`importmap`): diz ao navegador que, quando o código pedir `"three"`, ele deve carregar o arquivo local `./terceiros/three.module.min.js`. **Three.js** é uma biblioteca de JavaScript para desenhar 3D no navegador; ela vem dentro do projeto, por isso o 3D funciona sem internet.

### Corpo (linhas 12–53)
- Linha 13: `#cena`, onde o desenho 3D é colocado.
- Linhas 15–32: o topo: botão **Painel** (volta ao `inicio.html`), título com o status (`#hud-status`), os botões de andar (`#andares`: 1º, 2º, 3º · Excel, Prédio — o JavaScript redesenha esses botões conforme os andares que existem) e as ações **Seguir documento** (`aria-pressed` diz se está ligado), **Enviar planilha** e **Processar agora**.
- Linha 34: `#hud-equipe`, a lista lateral da equipe.
- Linha 36: `#hud-ficha`, a ficha do agente (escondida até clicar em alguém).
- Linhas 38–41: rodapé: `#hud-agora` (a frase do que está acontecendo) e a dica de controles (W A S D, Q/E, Shift, 1 a 5, P, arrastar, rolar, clicar).
- Linhas 43–49: `#sem-3d`, aviso mostrado se o computador não conseguir desenhar 3D (WebGL indisponível), com botão de voltar.
- Linha 50: área de avisos.
- Linha 52: carrega `escritorio.js` como **módulo** (`type="module"`), o tipo de script que pode usar `import`.

**Erros que este arquivo evita**: 3D dependente de internet (importmap local); tela preta sem explicação quando o WebGL falha (`#sem-3d`).

---

## robo/painel/estaticos/escritorio.js

- **Para que serve**: monta um prédio 3D em que **cada agente é uma etapa real do robô**. Quando uma planilha chega, um "documento" aparece na recepção, passa de mesa em mesa (leitura, limpeza, auditoria...), sobe de elevador para os andares de análise e Excel e termina na caixa verde (Bases-Tratadas), na vermelha (Bases-Erros) ou na estante de relatórios. Supervisores andam pelos corredores, TVs mostram os números do dia e um clique em qualquer pessoa abre a ficha dela.
- **Onde entra no fluxo**: carregado por `escritorio.html`; lê `/api/escritorio` a cada 1 s e `/api/estado` a cada 4 s; os eventos vêm de `ControleRobo._registrar_etapa` (controle.py, linhas 163–166), que o pipeline chama a cada etapa.

Vocabulário do 3D (Three.js):
- **WebGL**: a tecnologia do navegador que usa a placa de vídeo para desenhar 3D.
- **Cena** (`Scene`): o "palco" onde tudo é colocado. **Câmera**: o ponto de vista. **Renderizador** (`WebGLRenderer`): quem desenha a cena vista pela câmera na tela.
- **Malha** (`Mesh`): um objeto visível = **geometria** (forma: caixa, cilindro, esfera...) + **material** (cor, brilho). **Grupo** (`Group`): uma caixa invisível que agrupa objetos para mover tudo junto.
- **Sprite**: uma imagem plana que sempre fica de frente para a câmera (usada nas etiquetas com nomes).
- **Canvas**: uma "folha" de desenho 2D do navegador; aqui é usada para escrever textos que viram **textura** (imagem aplicada sobre uma superfície 3D).
- **Vetor** (`Vector3`): um ponto ou direção com x (largura), y (altura) e z (profundidade).

### Cabeçalho e imports (linhas 1–8)
Linhas 1–6: comentário (cada agente é uma etapa real; a cena é montada a partir da equipe configurada). O comentário fala em `./vendor`, mas a pasta real é `./terceiros`. Linha 7: importa o Three.js inteiro como `THREE`. Linha 8: importa `OrbitControls`, que deixa você girar, aproximar e arrastar a câmera com o mouse.

### Utilitários (linhas 10–13)
Linha 10: `$` (achar elemento). Linha 11: `esc` (proteção contra código em textos, igual ao painel). Linha 12: `num` (número brasileiro). Linha 13: `ESCURO` é verdadeiro se o Windows estiver no tema escuro.

### api (linhas 15–24)
Linhas 15–24: versão enxuta da função do painel: POST quando há corpo ou arquivo, sempre com `X-Robo-Painel: 1`; arquivo vai com `X-Nome-Arquivo`; erro HTTP vira exceção com a mensagem do servidor.

### avisar (linhas 25–29)
Linhas 25–29: balão de aviso que some em 4,5 s (usa `textContent`, que nunca interpreta HTML).

### Renderizador (linhas 32–45)
- Linhas 32–38: tenta criar o renderizador com suavização de bordas; se o WebGL não existir, mostra o aviso `#sem-3d` e interrompe o script.
- Linhas 39–40: resolução (no máximo 2× em telas de alta densidade, para não pesar) e tamanho da janela.
- Linhas 41–44: liga sombras suaves e um ajuste de cores com aparência de cinema (`ACESFilmic`), mais escuro no tema escuro.
- Linha 45: coloca o desenho na página.

### Cena, câmera, controles e luzes (linhas 47–64)
- Linhas 47–49: cena com fundo claro ou escuro e **neblina** a partir de 45 m (dá profundidade).
- Linha 50: câmera em perspectiva com abertura de 38°.
- Linhas 51–55: controles de órbita com "amortecimento" (movimento suave), sem deixar a câmera ir para baixo do piso (`maxPolarAngle`) e com distância entre 6 e 55.
- Linha 57: luz ambiente de "céu e chão" (`HemisphereLight`).
- Linhas 58–64: o "sol" (`DirectionalLight`) que projeta sombras; as linhas 61–63 definem o tamanho e a área do mapa de sombras e um pequeno ajuste para evitar manchas.

### mat (linhas 67–72)
Linhas 67–72: cria materiais e guarda cada combinação cor+extras num dicionário; pedir a mesma cor de novo reaproveita o material (economiza memória da placa de vídeo).

### caixa e cilindro (linhas 73–82)
Linhas 73–77: cria uma caixa de largura × altura × profundidade numa posição, que projeta e recebe sombra. Linhas 78–82: o mesmo para cilindros (raio de cima, raio de baixo, altura, número de lados).

### texturaTexto e retanguloArredondado (linhas 83–94)
Linhas 83–90: cria um canvas, deixa uma função desenhar nele e transforma o resultado em textura com cores corretas. Linhas 91–94: desenha um retângulo de cantos arredondados no canvas.

### rotulo (linhas 95–110)
Linhas 95–110: a etiqueta flutuante de cada agente: cartão branco (ou escuro) com sombra, faixa da cor do agente, nome em negrito e subtítulo (papel e nível). Vira um sprite de 2,3 × 0,72.

### selo (linhas 111–122)
Linhas 111–122: círculo colorido com símbolo (✓ verde, ! vermelho, ✎ azul) que aparece sobre a cabeça; começa invisível e é marcado como `selo` (para não ser escondido junto com as etiquetas).

### placa (linhas 123–132)
Linhas 123–132: placa retangular colorida com texto branco centralizado (nomes de andares, caixas, elevador).

### Personagem — PELES, CABELOS, hashTexto, criarPersonagem (linhas 135–184)
- Linhas 135–136: paletas de tons de pele e cabelo.
- Linha 137: `hashTexto` transforma o id do agente num número fixo; assim cada pessoa sempre tem a mesma aparência.
- Linhas 139–144: cria o grupo e escolhe pele, cabelo e calça.
- Linhas 145–156: pernas: em pé, cada perna fica num "quadril" que pode balançar ao andar; sentado, coxas, canelas e sapatos em posição de cadeira.
- Linhas 157–159: tronco (cápsula da cor do agente) mais alto quando em pé.
- Linhas 160–169: cabeça com rosto, cabelo (meia esfera), dois olhos e um sorriso (meio anel virado).
- Linhas 170–178: braços presos em "ombros" giráveis, com mãos; sentado, os braços ficam para a frente (digitando).
- Linhas 179–182: quem anda em pé carrega uma prancheta na mão.
- Linha 183: devolve as partes que serão animadas.

### Mobiliário — criarMesa, criarCadeira, criarPlanta (linhas 187–222)
- Linhas 187–203: mesa (tampo e 4 pernas), notebook com a tampa virada para o agente e um logo redondo da cor do agente (ele "acende" quando a pessoa trabalha), caneca e pilha de papéis.
- Linhas 204–211: cadeira (assento, encosto, coluna e base).
- Linhas 212–222: vaso com 7 "folhas" (esferas) em duas tonalidades de verde.

### Constantes e estado da cena (linhas 226–253)
- Linha 226: `ALTURA = 4.4` m entre andares.
- Linhas 227–232: nomes longos e curtos de cada andar, texto e cor da placa, cores do degradê das TVs.
- Linhas 233–236: `yAndar` (altura do piso de um andar), `andarDe` (andar de um agente, padrão 1) e `nivelVista` ("prédio" conta como 99, para mostrar todos).
- Linhas 237–242: `estado`, tudo o que a cena sabe: equipe, estações (cada agente na cena), último evento recebido, documentos em movimento, fila de eventos a animar, o evento que está "tocando", agente selecionado, andar visível, se a câmera segue o documento e a hora do último movimento manual.
- Linhas 243–250: o grupo raiz, os andares, a geometria do prédio (`geo`), o elevador, as caixas e pilhas de papel, LEDs do servidor, prateleiras, TVs e a lista de objetos clicáveis.
- Linhas 251–253: as etapas "nativas" que têm uma estação com o mesmo nome.

### montarPredio (linhas 255–279)
- Linhas 256–260: apaga o prédio anterior e zera tudo (é chamado de novo quando a equipe muda).
- Linha 261: os andares existentes são 1, 2 e 3 sempre, mais qualquer andar que algum agente use (um agente no 7º andar cria o 7º andar).
- Linhas 262–268: separa a equipe por andar e calcula a largura do prédio a partir do andar com mais pessoas sentadas (duas fileiras, no mínimo 3 por fileira, 3,9 m entre mesas). `geo` guarda as medidas: colunas, limites, fileira do fundo e da frente, parede, profundidade e a posição do elevador.
- Linhas 269–273: para cada andar, cria um grupo na altura certa e o constrói.
- Linhas 274–278: corrige o andar visível se ele deixou de existir, redesenha os botões de andar, constrói o elevador, calcula as posições de câmera e mostra o andar.

### corredores (linha 282)
Linha 282: as linhas por onde os supervisores andam: um corredor atrás da fileira do fundo, um na frente da fileira da frente e as duas laterais.

### criarAndarilho (linhas 284–307)
Para quem faz **ronda** (supervisores e coordenadores):
- Linhas 285–291: cria o personagem em pé, define a ronda (um retângulo pelos corredores; metade anda no sentido contrário) e o ponto de partida.
- Linhas 292–298: etiqueta mais alta, um anel brilhante (aparece quando está trabalhando), os três selos (o ✎ aparece se estiver de prontidão) e marca cada peça como clicável com o id do agente.
- Linhas 300–306: registra a estação como `movel: true`, com ronda, caminho, uma "mesa falsa" (para o resto do código não quebrar) e `mesaPos` calculada na hora a partir de onde a pessoa está.

### caminhoAte (linhas 310–321)
Linhas 310–321: calcula o trajeto pelos corredores até ficar de frente para um ponto: se o destino está no outro corredor, passa pela lateral mais próxima. Devolve a lista de pontos.

### construirAndar (linhas 323–472)
- Linhas 328–341: **piso**. No 1º andar, piso de madeira com frisos. Nos demais, carpete em duas peças deixando o **vão do elevador**, faixas no chão, guarda-corpo baixo e uma "borda da laje" na fachada que esconde o andar de baixo.
- Linhas 342–343: tapetes dos corredores.
- Linhas 346–356: paredes (cor diferente no 1º e no 3º andar), rodapé e duas janelas com caixilho.
- Linhas 357–359: placa do andar no alto da parede.
- Linhas 362–368: **a TV do andar**: um canvas de 1024×512 vira textura de uma tela (material que não sofre efeito de luz, para ficar legível) numa moldura; `desenharTV` preenche.
- Linhas 371–390: **1º andar**: mesa da recepção com a placa "Bases-Limpeza" (onde os documentos nascem), os caixotes verde "Bases-Tratadas" e vermelho "Bases-Erros" e um sofá.
- Linhas 391–425: **demais andares**: estante de entregas colorida (placa "Entregas Excel", "Atas das sprints", "Servidor local" ou "Bases-Relatorios"), o ponto onde os documentos são guardados, a mesa redonda de reunião com 5 cadeiras e uma lousa: no 3º andar uma planilha com a fórmula `=CONT.SES(...)` e "OK" em verde; nos outros, um gráfico "Evolução do NPS".
- Linhas 426–428: três plantas.
- Linhas 431–433: separa quem faz ronda (vira andarilho) de quem fica sentado.
- Linhas 436–471: **estações sentadas**: a fileira do fundo é preenchida da esquerda para a direita e a da frente da direita para a esquerda (assim o documento percorre um "U"). Para cada agente: grupo, mesa, cadeira, personagem sentado, etiqueta com papel e nível, anel e selos. O agente `banco` ganha um rack de servidor com 18 LEDs verdes. A cada três mesas há uma planta. Tudo é marcado como clicável; quem está de prontidão já começa com o ✎. A estação guarda `mesaPos`, o ponto da mesa onde o documento pousa.

### construirElevador e pontoElevador (linhas 474–495)
Linhas 474–494: poço de vidro translúcido da altura do prédio com quatro colunas, cabine (piso, teto, fundo e uma luz) e uma placa "Elevador · Nº" em cada andar. Linha 495: o ponto dentro do elevador num andar.

### enquadrarCameras (linhas 498–513)
Linhas 498–513: calcula, para cada andar, uma posição de câmera e um alvo que enquadram o andar inteiro, levando em conta a proporção da tela e a lista lateral (desloca o centro quando a tela tem 900 px ou mais). Calcula também a vista "prédio" (de mais longe e mais alto). Na primeira vez, já posiciona a câmera.

### desenharBotoesAndares (linhas 515–520)
Linhas 515–520: recria os botões de andar a partir dos andares existentes, mais "Prédio", e marca o ativo.

### definirAndarVisivel (linhas 522–533)
Linhas 522–533: mostra só os andares até o escolhido (os de cima ficam invisíveis, como um corte do prédio); num andar de cima, esconde as etiquetas dos andares de baixo (para não aparecerem "flutuando" através da laje), mas não os selos.

### irParaAndar (linhas 535–545)
Linhas 535–545: se foi você que pediu, anota a hora (a câmera não vai "brigar" com você). Se está subindo, mostra o andar antes do voo; se está descendo, só esconde o de cima quando o voo termina. Cria um **voo** de câmera de 1,1 s, marca o botão, fecha a ficha e redesenha a equipe.

### Teclado (linhas 547–560)
Linhas 547–560: ignora teclas enquanto você digita num campo. Números levam ao andar; P ou 0 ao prédio; F liga/desliga "seguir"; Esc reenquadra o andar; W A S D, Q E, setas e Shift ficam guardados num conjunto enquanto estão apertados (as setas não rolam a página). Soltar a tecla ou sair da janela limpa o conjunto.

### caminhar (linhas 562–588)
Linhas 562–588: a cada quadro, calcula a direção "para a frente" da câmera no plano do chão e a "direita"; soma o movimento das teclas, com velocidade 7 m/s (2,4× com Shift), sem sair dos limites do andar, e move câmera e alvo juntos. Q e E giram a câmera em volta do alvo. Qualquer movimento cancela o voo automático. Linha 589: começar a arrastar com o mouse também.

### alternarSeguir (linhas 591–595)
Linhas 591–595: liga/desliga "a câmera acompanha o documento entre os andares", atualiza o botão e avisa.

### desenharTV (linhas 598–664)
- Linhas 599–608: fundo em degradê da cor do andar, título ("HOJE NA ENGENHARIA", "HOJE NA ANÁLISE", "HOJE NA SALA EXCEL", "HOJE NA DIRETORIA", "SAÚDE DO SISTEMA") e, à direita, "● Monitorando" (verde) ou "● Pausado" (laranja).
- Linhas 609–627: os blocos de números: 1º andar — aprovados, reprovados, na fila, linhas (dos KPIs de `/api/estado`); 5º — status, alertas e pessoas de TI; 4º — mensagens hoje, dias restantes da sprint, pessoas; 3º — entregas, conferências e "Divergências" (sempre 0 no código); 2º — bases, diferenças reais, alertas.
- Linhas 628–633: desenha cada bloco (números maiores no 1º andar).
- Linhas 634–662: o texto de baixo: 2º — último resumo executivo; 5º — horário da última ronda e alertas (ou "Disco, dependências, logs e segurança verificados."); 4º — dias para fechar a sprint e a última mensagem do canal; 3º — última entrega e duas frases sobre a conferência das fórmulas; 1º — "Atualizado HH:MM:SS".
- Linha 663: avisa o Three.js que a textura mudou.

### Documentos — novoDocumento, moverDocumento, empilhar, atualizarPilhaEntrada (linhas 667–699)
- Linhas 667–675: o documento é uma folha branca com uma faixa colorida, nascendo na mesa da recepção; é guardado pelo nome do arquivo.
- Linhas 677–688: monta a rota do documento como uma lista de trechos: no mesmo andar, um "salto" até o destino; em outro andar, salta até o elevador, sobe/desce na vertical (1,5 s) e salta até o destino. Devolve a duração total.
- Linhas 689–693: põe uma folha numa pilha (com leve bagunça aleatória), no máximo 14 folhas.
- Linhas 694–699: a pilha da recepção mostra quantos arquivos estão na fila (até 8), descontando o que está sendo animado.

### DURACAO, FRASE e DURACAO_EXTRA (linhas 702–723)
Linhas 702–723: quanto tempo cada etapa fica na tela e a frase que o rodapé narra para cada agente (por exemplo, `limpeza: "está limpando"`, `excel_trade: "está montando o SOMASES de trade..."`). Supervisores e coordenadores ganham tempo extra.

### idAgente (linhas 725–729)
Linhas 725–729: traduz o nome da etapa no id da estação: `agente:tina` → `tina`; `analise:perfil` → `analise_perfil`; uma etapa nativa ou que já tenha estação → ela mesma; senão, nenhuma.

### definirSituacao (linhas 731–739)
Linhas 731–739: muda a situação de um agente (parado, trabalhando, ok, erro), opcionalmente por alguns segundos; liga o anel ao trabalhar, mostra ✓ ou !, mostra ✎ quando parado em prontidão, acende o logo do notebook e atualiza a lista lateral.

### seguirPara (linhas 741–744)
Linhas 741–744: se "seguir" estiver ligado, você não mexeu na câmera nos últimos 8 s e não está vendo o prédio inteiro, a câmera vai para o andar onde a ação está.

### iniciarEvento — como um evento real vira animação (linhas 746–807)
- Linhas 747–751: se há muitos eventos acumulados, acelera (60% ou 35% do tempo); conferências rápidas do quadro (`eng_`, `ana_`, `xl_`, `gov_`, `ger_`) duram menos. Encurta nomes longos e pega o documento desse arquivo (se já existir).
- Linhas 754–780: **fim do processamento** (`concluido` ou `adiado`):
  - adiado: faixa laranja, volta para a recepção, narra "⏳ adiado".
  - sucesso num andar de cima (2º ou mais): faixa verde, vai para a estante do andar, uma folha entra em Bases-Tratadas, o relator (ou o supervisor do Excel no 3º) fica com ✓, narra "✅ aprovado ... análise e entrega Excel em Bases-Relatorios".
  - sucesso no 1º andar: vai para a caixa verde, a publicação fica com ✓.
  - reprovado: faixa vermelha, vai para a caixa vermelha; quem barrou (o supervisor, se o motivo citar "Supervisor", senão a auditoria) fica com ! por 3 s; narra "⛔ reprovado — N erro(s)".
  - Em todos: a câmera segue e o evento fica "tocando" até a animação terminar.
- Linhas 782–784: descobre a estação do agente da etapa; se não houver, o evento passa em 50 ms.
- Linhas 786–796: **agente que anda** (supervisor/coordenador): se o documento estava em trânsito, coloca-o no destino final; calcula o caminho até ele, desliga quem estava trabalhando, marca este como trabalhando, narra e define o tempo (caminhada até 3,5 s + conferência).
- Linhas 798–806: **agente sentado**: a faixa do documento ganha a cor do agente; o documento vai até a mesa dele (pegando o elevador se for outro andar); a câmera segue; só um agente trabalha por vez; narra (com "⬆ Subiu para o Nº andar" quando trocou de andar).

### finalizarEvento (linhas 809–819)
Linhas 809–819: encerra o evento: quem trabalhava volta a "parado"; se era o fim do documento, ele some e vira uma folha na pilha certa (tratadas, erros ou a estante do andar).

### narrar (linha 821)
Linha 821: escreve a frase no rodapé.

### Lista lateral — NOME_SITUACAO, linhaMembro, desenharEquipe (linhas 824–865)
- Linhas 824–825: textos e classes de cada situação ("de plantão", "trabalhando", "concluiu", "barrou", "de prontidão").
- Linhas 827–832: a situação e o detalhe de cada pessoa: a prontidão, o número do dia (ex.: "1.234 linhas lidas hoje"), o número de habilidades ou o papel.
- Linhas 834–855: só **remonta** a lista quando a equipe muda (compara um "resumo" em texto): agrupa por andar, do mais alto para o mais baixo, com o nome do andar clicável e um botão por pessoa; no fim, um link para a tela de equipe do painel.
- Linhas 857–864: a cada atualização, troca só textos e classes (o botão não "pula" enquanto você clica).

### mostrarFicha (linhas 867–895)
Linhas 867–895: monta a ficha: avatar, nome, cargo, nível, área, provas técnicas, andar, gestor, descrição, aviso de prontidão ("Ninguém aqui dorme..."), número do dia, metodologias, responsabilidades, critérios, limites, habilidades e link para a ficha completa. Se a pessoa está noutro andar, mostra esse andar e voa a câmera até ela.

### voo e focarAgente (linhas 897–904)
Linha 897: `voo` guarda a animação de câmera em andamento. Linhas 898–904: calcula a posição da pessoa e cria um voo de 0,9 s até um ponto um pouco acima e à frente dela.

### Botões do HUD (linhas 906–924)
- Linhas 906–909: clique na lista lateral: no nome do andar, vai até ele; numa pessoa, abre a ficha.
- Linha 910: o ✕ da ficha reenquadra o andar.
- Linha 911: botões de andar.
- Linha 912: "Seguir documento".
- Linhas 913–915: "Processar agora" chama a rota (o `{}` como corpo faz o pedido ser POST).
- Linhas 916–924: "Enviar planilha": escolhe vários arquivos e envia um a um para `/api/enviar` ("entregue na recepção").

### Clique na cena (linhas 927–945)
Linhas 927–930: um **raycaster** "lança um raio" a partir do ponto do mouse para dentro da cena e descobre em que objeto ele bate; só conta objetos visíveis (com todos os "pais" visíveis). Linhas 931–937: ao mover o mouse, anota se houve arrasto (mais de 5 px) e troca o cursor para "mãozinha" sobre um agente. Linhas 938–945: ao soltar sem ter arrastado, se o raio acertou um agente, abre a ficha.

### Redimensionar (linha 946)
Linha 946: ao mudar o tamanho da janela, ajusta a proporção da câmera, o tamanho do desenho e os enquadramentos.

### atualizar — dados do robô (linhas 949–976)
- Linhas 951–953: busca `/api/escritorio?desde=` e guarda ligado, fila, números por agente, banco, análise, Excel, canal e TI.
- Linhas 954–959: monta uma "chave" com o que importa da equipe (id, nome, papel, cor, prontidão, andar, ronda, habilidades, nível); se mudou (contratação, troca de andar...), apaga os documentos e **remonta o prédio**.
- Linhas 960–964: coloca os eventos novos na fila de animação; ao abrir a página, ignora eventos com mais de 20 s (não repete o passado).
- Linhas 965–968: guarda o último número de evento e atualiza o status do topo (configuração pendente, monitorando com X na fila, pausado).
- Linhas 969–971: sem nada acontecendo, narra a fila ou "Aguardando planilhas em Bases-Limpeza…".
- Linha 972: atualiza a pilha da recepção, a lista da equipe e as TVs do 2º ao 5º andar.
- Linhas 973–975: sem conexão, mostra "Sem conexão com o robô".

### atualizarTV (linhas 977–979)
Linhas 977–979: busca os KPIs de `/api/estado` e redesenha a TV do 1º andar.

### andarAgente (linhas 982–1017)
Linhas 982–1017: move os andarilhos: trabalhando, seguem o caminho até o documento a 2,6 m/s; senão, continuam a ronda a 0,9 m/s. Viram suavemente na direção do movimento; ao chegar, viram para a mesa, baixam a cabeça e conferem a prancheta; andando, balançam pernas e um braço e o corpo sobe e desce levemente. Os selos flutuam. A etiqueta fica transparente quando a câmera está muito perto (exceto a do selecionado).

### animar — o laço de animação (linhas 1020–1093)
`requestAnimationFrame` pede ao navegador para chamar a função de novo no próximo quadro de tela (cerca de 60 vezes por segundo).
- Linhas 1024–1025: tempo total e tempo desde o último quadro (no máximo 0,05 s, para não "pular" depois de a aba ficar escondida).
- Linhas 1027–1028: sem evento tocando, começa o próximo da fila; evento que terminou, finaliza. **É assim que os eventos reais viram animação: um de cada vez, na ordem em que o robô os publicou.**
- Linhas 1030–1065: para cada estação: volta a "parado" quando o tempo da situação acaba; move os andarilhos; pula andares invisíveis; e anima os sentados conforme a situação: trabalhando (digita rápido, cabeça balança, anel gira), erro (levanta um braço), ok (levanta os dois braços e "pula"), prontidão (digita devagar olhando a tela, ✎ flutua), parado (olha em volta e "respira"). Ajusta a transparência das etiquetas pela distância.
- Linhas 1066–1070: os LEDs do servidor piscam rápido e aleatórios quando o banco trabalha, devagar quando está parado e ficam quase apagados se o PostgreSQL estiver desligado.
- Linhas 1072–1082: move cada documento pelo trecho atual da rota com movimento suave (curva `s = k²(3−2k)`, que acelera e freia); nos saltos, sobe num arco e gira um pouco; no trecho vertical, a cabine do elevador acompanha. Trecho concluído sai da rota.
- Linhas 1084–1091: aplica o caminhar pelo teclado e o voo de câmera (com a função `aoTerminar` quando houver) e atualiza os controles.
- Linha 1092: desenha o quadro.

### Início (linhas 1095–1099)
Linhas 1095–1099: busca os dados e os KPIs pela primeira vez, começa a animação e liga os relógios: `/api/escritorio` a cada 1 s e `/api/estado` a cada 4 s.

**Erros que este arquivo evita**:
- Animação que não corresponde à realidade: só eventos reais do pipeline são animados, na ordem, e o passado não é repetido ao abrir.
- Fila de animação atrasando para sempre quando chegam muitos arquivos (aceleração automática).
- Câmera "roubando" o controle de você (8 s de respeito após mexer manualmente; botão "Seguir").
- Lista lateral pulando enquanto você clica (remonta só quando a equipe muda).
- Página travada em computadores sem 3D (aviso `#sem-3d`).
- Gasto excessivo de memória de vídeo (materiais reaproveitados, resolução limitada a 2×, pilhas de no máximo 14 folhas).

---

## robo/painel/estaticos/painel.css e escritorio.css (visão geral)

**CSS** é a linguagem que define a aparência (cores, tamanhos, posições) dos elementos do HTML.

### painel.css — organização
- **Tokens de tema (linhas 5–58)**: no `:root` ficam as **variáveis de cor** (`--nome: valor`), usadas no resto do arquivo como `var(--nome)`:
  - Fundo e superfícies: `--fundo`, `--superficie`, `--superficie-2`; bordas: `--borda`, `--borda-forte`.
  - Texto em três intensidades: `--texto`, `--texto-2`, `--texto-3`.
  - Cor principal (azul): `--primaria`, `--primaria-hover`, `--primaria-suave`.
  - Cores de significado, cada uma com versão "suave" para fundos: `--sucesso` (verde), `--perigo` (vermelho), `--alerta` (laranja), `--info` (azul).
  - Sombras (`--sombra`, `--sombra-media`), raios de canto (`--raio` 12 px, `--raio-p` 8 px) e fontes (`--fonte` Segoe UI, `--mono` Cascadia Mono/Consolas).
  - **Tema escuro automático**: o bloco `@media (prefers-color-scheme: dark)` (linhas 33–58) redefine as mesmas variáveis quando o Windows está no modo escuro. Como o resto do arquivo só usa as variáveis, tudo muda de cor sozinho.
- **Base (linhas 60–74)**: caixas medem com borda incluída, fonte padrão, atributo `hidden` sempre esconde, e o estilo dos ícones SVG (traço da cor do texto).
- **Seções**, cada uma marcada por um comentário `/* ---- nome */`: layout (barra lateral, menu, status com a bolinha que pulsa — e não pulsa se você pediu "menos movimento" ao sistema), cartões, botões, etiquetas, listas, fluxo das pastas, tabela, formulários, dropzone (área de soltar), veredito/ocorrências, camadas do banco, log, gaveta/modal/avisos, primeira configuração, consultas SQL, agentes e habilidades, organograma, canal, central de dados e estratégia.
- **Telas menores**: vários `@media (max-width: ...)` reorganizam as grades em menos colunas (por exemplo, os KPIs passam de 4 para 2 colunas abaixo de 1100 px; o formulário vira uma coluna abaixo de 700 px).

### escritorio.css — organização
- Linhas 2–5: página sem rolagem, fundo claro (ou escuro no tema escuro), a cena ocupando a tela toda.
- Linhas 7–20: o topo flutuante; ele próprio não captura cliques (`pointer-events: none`), só seus botões, para você conseguir girar a cena pelos espaços vazios. Os cartões usam fundo semitransparente com desfoque (`backdrop-filter`) e as variáveis do `painel.css`.
- Linhas 22–38: a lista da equipe (largura 290 px, rolagem própria) e as etiquetas de situação, coloridas com as variáveis `--info`, `--sucesso`, `--perigo`.
- Linhas 40–50: a ficha do agente. Linhas 52–60: rodapé e dica. Linhas 61–63: o aviso "sem 3D".
- Linhas 64–68 e 79: telas estreitas escondem a lista lateral e encurtam botões.
- Linhas 70–78: botão de andar e de "seguir" ativos, link dos andares, nível na lista e listas da ficha.

**Erros que estes arquivos evitam**: cores inconsistentes entre telas (tudo vem das mesmas variáveis); texto ilegível no modo escuro (tema automático); painel quebrado em janelas pequenas (regras `@media`); animação incômoda para quem pediu menos movimento.

---
## instalar.bat

- **Para que serve**: instala o robô no Windows com dois cliques: acha (ou instala) um Python compatível, cria um ambiente isolado, instala as bibliotecas, cria o `config.yaml`, confere as pastas, cria os atalhos e pergunta se o robô deve ligar com o Windows. Deve ser rodado uma vez, ou de novo depois de atualizar o projeto.
- **Onde entra no fluxo**: é o primeiro passo de tudo. Sem ele, o `Abrir Robo de Planilhas.vbs` avisa que o robô "ainda não foi instalado". Um arquivo **.bat** é uma lista de comandos que o Prompt de Comando do Windows executa em ordem.

### Preparação (linhas 1–11)
- Linha 1: `@echo off` esconde os próprios comandos, mostrando só as mensagens.
- Linha 2: `EnableDelayedExpansion` permite ler variáveis com `!nome!` dentro de blocos `( )` com o valor atualizado (usado em `!errorlevel!`).
- Linhas 3–5: comentários (`REM`).
- Linha 6: `cd /d "%~dp0"` entra na pasta onde o `.bat` está (`%~dp0`), mesmo que seja outro disco.
- Linha 7: título da janela.
- Linhas 9–11: explica que só as versões 3.11 a 3.14 do Python servem (versões mais novas ainda não têm pandas/PyYAML prontos para Windows e exigiriam compilar). `VERIFICA` é um pequeno programa Python que termina com 0 (ok) ou 1 (versão fora da faixa).

### Passo 1/5 — achar o Python (linhas 13–40)
- Linhas 14–19: tenta, nessa ordem, `py -3.13`, `py -3.12`, `py -3.14`, `py -3.11` (o `py` é o lançador oficial do Python no Windows). O primeiro que passar no `VERIFICA` fica em `PY`. `>nul 2>nul` esconde as mensagens; `&&` só executa o `set` se o comando anterior deu certo.
- Linhas 20–22: se nenhum servir, tenta o comando `python`.
- Linhas 23–31: se ainda nada e o `py` existe (`where py`), instala o Python 3.13 ao lado do atual (sem remover o seu) com `py install 3.13` e testa de novo.
- Linhas 32–39: sem Python compatível, explica onde baixar (marcar "Add python.exe to PATH"), pausa e sai com erro.
- Linha 40: mostra qual versão será usada.

### Passo 2/5 — ambiente virtual (linhas 42–55)
Um **ambiente virtual** (`.venv`) é uma pasta com um Python e bibliotecas só deste projeto, sem misturar com outros programas do computador.
- Linhas 43–49: se já existe um `.venv` mas com versão incompatível, apaga e recria.
- Linha 50: cria o `.venv` se não existir.
- Linhas 51–55: se não conseguiu, mostra erro e sai.

### Passo 3/5 — bibliotecas (linhas 57–65)
- Linha 58: atualiza o **pip** (o instalador de bibliotecas do Python).
- Linhas 59–60: instala tudo o que está em `requisitos.txt` usando **apenas pacotes prontos** (`--only-binary=:all:`), nunca tentando compilar.
- Linhas 61–65: falhou → pede para copiar a mensagem e sai.

### Passo 4/5 — config (linhas 67–68)
Linha 68: se não existe `config.yaml`, copia o `config.exemplo.yaml` (nunca sobrescreve o seu).

### Passo 5/5 — pastas (linhas 70–71)
Linha 71: roda `python -m robo status`, que mostra se as pastas do OneDrive foram encontradas.

### Atalhos e inicialização (linhas 73–83)
- Linha 75: `python -m robo atalhos` cria os atalhos na Área de Trabalho e no Menu Iniciar.
- Linhas 78–83: `choice /c SN` pergunta Sim/Não; `errorlevel 2` significa "N" → desliga a inicialização automática; "S" → liga.

### Conclusão (linhas 85–94)
Linhas 85–90: mensagem final. Linhas 91–94: pergunta se quer abrir agora; "S" abre o lançador `.vbs` com o `wscript.exe` (o executor de VBScript do Windows); `:fim` é o rótulo para onde o `goto` pula.

**Erros que este arquivo evita**: instalar com um Python novo demais que tentaria compilar e falharia; misturar bibliotecas com outros programas (`.venv`); `.venv` antigo com versão errada; apagar o seu `config.yaml`; ter que criar atalhos à mão.

---

## ferramentas/diagnosticar.bat

- **Para que serve**: você arrasta uma planilha para cima deste arquivo e ele mostra o que o robô faria com ela, sem gravar nem mover nada.
- **Onde entra no fluxo**: ferramenta de suporte, independente do painel (equivale à página "Testar planilha").

### Linhas 1–10
Linha 1: esconde os comandos. Linha 2: comentário. Linha 3: `cd /d "%~dp0.."` entra na pasta **acima** de `ferramentas` (a raiz do projeto). Linhas 4–8: `%~1` é o primeiro arquivo arrastado; se vazio, explica como usar e sai. Linha 9: roda `python -m robo diagnosticar "<arquivo>"` com o Python do `.venv`. Linha 10: pausa para você ler.

**Erros que este arquivo evita**: rodar sem arquivo; alterar a planilha ao só querer conferir.

---

## ferramentas/parar_robo.bat

- **Para que serve**: desliga o robô que está rodando em segundo plano (com ou sem painel).
- **Onde entra no fluxo**: alternativa ao botão "Encerrar aplicativo" do painel.

### Linhas 1–4
Linha 2: comentário. Linha 3: um único comando PowerShell que: (1) tenta o jeito educado, um POST em `http://127.0.0.1:8765/api/sair` com o cabeçalho `X-Robo-Painel: 1`, esperando 3 s; (2) se falhar (`catch`), procura processos `python.exe`/`pythonw.exe` cuja linha de comando contenha `-m robo` e os encerra à força, mostrando o número de cada processo (PID). Linha 4: pausa.

**Erros que este arquivo evita**: ficar com um robô "fantasma" rodando sem janela; usa primeiro o encerramento limpo (que pausa o robô e solta a trava).

---

## ferramentas/processar_agora.bat

- **Para que serve**: processa uma única vez tudo o que estiver em Bases-Limpeza e termina.
- **Onde entra no fluxo**: uso manual, **com o robô fechado** (o comentário avisa).

### Linhas 1–5
Linha 2: comentário/aviso. Linha 3: vai para a raiz do projeto. Linha 4: `python -m robo varrer`. Linha 5: pausa.

**Erros que este arquivo evita**: precisar abrir o painel só para processar um lote.

---

## ferramentas/robo_sem_painel.bat

- **Para que serve**: liga o robô sem o painel, mostrando o log ao vivo na própria janela (útil para diagnóstico). Fechar a janela desliga.
- **Onde entra no fluxo**: modo alternativo ao aplicativo; usa a mesma trava de instância, então não roda junto com o painel.

### Linhas 1–7
Linhas 2–3: comentários. Linha 4: raiz do projeto. Linha 5: título da janela. Linha 6: `python -m robo monitorar`. Linha 7: pausa ao terminar.

**Erros que este arquivo evita**: investigar problemas "às cegas" (você vê cada mensagem).

---

## ferramentas/status.bat

- **Para que serve**: mostra pastas, arquivos na fila, reprovados e últimos processamentos no Prompt de Comando.
- **Onde entra no fluxo**: consulta rápida sem abrir o painel.

### Linhas 1–5
Linha 2: comentário. Linha 3: raiz do projeto. Linha 4: `python -m robo status`. Linha 5: pausa.

**Erros que este arquivo evita**: precisar do painel para uma conferência simples.

---

## Abrir Robo de Planilhas.vbs

- **Para que serve**: é o lançador que o atalho "Robô de Planilhas" executa. Liga o robô e mostra o painel numa janela; se já estiver aberto, só mostra a janela de novo; com `/oculto` (usado na inicialização do Windows), liga sem abrir janela. **VBScript** (`.vbs`) é uma linguagem antiga de automação do Windows; aqui ela é usada porque consegue iniciar o Python sem a janela preta do Prompt.
- **Onde entra no fluxo**: atalho → este arquivo → `pythonw.exe -m robo app` → `iniciar_app` (servidor.py).

### Comentários (linhas 1–6)
Linhas 1–6: descrevem os dois modos (normal e `/oculto`). Em VBScript, comentários começam com `'`.

### Pasta do projeto (linhas 7–10)
Linha 7: cria o objeto que lida com arquivos e pastas. Linha 8: descobre a pasta onde o `.vbs` está. Linhas 9–10: cria o objeto `WScript.Shell` (que roda programas) e define essa pasta como pasta atual.

### Instalação conferida (linhas 12–17)
Linha 12: monta o caminho do `pythonw.exe` do `.venv` (o `pythonw` é a versão do Python que roda sem janela). Linhas 13–17: se ele não existe, mostra uma caixa de aviso pedindo para rodar o `instalar.bat` e sai.

### Argumentos (linhas 19–22)
Linha 19: o comando básico é `-m robo app`. Linhas 20–22: se o primeiro argumento for `/oculto` (sem diferenciar maiúsculas), acrescenta `--sem-janela`.

### Execução (linha 24)
Linha 24: roda o Python com o caminho entre aspas (as quatro aspas `""""` geram uma aspa literal, por causa de espaços no caminho), com a janela escondida (`0`) e sem esperar terminar (`False`).

**Erros que este arquivo evita**: janela preta aberta o dia inteiro; mensagem confusa quando o robô não foi instalado; falhas com espaços no caminho da pasta.

---

## pytest.ini

- **Para que serve**: configura o **pytest**, a ferramenta que roda os testes automáticos. Um teste automático é um pequeno programa que usa o robô de verdade e confere se o resultado é o esperado.
- **Onde entra no fluxo**: lido quando você roda `pytest` na raiz do projeto.

### Linhas 1–5
Linha 1: comentário (o nome do arquivo é exigido pelo pytest). Linha 2: início da seção `[pytest]`. Linha 3: os testes ficam na pasta `testes`. Linha 4: arquivos de teste começam com `teste_` (em português, em vez do padrão `test_`). Linha 5: funções de teste também começam com `teste_`.

**Erros que este arquivo evita**: o pytest não encontrar nenhum teste por causa dos nomes em português.

---

## testes/conftest.py

- **Para que serve**: guarda os "ingredientes" compartilhados pelos testes: pastas temporárias que imitam o OneDrive, uma fábrica de configurações, uma planilha bagunçada de exemplo e a regra de validação NPS. O pytest lê este arquivo automaticamente.
- **Onde entra no fluxo**: usado por quase todos os `teste_*.py`. Uma **fixture** é uma função marcada com `@pytest.fixture` que prepara algo para o teste; o teste a recebe só por colocar o nome dela como parâmetro.

### Imports (linhas 1–8)
Linhas 1–8: datas, caminhos, pandas, pytest, `Workbook` (criar arquivos Excel com openpyxl) e `carregar_config`.

### pastas (linhas 11–16)
Linhas 11–16: dentro de uma pasta temporária (`tmp_path`, apagada pelo pytest depois), cria `OneDrive/Bases-Limpeza` e `OneDrive/Bases-Tratadas` e devolve a pasta `OneDrive`. Nenhum teste toca suas pastas reais.

### cfg_factory (linhas 19–26)
Linhas 19–26: devolve uma função que cria uma configuração apontando para as pastas temporárias (entrada, logs, agentes, habilidades), com as regras e extras que o teste pedir. Usa um config que "não existe" para partir só dos padrões.

### planilha_baguncada (linhas 29–46)
Linhas 29–46: cria `nps_outubro.xlsx` como uma planilha "da vida real": título na primeira linha, linha vazia, cabeçalho com espaços, data como data e como texto, nota como número e como texto, curso com espaços, UF em minúsculas, valores em reais em texto (`R$ 1.234,56`), traço como vazio, uma linha duplicada e uma linha de "Total" no fim.

### REGRA_NPS (linhas 49–58)
Linhas 49–58: a regra usada em vários testes: vale para `nps_*`, exige colunas, não aceita vazios em id e nota, id único, tipos (data e inteiro), nota de 0 a 10, UF em maiúsculas e só SP/RJ/MG.

### _limpar_habilidades_personalizadas (linhas 61–67)
Linhas 61–67: fixture automática (`autouse=True`, vale para todo teste): depois de cada teste (`yield` marca o "depois"), remove do catálogo as habilidades personalizadas que o teste criou, para que um teste não contamine o próximo.

**Erros que este arquivo evita**: testes mexendo nas suas pastas reais; testes que passam ou falham dependendo da ordem; repetição de código de preparação.

---

## testes/ — o que cada arquivo garante

Testes marcados com **PG** só rodam se a variável `ROBO_TESTE_PG` apontar para um PostgreSQL real; os marcados com **LibreOffice** só rodam se o `soffice` estiver instalado (ele recalcula as fórmulas como o Excel faria). `monkeypatch` é uma ferramenta do pytest para trocar temporariamente uma função por outra (por exemplo, simular um defeito) durante um teste.

| Arquivo | O que ele garante |
|---|---|
| `teste_analise.py` | O 2º andar reconhece o papel de cada coluna (id, data, categoria, texto livre) e detecta o NPS; NPS e margem de erro batem com a fórmula; a estatística acha a diferença real (Medicina pior) e **não inventa** diferenças (UF, bases sem efeito); bases pequenas são sinalizadas; correção de Holm; o monitoramento compara com cargas anteriores (volume, coluna sumida, categoria inédita como "Medicna"); ondas do mesmo estudo são agrupadas pelo nome; o pipeline gera `nps_analise.xlsx` e as etapas `analise:*` em ordem; um analista com defeito não impede a publicação; a análise pode ser desligada. |
| `teste_backup.py` | Sem banco, o backup não finge que fez nada; **PG**: backup real com `pg_dump` ou, sem ele, em CSV, guardando só os últimos N. |
| `teste_banco.py` | **PG**: o ELT completo (bruto com exatamente o que chegou, tratado tipado e limpo, analítico criado pelos modelos SQL, controle em `robo.lotes`, calendário de 365 dias, análise gravada no schema `analise`); reprocessar não duplica; dimensões mantêm as chaves entre arquivos; modo "mesclar" atualiza por chave; conflito de tipo reprova sem publicar (mas o bruto guarda para auditoria); tipo que "alarga" e coluna nova são aceitos; modelo SQL com erro reprova; banco fora do ar **adia** sem mexer no arquivo. |
| `teste_calculos.py` | A calculadora do canal entende pedidos em português ("nps por curso", "contagem por curso onde nota_nps > 5"), aproxima nomes de colunas, avisa quando a coluna não existe, não soma texto, é usada pelo canal e responde com honestidade quando não há base publicada. |
| `teste_canal.py` | Pergunta de Excel vai para o especialista; o status usa dados reais; frase sem sentido vira "não entendi" (não inventa); cálculo amostral exato (385 para 5%; ±4,9 com 400); conversas ficam registradas e filtráveis; acontecimentos não são postados duas vezes; sprint com a fala de cada pessoa; sprint de 15 dias fechada e publicada sozinha; o canal responde pelo manual `.md` do agente. |
| `teste_consultas.py` | A biblioteca de consultas tem pelo menos 25 itens com título, pergunta, "como ler" e requisitos; **PG**: **todas** as consultas executam e retornam linhas com dados de exemplo; números de NPS, duplicidades e outliers conferem; a execução é **somente leitura** (um `CREATE TABLE` é recusado); não é possível ler arquivo fora da pasta (`../config.yaml`). |
| `teste_contratacao.py` | Contrata estagiário automaticamente só com demanda comprovada (e-mails fora do padrão), com manual e anúncio no canal #rh, sem alterar o dado publicado; não contrata sem trabalho nem duas vezes para a mesma necessidade; experiência de 90 dias com avaliação ("efetivar" ou "desligar"); contratação manual num andar novo; não confunde datas ou números com contatos; não contrata quando quase tudo seria inválido. |
| `teste_estrategia.py` | A Central de dados conta recebidos, aprovados, reprovados e quem barrou; prioridades automáticas nascem das reprovações e se fecham sozinhas quando o problema some; prioridade do dono = impacto × urgência ÷ esforço e aparece no alinhamento do andar; a avaliação técnica cobre todo o quadro (≥ 50 pessoas, todas aprovadas); as trilhas de treinamento são dominadas. |
| `teste_excel.py` | Critérios das fórmulas escapam curingas (`*`, `?`) e aspas; **LibreOffice**: depois de recalculadas, **todas** as fórmulas da entrega Excel batem com a aba Conferência (cenários de pesquisa e de trade, e escala escrita convertida em CSAT); o pipeline gera `nps_excel.xlsx` e a etapa `excel_supervisor`. |
| `teste_habilidades.py` | O catálogo tem ≥ 24 habilidades documentadas; cada habilidade principal funciona (título em português, de-para sem acento e caixa, CPF/CNPJ com dígito e zero perdido, e-mail, telefone, CEP, grupos NPS/CSAT, temas de comentários, faixas, outliers, coluna calculada, filtro, duplicidade, anonimização); parâmetros errados viram erro claro; agente personalizado trabalha na posição certa e respeita "arquivos que trata"; agente inválido **reprova** em vez de publicar errado; nomes inválidos e exclusão de nativos são recusados; habilidade personalizada em Python é carregada e usada. |
| `teste_leitura.py` | A leitura acha o cabeçalho abaixo do título (e guarda o número da linha do Excel); lê CSV com ponto e vírgula em codificação antiga (cp1252) e CSV com vírgula. |
| `teste_limpeza.py` | Nomes de colunas viram `minusculas_sem_acento`; números brasileiros, moeda, negativos entre parênteses e porcentagens são convertidos (e textos ambíguos não); tipos são inferidos sem perder zeros à esquerda (matrícula, CEP); inteiros viram `Int64`; erros do Excel (`#REF!`, `#N/D`) reprovam; "N/A" e "-" viram vazio e espaços são limpos; tipo forçado inválido gera erro com a linha; coluna quase numérica esvazia os inválidos com aviso. |
| `teste_painel.py` | Sobe o servidor numa porta livre e: todas as rotas de leitura respondem 200; a equipe do escritório começa por recepção/leitura/limpeza, a Sala Excel fica no 3º andar e ninguém aparece desligado; `escritorio.js` sai como `text/javascript`; **segurança**: POST sem `X-Robo-Painel` → 403, `Origin` de outro site → 403, abrir `C:/Windows/system32/calc.exe` → 404; testar planilha com `#REF!` → reprovada; `virus.exe` → 415; enviar coloca em Bases-Limpeza; salvar agente válido/ inválido; excluir nativo → 400; respostas têm `X-Frame-Options: DENY` e CSP; corpo de 3 MB é recusado (413 ou conexão encerrada); canal responde pela API. |
| `teste_pipeline.py` | Fluxo completo de sucesso (saída limpa com 4 linhas, sem duplicada nem Total, original guardado, relatório de qualidade e histórico); reprovado vai para Bases-Erros com relatório citando faixa, chave repetida, erro de fórmula e linha; modelo estrela com dimensão e calendário; diagnóstico não mexe em nada; PDF é reprovado; o monitor espera a sincronização (10 s) e ignora temporários (`~$`, `desktop.ini`); saída em CSV brasileiro; **a ordem exata de todas as etapas** emitidas (a mesma que o escritório 3D anima); texto começando com `=` não vira fórmula ativa (segurança). |
| `teste_producao.py` | Arquivo aprovado tem o checklist de produção assinado; o supervisor barra linhas que somem sem explicação; **PG**: o DBA desfaz uma carga que não bate; o coordenador de análise (Marcos) revisa e assina. |
| `teste_quadro.py` | Todo andar tem do gerente ao estagiário (e sênior/especialista); todo cargo passou nas provas do RH com escopo definido; um júnior que acha problema **bloqueia** a publicação; o estagiário só observa (aviso, sem reprovar); releitura divergente desfaz a publicação; conferência que quebra não vira aprovação; o catálogo de dados é atualizado. |
| `teste_rh.py` | Toda habilidade nativa tem prova técnica e passa; toda a equipe nativa, supervisores, Sala Excel e analistas foram aprovados no "processo seletivo"; o risco depende dos parâmetros e o nível limita o risco (júnior só baixo, pleno até médio); promoção libera; estagiário trabalha em observação sem alterar dados; habilidade personalizada reprovada na prova não é contratada. |
| `teste_ti.py` | A ronda de TI passa num ambiente saudável e cobre toda a equipe de TI; um alerta crítico (disco) vai para o canal #ti **uma vez só**; código novo de habilidade é vigiado pela segurança. |
| `teste_treinamento.py` | Cada caso difícil do centro de treinamento passa — se algum falhar, o robô "ficou engessado" para aquele tipo de planilha. |

**Erros que a pasta de testes evita**: uma mudança no código quebrar, sem ninguém perceber, a limpeza, a validação, a segurança do painel, a ordem das etapas, as fórmulas do Excel ou as regras de RH. Rodar `pytest` antes de usar uma versão nova dá a confiança de que o comportamento combinado continua igual.
