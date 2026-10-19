# Apache Airflow no Robô de Planilhas

## Resumo

O robô já agenda as próprias rotinas sozinho. O Airflow é **opcional**. Ele serve para você ver cada rotina como uma
"DAG" na tela do Airflow, com histórico, retentativas e tempo limite. Também é bom para treinar a ferramenta que o
mercado de engenharia de dados usa.

A equipe de Orquestração do 5º andar é quem cuida disso:

| Pessoa | Cargo | O que faz de verdade (código) |
|---|---|---|
| Henrique | Especialista em Orquestração (Apache Airflow) | Confere o desenho dos fluxos e a DAG gerada (`ti.chk_fluxos`), na ronda de TI |
| Bianca | Engenheira de Dados Pleno — Airflow e SLA | Mede o SLA de cada rotina pelos registros (`orquestracao.analisar_sla`), na ronda de TI |
| Davi | Estagiário (observação) | Relata as rotinas que ainda não deixaram registro |

Todo o 5º andar treina a competência **"SLA das rotinas"**, nos níveis 1 a 5, com casos preparados pelo Augusto (Sala de Casos).

## Regras de SLA (as mesmas no robô, no treino e aqui)

- **Atrasada**: a rotina não é verificada há mais de 1,5 vez o intervalo dela. Nos primeiros 20 minutos depois de abrir
  o notebook isso não conta, porque o robô ainda está colocando tudo em dia.
- **Com erro**: a **última** execução terminou em erro. Um erro antigo, já seguido de sucesso, não conta como erro atual.
  Ele só aparece na contagem de falhas das últimas 24 h.
- **Lenta**: a última execução levou mais de 3 vezes a mediana das 20 anteriores **e** mais de 60 segundos acima dela.
  Só é avaliada quando há pelo menos 5 execuções anteriores.

## Fluxos (um lugar só: `robo/orquestracao.py`)

| DAG | Quando | Tarefas |
|---|---|---|
| robo_horario | de hora em hora | estrategia → backup → memoria_pg → pdca → licoes → estudo → auditoria → reuniao |
| robo_treino | a cada 5 min | treino |
| robo_laboratorio | a cada 10 min | laboratorio |
| robo_ronda_ti | a cada 30 min | ronda_ti |

O **canal** continua no robô, a cada minuto: o Airflow não foi feito para agendar tarefas de minuto em minuto.

Cada tarefa roda `python -m robo rotina <nome>`, que devolve um código de saída:

- **0**: a rotina fez o trabalho ou estava em dia.
- **1**: deu erro. O Airflow tenta de novo 2 vezes, com 5 minutos de espera entre as tentativas.
- **99**: a rotina já estava rodando no robô. O Airflow marca a tarefa como **pulada**.

Uma trava de arquivo do sistema operacional garante que o robô e o Airflow **nunca** rodem a mesma rotina ao mesmo tempo.
Se um dos programas morrer, o próprio sistema solta a trava.

## Passo a passo no Windows (WSL2)

O Airflow não roda direto no Windows. Ele precisa do WSL2, que é um Linux oficial da Microsoft dentro do Windows.
Nada vai para a nuvem.

1. Clique no **Menu Iniciar**, digite `PowerShell`, clique com o botão direito em **Windows PowerShell** e escolha
   **Executar como administrador**.
2. Digite `wsl --install -d Ubuntu-24.04` e aperte Enter. Reinicie o computador quando ele pedir.
3. Depois de reiniciar, a janela do Ubuntu abre sozinha. Crie um usuário e uma senha para o Linux.
   Eles são diferentes da senha do Windows.
4. Na janela do Ubuntu, digite um comando por vez:
   ```bash
   sudo apt update && sudo apt install -y python3-venv
   python3 -m venv ~/airflow-venv
   source ~/airflow-venv/bin/activate
   pip install "apache-airflow==3.1.8" --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.1.8/constraints-3.12.txt"
   ```
   Use o `constraints-3.12.txt` se o `python3 --version` mostrar 3.12, ou o `3.13` se mostrar 3.13.
5. No **Prompt de Comando do Windows**, aberto na pasta do projeto, gere a DAG:
   `python -m robo airflow-dag`

   Ele mostra as 4 DAGs e grava `airflow\dags\robo_empresa.py`, já com os caminhos convertidos para o WSL
   (`C:\...` vira `/mnt/c/...`).
6. No Ubuntu, copie a DAG para a pasta do Airflow. Troque `SEU_USUARIO` e o caminho pelo seu:
   ```bash
   mkdir -p ~/airflow/dags
   cp /mnt/c/Users/SEU_USUARIO/Robo-data/airflow/dags/robo_empresa.py ~/airflow/dags/
   airflow standalone
   ```
7. Abra `http://localhost:8080` no navegador do Windows. O usuário e a senha aparecem na janela do Ubuntu, na linha
   `Login with username`.
8. **Escolha quem agenda.** Senão os dois vão disputar, e a trava vai fazer o Airflow pular várias tarefas:
   - **Só o robô** (padrão): deixe as DAGs pausadas no Airflow e use a tela só para estudar.
   - **Airflow no comando**: no `config.yaml`, coloque
     ```yaml
     rotinas:
       agendador: airflow
     ```
     Depois feche e abra o robô. A Bianca passa a avisar na ronda de TI se o Airflow parar, porque as rotinas vão
     ficar atrasadas.

## Como validar que deu certo

- **Lista de DAGs:** `airflow dags list` mostra robo_horario, robo_treino, robo_laboratorio e robo_ronda_ti.
- **Erros de importação:** `airflow dags list-import-errors` tem que vir vazio.
- **Teste de verdade:** `airflow dags test robo_ronda_ti`. Ele roda a rotina real e mostra `ronda_ti: fez —` no log.
- **Fluxos atualizados:** depois de qualquer mudança nas rotinas, o Henrique avisa na ronda de TI que a DAG está
  desatualizada. Para resolver, gere de novo (passo 5) e copie de novo (passo 6).

## Erros comuns

- **Rodar o Airflow e o robô agendando ao mesmo tempo.** Nada roda em dobro, mas as tarefas aparecem como puladas.
  Escolha um dos dois (passo 8).
- **Editar a DAG à mão.** A próxima geração apaga a edição, e o Henrique aponta que a DAG foi editada.
  Mude os fluxos em `robo/orquestracao.py`.
- **Senha do banco "sumindo" no WSL.** O robô lê a senha gravada pelo `setx` direto no registro do Windows,
  então funciona mesmo quando é chamado pelo Airflow.
