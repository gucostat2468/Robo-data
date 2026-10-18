# Auditoria completa e visão de gestão — outubro/2026

Este documento responde a quatro perguntas:

1. Os funcionários aprendem de verdade?
2. Eles evoluem de verdade?
3. Tudo fica registrado?
4. O que falta?

Também traz a visão de gestão do projeto: cada página, cada andar e cada função.

> A visão de gestão **ao vivo** está no painel, em **Gestão do projeto**. Ela confere na hora:
> - as rotas de cada página;
> - o uso e a taxa de acerto de cada função;
> - a cobertura de testes de cada módulo;
> - a evolução semana a semana de cada funcionário.
>
> Este arquivo é uma fotografia dessa tela, tirada na empresa de demonstração em 18/10/2026.

---

## 1. Respostas diretas (sem enfeite)

### Os funcionários aprendem de verdade?

**Antes desta auditoria: não.** O sistema *registrava* bem (erros, lições, estudos), mas nada disso mudava o comportamento do robô na vez seguinte. Os sinais eram claros:
- o caderno marcava 1.628 lições como "aplicadas" **sem prova**;
- o PDCA "verificava" erros só porque o tempo passou.

**Agora: sim, num caminho real e comprovado** (`robo/aprendizado.py`):
1. A planilha é reprovada por algo que uma regra resolve:
   - coluna obrigatória que veio com outro nome;
   - valor novo fora da lista permitida.
2. O funcionário responsável **propõe** a regra.
3. **Só você aprova** (ninguém aprova a própria proposta).
4. A regra vale na hora, e o arquivo volta para a fila.
5. Se ele passar, a proposta vira **comprovada**, com a execução como prova. Daí em diante, os arquivos parecidos passam direto.

Isso foi testado de ponta a ponta no navegador. Na demonstração, a planilha de professores com "Nota NPS Professor" foi reprovada, a proposta foi aprovada e o mesmo arquivo passou (120 linhas).

**O que continua sendo só "registro":** lições de manual e de correção não mudam o código. Por isso agora elas só contam como "aplicadas" quando a pessoa **usa** a lição numa resposta, e isso fica registrado em `licoes_uso`.

### Eles evoluem de verdade?

**Agora dá para medir.** A página Gestão → "Evolução por funcionário" mostra, para cada pessoa:
- a taxa de acerto semana a semana (8 semanas);
- a tendência: **evoluindo / estável / piorando**.

A tendência só aparece com amostra mínima:
- pelo menos 5 eventos nas 2 últimas semanas e 5 nas anteriores;
- diferença de pelo menos 5 pontos.

Sem isso, a tela diz "dados insuficientes". Na demonstração (1 dia de histórico) aparece "dados insuficientes" para todos, **e isso é o correto**.

As métricas estavam infladas e foram corrigidas:

| Problema | Antes | Agora |
|---|---|---|
| Ajudar um colega | contava como "acerto" | conta como **colaboração** |
| Prova que não rodou por falha de código | culpava a pessoa | vira erro de sistema (TI) |
| Mesma reprovação | contava erro novo a cada rodada | só conta quando o resultado muda |
| Reconferência do caderno | gravava treinos, acertos e erros para outras pessoas | não grava nada |
| "Pessoas com memória registrada" | ia para 100% depois de qualquer rodada de estudo | conta só acerto ou erro de trabalho real |

### Tudo fica registrado?

**Agora sim, e não pode ser apagado.**
- **Proteção no banco:** gatilhos recusam DELETE em todas as tabelas de registro (experiências, handovers, boas práticas, memória, reuniões, conversas, mensagens, solicitações, etapas, aprovações, eventos, lições, propostas, erros de sistema, uso de ferramentas, salas).
- **Histórico de cada erro:** `handover_eventos` guarda cada ocorrência e cada mudança de estado, manual ou automática, e não aceita alteração.
- **Erro que volta depois de "verificado":** a boa prática fica sob suspeita e as lições voltam de "aplicada" para "avaliada", com registro.
- **Cadeia do conhecimento** (SHA-256), com três conferências:
  1. a própria cadeia;
  2. uma **âncora fora do banco**, que pega quem apagou o fim da cadeia;
  3. o estado de cada pessoa conferido contra a cadeia, que pega estado forjado.
- **Espelho no PostgreSQL:** recebe todas as tabelas de registro. As só de inclusão nunca são sobrescritas, então adulterar o SQLite não "conserta" a cópia.
- **Uso de cada ferramenta** (quem usou, deu certo, tempo): fica em `uso_ferramentas`.

---

## 2. Como a auditoria foi feita

- **Quatro revisões independentes, com reprodução de cada achado:**
  - ETL e dados;
  - aprendizado e registro;
  - painel e segurança;
  - telas.
- **Operação real no navegador** (Playwright + Chromium), sobre a demonstração recomeçada do zero:
  - login e as 21 páginas;
  - as 23 ações da sala de reunião;
  - o ciclo do aprendizado;
  - as 5 abas da Gestão;
  - rascunho preservado;
  - celular (390 px).
  - Resultado final: **55 passos, 0 erros**.
- **Testes automatizados:** **278 passando**, incluindo PostgreSQL real. Cada achado virou teste de regressão:
  - `teste_auditoria.py`;
  - `teste_aprendizado.py`;
  - `teste_gestao.py`;
  - testes novos em `teste_painel.py`, `teste_banco.py` e `teste_conhecimento.py`.

---

## 3. Achados e o que foi feito

### Segurança e painel

| # | Gravidade | Problema | Situação |
|---|---|---|---|
| S1 | crítico | Se a configuração falhasse ao carregar, a senha deixava de valer e qualquer um podia trocá-la | ✅ senha lida do arquivo; falha **fechada** |
| S2 | alto | "Excluir agente" aceitava `../config` e movia arquivos de fora da pasta | ✅ identificador validado |
| S3 | alto | SQL "somente leitura" deixava apagar dados (`SET … ; DELETE`) e rodar funções administrativas | ✅ 4 camadas (um comando, lista de proibidos, leitura, desfaz sempre) + opção de usuário só leitura |
| S4 | médio | JSON inválido ou que não é objeto derrubava a conexão (erro 500) | ✅ responde 400 |
| S5 | médio | Cada envio de arquivo vazava um descritor | ✅ |
| S6 | médio | Conexão lenta prendia uma linha de execução para sempre | ✅ tempo limite de 30 s |
| S7 | médio | Tarefa interrompida não era retomada; tarefa sem etapas saía "concluída" | ✅ |
| S8 | médio | A mesma rotina podia rodar duas vezes ao mesmo tempo | ✅ trava por rotina |

### Dados e ETL

| # | Gravidade | Problema | Situação |
|---|---|---|---|
| D1 | alto | NPS contava 99 ("não sabe") como promotor | ✅ só notas 0–10 em Python, SQL, Excel e conferência |
| D2 | alto | "tempo_atendimento" era lido como CSAT | ✅ |
| D3 | alto | Pesquisa sem ID perdia respostas iguais (mudava o NPS) | ✅ sem ID, mantém e avisa |
| D4 | alto | Banco gravava, mas o arquivo travado no Excel adiava, e a nova tentativa duplicava | ✅ checa antes; se travar depois, desfaz o lote |
| D5 | médio | "Total" como categoria era apagado | ✅ |
| D6 | médio | Uma data impossível (ano 0202) reprovava o arquivo inteiro | ✅ vira "não convertido", com a linha |
| D7 | médio | Cabeçalho com anos virava dado; CSV com título e UTF-16 não eram lidos | ✅ |
| D8 | médio | Calculadora lia o CSV publicado sem o decimal com vírgula | ✅ |
| D9 | médio | Fórmula ativa nos relatórios e no CSV de saída | ✅ |
| D10 | médio | Queda de conexão no meio da carga reprovava a planilha | ✅ adia |
| D11 | médio | Original travado (OneDrive) escapava sem registro e era reprocessado | ✅ novas tentativas, cópia e marca |
| D12 | médio | Retenção apagava o original no dia seguinte (contava pela data antiga) | ✅ |
| D13 | médio | Segmentação usava 720 MB em base média | ✅ 55 MB |
| D14 | — | "NPS da pesquisa de alunos" tratado como coluna | ✅ reconhece o nome da base |
| D15 | — | Regra ampla (`nps_*`) juntava pesquisas diferentes numa base só | ✅ agrupa pelo nome do arquivo (achado pela própria Gestão) |

### Aprendizado e registro

| # | Problema | Situação |
|---|---|---|
| A1 | Nada mudava o comportamento | ✅ regras aprendidas com aprovação do dono e prova |
| A2 | PDCA verificava só pelo tempo | ✅ exige carga aprovada depois da correção |
| A3 | Erro que voltava não desfazia "aplicada" | ✅ regressão registrada |
| A4 | Reconferência do laboratório tinha efeitos colaterais e revisava outra biblioteca | ✅ |
| A5 | Lições parecidas nunca saíam de "estudada" | ✅ |
| A6 | Uma lição nova por semente de laboratório (~144 por dia) | ✅ uma por área, etapa e responsável |
| A7 | Funcionário novo não recebia lições antigas; manual editado não virava versão | ✅ |
| A8 | Duas rodadas ao mesmo tempo aplicavam em dobro | ✅ |
| A9 | Integridade não via fim apagado nem estado forjado | ✅ âncora + conferência de estados |
| A10 | Tabelas sem proteção; histórico sobrescrito; PostgreSQL incompleto | ✅ |
| A11 | Métricas infladas (colaboração, provas, repetição) | ✅ |
| A12 | Ids de handover colidiam; erros de colunas diferentes se misturavam | ✅ |

### Telas

| # | Problema | Situação |
|---|---|---|
| T1 | O texto digitado sumia com a atualização automática (Solicitações e Sala) | ✅ |
| T2 | A Visão geral redesenhava a cada 2 s (foco, cliques e seleção se perdiam) | ✅ só quando o dado muda |
| T3 | No celular, Início, Consultas, Sala e 3D transbordavam | ✅ |
| T4 | Teclado: cartões e linhas clicáveis não eram alcançáveis | ✅ Enter e Espaço |
| T5 | Campos, interruptores e ícones sem nome acessível | ✅ |
| T6 | Contraste do botão principal no modo escuro (3,07:1) | ✅ |
| T7 | Página da sala sumia (nome repetido entre arquivos); recap gravado no lugar da reunião semanal; 401 antes do login | ✅ |
| T8 | TI dava vermelho na primeira abertura (banco ainda não criado) | ✅ |

### Ainda abertos (honesto)

| Item | Risco | Próximo passo |
|---|---|---|
| "Processar agora" depois de recarregar a config pode ter dois monitores | baixo | trava única do monitor |
| Cancelar uma tarefa não interrompe a etapa que já está rodando | baixo | checar o cancelamento entre etapas |
| Dois envios simultâneos com o mesmo nome podem se sobrescrever | baixo | mover com nome reservado |
| Coluna que mistura "1.500" e "1.5" | baixo | avisar quando houver os dois formatos |
| Escala do CSAT deduzida pelo maior valor | médio | declarar a escala na regra |
| 15 funções e 11 módulos sem teste **direto** (vários são testados indiretamente) | médio | criar testes diretos |

---

## 4. Visão de gestão — cada página

| Página | Para que serve | Andar dono | Rotas conferidas ao vivo |
|---|---|---|---|
| Visão geral | Saber em 5 s se o robô está trabalhando e o que entrou hoje | 4º | estado, histórico |
| Central de dados | Volume, qualidade e fila em tempo real | 4º | central |
| Estratégia | Sprint, avaliações técnicas, boas práticas | 4º | estratégia, boas práticas |
| Escritório 3D | Quem está fazendo o quê | 4º | escritório |
| Sala de reunião | Reunir a liderança de um andar (Teams) | 4º | salas |
| Raio-X da empresa | Como está agora e onde tudo fica | 4º | raio-x |
| **Gestão do projeto** | Páginas, andares, funções, módulos, evolução | 4º | gestão |
| Chat da empresa | Conversar com qualquer funcionário | 4º | funcionários |
| Solicitações | Pedidos, planos, aprovações, entregas | 4º | solicitações |
| Conhecimento | Caderno de lições, **regras aprendidas**, erros de sistema | 4º | conhecimento, erros |
| Memória e reuniões | Acertos, erros, handovers, PDCA, reunião semanal | 4º | memória |
| Canal da equipe | Mensagens e sprints | 4º | canal |
| Equipe e contratações | Fichas, provas, contratação | 4º | agentes |
| TI e segurança | Rondas de saúde e alertas | 5º | ti |
| Reprovados | Planilhas barradas e o motivo | 1º | reprovados |
| Histórico | Toda planilha processada | 1º | histórico |
| Testar planilha | Diagnóstico sem gravar | 1º | — |
| Banco de dados | Bruto → tratado → analítico | 1º | banco |
| Consultas SQL | Consultas por problema de negócio | 2º | consultas |
| Atividade | Log ao vivo | 5º | log |
| Configurações | Pastas, banco, senha | 5º | config |

Situação na fotografia: **21 de 21 páginas ok**, e todas as rotas responderam (entre 0 e 163 ms).

## 5. Visão de gestão — cada andar

Fotografia na demonstração recém-aberta: 1 dia de histórico, 78 funcionários.

| Andar | Pessoas | Farol do diretor | Acerto 30 d | Handovers abertos | Lições comprovadas | Evolução |
|---|---|---|---|---|---|---|
| 1º Engenharia de Dados | 19 | 🟡 | 100% | 3 | 0% | dados insuficientes |
| 2º Analytics e Ciência de Dados | 16 | 🟢 | 100% | 0 | 0% | dados insuficientes |
| 3º Sala Excel e BI | 10 | 🟢 | 100% | 0 | 0% | dados insuficientes |
| 4º Operações, governança, canal e RH | 15 | 🟡 | 100% | 0 | 0% | dados insuficientes |
| 5º TI, DevOps e segurança | 18 | 🟢 | 100% | 0 | 0% | dados insuficientes |

Como ler:
- **"Lições comprovadas 0%" é a verdade de uma empresa com um dia de vida.** As lições já foram estudadas e avaliadas, mas nenhuma tem prova prática ainda. A régua antiga mostraria cerca de 97%.
- **"Acerto 100%" mostra o limite do termômetro.** O treino atual raramente falha, então ainda não separa quem sabe de quem não sabe (ver o item 7, "laboratório com dificuldade crescente").

## 6. Visão de gestão — cada função

São 26 funções (ferramentas). Cada uso fica registrado com quem usou, se deu certo e o tempo. A tabela completa, ao vivo, está em Gestão → Funções.

| Função | Responsável padrão | Risco | Teste direto |
|---|---|---|---|
| Calcular | Davi (estatístico sênior) | baixo | ✅ |
| Consultar conhecimento | Nina (canal) | baixo | ✅ |
| Diagnosticar planilha | coordenação de engenharia | baixo | ✅ |
| Consulta SQL | Dora (DBA) | baixo | ✅ |
| Drivers do indicador | Vinícius | baixo | ✅ |
| Laboratório | head de engenharia | baixo | ✅ |
| Desempenho | Mauro (RH) | baixo | ✅ |
| Revisão de biblioteca | Henrique (guilda Python) | baixo | ✅ |
| Raio-X da empresa | diretoria de operações | baixo | ✅ |
| Resumo executivo | relator | médio | ✅ |
| Publicar planilha | recepção | **alto** (exige aprovação) | ✅ |
| Histórico, Perfil e indicadores, Dados pessoais, Ronda de TI, Reunião ao vivo, Ideias, Segmentação, Anomalias, Scorecard, Auditoria, Recrutamento, Desenvolvimento, People analytics, Estratégia Python, Organização | vários | baixo | ⚠ só teste indireto |

Na fotografia: Calcular 2 usos, 100% ok; Scorecard 1, 100%; Laboratório 1, 100%.

---

## 7. O que melhorar e expandir (em ordem de valor)

### Curto prazo (mais real e menos erro)

1. **Testes diretos** para as 15 funções e os 11 módulos sem teste direto.
2. **Laboratório com dificuldade crescente.** Incluir casos que hoje falham (treinamento difícil). Só assim "acerto 100%" vira um termômetro que mede evolução quando o código melhora.
3. **Mais tipos de regra aprendida:**
   - tipo de coluna;
   - faixa;
   - mapeamento de valores ("Sp." → "SP", com sua aprovação);
   - desativar sozinha a regra que "não resolveu".
4. **Correções que você faz no chat valendo para a empresa inteira,** com sua aprovação. Hoje valem só naquela conversa.
5. **Usuário do PostgreSQL só leitura** (`banco.usuario_leitura`) para as consultas livres. Já está suportado: falta criar o usuário no seu servidor.
6. Fechar os 6 itens da tabela "Ainda abertos".

### Médio prazo (mais robusto)

7. **Fotografia semanal** de desempenho por pessoa (tabela própria), para comparar trimestres.
8. **Teste real no seu Windows** (OneDrive, Excel aberto, antivírus) e **teste de volume** (300 mil linhas).
9. **Alertas de regressão:** se a taxa de alguém cair 5 pontos ou mais, a mão sobe sozinha na reunião do andar.

### Expansão

10. Conectores para **SQL Server e MySQL** (se for o caso do seu trabalho).
11. **Apresentação .pptx** gerada a partir do resumo executivo.
12. **Voz offline** na sala de reunião (Vosk: local, sem nuvem).
13. **IA local opcional** para redigir textos, sempre com a natureza "hipótese" e nunca no lugar do cálculo.
