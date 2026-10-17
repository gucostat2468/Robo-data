# RH, desenvolvimento e crescimento da empresa

Regras que o código cumpre. Onde algo depende de você, está escrito.

## 1. Quem são os funcionários

Cada funcionário é uma **rotina de código** com cargo, nível, gestor, ferramentas autorizadas, limites e um revisor
(`robo/organizacao.py`). Não são pessoas nem IA: o mesmo pedido gera sempre a mesma resposta, e cada resposta
diz de onde veio: conhecimento, cálculo, execução, ferramenta, hipótese, confirmação ou limitação.

| Nível | Pode | Não pode |
|---|---|---|
| Diretor(a) | responder pelo resultado da área (scorecard com meta e farol), propor ao dono | executar etapa, decidir no lugar do dono |
| Head | autoridade técnica: auditoria semanal por amostragem, padrões da área | aprovar o próprio trabalho |
| Gerente | responder pelo andar, aprovar trabalho alheio | executar etapa operacional, aprovar o próprio trabalho |
| Coordenador | liberar para produção, revisar | refazer o trabalho da equipe |
| Especialista e sênior | etapas críticas; alterar dados **com a sua aprovação** | aprovar a própria entrega |
| Pleno | segunda conferência independente | mudar regra ou dado |
| Júnior | checagens padronizadas de baixo risco | interpretar ou mudar dado |
| Estagiário | observar, calcular, relatar | alterar, aprovar ou bloquear qualquer coisa |

Só você promove, muda permissão e decide desligamento (`organizacao.pode_alterar_permissoes`).

### Liderança por área (desde 17/10/2026)

| Andar | Diretor(a) | Head | Abaixo |
|---|---|---|---|
| 1º Engenharia de Dados | Beatriz (CDO) | Eduardo | Marcelo (gerente) → Carla (coord.) → engenheiros |
| 2º Analytics e Ciência de Dados | Rogério | Natália (Ciência de Dados) | Patrícia, Marcos; cientistas Vinícius, Carolina, Lucas |
| 3º Sala Excel e BI | Rogério | Felipe (BI e Excel) | Ricardo, Sílvia e especialistas |
| 4º Operações e Governança | Cláudia | Simone (Governança) | Renata, Vitor, Lara, canal |
| 4º Pessoas (RH) | Marta (CHRO) | Juliana (Gente e Gestão) | Helena (coord.) → Priscila (R&S), Roberta (T&D), Mauro (desempenho), Tiago (people analytics), Bianca (estagiária) |
| 5º TI | Alexandre (CTO) | André (Infra e Segurança) | Gustavo, Fernanda e equipe |
| 5º Guilda Python | Alexandre (CTO) | Henrique (Engenharia Python) | Sofia (pandas), Nicolas (numpy), Olívia (openpyxl), Xavier (xlrd), Elisa (PyYAML), Pietro (psycopg), Silas (sqlite3) |

**A guilda Python é a mais cobrada da empresa.** O acerto mínimo deles é de 90%; no resto da empresa é de 70%.
Cada especialista responde pelos comportamentos da sua biblioteca dos quais o robô depende e pelos avisos de
depreciação no código. Só existe especialista para biblioteca usada de verdade (`requisitos.txt` + sqlite3).

O escopo de cada cargo foi baseado em fontes públicas confiáveis. A lista com os links está em
`conhecimento/lideranca_e_gestao.md`, que a liderança consulta no chat.

## 2. Contratação

- **Automática** (`robo/contratacao.py`): quando uma planilha traz um dado que ninguém trata (e-mail, telefone,
  CPF, CEP), o líder do andar contrata um estagiário em modo observação. São 3 meses de experiência.
- **Manual:** tela Equipe → Contratar, com habilidades e manual `.md`.
- **Regra:** ninguém trabalha sem passar na prova técnica do cargo (caso bom mais um erro plantado). Sem prova,
  a pessoa fica bloqueada.

## 3. Avaliação de desempenho

- **Fonte:** a memória de cada funcionário em `logs/trabalho.db`, copiada no PostgreSQL em `robo.memoria_experiencias`.
  Ela guarda acertos, erros, aprendizados e treinamentos, cada um com a origem: pipeline, tarefa, revisão, prova ou estudo.
- **Taxa** = acertos ÷ (acertos + erros) na semana. "Insuficiente" = pelo menos 5 eventos e menos de 70% de acerto.
- **1ª reunião insuficiente:** a pessoa entra em plano de melhoria (PDI).
- **2ª reunião seguida:** a liderança **propõe** o desligamento, e só você aprova (Solicitações → aprovações).
- **Cargo fixo:** cargos fixos do pipeline são o próprio código do robô. Desempenho ruim de um deles é **defeito
  de programa**: vira handover para a TI (Diego) com teste automatizado. Desligar o código que lê as planilhas
  pararia a empresa.

## 4. Desenvolvimento (duas vezes por semana)

Na rodada de estudo (`robo/desenvolvimento.py`), **todos** os funcionários:
1. refazem a prova técnica;
2. revisam os próprios erros da semana;
3. estudam os handovers abertos do andar;
4. estudam as boas práticas novas do andar.

Tudo entra na memória de cada um. Prova reprovada vira erro e handover para o RH.

Limite: estudar não muda o código sozinho. O que muda o comportamento é a regra aplicada, no `config.yaml` ou no
código com teste. A rodada garante que nada disso se perca e que a liderança veja quem está caindo.

## 4b. Promoção

A reunião semanal sugere a promoção de contratados com 20 ou mais trabalhos em 30 dias, 95% ou mais de acerto
e sem plano de melhoria. Você aprova em Solicitações. O RH reaplica o processo seletivo no nível novo: se a pessoa
não tiver competência para o risco do nível, a promoção é recusada com o motivo.

## 4c. Como confiar nos resultados

1. **Prova técnica de todos.** Ninguém trabalha reprovado.
2. **Conferência no banco.** Cada cálculo é refeito em SQL; uma divergência vira hipótese, nunca número.
3. **Auditoria semanal dos heads.** Cada head sorteia até 3 entregas da área e refaz por outro caminho; achado
   vira handover.
4. **Scorecard da diretoria.** Mede o resultado com meta e farol, calculado dos registros.
5. **Revisor independente.** Toda tarefa é revisada por alguém que não a executou.

## 4d. Laboratório: treino contínuo

Com o notebook ligado, a cada 10 minutos o laboratório gera uma planilha nova de uma área: educação/NPS, varejo,
RH, financeiro, marketing ou logística. Ela já vem suja como na vida real: título, acento, R$ em texto, datas em
texto, duplicata e linha de Total.
- **Como confere:** o gerador conhece a resposta certa. Por isso cada etapa (engenharia, cálculo, ciência de dados,
  PostgreSQL, biblioteca) é conferida contra a verdade.
- **O que acontece com o resultado:** acerto e erro vão para a memória de cada um. Erro vira handover, e quem errou
  pede ajuda a quem sabe (a conversa aparece no canal e como balão no 3D).
- **Onde fica:** os dados são sintéticos e ficam separados, em `logs/laboratorio` e no schema `laboratorio`.
  Nada vai para a produção.
- **Do que depende:** de nada externo (celular, internet ou créditos). Só do notebook ligado com o robô aberto.

## 5. PDCA contínuo e boas práticas

| Fase | Estado do handover | Quem |
|---|---|---|
| P — planejar | aberto ou reaberto: causa, regra para não repetir, como verificar | criado sozinho a partir do erro |
| D — fazer | em aplicação: item no backlog com responsável e prazo | reunião semanal |
| C — checar | aplicado: o robô confere se o erro voltou | automático |
| A — agir | verificado: vira **boa prática** padronizada, consultável no chat | automático |

Erro que volta reabre o handover. Erro repetido 3 vezes sobe para o líder do andar.

## 6. Reuniões

- **Semanal**, por andar, com o coordenador: deu certo, deu errado (com o porquê e o porquê de não estar
  resolvido), plano de ação, PDCA e desempenho. A ata vai para `logs/reunioes/`, para o canal #lideranca e para o backlog.
- **Ao vivo:** a qualquer momento, em Memória e reuniões → escolha o andar, ou pergunte ao coordenador no chat
  "como está o andar?".

## 7. Como subir um andar novo (quando houver trabalho real)

Andar novo só faz sentido com **trabalho real** para ele. Um andar sem ferramenta seria decoração. Passos:
1. **Ferramenta:** o que o andar faz, em código com teste (ex.: andar de Marketing → ferramenta que lê a base de
   campanhas e calcula ROI e CAC).
2. **Pessoas:** cargos em `robo/quadro.py`, com conferência, nível e gestor; a prova técnica de cada cargo.
3. **Líder:** entrada em `contratacao.LIDER_DO_ANDAR` e em `organizacao.LIDERES`; ferramentas em `FERRAMENTAS_ANDAR`.
4. **Nome e canal:** `organizacao.NOME_ANDAR` e `CANAL_DO_ANDAR`.
5. **Escritório 3D:** as mesas são desenhadas a partir da lista de pessoas.

Os testes de "registro único" e de "andar completo" acusam se faltar algum passo.
