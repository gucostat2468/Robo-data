# Pedidos do dono — acompanhamento

Todo pedido feito na conversa, com a situação real. Atualizado em 17/10/2026 (Fase 1 da evolução arquitetural).
Legenda: ✅ feito e testado · 🟡 feito em parte · ⏳ pendente

| # | Pedido | Situação | Onde está |
|---|---|---|---|
| 1 | ETL automático de Bases-Limpeza para Bases-Tratadas, só sem erros, tudo em Python, local | ✅ | `robo/pipeline.py` e etapas |
| 2 | App de uso próprio, sem nuvem (EC2 etc.) | ✅ | tudo roda em 127.0.0.1 |
| 3 | Interface gráfica caprichada (UI/UX) | ✅ | `robo/painel/` |
| 4 | PostgreSQL (ELT) | ✅ | `robo/banco.py` |
| 5 | Onde colocar o PostgreSQL real | ✅ | Configurações → Banco de dados; variável `ROBO_PG_SENHA` |
| 6 | Ver funcionando em tempo real | ✅ | vídeo enviado; Central de dados ao vivo |
| 7 | 2º andar no escritório, navegação fluida entre andares | ✅ | `escritorio.js` (hoje 5 andares) |
| 8 | RH profissional, meritocracia técnica, sêniores que contratam pleno/júnior/estagiário | ✅ | `robo/rh.py`, `robo/quadro.py` |
| 9 | Canal com a equipe, filtros e caixa de texto que entende o dono | ✅ | `robo/canal.py`, página Canal |
| 10 | Sprint de 15 dias (feito, bom, travou, backlog) | ✅ | canal + página Estratégia |
| 11 | Alguém para dar ideias | ✅ | Iara (`canal.ideias`) |
| 12 | Supervisor de planilhas, pessoa do PostgreSQL, coordenadores conferindo antes da produção | ✅ | `robo/producao.py` |
| 13 | Organização com boas práticas de engenharia, análise e ciência de dados | ✅ | `conhecimento/boas_praticas.md`, aba Boas práticas |
| 14 | Sala Excel de especialistas (trade e pesquisa) com supervisor ex-Microsoft que responde no chat e coordena a limpeza | ✅ | `robo/excel.py`; Ricardo barra o que o Excel corromperia |
| 15 | Sem API, sem internet, nenhum agente dormindo | ✅ | canal offline; estado "de plantão" |
| 16 | Falar em português | ✅ | — |
| 17 | Repositório e arquivos com nomes em português | 🟡 | tudo renomeado; o nome do repositório no GitHub ("Robo-data") só pode ser trocado por você em Settings |
| 18 | Todos os andares lotados, do gerente ao estagiário, com escopo por senioridade | ✅ | 5 andares, 52 pessoas no quadro + contratados |
| 19 | Andares contratando sempre, com habilidades e manuais .md, também de forma automática | ✅ | `robo/contratacao.py`, página Equipe |
| 20 | Andar de TI, AWS, dev, DevOps, infra e segurança | ✅ | `robo/ti.py` (AWS consultiva, sem nuvem) |
| 21 | Quais linguagens, se é seguro, se é produto profissional | ✅ | respondido na conversa e no guia |
| 22 | Líderes com autonomia para contratar estagiários; experiência de 3 meses | ✅ | `contratacao.avaliar_experiencias` |
| 23 | Painel de dados em tempo real (erros, acertos, planilhas erradas) | ✅ | página Central de dados |
| 24 | Estratégia: sprints com prioridades alinhadas, testes técnicos e treinamentos | ✅ | página Estratégia |
| 25 | Equipe preparada para qualquer cálculo, cabeçalho, variável, segmentação, erro | ✅ | centro de treinamento (17 casos difíceis), calculadora |
| 26 | Explicação de tudo, linha por linha | ✅ | `documentacao/guia/` |
| 27 | Texto único descrevendo o projeto (para outra IA) | ✅ | enviado na conversa |
| 28 | Senha no painel | ✅ | Configurações → Senha do painel, ou `python -m robo senha` (PBKDF2, sessão HttpOnly, trava contra força bruta) |
| 29 | Backup automático do banco | ✅ | `robo/backup.py` |
| 30 | Teste de volume | 🟡 | 100 mil linhas em 154 s (ok); 300 mil interrompido por reinício da máquina de testes |
| 31 | Rodar no Windows do dono | ⏳ | depende de você: `instalar.bat` |
| 32 | Conversar direto com qualquer funcionário, com memória | ✅ | botão Conversar na ficha; `robo/atendimento.py` |
| 33 | Central de solicitações com estados, aprovações e histórico | ✅ | página Solicitações; `robo/trabalho.py`, `robo/orquestrador.py` |
| 34 | Banco de memória de cada funcionário (erros, acertos, aprendizados) no SQL | ✅ | `logs/trabalho.db` + PostgreSQL `robo.memoria_experiencias` |
| 35 | Todo erro vira handover para a área | ✅ | `robo/memoria.py`; `robo.memoria_handovers` |
| 36 | Reunião semanal da liderança (certo, errado, plano de ação) | ✅ | página Memória e reuniões; `robo/reuniao.py` |
| 37 | Desligar quem não tem desempenho | 🟡 | contratados: PDI → proposta → sua aprovação; cargos fixos viram correção de código (demitir o código pararia o robô) |
| 39 | NPS sem casas decimais, com a conta aberta | ✅ | calculadora, resumo do 2º andar e Excel |
| 40 | Fazer à mão quando eu precisar | ✅ | todo cálculo traz fórmula do Excel e SQL equivalente |
| 41 | Confiabilidade de SQL e cálculos | ✅ | dupla checagem no PostgreSQL (conferido / divergente / não aplicável) |
| 42 | Qualquer consulta SQL | ✅ | Dora roda SELECT livre em transação somente leitura |
| 43 | PDCA contínuo e boas práticas | ✅ | `robo/memoria.py` (checagem automática) |
| 44 | Estudo de todos 2x por semana | ✅ | `robo/desenvolvimento.py` |
| 45 | Reunião com cada coordenador, também ao vivo | ✅ | Memória e reuniões; "como está o andar?" no chat |
| 46 | Chat com todos, com filtros | ✅ | página Chat da empresa |
| 47 | Alguém pensando no futuro com a memória | ✅ | Iara (`robo/ideias.py`) |
| 48 | RH bem definido, novos andares | ✅ | `documentacao/rh_e_desenvolvimento.md` |
| 49 | Qualquer tipo de banco de dados | 🟡 | PostgreSQL e SQLite hoje; SQL Server/MySQL exigem driver (ver resposta) |
| 50 | Diretores e heads em cada área, com escopo pesquisado | ✅ | `robo/lideranca.py`, `conhecimento/lideranca_e_gestao.md` (com fontes) |
| 51 | Cientistas de dados | ✅ | Vinícius (drivers), Carolina (segmentação), Lucas (anomalias) — `robo/ciencia.py` |
| 52 | Sala de RH completa | ✅ | Marta (CHRO), Juliana (head), Helena, Priscila, Roberta, Mauro, Tiago, Bianca |
| 53 | Conversa natural e organizada | ✅ | frase em português primeiro, detalhes em seções recolhíveis |
| 54 | Como confiar nos resultados | ✅ | auditoria semanal dos heads + conferência no banco + scorecard + revisor independente |
| 55 | Como está a empresa agora / onde tudo é registrado | ✅ | página Raio-X da empresa |
| 56 | Funcionar bem só com o notebook aberto | ✅ | rotinas registradas, recuperação do que atrasou e resumo de abertura |
| 57 | Liderança que desenvolve pessoas (lifelong learning) | ✅ | Project Oxygen, SBI, 1:1, 70-20-10, PDI e promoção |
| 58 | Reunião em tela, estilo Teams, telas abertas enquanto falo | ✅ | página Sala de reunião (`robo/sala.py`) |
| 59 | Trabalhar sozinhos com Excel e PostgreSQL de várias áreas | ✅ | laboratório a cada 10 min (`robo/laboratorio.py`), schema `laboratorio` |
| 60 | Funcionar com celular desligado ou sem créditos | ✅ | tudo local; só depende do notebook ligado |
| 61 | TI Python estratégica | ✅ | Henrique e TI: velocidade por volume, projeção e dívida técnica |
| 62 | Especialista para cada biblioteca, os mais cobrados | ✅ | guilda Python, exigência de 90% (`robo/bibliotecas.py`) |
| 63 | Interação entre funcionários e balão no 3D | ✅ | `robo/interacoes.py`; balões no escritório 3D |
| 64 | NPS numa fórmula só | ✅ | `=ARRED((CONT.SES(…>=9) − CONT.SES(…<=6)) / CONT.SES(…>=0) * 100; 0)` |
| 65 | Conhecimento sólido de todos, sem perder nada, para sempre | ✅ | caderno de lições (`robo/licoes.py`): todo erro, boa prática, falha de treino, correção sua e manual vira lição; cada um estuda, é testado e só conta como aplicada com prova |
| 66 | Governança, segurança e organização do conhecimento | ✅ | nada se apaga (gatilhos no banco), versão nova e arquivamento só por você, cadeia SHA-256 que denuncia adulteração, cópia em JSONL e no PostgreSQL |
| 67 | Todo erro de sistema registrado para nunca mais acontecer | ✅ | `robo/erros.py`: todo log de erro vira registro permanente com traceback, handover para a TI e reabertura se voltar; tela Conhecimento |
| 68 | Ver a operação inteira na minha frente e interagir | ✅ | `python -m robo demo` / `Demonstracao.bat`: empresa separada, 6 áreas + 1 planilha com defeito real |
| 69 | Engenharia reversa do Teams | ✅ | `documentacao/sala_teams.md`: mão levantada, reações, pessoas, compartilhar, galeria/palestrante/fixar, câmera local, leitura em voz, pauta, anotações, tarefas e recap |
| 70 | Nada de erro na operação | ✅ | percurso automático no navegador: 20 páginas e 23 ações da sala sem erro; 255 testes; ronda de TI saudável |
| 71 | Aprendem de verdade? | ✅ | regras aprendidas com aprovação do dono e prova (`robo/aprendizado.py`); antes era só registro — ver `documentacao/auditoria_e_gestao.md` |
| 72 | Evoluem de verdade? | ✅ | evolução semanal por pessoa com amostra mínima (Gestão → Evolução); métricas infladas corrigidas |
| 73 | Tudo registrado? | ✅ | nada se apaga (gatilhos), histórico de cada erro, cadeia com âncora, espelho completo no PostgreSQL |
| 74 | Auditoria completa e correção de cada detalhe | ✅ | 4 revisões independentes + operação no navegador: 46+ achados, corrigidos com teste de regressão; abertos listados |
| 75 | Visão de gestão de cada página, andar e função | ✅ | página Gestão do projeto (ao vivo) + `documentacao/auditoria_e_gestao.md` |
| 76 | Treino que mede evolução de verdade | ✅ | laboratório com 4 níveis (`robo/laboratorio.py`); Gestão → Laboratório (termômetro): nível 4 subiu de 50% para 100% quando o código aprendeu |
| 77 | Regra aprendida mais completa | ✅ | correção de valor ("Sp." → "SP") e desativação automática da regra que não resolveu (`robo/aprendizado.py`) |
| 78 | Correção minha no chat valendo para todos | ✅ | vira proposta; aprovada, todo cálculo da empresa usa e avisa; o 1º cálculo comprova |
| 79 | Fechar os itens abertos da auditoria | ✅ | os 6, mais 9 achados novos (N1–N9 em `documentacao/auditoria_e_gestao.md`) |
| 80 | Alerta quando alguém piora | ✅ | queda de 5 pontos ou mais → mão levantada na reunião do andar, com nomes e números |
| 81 | Como está o banco e como está organizado | ✅ | página **Banco da empresa** (ao vivo) + `documentacao/banco_de_dados.md` (gerado do código, 40 tabelas) |
| 82 | Nunca perder nada (base para Machine Learning) | ✅ | toda tabela recusa DELETE (inclusive as futuras); backup diário conferido do SQLite; 1º backup do mês para sempre; espelho completo no PostgreSQL; originais guardados para sempre |
| 83 | Treino contínuo de todos, no nível de cada um, sem planilha real | ✅ | `robo/treino.py`: 13 competências × 5 níveis, casos sintéticos com gabarito, a ferramenta real do contrato, nível sobe/desce com prova |
| 84 | Uma sala de quem prepara os trabalhos, que saiba mais que todos | ✅ | Sala de Casos (4º andar): designers certificados no nível desafio, revisora independente, planejadora |
| 85 | Reuniões levadas a sério | ✅ | decisão com dono, prazo e critério; reunião abre cobrando; atrasada não passa em branco; ata com SHA-256 |
| 86 | Criar o banco real e passar as variáveis | ✅ | `python -m robo instalar-banco` (usuários robo_app e robo_leitura, senhas em variáveis de ambiente) |
| 87 | Boas práticas para tudo | ✅ | `documentacao/boas_praticas_operacao.md` |
| 88 | Acompanhar a empresa pelo celular | ✅ | `python -m robo celular --ligar`: página SOMENTE LEITURA na rede de casa, mesma senha do painel, bloqueio por força bruta, todo acesso registrado (`acessos_celular`) |
| 89 | Ligar o app de banco do celular no meu PostgreSQL | ✅ | `python -m robo liberar-banco-celular` (Prompt como Administrador): só `robo_leitura`, só a rede de casa, cópia do pg_hba.conf antes de mexer, imprime os campos do app |
| 90 | Profissionais de Airflow | ✅ | Henrique, Bianca e Davi (5º andar): fluxos únicos para robô e Airflow, DAG gerada (`python -m robo airflow-dag`) e validada no Airflow 3.1.8 real, SLA das rotinas na ronda de TI, competência de treino 'orquestracao' — guia `documentacao/airflow.md` |
| 91 | Conversas e trocas reais entre todos | ✅ | `robo/interacoes.py`: erro de treino → mentoria com quem já acertou (com a lição real); quem sobe de nível ensina um colega; conversas entre áreas por fatos (SLA, queda de acerto); mentoria fechada como 'ajudou'/'não ajudou' |
| 92 | A Sala de Casos também treina e evolui | ✅ | competência `revisao_casos`: revisar casos com defeito plantado; 10 revisores reforçados (antes deixavam passar gabarito adulterado) |
| 93 | RH com meritocracia (admissão, promoção, desligamento) | ✅ | `robo/rh_desempenho.py`: promoção por dados (validada pelo gestor; estagiário→júnior e pleno→sênior só com o dono), plano de melhoria, afastamento da ferramenta, reintegração; desligamento só de contratados e só com o dono |
| 94 | Liderança decide quando eu estiver fora | ✅ | `robo/alcadas.py`: com o dono fora há 12 h, itens de baixo risco são decididos por um líder e validados por outro; o dono reverte em até 7 dias; risco médio/alto fica com o dono |
| 95 | Tudo registrado no SQLite e no PostgreSQL | ✅ | `robo/registro_total.py`: log do sistema, canal, atas, RH, conhecimento, estado da TI e config (sem senhas) no banco; cópia incremental no PostgreSQL a cada 10 min |
| 96 | Backup constante e nunca cair | ✅ | backup conferido de hora em hora + cópia num 2º lugar (`backup: copia_extra`); vigia que religa o robô (`python -m robo vigia ligar`); `python -m robo diagnostico` |
| 97 | App só meu no celular, ao vivo | ✅ | abas Ao vivo / Andares / Operação, renova a cada 10 s, só leitura, só rede de casa |
| 99 | Menu organizado e responsivo | ✅ | menu em 4 grupos (Acompanhar, Pessoas, Dados, Gestão) que lembram se estão abertos; no celular vira gaveta (☰) |
| 100 | Ver a conversa dos funcionários em balões, ao vivo | ✅ | escritório 3D: balões em cima de quem fala, com as conversas e as tentativas de treino REGISTRADAS no banco (`interacoes`, `treino_tentativas`) e há quanto tempo |
| 101 | Especialista de Power BI que monta e mantém os dashboards | ✅ | Bárbara (especialista) e Heitor (reconciliação), 3º andar: `robo/paineis.py`, tela Dashboards, rotina `paineis` de hora em hora, versões em `paineis_versoes` (imutável), modelo estrela refeito em `logs/paineis/estrela/` |
| 102 | Kit Power BI (estrela, DAX, Power Query, telas) | ✅ | `powerbi/` com guia clique a clique; o .pbix não foi gerado porque o Power BI Desktop só roda no Windows |
| 103 | Tudo registrado para ML/DL, nada se perde | ✅ | todo registro de treino, conversa, mentoria, RH, rotina e painel é só de inclusão (gatilho bloqueia UPDATE/DELETE), copiado para o PostgreSQL e com a versão do código em cada tentativa |
| 104 | Especialista em Power BI analisando as planilhas (reais e sintéticas) | ✅ | `robo/leitura_bi.py`: tema pelos cabeçalhos, dicionário, regras de negócio conferidas, modelo estrela, DAX e números-âncora; Heitor confere por outro caminho; registro em `paineis_planilhas` |
| 105 | Engenharia reversa completa do Power BI | 🟡 | feita pela documentação oficial (`documentacao/powerbi_engenharia_reversa.md`): o app do Power BI só roda no Windows e não pôde ser aberto daqui; o relatório interativo da aba Planilhas reproduz filtro cruzado, filtros, foco, tabela, CSV, ordenar, dicas e o tema |
| 106 | Quem faz o quê / o que o 5º andar faz | ✅ | página "Quem faz o quê": escopo e último trabalho registrado de cada um, parados em destaque |
| 107 | Toda ideia de funcionário chega até mim | ✅ | "Caixa do dono": ideias e pendências que só o dono decide; decisão registrada em `caixa_dono_eventos` |
| 108 | Esteira ponta a ponta funcionando (Airflow) | ✅ | rotina `jornada`: planilha suja passa pelas 7 etapas num computador de teste e cada etapa é conferida |
| 109 | Grupo de WhatsApp com os funcionários | ❌ | WhatsApp não tem grupo para robôs nem opção grátis oficial; alternativa grátis: grupo no Telegram com robô (precisa do token do @BotFather) |
| 110 | Status honesto: ninguém aparece trabalhando sem estar | ✅ | `robo/jobs.py`: trabalhando só com etapa de job aberta; rotina e ronda viram plantão; `/api/prova-de-trabalho`; topo do escritório com trabalho real agora e última planilha |
| 111 | Fábrica de planilhas sintéticas como prioridade, para todos os andares treinarem | ✅ | `robo/fabrica.py` + `robo/regras_negocio.py`: 15 regras de negócio, 2 a 20 mil linhas, esteira real, gabarito conferido, separada do real; achou e corrigiu uma falha real da limpeza (nota fiscal duplicada) |
| 112 | Funcionários conversam entre si só quando precisam, sem teatro | ✅ | `robo/fatos.py` + `robo/dialogo.py`: conversa só nasce de um fato registrado, 2 a 4 falas e um compromisso conferido depois; sem fato, o ciclo registra "sem assunto" |
| 113 | Comunicação natural, sem cara de robô | ✅ | `robo/voz.py`: tom do cargo, sem listas e sem ; * #, sem repetir o mesmo parágrafo em 24 h |
| 114 | A empresa aprende com cada erro e acerto | ✅ | `robo/aprendizados.py`: memória consultada antes de ler cada planilha; semente de 208 erros típicos (`python -m robo semear-aprendizado`); replay de erros antigos |
| 115 | App do celular de verdade | ✅ | `python -m robo diagnostico-celular` (8 passos e QR code), página "No celular" no painel com o QR, ícones PNG, service worker e tela offline (em HTTPS), telas sem rolar para o lado em 375 px, ações opcionais (pausar, retomar, ver log, reprocessar) desligadas por padrão e registradas |
| 116 | Todas as tabelas do banco com dados | 🟡 | causa de cada vazia levantada e registrada (`python -m robo cobertura-banco`); esteira passou a rodar na nuvem; `laboratorio` e `treino` passaram a receber o dado sintético. As que dependem de pedido do dono, reunião, RH ou chat continuam vazias até esses fatos acontecerem: encher com linhas inventadas seria mentir |
| 117 | Reestruturação operacional (24 itens) | 🟡 | etapas 1 a 4 de 9 feitas (diagnóstico, persistência, execução real, equipe de demandas); o que falta está em `documentacao/diagnostico_geral.md` |
| 118 | Funcionários recebendo e executando tarefas de verdade | ✅ | `robo/demandas.py` + orquestrador: tarefa com a ferramenta do contrato, critérios de aceitação conferidos sem IA, revisão por outra pessoa, job como prova; 87 de 87 elegíveis receberam e executaram demanda no teste local (79 de 81 aprovadas na 1ª rodada; as 2 falhas eram defeito da preparação, corrigido) |
| 119 | Cinco funcionários distribuindo demandas sintéticas em 4 níveis, sem deixar ninguém para trás | ✅ | Aurora, Vicente, Isadora, Renan e Bento (`robo/demandas.py`); níveis básico a profissional com trabalho diferente em cada um; cobertura por andar e área (`python -m robo cobertura-demandas`); abandono, treinamento no lugar e avaliação independente registrados |
| 120 | Diagnóstico geral do projeto e decisões com autonomia | ✅ | `documentacao/diagnostico_geral.md`: 32 itens abertos, 6 que dependem do dono, ordem recomendada; nomes repetidos resolvidos (Gael, Caetano, Lorena) |
| 121 | Organograma visual | ⏳ | planejado (diagnóstico geral, item 13) |
| 122 | Grupo no Telegram com foto, nome, área e cargo de cada funcionário | 🟡 | código pronto e testado (`robo/telegram.py`, `python -m robo telegram`): responde só você, assina por funcionário, cartão com foto de cada um, tudo registrado; falta o token do @BotFather (seu celular, 2 min) |
| 123 | Fundos de Power BI no estilo Figma | ⏳ | planejado (diagnóstico geral, item 24) |
| 124 | Skill de engenharia reversa para o Claude | ⏳ | planejado (diagnóstico geral, item 25) |
| 125 | Funcionário de pesquisa (Markdown, PDF, fontes, notificações) | ⏳ | planejado (Etapa 7; fontes gratuitas, Perplexity só com chave sua) |
| 126 | Head de AWS e Sênior de AWS/Linux/Ubuntu | ✅ | Heloísa (Head de AWS) e Ícaro (Sênior AWS/Linux/Ubuntu) com trabalho real: prontidão para servidor, backup que restaura, saúde do PostgreSQL, segredos no repositório; demanda a cada 2 h; sem acesso à nuvem (menor privilégio) |
| 127 | IA local para os funcionários | ⏳ | planejado (Etapa 5); a instalação no seu notebook depende de você |
| 128 | Machine learning e deep learning com os dados do banco | ⏳ | planejado (Etapa 9): primeiro experimento com as tentativas de treino |
| 129 | Extras 7.1 a 7.7 (contrato de dados, drift, linhagem, fila com SLA, dia acelerado, relatório semanal em PDF, teste de caos) | ⏳ | planejado |
| 130 | Relatório final com vídeo dos andares | ⏳ | planejado |
| 131 | Funcionários de dados treinando SQL, não só planilha | ✅ | `robo/sql_treino.py`: 4 níveis (contagem → reconciliação com CTE) sobre os lotes da fábrica no PostgreSQL, conferidos contra o gabarito; áreas de dados alternam SQL e ferramenta própria |
| 132 | Consultas SQL que funcionam com o que temos | ✅ | `consultas_sql/07 Treino da fábrica` (30, uma por regra) e `08 Operação da empresa` (10, sobre a memória); a tela marca ●/○ e diz o que falta para cada consulta |
| 133 | 5º andar e AWS trabalhando mais | ✅ | 5º andar a cada 6 h, Heloísa/Ícaro/Cloud a cada 2 h (geral: 24 h); 4 verificações novas na ronda de TI |
| 134 | Desenho do Google Cloud (Cloud Run + Cloud SQL) | 🟡 | projeto pronto (Dockerfile sem root, PORT, Unix socket do Cloud SQL, saúde só leitura, instância única) e testado em contêiner; NADA criado no Google: custa cerca de US$ 70–100/mês (`documentacao/nuvem_google.md`) |
| 135 | Todas as tabelas do PostgreSQL com dados reais e coerentes | 🟡 | schemas laboratorio/treino/robo enchem com o trabalho real; tratado/analitico só com planilha REAL sua (não invento); causas em `python -m robo cobertura-banco` |
| 136 | App no celular para acompanhar em tempo real, sem computador | ✅ | página "Empresa ao Vivo" no Claude lendo o boletim que a nuvem publica a cada 5 min (`robo/boletim.py`); guia em `documentacao/celular_sem_pc.md` |
| 137 | Telegram configurado só pelo celular | 🟡 | `/vincular CÓDIGO` no grupo (sem ids, sem computador); falta você criar o robô e os 2 segredos no GitHub |
| 138 | Empresa trabalhando de verdade o dia todo | ✅ | turnos de 40 min que chamam o próximo (antes: 20 min a cada 3–6 h); o 1º boletim achou e foi corrigido o SQL que falhava na nuvem |
| 139 | Cada funcionário fazendo o seu papel de verdade | ✅ | trabalho definido pela área/andar com rodízio (antes 73 de 94 repetiam sempre o mesmo trabalho; depois 7 de 85, todos da Sala de Casos, cujo papel é um só); RH faz RH, Sala de Casos revisa casos, TI opera, Governança faz LGPD |
| 140 | Testes difíceis | ✅ | laboratório nível 5 (sistema antigo), nível inicial perto do limite do cargo; o nível 5 achou e corrigiu um defeito real da limpeza (cabeçalho repetido); casos velhos são reconferidos antes de reusar |
| 141 | Tudo registrado para treinamento e para todos aprenderem | ✅ | erro de treino vira lição para a equipe da mesma área; replay diário dos erros reais; estagiários registram o que observam; manual com o método de cada um dos 28 trabalhos |
| 142 | Todos os funcionários fazendo o trabalho deles | 🟡 | conferido no boletim real da nuvem: 22 estudavam por falta de planilha na máquina nova → turno com a correção: 92 de 101 no papel + 7 estagiários observando; 2 aguardavam o próximo ciclo |
| 143 | Plano mestre: produto real, auditável, com celular | 🟡 | ciclo 1: inventário conferido no código (documentacao/inventario_capacidades.md); cobertura real das tabelas e acerto por nível no boletim do celular; testes automáticos a cada push (.github/workflows/testes.yml); próximos passos no backlog do inventário |
| 144 | Equipe de AI Engineering e inteligência própria | 🟡 | 4 papéis novos nos andares existentes; 1º modelo próprio (risco de a demanda não ser concluída) com dataset versionado, baseline, avaliação independente, promoção por eventos, rollback e sombra (documentacao/inteligencia_propria.md); uso em decisão real só com o dono |
| 145 | App no celular pelo Floot | ✅ | https://robo-de-planilhas-ao-vivo.floot.app — lê o boletim real, somente leitura, horário e atraso visíveis, instalável pelo Safari (documentacao/celular_sem_pc.md) |
| 146 | Níveis de verdade (difícil e profissional acontecendo) | 🟡 | boletim real: só básico (163) e médio (9). 1ª demanda agora começa no início do cargo (sênior no médio, gerente/head/diretor no difícil), com recalibração única de quem tinha só histórico abaixo; acima disso só com 2 entregas concluídas seguidas |
| 147 | No celular, o MESMO painel de antes (com o 3D dos 5 andares) | ✅ | conferido com o espelho REAL da nuvem (16:52 UTC): painel, equipe de 105 pessoas e escritório 3D com conversa real entre funcionários, num Chromium com tela de iPhone |
| 148 | Histórico da nuvem com linhas cortadas (achado pelo app) | ✅ | a restauração entre turnos recriava o CSV sem o \r e a captura seguinte continuava de uma posição antiga, cortando o começo das linhas novas; planilhas de treino passavam por reais e a Central de dados quebrava. Linha agora guardada exatamente como escrita, cursor alinhado ao arquivo recriado e linha cortada antiga fora de toda conta (testes de 3 turnos seguidos) |
| 98 | Você acessar meu PC | 🟡 | esta sessão roda na nuvem e não alcança o seu PC; para eu operar no Windows: Claude Desktop ou `claude remote-control` na pasta do projeto |
| 38 | IA opcional sem fingir | ✅ | `robo/ia.py`: desligada por padrão; Ollama local, API compatível ou Claude; só redige, nunca calcula; texto com número fora dos fatos é descartado; frase de IA marcada como hipótese com o modelo |
