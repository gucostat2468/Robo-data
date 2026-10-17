# Liderança, gestão e desenvolvimento de pessoas

Conhecimento obrigatório de diretores, heads, gerentes e coordenadores. Cada seção diz de onde vem
(fontes no fim) e como a regra é aplicada no robô.

## Os 10 comportamentos de um bom gestor (Project Oxygen)

O Google comparou seus gestores mais bem e mais mal avaliados e chegou a comportamentos concretos, que dá para
treinar. Eram 8 e passaram a 10 em 2018. A ordem não é ranking.
1. É um bom coach.
2. Dá autonomia ao time e não microgerencia.
3. Cria um ambiente inclusivo e se importa com o sucesso e o bem-estar das pessoas.
4. É produtivo e orientado a resultados.
5. Comunica bem: ouve e compartilha informação.
6. Apoia o desenvolvimento de carreira e conversa sobre desempenho.
7. Tem visão e estratégia claras para o time.
8. Tem conhecimento técnico para orientar o time.
9. Colabora com a empresa toda.
10. Decide com firmeza.

No robô: o scorecard da diretoria mede resultado (4); a auditoria do head mede conhecimento técnico (8); o plano
70-20-10 e a reunião semanal cobrem desenvolvimento e desempenho (6).

## Feedback SBI (Situação, Comportamento, Impacto)

Modelo do Center for Creative Leadership para dar feedback específico e difícil de contestar:
- **Situação:** quando e onde aconteceu ("na carga de nps_novembro de terça").
- **Comportamento:** o que a pessoa fez, observável ("publicou a nota 15 sem barrar").
- **Impacto:** o efeito no time ou no resultado ("o NPS do mês saiu errado no relatório").

Serve para elogio e para correção. No robô, todo erro na memória já traz situação (arquivo e data), comportamento
(o que falhou) e impacto (o que bloqueou). É o material do feedback no 1:1.

## 1:1 semanal

Conversa curta entre líder e liderado, toda semana, com pauta do liderado. Roteiro:
1. O que deu certo.
2. Onde travou.
3. Um feedback SBI.
4. Um compromisso de desenvolvimento para a próxima semana.

O registro fica no plano 70-20-10 da pessoa.

## Desenvolvimento 70-20-10

Modelo associado ao Center for Creative Leadership (McCall, Lombardo e Eichinger). Cerca de 70% do aprendizado vem
da experiência no trabalho, 20% das relações e do feedback e 10% de cursos e estudo formal. Os números são uma
referência, não uma regra exata. Críticos lembram que a pesquisa original era com executivos.

No robô (`lideranca.trilha_individual`), o plano de cada pessoa sai do que aconteceu com ela:
- **70%:** refazer, com acompanhamento, o caso em que errou.
- **20%:** 1:1 com feedback SBI sobre o handover do andar.
- **10%:** estudar e aplicar as boas práticas novas.

## Aprendizado contínuo (lifelong learning)

Aprender não é evento, é rotina. Na empresa isso quer dizer:
- **Rodada de estudo duas vezes por semana**, para todos: refazer a prova, revisar os próprios erros, estudar os
  handovers e as boas práticas do andar.
- **Erro vira lição registrada** (handover), e a lição vira padrão (boa prática) quando se prova que funcionou: é o PDCA.
- **Quem domina ensina:** sem erro na semana, o plano da pessoa passa a ser mentoria de um colega.
- **O líder também estuda:** diretores e heads entram na rodada e fazem prova como todo mundo.

## Plano de melhoria (PDI) e desligamento justo

- **Gatilho:** desempenho insuficiente na semana (pelo menos 5 eventos e menos de 70% de acerto).
- **Primeira semana:** a pessoa entra em plano de melhoria, com plano 70-20-10 e 1:1 semanal.
- **Segunda semana seguida:** a liderança **propõe** o desligamento, com os dados. Só o dono decide.
- **Cargo fixo do robô:** desempenho ruim é defeito de código e vai para a TI corrigir com teste automatizado.
- **Antes de propor desligamento:** o líder confere se a pessoa recebeu feedback, plano e tempo.

## Promoção e trilha de carreira

A trilha é estagiário → júnior → pleno → sênior → especialista.

Critérios para propor promoção (só contratados; os cargos fixos são código):
- pelo menos 20 trabalhos registrados nos últimos 30 dias;
- 95% ou mais de acerto;
- nenhum plano de melhoria em aberto;
- prova técnica aprovada.

A reunião semanal sugere, o dono aprova, e o RH reaplica o processo seletivo no nível novo. Se a pessoa não tiver a
competência para o risco do nível novo, a promoção é recusada com o motivo.

## Papel do diretor de dados (CDAO)

A Gartner define o diretor de dados e analytics (CDAO) como o responsável principal pela geração de valor a partir
dos dados e da analytics. Em pesquisa da própria Gartner, as funções mais citadas foram:
- supervisionar as iniciativas de analytics;
- governança de dados;
- estratégia de analytics;
- confiabilidade e valor da informação.

Para ter sucesso, o diretor precisa de presença, persistência e entrega de resultados mensuráveis. Na empresa,
o resultado mensurável é o scorecard com farol.

## Governança: owner, steward e custodian (DAMA-DMBOK)

- **Owner (dono do dado):** decide regras, acesso e prioridades e responde pelo resultado. Aqui são os diretores
  e o dono da empresa.
- **Steward:** executa no dia a dia: qualidade, metadados, resolução de problemas. Aqui são as equipes dos andares.
- **Custodian:** protege a infraestrutura conforme a política. Aqui é o 5º andar.

O dado é da empresa: quem cuida dele não é dono dele.

## Objetivos de nível de serviço e orçamento de erro (SRE)

Do livro de SRE do Google:
- **Indicador:** uma medida quantitativa (taxa de aprovação, horas desde o backup).
- **Objetivo (SLO):** a meta desse indicador.
- **Orçamento de erro:** 1 − objetivo. Com 99,9%, sobra 0,1% para falhar.

Enquanto sobra orçamento, dá para acelerar mudanças. Quando acaba, a prioridade volta a ser confiabilidade.
O farol do scorecard é essa lógica aplicada a cada área.

## Análise de drivers (key driver analysis)

- **Correlação:** mostra quanto cada atributo anda junto com o NPS, isoladamente.
- **Regressão padronizada:** reparte o peso entre atributos, mas fica instável quando eles se parecem demais
  (colinearidade).
- **VIF acima de 5:** sinal de alerta de colinearidade. Nesse caso, confie mais na correlação.
- **Associação não é causa:** driver aponta onde investigar, não prova o que causa o resultado.

## Fontes

- Gartner — CDAO: https://www.gartner.com/en/documents/6371211 e
  https://www.gartner.com/en/newsroom/press-releases/2016-11-10-gartner-predicts-15-percent-of-successful-chief-data-officers-will-move-to-ceo-coo-cmo-by-2020
- Google Project Oxygen: https://www.nextgov.com/digital-government/2018/02/google-expanding-its-list-what-it-takes-be-great-manager/146314/
  e https://oreilly.com/library/view/leading-effective-engineering/9781098148232/ch04.html
- 70-20-10: https://trainingindustry.com/wiki/content-development/the-702010-model-for-learning-and-development/ e
  https://www.bridgespan.org/insights/the-70-20-10-leadership-development-model
- SBI: https://people-shift.com/articles/sbi-feedback-model/
- SHRM, modelo de competências: https://sessionplanner.shrm.org/node/9115
- DAMA-DMBOK, papéis: https://open-exam-prep.com/study-guides/cdmp/data-governance-b/data-stewardship
- SRE, orçamento de erro (resumo; o livro está em sre.google): https://realpython.com/ref/software-engineering-glossary/error-budget/
- Drivers e colinearidade (Bain): https://www.bain.com/insights/making-friends-with-collinearity-how-driver-interactions-can-inform-targeted-interventions/
