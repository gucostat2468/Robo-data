# RH, desenvolvimento e crescimento da empresa

Regras que o código cumpre. Onde algo depende de você, está escrito.

## 1. Quem são os funcionários

Cada funcionário é uma **rotina de código** com cargo, nível, gestor, ferramentas autorizadas, limites e um revisor
(`robo/organizacao.py`). Não são pessoas nem IA: o mesmo pedido gera sempre a mesma resposta, e cada resposta
diz de onde veio: conhecimento, cálculo, execução, ferramenta, hipótese, confirmação ou limitação.

| Nível | Pode | Não pode |
|---|---|---|
| Gerente | responder pelo andar, aprovar trabalho alheio | executar etapa operacional, aprovar o próprio trabalho |
| Coordenador | liberar para produção, revisar | refazer o trabalho da equipe |
| Especialista e sênior | etapas críticas; alterar dados **com a sua aprovação** | aprovar a própria entrega |
| Pleno | segunda conferência independente | mudar regra ou dado |
| Júnior | checagens padronizadas de baixo risco | interpretar ou mudar dado |
| Estagiário | observar, calcular, relatar | alterar, aprovar ou bloquear qualquer coisa |

Só você promove, muda permissão e decide desligamento (`organizacao.pode_alterar_permissoes`).

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
