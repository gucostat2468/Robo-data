# Boas práticas da operação — tudo registrado, nada perdido

Este guia diz **o que fazer, quando e por quê** em cada parte da empresa. Cada regra aqui já está no código. Onde a regra
depende de você, ela aparece como **(você)**.

---

## 1. Os 10 princípios (valem para tudo)

| # | Princípio | Como o robô garante |
|---|---|---|
| 1 | **Nada se apaga** | O banco recusa `DELETE` em toda tabela de registro, inclusive nas futuras. Planilhas originais e relatórios são guardados para sempre. |
| 2 | **Todo número tem origem** | Cada resposta mostra a evidência (arquivo, linha, consulta). Cálculo aplicável é conferido no PostgreSQL por outro caminho. |
| 3 | **Ninguém aprova o próprio trabalho** | Revisor independente na central, revisora de casos na Sala de Casos e você nas regras, repactuações e promoções. |
| 4 | **Situação é apurada, não declarada** | "Cumprida", "aplicada" e "verificado" só com prova nos registros (tarefa revisada, acerto depois da lição, erro que não voltou). |
| 5 | **Erro vira aprendizado registrado** | Erro → experiência da pessoa → lição no caderno → handover da área a partir de 3 repetições → PDCA → boa prática. |
| 6 | **Decisão tem dono, prazo e critério** | Sem os três, a decisão não é registrada. A próxima reunião cobra. |
| 7 | **Backup conferido** | O backup diário passa pelo `integrity_check` e ganha SHA-256. O primeiro de cada mês fica para sempre. |
| 8 | **Segredo não vai para arquivo** | Senhas ficam só em variáveis de ambiente. O `config.yaml` guarda apenas o nome da variável. |
| 9 | **Treino não toca a produção** | Casos rodam em pastas de teste. O histórico, as Bases-Tratadas e o banco de negócio ficam intactos. |
| 10 | **Versão do código em cada resultado** | Toda tentativa de treino grava a impressão digital do código: dá para saber o que mudou quando um número muda. |

---

## 2. Sua rotina como dono

### Todo dia (5 minutos)
1. Abra o painel e veja a **Visão geral**: a luz deve estar verde ("Monitorando").
2. Abra **Reprovados**: cada planilha barrada traz o motivo. Corrija na origem e reenvie.
3. Abra **Conhecimento → Aprendizado**: aprove ou recuse as regras propostas. Recusar exige motivo, e o motivo também vira aprendizado.
4. Abra **Solicitações**: veja as aprovações pendentes. Nenhuma deve esperar mais de 48 h.

### Toda semana (30 minutos)
1. Abra a reunião do andar com mais pendências (**Sala de reunião**). Ela começa cobrando as decisões atrasadas.
2. Trate cada atrasada: **novo prazo com motivo** ou **cancelamento com motivo**. Sem isso a reunião não encerra.
3. Abra **Treino contínuo** e olhe:
   - **Erros que mais se repetem**: a partir de 3 repetições, eles viram handover para a área. Confira se a TI pegou.
   - **Mudanças de nível**: quem caiu de nível aparece também na reunião do andar.
4. Abra **Gestão do projeto → Evolução por funcionário**.

### Todo mês (1 hora)
1. Abra **Banco da empresa** e confira:
   - integridade "ok";
   - cadeia "íntegra";
   - último backup de hoje ou de ontem;
   - "No PostgreSQL" igual a "Linhas" (✅).
2. **Teste de restauração (você)** — veja a seção 7. Backup que nunca foi restaurado não é backup.
3. Revise `logs/backups_sqlite/`: o primeiro de cada mês está lá. Se puder, copie esse arquivo para um HD externo ou pen drive guardado em outro lugar.

---

## 3. Entrada de dados (planilhas)

| Faça | Por quê |
|---|---|
| Uma regra por tipo de arquivo (`regras:` no `config.yaml`) com colunas obrigatórias, chave única e faixas | O robô barra o que está errado em vez de publicar errado |
| Declare `escala_csat` em toda pesquisa de CSAT | Sem isso a escala é deduzida (e o robô avisa que deduziu) |
| Use `valores_permitidos` para listas fechadas (UF, curso, canal) | "Sp." vira proposta de correção, não um valor novo silencioso |
| Nomeie arquivos com o padrão da regra (`nps_2026_10.xlsx`) | A regra certa é aplicada sozinha |
| Mantenha `dias_retencao_originais: 0` | A planilha original é a prova e a base para ML |

**Nunca:**
- edite à mão um arquivo em Bases-Tratadas (a fonte é a planilha original + regra);
- coloque senha no `config.yaml`.

---

## 4. Treino contínuo (todos os funcionários, todos os andares)

- **Como funciona.** A cada 2 minutos, os 6 funcionários há mais tempo sem treinar recebem um caso da competência que estão há mais tempo sem praticar, **no nível deles**. Em uma hora, todos treinam.
- **Níveis.**
  - Começam pelo cargo: estagiário e júnior no 1; pleno e sênior no 2; especialista, coordenador, gerente e diretor no 3; head no 4.
  - Com 4 acertos em 5 tentativas, a pessoa sobe de nível; com 2 ou menos, desce.
  - Toda mudança fica registrada com as 5 tentativas que a provaram.
- **O que é sintético e o que é real.**
  - Os **dados** dos casos são sintéticos.
  - A **ferramenta** usada, a **correção**, os **níveis**, as **lições** e os **registros** são reais.
  - O que muda o comportamento do robô é o código corrigido (handover → TI), as regras que você aprova e o caderno de lições.
- **Sala de Casos** (4º andar, responde a você):
  - Designers só geram casos da competência em que passaram no exame dos 5 níveis.
  - A revisora confere **cada** caso por outro caminho antes de ele chegar a alguém.
  - Caso reprovado conta contra o designer: 2 reprovações em 10 suspendem a certificação até um novo exame.
- **Quando o treino acha uma lacuna real**, ela vira handover para a área dona da ferramenta. Exemplos já encontrados e corrigidos:
  - LGPD não reconhecia telefone com "+55";
  - CPF falso (dígito verificador inválido) era tratado como CPF;
  - e-mail escondido em texto livre passava;
  - colunas `dias_*` e `anos_*` eram ignoradas na ciência de dados;
  - o NPS sumia quando havia código 99.
- **(você)** Ao mudar um gerador de casos, a versão dele sobe. Os designers refazem o exame automaticamente e os casos da versão antiga saem de uso.

---

## 5. Reuniões e decisões

1. **Pauta antes.** Use o painel "Pauta, notas e decisões".
2. **Decisão = dono + prazo + critério de pronto.**
   - Ruim: "melhorar as datas".
   - Bom: "Padronizar a coluna de data da base de vendas — Lia — 25/10 — pronto quando duas cargas seguidas passarem sem aviso de data em texto".
3. **A reunião abre cobrando.** As decisões abertas do andar aparecem com a situação apurada pelos registros.
4. **Atrasada se trata na hora:**
   - novo prazo com motivo, ou
   - cancelamento com motivo.

   Repactuar e cancelar são decisões **suas**.
5. **A ata é imutável.** O arquivo `.md` tem o SHA-256 gravado no banco: qualquer mudança posterior é detectável.
6. **O plano de ação da reunião semanal** vira decisão ligada ao handover. Ela é cumprida quando o PDCA prova que o erro não voltou.

---

## 6. Conhecimento e aprendizado

- **Regra aprendida.**
  - Só você aprova.
  - A prova é o arquivo que tinha reprovado passar depois.
  - A regra que não resolveu se desativa sozinha.
- **Correção no chat** ("na verdade a coluna X é Y"):
  - vale na hora naquela conversa;
  - para valer para todos, você aprova em Conhecimento.
- **Lição "aplicada" só com prova.**
  - Erro de treino: a pessoa acerta depois, no mesmo nível ou acima.
  - Handover: o PDCA verifica.
  - Manual: a lição foi usada numa resposta real.
- **Cadeia de integridade.** Todo registro de conhecimento tem SHA-256 encadeado, com âncora em arquivo. "QUEBRADA" na tela = investigar na hora.

---

## 7. Banco de dados, backup e restauração

| O quê | Onde | Frequência |
|---|---|---|
| Memória da empresa (fonte) | `logs/trabalho.db` (SQLite, modo WAL, `synchronous=FULL`) | contínuo |
| Backup conferido | `logs/backups_sqlite/trabalho_AAAAMMDD_HHMMSS.db.gz` + `.manifesto.json` | 1x por dia; o 1º do mês fica para sempre |
| Espelho completo | PostgreSQL `robo_dados`, schema `robo`, tabelas `memoria_*` | 1x por hora |
| Backup do PostgreSQL | `logs/backups/<data>/robo_dados.dump` (`pg_dump`) | 1x por dia; o 1º do mês fica para sempre |

### Instalar o banco real (uma vez, no seu PC)
1. Instale o PostgreSQL 16 ou superior (postgresql.org → Download → Windows) e anote a senha do usuário `postgres`.
2. Na pasta do robô: `python -m robo instalar-banco` e digite essa senha.
3. O comando:
   - cria os usuários `robo_app` (grava) e `robo_leitura` (só lê);
   - cria o banco `robo_dados` e os schemas;
   - grava as senhas em `ROBO_PG_SENHA` e `ROBO_PG_SENHA_LEITURA` (variáveis do seu usuário do Windows);
   - prova que o usuário de leitura não escreve;
   - copia toda a memória.
4. **Guarde as duas senhas num gerenciador de senhas.** Elas aparecem só uma vez.
5. Feche e abra o robô (para ele ler as variáveis novas).

### Teste de restauração do SQLite (mensal, 10 minutos)
1. Feche o robô.
2. Copie `logs/trabalho.db` para `logs/trabalho_ANTES_DO_TESTE.db`.
3. Abra o `.db.gz` mais recente de `logs/backups_sqlite/` com o 7-Zip e extraia o arquivo.
4. Compare o tamanho e o SHA-256 com o `.manifesto.json` ao lado (PowerShell: `Get-FileHash arquivo.db`).
5. Abra o robô com o arquivo restaurado no lugar do original. **Banco da empresa** deve mostrar integridade "ok" e as mesmas contagens do manifesto.
6. Volte o arquivo original (`trabalho_ANTES_DO_TESTE.db` → `trabalho.db`).

**Nunca:**
- apague arquivos de `logs/` à mão;
- rode `DELETE` ou `DROP` no PostgreSQL;
- dê ao Power BI o usuário `robo_app` (use sempre `robo_leitura`).

---

## 8. Machine Learning (quando chegar a hora)

- **A base principal é `treino_tentativas`.**
  - Rótulo: acertou ou errou.
  - Atributos: competência, nível, cargo, andar, tempo e versão do código.
  - Some a ela `experiencias`, `handover_eventos`, `decisoes_eventos`, `uso_ferramentas` e `erros_sistema`.
- **Use o PostgreSQL** (schema `robo`) com o usuário `robo_leitura`. Nunca leia o `trabalho.db` com o robô aberto escrevendo nele (use um backup restaurado, se precisar do arquivo).
- **Separe por tempo**: treine com o passado e teste com o futuro. Por isso cada linha tem data.
- **Separe por versão do código**: resultado de versão diferente não é comparável sem esse cuidado.
- **Caso sintético é reproduzível**: semente + versão do gerador recriam exatamente o mesmo caso (e o SHA-256 do conteúdo confirma).

---

## 9. Segurança

- O painel tem senha. Ele só responde nesta máquina (`127.0.0.1`).
- A ronda de TI roda a cada 30 minutos e alerta:
  - painel sem senha;
  - senha no `config.yaml`;
  - código novo sem aviso;
  - erros no log.
- O usuário do PostgreSQL usado no dia a dia (`robo_app`) não é administrador. O usuário do Power BI (`robo_leitura`) só lê.
- **(você)** Mantenha o Windows e o PostgreSQL atualizados e use BitLocker no disco, se puder: os dados ficam cifrados se o notebook for perdido.

---

## 10. Sinais de alerta (o que fazer)

| Sinal | Onde aparece | O que fazer |
|---|---|---|
| Integridade ≠ ok | Banco da empresa | Feche o robô, restaure o último backup (seção 7) e abra um handover para a TI |
| Cadeia QUEBRADA | Conhecimento / Banco da empresa | Alguém mexeu no arquivo: compare com o PostgreSQL (cópia imutável) |
| Backup com mais de 2 dias | Banco da empresa | Veja Atividade e TI: o robô ficou desligado ou o disco encheu |
| "No PostgreSQL" diferente de "Linhas" por mais de 2 h | Banco da empresa | PostgreSQL fora do ar ou senha trocada: rode `python -m robo banco testar` |
| Mesmo erro de treino 3x | Treino contínuo / handovers | É defeito de código, não da pessoa: a TI corrige e o treino comprova |
| Decisão repactuada 2x ou mais | Pendências do andar | Quebre a decisão em entregas menores ou troque o dono |

## Acesso pelo celular (regras que não se negociam)

| Regra | Por quê |
|---|---|
| Pelo celular é **só leitura** (página de acompanhamento e usuário `robo_leitura` no banco) | Ninguém altera, aprova ou apaga nada fora do notebook, nem com a senha vazada |
| Só **rede privada** (Wi-Fi de casa ou VPN Tailscale) | O servidor do celular recusa qualquer endereço de internet (403); o pg_hba.conf só aceita a sub-rede da casa |
| **Nunca** abrir porta no roteador (redirecionamento de porta) | Expõe o notebook à internet inteira; para fora de casa existe a VPN |
| Painel **com senha** antes de ligar o celular | Sem senha o celular não liga, e a ronda de segurança da TI acusa CRÍTICO |
| Firewall do Windows: marcar só **"Redes privadas"** | Em Wi-Fi público (café, aeroporto) a porta fica fechada |
| 5 senhas erradas = aparelho bloqueado 15 min; toda entrada registrada (`acessos_celular`) | Força bruta não passa e tudo fica auditável |
| Senha do banco só em variável de ambiente (`%ROBO_PG_SENHA_LEITURA%`) | Nunca em arquivo, print ou mensagem |
| Celular perdido ou trocado | Troque a senha do painel (derruba todas as sessões) e rode de novo `python -m robo instalar-banco` (senhas novas do banco) |
