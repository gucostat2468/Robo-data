# Diagnóstico geral do Robô de Planilhas (23/10/2026)

Pedido do dono: "faça um diagnóstico completo: o que falta, o que podemos fazer, o que depende de mim (deixo a
autonomia com você) e quanto falta em tudo". Cada número abaixo veio de um comando executado nesta data.

## 1. Onde o projeto está

| O que | Número | Como foi medido |
|---|---|---|
| Funcionários | 98 em 5 andares (7 estagiários em observação) | `organizacao.lista()` |
| Código | 85 módulos, cerca de 32 mil linhas de Python | `robo/*.py`, `robo/painel/*.py` |
| Testes automáticos | 604 passando, 60 arquivos de teste | `python -m pytest` |
| Rotinas automáticas | 22 | `rotinas.ROTINAS` |
| Páginas do painel | 27 | menu de `inicio.html` |
| Pedidos registrados | 119: 109 feitos, 8 parciais, 1 aguardando você, 1 impossível do jeito pedido | `pedidos_do_dono.md` |
| Tabelas do banco local | 48 de 72 com dados; as 24 vazias têm causa registrada | `python -m robo cobertura-banco` |
| IA | desligada (nenhum modelo instalado) | `ia.status` |
| Base de conhecimento | 4 manuais, cerca de 260 linhas | `conhecimento/*.md` |

Reestruturação (pedido de 24 itens): etapas 1 a 4 de 9 feitas (diagnóstico, persistência, execução real e equipe de
demandas). Detalhes em `documentacao/diagnostico_reestruturacao.md`.

## 2. O que falta (32 itens)

### Funcionários, IA e conversas (4)
1. IA local de verdade: diagnóstico do computador (RAM, disco, processador), recomendação do modelo que cabe nele,
   UMA instância compartilhada com fila e limite, e registro de cada chamada (quem, quando, para quê, quanto tempo).
2. Conversa com qualquer funcionário usando a memória dele, as tarefas que fez e o que errou, e dizendo "estou
   indisponível" quando estiver.
3. Pedido de ajuda entre funcionários com subtarefa, entrega e validação (hoje existe o repasse do orquestrador e
   a conversa com fato; falta o ciclo completo de ajuda).
4. APIs externas de IA como opção, com teto de custo e sem dado pessoal (desligadas por padrão).

### Memória e conhecimento (3)
5. Base de conhecimento pequena: 5 ferramentas sem nada documentado (diagnosticar planilha, perfil e indicadores,
   estratégia Python, anomalias, people analytics). Achado da Etapa 4: 28 de 92 demandas ficam parciais por isso.
6. Funcionário de pesquisa: fontes gratuitas e verificáveis (documentação oficial, PyPI, GitHub), relatórios em
   Markdown e PDF, notificações com fonte e data.
7. Governança da memória: separar confirmado, hipótese, desatualizado e não verificado; retenção e compactação sem
   apagar o original.

### Nuvem e AWS (2)
8. Head de AWS e Sênior de AWS/Linux/Ubuntu com trabalho real e sem acesso à nuvem (menor privilégio).
9. Plano de operação 24 h comparando custos (GitHub Actions, que já roda grátis; máquinas gratuitas; AWS; Google;
   Azure), com riscos, segurança e plano de volta.

### Dados e machine learning (2)
10. Catálogo das 8 categorias de dados do pedido (real, sintético, resultado de agente, aprovado, preparado para
    modelo, modelo treinado, avaliado, implantado) e tabelas de experimentos e versões de modelo.
11. Primeiro experimento pequeno e mensurável, com os dados que já existem (milhares de tentativas de treino com
    acerto ou erro), validação no tempo e sem vazamento.

### Escritório e painel (4)
12. Página "Demandas": cobertura por andar e área, níveis, avaliações do Bento e lacunas de conhecimento (hoje só
    existe o comando `python -m robo cobertura-demandas`).
13. Organograma visual (pedido antigo).
14. Escritório 3D mostrando repasses e avaliações (quem passou trabalho para quem).
15. Página da cobertura do banco (hoje só o comando).

### Extras da especificação anterior (7)
16. Contrato de dados. 17. Detecção de drift. 18. Linhagem. 19. Fila com pesos e SLA. 20. Modo dia acelerado.
21. Relatório semanal em PDF. 22. Teste de caos.

### Pedidos antigos ainda abertos (5)
23. Grupo no Telegram com os funcionários. 24. Fundos de Power BI no estilo Figma (pesquisa e arquivos).
25. Skill de engenharia reversa para o Claude. 26. Relatório final com vídeo dos andares.
27. Trilhas normal e avançada de treino (os níveis das demandas cobrem parte; falta no treino com gabarito).

### Dívida técnica (5)
28. `aprendizados.replay` existe e nenhuma rotina o chama.
29. O guia arquivo por arquivo (`documentacao/guia/`) não cobre as Etapas 1 a 4.
30. A busca de conhecimento é por palavra-chave e às vezes acerta mal (ex.: "revisão de biblioteca" achou uma seção
    de liderança).
31. O Neon (banco da nuvem) não foi conferido diretamente: as credenciais ficam só no GitHub.
32. A bateria de testes leva cerca de 5 minutos.

## 3. O que depende do dono (não dá para delegar)

| Item | Por que só você | Quanto tempo leva |
|---|---|---|
| Atualizar o notebook e rodar o diagnóstico | eu não alcanço o seu computador | 5 min: `git pull`, `instalar.bat`, `python -m robo diagnostico` |
| Instalar o Ollama (IA local) | instala programa no seu Windows e baixa de 2 a 5 GB | 15 min, depois do item acima |
| Token do Telegram | é criado pela sua conta, no seu celular (@BotFather) | 2 min |
| Chaves de API pagas (Claude, OpenAI, Perplexity) | custa dinheiro; a sua regra é não ter nada pago | só se você mudar a regra |
| Conta AWS, Google ou Azure | exige cartão | só se você mudar a regra |
| Abrir o Power BI Desktop | só roda no Windows | quando quiser o .pbix |

## 4. Decisões tomadas com a autonomia dada

1. **Nomes repetidos resolvidos** (só o nome exibido; id, histórico e permissões iguais):
   - `airflow_estagiario`: Davi → Gael;
   - `airflow_especialista`: Henrique → Caetano;
   - `rh_estagiaria`: Bianca → Lorena.
   O Davi da Estatística, o Henrique Head de Python e a Bianca do Airflow continuam com os nomes, porque são os
   mais citados no código e nos textos.
2. **Nada pago:** IA local (Ollama) como padrão; APIs externas ficam construídas e desligadas; pesquisa só com
   fontes gratuitas; nuvem continua no GitHub Actions e no Neon gratuito.
3. **Teto de 100 MB** para os dados sintéticos no banco da nuvem continua (proteção do plano gratuito).
4. **Ordem do trabalho** (seção 5), escolhida pelo que destrava mais coisas.

## 5. Ordem recomendada (cerca de 12 a 15 sessões)

| # | O quê | Itens | Sessões |
|---|---|---|---|
| 1 | Conhecimento das 5 ferramentas sem manual + replay ligado + guia atualizado | 5, 28, 29 | 1 |
| 2 | IA local: diagnóstico, fila compartilhada e registro de chamadas (funciona desligada até você instalar) | 1, 4 | 1 a 2 |
| 3 | Conversas com memória e pedido de ajuda entre funcionários | 2, 3 | 1 a 2 |
| 4 | Página Demandas, organograma e escritório 3D com repasses | 12 a 15 | 1 a 2 |
| 5 | Pesquisador com fontes gratuitas + governança da memória | 6, 7, 30 | 2 |
| 6 | Equipe AWS + plano 24 h com custos | 8, 9 | 1 |
| 7 | Catálogo de dados + primeiro experimento de ML | 10, 11 | 1 a 2 |
| 8 | Extras 7.1 a 7.7 | 16 a 22 | 2 a 3 |
| 9 | Pedidos antigos | 23 a 27 | 1 a 2 (Telegram depende do token) |
