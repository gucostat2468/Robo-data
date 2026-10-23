# Acompanhar a empresa só pelo celular (sem ligar o computador)

Tudo abaixo roda na nuvem gratuita do GitHub e no PostgreSQL gratuito (Neon). O computador pode ficar desligado.

## 1. Como a empresa trabalha sozinha

- Um **turno de 40 minutos** roda no GitHub Actions; ao terminar bem, ele chama o próximo (empresa contínua).
  Antes, o GitHub atrasava o horário marcado em 3 a 6 horas e a empresa ficava parada a maior parte do dia.
- Durante o turno, a cada **5 minutos** sai um **boletim**: andares, quem está trabalhando, últimas entregas,
  exercícios de SQL, fábrica de planilhas. Ele fica guardado como um commit no ramo `painel-celular` (o histórico
  inteiro fica, nada é apagado).
- **Pausar a empresa contínua** (pelo celular): github.com → repositório → Settings → Secrets and variables →
  Actions → aba **Variables** → New repository variable → nome `ROBO_TURNO_CONTINUO`, valor `0`. Para voltar,
  apague a variável ou troque para `1`. O agendamento de hora em hora continua como rede de segurança.

**Atenção ao banco gratuito:** trabalhando quase o dia todo, o Neon usa mais horas de processamento. O plano
gratuito tem um limite mensal; ao chegar nele, o Neon suspende o banco até o mês seguinte (o plano grátis não
cobra nada e os dados ficam guardados). Confira em neon.tech → seu projeto → **Usage** na primeira semana.

## 2. O app (página "Empresa ao Vivo" no Claude)

1. Abra o link da página no **app do Claude** no celular (o mesmo que você usa para conversar comigo).
2. Na primeira vez, ele pede para usar o conector do **GitHub**: toque em **Permitir**. Se o GitHub ainda não
   estiver conectado na sua conta do Claude, ele oferece conectar (Configurações → Conectores → GitHub).
3. Pronto: a página mostra o estado da empresa e se atualiza sozinha enquanto estiver aberta.

O que aparece: se a empresa está **trabalhando agora**, **entre turnos** ou **parada** (sem boletim há mais de
1 hora); demandas do dia, concluídas, quem já trabalhou; quem está trabalhando no momento; os andares; o ritmo do
dia (gráfico); as 10 últimas entregas com o resultado da revisão. Horários em Brasília.

## 3. Grupo do Telegram sem computador

1. **Criar o robô:** no Telegram, procure **@BotFather** → envie `/newbot` → dê um nome (ex.: Robô de Planilhas)
   → dê um usuário terminado em `bot` (ex.: `robo_planilhas_gustavo_bot`). Ele responde com o **token** (uma linha
   comprida com dois-pontos). Toque e segure a mensagem → **Copiar**. Não mande o token para ninguém.
2. **Deixar o robô ler o grupo:** ainda no @BotFather, envie `/setprivacy` → escolha o seu robô → **Disable**.
3. **Criar o grupo:** Telegram → Novo grupo → adicione o seu robô (procure pelo usuário dele) → dê um nome.
4. **Inventar um código secreto** de 8 caracteres ou mais (ex.: `laranja-azul-2026`). Ele prova para o robô que
   quem está no grupo é você.
5. **Guardar os dois segredos no GitHub** (no navegador do celular; se não aparecer "Settings", toque nos três
   pontinhos do navegador → **Versão para computador**):
   github.com/gucostat2468/Robo-data → **Settings** → **Secrets and variables** → **Actions** →
   **New repository secret**:
   - Nome `ROBO_TELEGRAM_TOKEN`, valor: o token do passo 1;
   - Nome `ROBO_TELEGRAM_CODIGO`, valor: o código do passo 4.
6. **Vincular:** no grupo, escreva `/vincular laranja-azul-2026` (o seu código). Os segredos passam a valer no
   próximo turno (até uns 40 minutos). O robô responde "Grupo vinculado" e passa a obedecer só a você. **Apague a
   mensagem com o código** depois.
7. **Conhecer a equipe:** escreva `/apresentar`. Chegam os cartões de cada funcionário (foto com iniciais, nome,
   cargo, área e andar), em álbuns de 10.
8. **Conversar:** pergunte qualquer coisa ("como está a fábrica?", "quem trabalhou hoje?"). A resposta vem
   assinada por quem respondeu. De tempos em tempos chega um resumo do período.

Segurança: o código nunca é gravado (o registro guarda `/vincular ****`); vínculo no privado do robô não vale;
quem não é você é registrado e ignorado; o token fica só nos segredos do GitHub.
