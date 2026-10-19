# Empresa na nuvem, grátis, configurada só pelo celular

## Como funciona

| Peça | Onde | Custo |
|---|---|---|
| A empresa trabalhando (90 funcionários, todas as rotinas) | GitHub Actions: um turno de 20 min por hora (pedido toda hora) | Grátis (repositório público) |
| O banco com toda a memória | PostgreSQL gratuito do Neon | Grátis (0,5 a 1 GB) |
| Você acompanhando | O app de banco do seu celular, ligado direto no Neon | Grátis |

**Nada se perde, por estes motivos:**

- **Salvamento a cada 10 minutos.** Durante o turno, e de novo no fim, o robô salva nesta ordem: o registro total, uma cópia
  inteira do SQLite conferida por SHA-256 e a cópia das tabelas no schema `robo`. Só sobem as linhas novas, e nenhuma
  linha é apagada.
- **Máquina nova a cada turno, mesma memória.** Cada turno começa numa máquina zerada. Ela baixa a última cópia do banco
  e reconstrói os arquivos byte a byte, inclusive o canal, o estado da TI e a âncora de integridade. Por isso o trabalho
  continua exatamente de onde parou.
- **Se a máquina do GitHub cair no meio do turno:** perde-se no máximo o trabalho desde o último salvamento (até 10 minutos de
  treino sintético). Esse trabalho é refeito no turno seguinte, e nada do que já foi salvo some.

## Passo a passo (dá para fazer tudo pelo celular)

### 1. Criar o banco gratuito (Neon)

1. No navegador do celular, abra **neon.tech** e toque em **Sign up**.
2. Escolha **Continue with GitHub** e entre com a sua conta gucostat2468.
3. Em **Create project**, preencha:
   - **Name:** `robo-planilhas`;
   - **Postgres version:** a mais nova;
   - **Region:** **AWS São Paulo (sa-east-1)**, se aparecer; senão, a mais próxima.
4. Toque em **Create**. Aparece a tela **Connection details**.
5. Desligue a opção **Connection pooling** e copie a linha **Connection string**. Ela tem este formato:
   `postgresql://neondb_owner:SENHA@ep-xxxx.sa-east-1.aws.neon.tech/neondb?sslmode=require`
   Essa linha é a chave do banco: **não mande para ninguém, nem para mim**.

### 2. Guardar as chaves no GitHub (Secrets)

1. Abra **github.com/gucostat2468/Robo-data** no navegador do celular. Se o site abrir no modo celular, toque nos três
   pontinhos e escolha **Desktop site**.
2. Toque em **Settings**, depois em **Secrets and variables**, depois em **Actions**, depois em **New repository secret**.
3. Crie o primeiro segredo:
   - **Name:** `ROBO_PG_URL`;
   - **Secret:** cole a Connection string do passo 1;
   - toque em **Add secret**.
4. Crie o segundo segredo do mesmo jeito:
   - **Name:** `ROBO_PG_SENHA_LEITURA`;
   - **Secret:** uma senha que **você inventa** (mínimo de 12 caracteres, com letras e números);
   - anote essa senha: é a que vai no app do celular.

### 3. Ligar a empresa

1. No repositório, toque em **Actions**.
2. Toque em **Empresa na nuvem (turnos)**, depois em **Run workflow**, e confirme em **Run workflow**.
3. Em uns 25 minutos o turno termina com o ✔ verde. A partir daí, a empresa trabalha sozinha: um turno pedido toda hora.

### 4. Ligar o app do celular (o da tela "New Connecion")

| Campo | O que colocar |
|---|---|
| Name | Robô de Planilhas |
| Hostname | a parte depois do `@` e antes da `/` na Connection string (ex.: `ep-xxxx.sa-east-1.aws.neon.tech`) |
| Port | 5432 |
| Database | `neondb` |
| User | `robo_leitura` |
| Password | a senha que você inventou no passo 2 |
| SSL | ligado (require) |

Toque em **TEST**. As tabelas ficam no schema `robo` e todas começam com `memoria_`:
`memoria_treino_tentativas`, `memoria_interacoes` (conversas), `memoria_mentorias`, `memoria_rh_movimentos`,
`memoria_licoes`, `memoria_logs_sistema`, `memoria_canal_mensagens` e as demais.

## Limites (com franqueza)

- **Não é 24 h contínuas:** o turno é pedido toda hora, mas o agendador gratuito do GitHub pula horários em momentos
  de carga (em 19/10, de 3 horários pedidos, só 1 rodou). Na prática, entre 8 e 24 turnos de 20 minutos por dia. Rodar sem parar no
  GitHub iria contra as regras de uso do Actions.
- **Espaço:** o plano gratuito do Neon dá 0,5 a 1 GB.
  - No ritmo dos turnos, o banco cresce alguns MB por dia.
  - Com 80% do limite usado, a DBA avisa no canal e o GitHub mostra um aviso amarelo.
  - Nada é apagado sem a sua decisão.
- **O GitHub pausa agendamentos** de repositórios públicos depois de 60 dias sem nenhuma atividade. Qualquer commit ou
  execução manual reativa.
- **Mudar de plano gratuito para pago** é decisão sua. Nada aqui cobra sozinho.
