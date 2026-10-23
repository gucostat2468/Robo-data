# Diagnóstico e plano: reestruturação operacional (23/10/2026)

Pedido de origem: "ROBÔ DE PLANILHAS — REESTRUTURAÇÃO OPERACIONAL, MULTIAGENTES, IA LOCAL, TREINAMENTO E
ESCALABILIDADE" (24 itens). Este documento é o diagnóstico exigido no item 1 e o plano do item 22. Cada afirmação
abaixo vem de um comando executado ou de um trecho de código citado; nada foi presumido.

## 1. Como o diagnóstico foi feito

- Estado do Git: branch `claude/robo-planilhas-etl-n5ckuc`, árvore limpa, último commit `765585e` (Fase 6).
- Turno da nuvem reproduzido de verdade: o MESMO código que o GitHub Actions chama (`nuvem.turno`) rodou contra um
  PostgreSQL vazio (banco `robo_diag`), e depois cada tabela de cada schema foi contada.
- Banco local deste ambiente (`robo_dados`, instalado como no seu notebook): contado com
  `python -m robo cobertura-banco` (comando novo, abaixo).
- As credenciais do Neon NÃO estão neste ambiente (ficam só nos Secrets do GitHub). Por isso o banco da nuvem não foi
  lido diretamente; foi reproduzido com o mesmo código.

## 2. Por que só o schema `robo` tinha dados

| Schema | Estava | Causa encontrada (evidência) |
|---|---|---|
| `robo` | com dados | a rotina `memoria_pg` copia TODAS as 67 tabelas do SQLite para `robo.memoria_*` (`memoria.sincronizar_postgres`) |
| `bruto`, `tratado`, `analitico` | vazios | só recebem planilha REAL processada com o banco ligado (`pipeline._carregar_banco`). O turno da nuvem não rodava a esteira: nenhum job `planilha` em 2 min de turno |
| `analise` | vazio | só recebe a análise de planilha real (`analise._gravar_banco`) |
| `laboratorio` | vazio | o laboratório grava a tabela, confere o SQL e **apaga em seguida** (`laboratorio._sql_no_banco`, `DROP TABLE`): tabela temporária por desenho |
| `treino` | vazio | criado pelo instalador (`instalacao_banco.SCHEMAS`), mas **nenhum código gravava nele** |

Hipóteses do pedido (item 6), conferidas uma a uma:

| Hipótese | Resultado |
|---|---|
| Componentes não implementados | **Sim**, para `treino` (planejado, sem código) |
| Serviços não conectados ao banco | **Sim**: a esteira não rodava na nuvem; `aprendizados.replay` existe e nenhuma rotina o chama |
| Erros de inicialização | Não: o turno rodou sem exceção |
| Funcionários só estáticos | Não: os 94 têm tentativas de treino registradas; 28 têm etapas de job |
| Rotinas de persistência não chamadas | **Sim** (as duas acima) |
| Mapeamento modelo/tabela | Não: a cópia SQLite → PostgreSQL é fiel (as 23 tabelas vazias no PostgreSQL estão vazias no SQLite também) |
| Operações só em memória | Não encontrado |
| Transações falhando | Não encontrado |
| Interface não envia ao backend | Não se aplica à nuvem (não tem painel); no notebook, o chat grava em `conversas`/`mensagens` |
| Tarefas não executadas de verdade | **Sim, em parte**: o motor de solicitações (`solicitacoes`, `etapas`, `eventos`, `artefatos`, `aprovacoes`) só nasce de pedido do dono; nenhuma rotina distribui tarefas por ele |

As 23 tabelas vazias do SQLite e a causa de cada uma estão no relatório de cobertura (`logs/cobertura_banco.md`).

## 3. Inventário (o que existe)

- **Funcionários:** 94 em 5 andares (1º: 19, 2º: 16, 3º: 12, 4º: 26, 5º: 21), de `organizacao.lista`.
- **"Só um agente":** a pasta `agentes/` tem 1 arquivo (`tina_contatos.yaml`, agente personalizado). Os outros
  agentes são nativos, definidos em código (`robo/agentes.py`, `robo/organizacao.py`), e não aparecem na pasta.
- **Estados honestos já existentes:** `jobs`/`jobs_etapas` (trabalhando só com etapa aberta) e 5 estados em
  `atividade_equipe` (trabalhando, ativo hoje, plantão, ocioso, sem registro).
- **IA:** `robo/ia.py` com 4 provedores (nenhum, ollama local, API compatível, anthropic), desligada por padrão;
  disjuntor; texto com número fora dos fatos é descartado. Ollama não está instalado neste ambiente.
- **Tarefas atribuídas:** motor de solicitações em `robo/trabalho.py` (pedido → etapas → funcionário → ferramenta →
  aprovação → artefato), com permissões por nível em `organizacao.PERMISSOES_NIVEL`. Hoje só o dono o aciona.
- **Treino:** Sala de Casos (`head_casos`, `casos_planejamento`, 4 designers, `casos_revisor`), treino contínuo,
  laboratório e fábrica (15 regras de negócio).
- **Memória:** `aprendizados` (individual e compartilhada), `licoes`, `handovers`, `boas_praticas`, `interacoes`.
- **Equivalentes já existentes aos cargos pedidos:** `cloud_aws` (Arquiteta de Cloud AWS, 5º andar); Sala de Casos
  (planejar, gerar e revisar treino); `canal_iara` (ideias e evolução). Não existe Head de AWS nem Sênior
  Linux/Ubuntu.

## 4. Melhoria executada nesta sessão (Etapa 2: persistência e rastreabilidade)

1. **Esteira no turno da nuvem** (`robo/nuvem.py`): o monitor processa as planilhas da fábrica a cada volta, e a
   fábrica confere o gabarito no fim do turno. Lotes menores na nuvem (1.000 a 5.000 linhas).
2. **Dado sintético no PostgreSQL, separado** (`robo/pipeline.py`, `robo/analise.py`): planilha `TREINO_*` vai para
   `laboratorio` (cópia bruta) e `treino` (tratado, lotes, ocorrências, análise). Nunca para os schemas de produção.
   Uma tabela por regra de negócio (`treino_nps`), não uma por lote. Modelos SQL reais não rodam sobre dado sintético.
   Teto de 100 MB (`fabrica.pg_treino_mb_max`): chegou nele, para de carregar e avisa, **sem apagar nada**.
3. **Cobertura de persistência** (`robo/cobertura_banco.py`, `python -m robo cobertura-banco`): conta cada tabela do
   SQLite e do PostgreSQL e registra a causa de cada vazia (não acionada, desconectada, temporária, planejada ou sem
   causa conhecida). Cada levantamento fica em `cobertura_persistencia` (imutável) e roda em todo salvamento do
   turno da nuvem.

O que NÃO foi feito, de propósito: encher tabelas vazias com linhas inventadas. Isso contradiz o item 6 do próprio
pedido ("Não preencha o banco indiscriminadamente com registros falsos").

## 5. Plano por etapas (sem execução automática)

| Etapa | O que | Depende de | Estado |
|---|---|---|---|
| 1 | Diagnóstico e inventário | — | **feito** (este documento) |
| 2 | Persistência e rastreabilidade | 1 | **feito nesta sessão** (itens acima) |
| 3 | Execução real de funcionários: cada demanda vira `solicitacao` + `etapas` com responsável, ferramenta autorizada e evidência | 2 | próximo |
| 4 | 5 funcionários de demandas sintéticas (planejar, gerar básico a profissional, distribuir por andar, cobertura de quem ficou sem trabalho, avaliação independente), a partir da Sala de Casos | 3 | planejado |
| 5 | IA local: medir RAM/CPU do seu notebook antes de escolher modelo (ex.: Ollama com modelo de 3B a 8B); uma instância compartilhada com fila | 3 | planejado |
| 6 | Conversa natural com qualquer funcionário e handoffs registrados | 3, 5 | parcial (voz, diálogo com fato) |
| 7 | Funcionário de pesquisa (Markdown e PDF com fontes; Perplexity só por API oficial e com chave sua) | 5 | planejado |
| 8 | Head de AWS e Sênior Linux/Ubuntu (sem acesso real à nuvem); proposta de operação 24 h com custos | 3 | planejado; nenhum recurso pago criado |
| 9 | Dados analíticos e ML: começa por auditar volume e alvo (ex.: prever acerto no treino) | 2, 4 | planejado |

Riscos e autorizações pendentes:
- **Espaço no Neon gratuito:** com a esteira na nuvem, `laboratorio` e `treino` crescem a cada lote. Há teto de
  100 MB e o alerta de 80% já existente. Antes de subir o teto, decidir com você.
- **Nada foi publicado, nenhuma porta aberta, nenhum recurso pago criado.**
