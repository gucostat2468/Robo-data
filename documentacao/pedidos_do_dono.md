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
| 79 | Fechar os itens abertos da auditoria | ✅ | os 6, mais 8 achados novos (N1–N8 em `documentacao/auditoria_e_gestao.md`) |
| 80 | Alerta quando alguém piora | ✅ | queda de 5 pontos ou mais → mão levantada na reunião do andar, com nomes e números |
| 38 | IA opcional sem fingir | 🟡 | `robo/ia.py`: só modelo local, desligado; ainda não usado nas respostas |
