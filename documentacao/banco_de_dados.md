# Banco de dados da empresa

> Gerado pelo código (`python -m robo banco-doc`, a partir de `robo/dicionario_dados.py`). Não edite à mão: um teste confere que este arquivo bate com o código.

## Onde fica cada coisa

| Onde | O que guarda | Para quê |
|---|---|---|
| `logs/trabalho.db` (SQLite) | **Fonte de tudo**: a memória da empresa (41 tabelas abaixo) | Funciona sem internet e sem servidor; nada se apaga |
| `logs/backups_sqlite/` | Cópia diária do `trabalho.db`, conferida (`integrity_check`) e com SHA-256 | Restaurar se o disco falhar; o 1º de cada mês fica para sempre |
| PostgreSQL `robo_dados`, schema `robo` | Espelho de TODAS as tabelas (`memoria_<tabela>`) | Consultas em SQL, Power BI e Machine Learning |
| PostgreSQL schemas `bruto` → `tratado` → `analitico` | As planilhas de negócio (ELT) | Análise e Power BI |
| PostgreSQL schemas `laboratorio` e `treino` | Tabelas sintéticas temporárias do treino | Treino de SQL (refeitas pela semente) |

## Regras que valem para todas as tabelas

1. **Nada se apaga.** Toda tabela de registro tem um gatilho que recusa `DELETE` — inclusive as que forem criadas no futuro (`trabalho.proteger`).
2. **Três tipos de tabela.** *só acrescenta (imutável: não altera nem apaga)*; *registro com situação (a situação muda; a linha nunca some)*; *estado atual (sobrescrito de propósito; a história fica em outra tabela)*.
3. **Backup diário** do SQLite (online, sem parar a operação) e do PostgreSQL; o primeiro de cada mês nunca é apagado; cada backup fica registrado em `backups_registro`.
4. **Espelho completo** no PostgreSQL a cada hora: tabela imutável nunca é sobrescrita lá (adulterar o SQLite não muda a cópia).
5. **Cadeia de integridade** (SHA-256) no conhecimento, com âncora em arquivo: adulteração é detectada.
6. **Versão do código** em cada tentativa de treino: todo resultado é rastreável até o código que o produziu.

## Tabelas

### Pessoas e memória (o que cada funcionário fez, errou e aprendeu)

| Tabela | Para que serve | 1 linha = | Regra | Uso em Machine Learning |
|---|---|---|---|---|
| `experiencias` | Memória de cada funcionário: acertos, erros, aprendizados, colaboração e treinamento | um acontecimento de uma pessoa (com origem: produção, treino, laboratório, estudo…) | só acrescenta (imutável: não altera nem apaga) | série temporal de desempenho por pessoa; rótulo acerto/erro por origem |
| `handovers` | Cada tipo de erro vira um handover para a área: causa, regra, como verificar e PDCA | um tipo de erro numa base (repetição soma recorrência) | registro com situação (a situação muda; a linha nunca some) | taxonomia de erros e tempo até a correção (aberto → verificado) |
| `handover_eventos` | Histórico de cada handover: cada ocorrência e cada mudança de estado | um evento de um handover | só acrescenta (imutável: não altera nem apaga) | sequência de estados para modelar recorrência e regressão |
| `boas_praticas` | O que o PDCA comprovou que funciona (e se depois foi invalidado) | uma prática nascida de um handover verificado | registro com situação (a situação muda; a linha nunca some) | efeito das correções ao longo do tempo |
| `memoria` | Lembretes da empresa (correções do dono, estados de provas, conferências de cálculo) | um lembrete com tipo e chave | só acrescenta (imutável: não altera nem apaga) | contexto e decisões do dono |
| `interacoes` | Conversas entre funcionários (pedido de ajuda, mentoria, cobrança) | uma interação entre duas pessoas | só acrescenta (imutável: não altera nem apaga) | rede de colaboração (quem ajuda quem) |
| `mentorias` | Mentoria nascida de um erro de treino: quem ajudou quem, com qual lição, e se ajudou | um pedido de ajuda a um mentor escolhido pelos acertos registrados | registro com situação (a situação muda; a linha nunca some) | qualidade de cada mentor (taxa de 'ajudou') e efeito da mentoria no acerto seguinte |

### Trabalho (central de solicitações, conversas e entregas)

| Tabela | Para que serve | 1 linha = | Regra | Uso em Machine Learning |
|---|---|---|---|---|
| `solicitacoes` | Central de solicitações: pedidos, planos, resultado e revisão independente | um pedido (tarefa, projeto ou conversa) | registro com situação (a situação muda; a linha nunca some) | tempo de ciclo e taxa de aprovação na revisão |
| `etapas` | As etapas do plano de cada solicitação, com quem executou e o resultado | uma etapa de uma solicitação | registro com situação (a situação muda; a linha nunca some) | sucesso por ferramenta e por pessoa |
| `aprovacoes` | Pedidos de aprovação ao dono (risco, quem pediu, decisão e motivo) | um pedido de aprovação | registro com situação (a situação muda; a linha nunca some) | padrões de risco e decisão |
| `eventos` | Linha do tempo de cada solicitação (cada mudança de estado) | um evento de uma solicitação | só acrescenta (imutável: não altera nem apaga) | sequência de estados (process mining) |
| `artefatos` | Arquivos entregues pelas solicitações (relatórios, resumos) | um arquivo entregue | registro com situação (a situação muda; a linha nunca some) | o que foi entregue para cada pedido |
| `arquivos` | Arquivos anexados às conversas e solicitações | um anexo | registro com situação (a situação muda; a linha nunca some) | entradas do trabalho |
| `conversas` | Conversas com cada funcionário (e salas de reunião) | uma conversa | registro com situação (a situação muda; a linha nunca some) | contexto das perguntas do dono |
| `mensagens` | Cada mensagem das conversas, com a natureza da resposta e a evidência | uma mensagem | só acrescenta (imutável: não altera nem apaga) | perguntas × respostas × natureza (base para avaliar respostas) |

### Conhecimento e aprendizado (lições, regras aprendidas, cadeia de integridade)

| Tabela | Para que serve | 1 linha = | Regra | Uso em Machine Learning |
|---|---|---|---|---|
| `licoes` | Caderno de lições: tudo o que a empresa aprendeu (erros, PDCA, treino, manuais, dono) | uma versão de uma lição | registro com situação (a situação muda; a linha nunca some) | base de conhecimento versionada |
| `licoes_funcionario` | Cada lição de cada pessoa: atribuída → estudada → avaliada → aplicada (com prova) | uma lição para uma pessoa | registro com situação (a situação muda; a linha nunca some) | curva de aprendizado por pessoa e por tema |
| `licoes_uso` | Quando uma lição foi usada numa resposta de verdade | um uso de uma lição | só acrescenta (imutável: não altera nem apaga) | aplicação real do conhecimento |
| `registro_conhecimento` | Cadeia com hash (SHA-256) de tudo o que acontece com o conhecimento | um elo da cadeia (com o hash do anterior) | só acrescenta (imutável: não altera nem apaga) | auditoria: prova de que nada foi adulterado |
| `propostas_regra` | Regras propostas a partir de reprovações (só o dono aprova) e a prova | uma proposta de regra | registro com situação (a situação muda; a linha nunca some) | o que reprova e o que resolve |
| `regras_aprendidas` | Regras aprovadas em vigor (sinônimo, valor, correção, apelido) e desativações | uma regra aprovada | registro com situação (a situação muda; a linha nunca some) | efeito das regras na taxa de aprovação |

### Treino contínuo e laboratório (casos com gabarito, tentativas e níveis)

| Tabela | Para que serve | 1 linha = | Regra | Uso em Machine Learning |
|---|---|---|---|---|
| `treino_casos` | Casos de treino da Sala de Casos: gerador, semente, gabarito e revisão independente | um caso (reproduzível pela semente + versão do gerador) | registro com situação (a situação muda; a linha nunca some) | dificuldade de cada caso (taxa de acerto por caso) |
| `treino_tentativas` | Cada tentativa de cada funcionário: competência, nível, acertou, tipo de erro, tempo e a versão do código | uma tentativa | só acrescenta (imutável: não altera nem apaga) | principal base para ML: desempenho × nível × competência × versão do código |
| `treino_niveis` | Nível atual de cada pessoa em cada competência | pessoa × competência | estado atual (sobrescrito de propósito; a história fica em outra tabela) | a história fica em treino_niveis_eventos |
| `treino_niveis_eventos` | Cada subida e descida de nível, com as tentativas que provaram | uma mudança de nível | só acrescenta (imutável: não altera nem apaga) | progressão (curva de evolução) |
| `treino_certificacoes` | Exames dos designers da Sala de Casos (um caso de cada nível, revisado) | um exame | só acrescenta (imutável: não altera nem apaga) | qualidade de quem gera os casos |
| `laboratorio_exercicios` | Laboratório: planilhas sintéticas de 6 áreas em 4 níveis, etapa por etapa | uma etapa de um exercício | só acrescenta (imutável: não altera nem apaga) | termômetro do código por nível de sujeira |
| `laboratorio_medidas` | Tempo do pipeline por volume (projeção de capacidade) | uma medida | só acrescenta (imutável: não altera nem apaga) | regressão de tempo × linhas |

### Reuniões e decisões (atas, eventos e cobrança)

| Tabela | Para que serve | 1 linha = | Regra | Uso em Machine Learning |
|---|---|---|---|---|
| `reunioes` | Reunião semanal da liderança: ata completa por andar | uma reunião semanal | registro com situação (a situação muda; a linha nunca some) | o que se discutiu e o plano de ação |
| `sala_eventos` | Tudo o que acontece numa sala de reunião (abrir, mão, palavra, decisão, encerrar) | um evento de uma sala | só acrescenta (imutável: não altera nem apaga) | dinâmica das reuniões |
| `salas_encerradas` | Ata (recap) de cada reunião de andar, com o hash do arquivo | uma reunião encerrada | só acrescenta (imutável: não altera nem apaga) | decisões e pendências por reunião |
| `decisoes` | Decisões de reunião: dono, prazo, critério de pronto e situação apurada pelos registros | uma decisão | registro com situação (a situação muda; a linha nunca some) | cumprimento de prazo por área e por pessoa |
| `decisoes_eventos` | Histórico de cada decisão (criada, cobrada, repactuada, cancelada, situação) | um evento de uma decisão | só acrescenta (imutável: não altera nem apaga) | quantas repactuações até cumprir |

### Operação, TI e qualidade (rotinas, ferramentas, erros, auditorias e backups)

| Tabela | Para que serve | 1 linha = | Regra | Uso em Machine Learning |
|---|---|---|---|---|
| `rotinas_estado` | Última execução de cada rotina (para saber se está atrasada) | uma rotina | estado atual (sobrescrito de propósito; a história fica em outra tabela) | a história fica em rotinas_execucoes |
| `rotinas_execucoes` | Cada execução de cada rotina (início, fim, status e detalhe) | uma execução | só acrescenta (imutável: não altera nem apaga) | confiabilidade das rotinas |
| `sessoes` | Cada vez que o robô foi aberto (e quanto tempo ficou desligado antes) | uma sessão | registro com situação (a situação muda; a linha nunca some) | disponibilidade |
| `uso_ferramentas` | Cada uso de cada ferramenta: quem, se deu certo, tempo e exceção | um uso | só acrescenta (imutável: não altera nem apaga) | confiabilidade por ferramenta |
| `erros_sistema` | Todo erro de programa (com traceback), agrupado por tipo, ligado a um handover da TI | um tipo de erro (repetição soma ocorrência) | registro com situação (a situação muda; a linha nunca some) | estabilidade do código por versão |
| `auditorias` | Auditorias por amostragem dos heads (conferido por outro caminho) | uma auditoria | só acrescenta (imutável: não altera nem apaga) | confiança nos resultados publicados |
| `backups_registro` | Cada backup (SQLite e PostgreSQL): arquivo, SHA-256, linhas e integridade | um backup | só acrescenta (imutável: não altera nem apaga) | prova de que dá para restaurar |
| `acessos_celular` | Cada tentativa de entrar pelo celular (certa, errada ou bloqueada), com IP e aparelho | uma tentativa de entrada no acompanhamento pelo celular | só acrescenta (imutável: não altera nem apaga) | padrão de uso e detecção de acesso estranho (horário, IP, erros seguidos) |

## Colunas de cada tabela

- **`acessos_celular`**: `id`, `data_hora`, `ip`, `evento`, `detalhe`, `navegador`
- **`aprovacoes`**: `id`, `solicitacao_id`, `etapa_id`, `pedido`, `risco`, `solicitante`, `aprovador`, `estado`, `decidido_por`, `decidido_em`, `motivo`, `criada_em`
- **`arquivos`**: `id`, `conversa_id`, `solicitacao_id`, `caminho`, `nome`, `criado_em`
- **`artefatos`**: `id`, `solicitacao_id`, `etapa_id`, `caminho`, `tipo`, `descricao`, `criado_em`
- **`auditorias`**: `id`, `data_hora`, `head`, `area`, `amostra`, `aprovada`, `achados`, `conferidos`
- **`backups_registro`**: `id`, `data_hora`, `tipo`, `ok`, `arquivo`, `sha256`, `tamanho_mb`, `linhas`, `integridade`, `detalhe`
- **`boas_praticas`**: `id`, `handover_id`, `andar`, `area`, `responsavel`, `problema`, `pratica`, `como_verificar`, `evidencia`, `criada_em`, `valida`, `invalidada_em`, `motivo_invalidacao`
- **`conversas`**: `id`, `funcionario`, `titulo`, `origem`, `criada_em`, `atualizada_em`, `contexto`, `arquivada`
- **`decisoes`**: `id`, `criada_em`, `origem`, `reuniao_id`, `andar`, `texto`, `dono`, `prazo`, `criterio`, `vinculo_tipo`, `vinculo_id`, `registrada_por`, `estado`, `estado_em`, `evidencia`, `repactuacoes`
- **`decisoes_eventos`**: `id`, `decisao_id`, `data_hora`, `tipo`, `de`, `para`, `quem`, `reuniao_id`, `detalhe`
- **`erros_sistema`**: `id`, `impressao`, `primeira`, `ultima`, `ocorrencias`, `modulo`, `funcao`, `tipo`, `mensagem`, `traceback_primeiro`, `traceback_ultimo`, `handover_id`, `estado`
- **`etapas`**: `id`, `solicitacao_id`, `ordem`, `titulo`, `funcionario`, `ferramenta`, `parametros`, `depende`, `risco`, `precisa_aprovacao`, `estado`, `natureza`, `resultado`, `tentativas`, `inicio`, `fim`
- **`eventos`**: `id`, `solicitacao_id`, `data_hora`, `tipo`, `quem`, `de`, `para`, `texto`, `dados`
- **`experiencias`**: `id`, `funcionario`, `data_hora`, `tipo`, `resumo`, `detalhe`, `origem`, `referencia`, `andar`
- **`handover_eventos`**: `id`, `handover_id`, `data_hora`, `tipo`, `de`, `para`, `quem`, `detalhe`
- **`handovers`**: `id`, `chave`, `andar`, `area`, `responsavel`, `detectado_por`, `erro`, `causa`, `regra`, `como_verificar`, `exemplo`, `recorrencias`, `estado`, `backlog_id`, `criado_em`, `ultima_ocorrencia`, `atualizado_em`
- **`interacoes`**: `id`, `data_hora`, `de`, `para`, `tipo`, `texto`, `ref`
- **`laboratorio_exercicios`**: `id`, `rodada`, `data_hora`, `area`, `semente`, `etapa`, `responsavel`, `ok`, `detalhe`, `segundos`, `nivel`
- **`laboratorio_medidas`**: `id`, `data_hora`, `area`, `linhas`, `segundos`
- **`licoes`**: `id`, `origem_tipo`, `origem_ref`, `versao`, `substitui`, `andar`, `publico`, `titulo`, `conteudo`, `pergunta`, `como_aplicar`, `autor`, `criada_em`, `arquivada`, `motivo_arquivo`
- **`licoes_funcionario`**: `licao_id`, `funcionario`, `estado`, `atribuida_em`, `estudada_em`, `avaliada_em`, `aplicada_em`, `evidencia`, `tentativas`
- **`licoes_uso`**: `id`, `licao_id`, `funcionario`, `data_hora`, `contexto`
- **`memoria`**: `id`, `tipo`, `chave`, `texto`, `origem`, `solicitacao_id`, `criada_em`
- **`mensagens`**: `id`, `conversa_id`, `autor`, `texto`, `natureza`, `dados`, `solicitacao_id`, `criada_em`
- **`mentorias`**: `id`, `data_hora`, `mentor`, `aprendiz`, `competencia`, `nivel`, `tentativa_erro_id`, `licao_id`, `situacao`, `fechada_em`, `tentativa_resultado_id`
- **`propostas_regra`**: `id`, `criada_em`, `arquivo`, `arquivo_erros`, `padrao`, `tipo`, `coluna`, `valor`, `motivo`, `evidencia`, `alerta`, `autor`, `estado`, `decidido_por`, `decidido_em`, `motivo_decisao`, `comprovada_em`, `prova`, `para`
- **`registro_conhecimento`**: `id`, `data_hora`, `tipo`, `ref`, `quem`, `dados`, `hash_anterior`, `hash`
- **`regras_aprendidas`**: `id`, `proposta_id`, `padrao`, `tipo`, `coluna`, `valor`, `aprovada_por`, `aprovada_em`, `ativa`, `para`, `desativada_em`, `desativada_por`, `motivo_desativacao`
- **`reunioes`**: `id`, `inicio`, `fim`, `data_hora`, `ata`, `arquivo`
- **`rotinas_estado`**: `nome`, `ultima_verificacao`, `ultima_execucao`, `ultimo_status`, `detalhe`
- **`rotinas_execucoes`**: `id`, `nome`, `inicio`, `fim`, `segundos`, `status`, `detalhe`
- **`sala_eventos`**: `id`, `conversa_id`, `data_hora`, `quem`, `tipo`, `dados`
- **`salas_encerradas`**: `id`, `andar`, `inicio`, `fim`, `recap`, `arquivo`
- **`sessoes`**: `id`, `aberto_em`, `ultimo_batimento`, `desligado_antes_horas`, `briefing`
- **`solicitacoes`**: `id`, `tipo`, `titulo`, `pedido`, `origem`, `prioridade`, `estado`, `funcionario`, `andar`, `conversa_id`, `projeto_id`, `modelo`, `plano`, `resultado`, `revisor`, `revisao`, `tentativas`, `criada_em`, `atualizada_em`
- **`treino_casos`**: `id`, `criado_em`, `competencia`, `nivel`, `semente`, `versao_gerador`, `designer`, `resumo`, `parametros`, `gabarito`, `arquivo`, `conteudo_sha256`, `estado`, `revisor`, `revisado_em`, `revisao`, `versao_codigo`, `encerrado_em`, `arquivo_guardado`
- **`treino_certificacoes`**: `id`, `data_hora`, `designer`, `competencia`, `versao_gerador`, `ok`, `detalhe`, `revisor`
- **`treino_niveis`**: `funcionario`, `competencia`, `nivel`, `desde`
- **`treino_niveis_eventos`**: `id`, `data_hora`, `funcionario`, `competencia`, `de`, `para`, `motivo`, `evidencia`
- **`treino_tentativas`**: `id`, `data_hora`, `rodada`, `caso_id`, `funcionario`, `andar`, `cargo_nivel`, `competencia`, `nivel`, `ferramenta`, `acertou`, `nota`, `tipo_erro`, `detalhe`, `resposta`, `segundos`, `versao_codigo`
- **`uso_ferramentas`**: `id`, `data_hora`, `ferramenta`, `quem`, `ok`, `natureza`, `excecao`, `segundos`

## Como usar para Machine Learning (exemplo em SQL no PostgreSQL)

```sql
-- desempenho por competência e nível, por versão do código (cada linha = uma tentativa real, imutável)
SELECT competencia, nivel, versao_codigo, COUNT(*) AS tentativas, AVG(acertou) AS taxa_acerto,
       AVG(segundos) AS tempo_medio
FROM robo.memoria_treino_tentativas
GROUP BY competencia, nivel, versao_codigo
ORDER BY competencia, nivel;
```

Tabelas-chave para modelos: `treino_tentativas` (rótulo `acertou`, atributos nível/competência/cargo/andar/tempo), `experiencias` (série por pessoa), `handover_eventos` e `decisoes_eventos` (sequências de estado), `uso_ferramentas` e `erros_sistema` (confiabilidade por versão).

## Conectar o Power BI (só leitura)

1. Power BI Desktop → **Página Inicial** → **Obter dados** → **Mais…** → **Banco de dados PostgreSQL** → **Conectar**.
2. Servidor: `localhost:5432` · Banco de dados: `robo_dados` · Modo: **Importar** → **OK**.
3. Na janela de credenciais, aba **Banco de dados**: usuário `robo_leitura` e a senha mostrada pelo `python -m robo instalar-banco`.
4. Escolha as tabelas `robo.memoria_*` (memória da empresa) ou `analitico.*` (negócio) → **Transformar Dados**.
O usuário `robo_leitura` não consegue alterar nada: o banco recusa (o instalador prova isso).
