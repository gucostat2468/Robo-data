# Robô de Planilhas — ETL/ELT local com agentes, painel e escritório 3D

Você solta uma planilha em **Bases-Limpeza** (no OneDrive) e uma equipe de **agentes** limpa, valida e modela os dados. Se tudo estiver **100% sem erros**, a planilha pronta para o Power BI aparece em **Bases-Tratadas** e, se você quiser, também no **PostgreSQL**. Se houver qualquer erro, nada é publicado: o arquivo vai para **Bases-Erros** com um relatório dizendo o que corrigir e em qual linha.

**Tudo roda no seu computador.** Não há servidor, nuvem, EC2 nem serviço externo. O painel é um site local (`127.0.0.1`), acessível só pela sua máquina, e o PostgreSQL (opcional) também é instalado no seu Windows. O OneDrive só sincroniza as pastas, como já faz hoje.

```
OneDrive/
├── Bases-Limpeza      ← você solta a planilha aqui (ou arrasta para o painel)
├── Bases-Tratadas     ← sai a planilha tratada, pronta para o Power BI
├── Bases-Erros        ← reprovadas + relatório _ERROS.txt               (criada sozinha)
├── Bases-Originais    ← backup do original, organizado por mês           (criada sozinha)
└── Bases-Relatorios   ← qualidade, dicionário de dados e resumo de erros (criada sozinha)
```

---

## 1. Instalação (uma vez)

Você já tem o projeto em `C:\Robo-data`. Para atualizar e instalar:

1. Abra o **PowerShell** (tecla Windows → digite `PowerShell` → Enter).
2. Cole e aperte Enter:
   ```powershell
   cd C:\Robo-data
   git pull
   .\instalar.bat
   ```
3. O instalador:
   - escolhe uma versão compatível do Python (3.11 a 3.14) e, se precisar, instala a 3.13 **ao lado** da sua, sem remover nada;
   - instala as bibliotecas;
   - encontra suas pastas do OneDrive;
   - cria o atalho **Robô de Planilhas** na Área de Trabalho e no Menu Iniciar;
   - pergunta se o robô deve **ligar junto com o Windows** (recomendado: S).

**Como validar:** no final, as linhas de Bases-Limpeza e Bases-Tratadas aparecem com `OK`.

> Se ele não achar a pasta Bases-Limpeza, o próprio painel abre uma tela pedindo o caminho. Clique com o botão direito na pasta → **Copiar como caminho** → cole.

### Ver tudo funcionando antes (modo demonstração)

Dê dois cliques em **`Demonstracao.bat`** (ou rode `python -m robo demo`).

- **Empresa separada.** É criada a pasta `demonstracao/` com a própria pasta de entrada, os próprios logs e o próprio config. A sua produção não é tocada.
- **Planilhas de teste.** Entram planilhas sujas de 6 áreas, mais uma com `#REF!`/`#DIV/0!` que o robô precisa barrar.
- **Senha.** Na primeira vez, a demonstração pede uma senha para o painel.
- **Recomeçar.** Para começar do zero: `Demonstracao.bat --recomecar`.

## 2. Uso no dia a dia

Dois cliques no atalho **Robô de Planilhas**. Abre uma janela com o painel e o robô começa a trabalhar.

| Tela | Para que serve |
|---|---|
| **Visão geral** | Status do robô, números do dia, fila e últimos processamentos. Arraste planilhas para a janela para enviar ou só testar. |
| **Escritório 3D** | A equipe de agentes trabalhando ao vivo: o documento anda de mesa em mesa conforme as etapas reais. Clique num agente para ver o que ele faz. |
| **Agentes e habilidades** | Crie agentes e dê a cada um as habilidades (habilidades) da tarefa dele. |
| **Reprovados** | O que corrigir, em qual linha, com os botões *Abrir planilha* → *Já corrigi — reprocessar*. |
| **Histórico** | Todos os processamentos, com filtro, busca e detalhe completo. |
| **Testar planilha** | Mostra o que o robô faria com um arquivo **sem gravar nada**: veredito, erros e prévia dos dados. |
| **Banco de dados** | Camadas do PostgreSQL e últimas cargas. |
| **Consultas SQL** | 29 perguntas de negócio prontas (NPS, CSAT, churn, vendas…) para executar ou copiar para o Power BI. |
| **Atividade** | Log ao vivo. |
| **Configurações** | Inicialização com o Windows, notificações, pastas, formato de saída e banco. |

**Fechar a janela não desliga o robô.** Ele continua em segundo plano e avisa por notificação do Windows quando uma planilha é aprovada ou reprovada. Para desligar de vez: Configurações → **Encerrar aplicativo**.

## 3. A equipe de agentes

Cada agente é uma etapa **real** do processamento:

| Agente | Etapa | Aceita habilidades? |
|---|---|---|
| Rita — Recepção | Espera o OneDrive terminar de sincronizar e o Excel fechar o arquivo | — |
| Leo — Leitura | Lê xlsx/xls/csv, acha o cabeçalho, detecta `#REF!`, `#N/D`… | — |
| Lia — Limpeza | Padroniza colunas, textos, números (R$ 1.234,56), datas, remove Total e duplicadas | ✅ |
| *seus agentes* | Entram depois da Limpeza, depois da Auditoria ou antes da Modelagem | ✅ |
| Otto — Auditoria | Valida as regras; qualquer erro reprova o arquivo inteiro | ✅ |
| Ana — Modelagem | Modelo estrela (fato e dimensões) e calendário para o Power BI | ✅ |
| Beto — Banco | Carrega no PostgreSQL (bruto → tratado → analítico) | — |
| Duda — Publicação | Grava em Bases-Tratadas e arquiva o original | — |

### O prédio: 5 andares, do gerente ao estagiário

Além da linha de produção acima, cada andar tem gerente, coordenador(a), sêniores/especialistas, plenos, juniores e
estagiários — **cada cargo com uma conferência real**, executada em todo arquivo, e com prova técnica no RH
(um caso correto que ele precisa aprovar e um erro plantado que ele precisa pegar). Veja tudo em **Equipe e contratações**.

| Andar | O que faz | Quem pode barrar |
|---|---|---|
| 1º Engenharia de dados | Limpa, valida, modela, carrega no PostgreSQL e publica; plenos e juniores conferem tipos, espaços, origem e relêem o arquivo gravado | Coordenadora, supervisor, DBA, plenos e juniores (o arquivo vai para Bases-Erros) |
| 2º Análise e qualidade | Perfil, NPS/CSAT/CES com margem, testes estatísticos, monitoramento; pleno recalcula o NPS por conta própria | Ninguém barra (o dado já foi publicado): achados viram ressalvas |
| 3º Sala Excel | Entrega Excel com fórmulas vivas e aba Conferência; coordenadora confere integridade, pleno confere fórmulas, júnior confere formatos | Ressalva registrada na entrega |
| 4º Diretoria e canal | Boletim diário, sprints de 15 dias, ideias, RH, LGPD (dados pessoais) e catálogo de dados | — |
| 5º TI e segurança | Ronda a cada 30 min: dependências, disco e permissões, erros no log, segurança do painel, senha fora do arquivo, código novo vigiado, prontidão para nuvem (consultiva) | — (alerta no canal #ti) |

Escopo por senioridade: **gerente** responde por metas e prazos e não executa tarefa operacional; **coordenador**
libera ou barra a produção; **sênior/especialista** executa o crítico e revisa; **pleno** faz a segunda conferência
independente; **júnior** checa critérios objetivos; **estagiário** trabalha em **observação** (nunca altera nem barra).

### Contratações (manual e automática)
- **Você contrata** em **Equipe e contratações → Contratar**: nível, andar (de 1 a 9 — um andar novo aparece no prédio
  sozinho), cargo, área, mentor, habilidades e o **manual de procedimentos em Markdown (.md)**.
- **A liderança contrata sozinha, só estagiários**: quando uma coluna publicada mostra uma necessidade comprovada
  (e-mail, telefone, CPF/CNPJ ou CEP fora do padrão), a coordenadora do andar testa a habilidade numa cópia e,
  havendo trabalho de verdade, contrata um estagiário em observação. Datas e números nunca são confundidos com contato,
  e se mais da metade dos valores seria "inválida" a contratação não acontece (seria a coluna errada).
- **Experiência de 3 meses**: no fim, o líder recomenda efetivar como Júnior (você decide) ou desliga quem não teve
  trabalho/falhou. Como estagiário nunca altera dados, desligar não deixa rastro. Ajustes em `config.yaml`:
  `contratacao_automatica: {habilitada: true, maximo: 12, observacoes_minimas: 5, dias_experiencia: 90}`.

### Canal da equipe (sem internet, sem API)
**Canal da equipe** no painel: canais por área (#geral, #engenharia, #analise, #excel, #lideranca, #banco, #rh, #ideias, #ti),
filtros por pessoa, tipo, período e busca, e uma caixa de texto. Quem responde é um roteador de intenções em Python:
status do dia, erros, sprint, ideias, banco, equipe, cálculo de amostra/margem de erro (exato) e dúvidas de Excel,
Power BI/DAX, pesquisa e trade marketing. Chame alguém pelo nome ("Ricardo, como faço…"). Ele também procura nos
manuais `agentes/<id>.md` e nos arquivos `.md` da pasta `conhecimento/` (coloque lá o glossário e as regras da empresa).
Quando não tem certeza, diz que não entendeu — não inventa. A cada 15 dias cada pessoa publica a sprint:
feito, bom, travou e backlog.

### Criar um agente (pelo painel)
1. **Equipe e contratações** → **Contratar**.
2. Dê nome, função, cor, **quando trabalha** e **para quais arquivos** (`*` = todos; `nps_*` = só os que começam com nps_).
3. **Adicionar habilidade** → escolha no catálogo → preencha os campos marcados com `*`.
4. Abra **Conhecimento: quando usar e cuidados** em cada habilidade: é um guia de boas práticas.
5. **Salvar agente.** Já vale para a próxima planilha e ele ganha uma mesa no escritório 3D.

> Teste sempre em **Testar planilha** antes: você vê exatamente o que cada habilidade fez.

### Catálogo de habilidades (26 nativas)
- **Padronização:** padronizar textos, de-para de valores, converter tipo, arredondar.
- **Documentos e contato:** CPF/CNPJ (com dígito verificador), e-mail, telefone, CEP.
- **Qualidade e validação:** formato (regex), datas, duplicidade por chave, completude mínima, outliers (IQR / z-score), filtrar linhas.
- **Enriquecimento:** preencher vazios, coluna calculada, faixas (idade, valor…), partes da data, dividir e juntar colunas.
- **Pesquisa e Customer Insights:** classificar NPS (promotor/neutro/detrator), CSAT top-2-box, codificar verbatins por tema.
- **Estrutura:** selecionar e renomear colunas.
- **Privacidade (LGPD):** anonimizar (hash com chave secreta, mascarar ou remover).

### Habilidades em Python (para regras muito específicas)
Copie `habilidades_personalizadas/_exemplo_habilidade.py` com outro nome (sem `_` no início), ajuste e salve: ela aparece no catálogo. Se tiver erro, o painel mostra a mensagem e o robô continua funcionando.

Os agentes ficam em `agentes/*.yaml` (legíveis, dá para editar à mão e versionar). Há um exemplo desligado: `agentes/tina_contatos.yaml`.

## 4. Regras por tipo de arquivo (config.yaml)

Para validações que reprovam o arquivo (colunas obrigatórias, chave única, faixas) e para o modelo estrela, use `regras` no `config.yaml` (Configurações → **Editar config.yaml**). Há um exemplo completo comentado no arquivo:

```yaml
regras:
  - padrao: "nps_*"
    colunas_obrigatorias: [id_resposta, data_resposta, nota_nps]
    chave_unica: [id_resposta]
    tipos: {data_resposta: data, nota_nps: inteiro}
    faixas: {nota_nps: {min: 0, max: 10}}
    destino: {tabela: nps, modo: mesclar, chave: [id_resposta]}   # carga no PostgreSQL
    modelo:
      fato: fato_nps
      dimensoes:
        dim_curso: {colunas: [curso, modalidade], chave: id_curso}
      calendario: data_resposta
```

## 5. PostgreSQL (ELT) — opcional, local

### Instalar no seu Windows
1. Acesse https://www.postgresql.org/download/windows/ → **Download the installer** → versão mais recente para Windows x86-64.
2. Execute o instalador e clique em **Next** em tudo, exceto:
   - **Password:** crie uma senha e **anote** (é a do usuário `postgres`);
   - **Port:** deixe `5432`;
   - no final, desmarque o *Stack Builder*.
3. **Recomendado:** abra o Prompt de Comando na pasta do robô e rode `python -m robo instalar-banco` (digite a senha do
   `postgres`). Ele cria o banco `robo_dados`, o usuário `robo_app` (o robô grava com ele, não com o administrador) e o
   `robo_leitura` (só lê: painel e Power BI), dá as permissões, grava as senhas nas variáveis de ambiente do Windows
   (`ROBO_PG_SENHA` e `ROBO_PG_SENHA_LEITURA`), prova que o de leitura não escreve e copia a memória inteira.
   **Guarde as duas senhas que ele mostra** (num gerenciador de senhas) e reinicie o robô.
4. Alternativa manual: **Configurações → Banco de dados PostgreSQL** → servidor `127.0.0.1`, porta `5432`, banco
   `robo_dados`, usuário e senha em `ROBO_PG_SENHA` (nunca no arquivo) → **Testar conexão** → **Salvar**.

Tudo sobre o banco (cada tabela, proteção, backup, restauração e ML): `documentacao/banco_de_dados.md` e
`documentacao/boas_praticas_operacao.md`. No painel: **Banco da empresa**.

Onde isso fica gravado: seção `banco:` do `config.yaml` (`habilitado: true`, `host`, `porta`, `banco`, `usuario`).

O banco `robo_dados` é criado sozinho. Camadas:

| Camada | Conteúdo |
|---|---|
| `bruto.*` | Tudo o que chegou, exatamente como veio (texto), **inclusive reprovados**, para auditoria |
| `tratado.*` | Só arquivos aprovados: limpos, tipados e modelados |
| `analitico.*` | Suas regras de negócio em SQL (`modelos_sql/*.sql`, executados após cada carga): o "T" do ELT |
| `robo.lotes` / `robo.ocorrencias` | Controle de cada carga e de cada erro/aviso |

**Modos de carga:** `por_arquivo` (padrão: reprocessar o mesmo arquivo não duplica), `substituir`, `mesclar` (atualiza por chave) e `anexar`. Tudo de um arquivo entra numa única transação: **ou entra inteiro, ou nada entra**. Se o banco estiver desligado, o arquivo espera ("Adiado") e nada se perde.

## 6. Deixar pronto para o Power BI

O robô já entrega: tipos corretos, nomes de coluna sem acento ou espaço, sem linhas de Total nem duplicadas, colunas de auditoria (`_arquivo_origem`, `_processado_em`) e, com `modelo` na regra, **fato + dimensões + calendário**.

**Conectar**
- **Arquivo único que é substituído** (ex.: `nps.xlsx` todo mês): Obter dados → Pasta de trabalho do Excel → arquivo em Bases-Tratadas.
- **Vários arquivos que se acumulam:** Obter dados → **Pasta** → Bases-Tratadas → Combinar arquivos.
- **PostgreSQL (recomendado para histórico):** Obter dados → Banco de dados PostgreSQL → Servidor `localhost:5432`, Banco `robo_dados` → tabelas de `tratado` e visões de `analitico`.

**Modelar** (Exibição de modelo, 3º ícone à esquerda)
1. Arraste `dim_curso[id_curso]` → `fato_nps[id_curso]`: cardinalidade **1:\***, direção **Única**.
2. Arraste `dim_calendario[data]` → `fato_nps[data_resposta]`: **1:\***.
3. Botão direito em `dim_calendario` → **Marcar como tabela de datas** → coluna `data`.

**Medidas DAX essenciais** (Página Inicial → Nova medida)
```DAX
Respostas = COUNTROWS ( fato_nps )
NPS =
VAR Prom = CALCULATE ( [Respostas], fato_nps[nota_nps] >= 9 )
VAR Det  = CALCULATE ( [Respostas], fato_nps[nota_nps] <= 6 )
RETURN DIVIDE ( Prom - Det, [Respostas] ) * 100
```
Com a habilidade **Classificar NPS**, você também ganha a coluna `grupo_nps` (Promotor/Neutro/Detrator) para gráficos de barras empilhadas.

**Os painéis da própria empresa**
- **Tela Dashboards** (menu Acompanhar): 5 painéis (Visão Executiva, Treino & Evolução, Pessoas & Andares, Conversas &
  Mentorias, Operação & Rotinas). A Bárbara (especialista em Power BI, 3º andar) monta do banco real de hora em hora
  (rotina `paineis`); o Heitor (analista de BI) refaz cada total por outro caminho e só então publica. Cada versão fica
  registrada para sempre em `paineis_versoes`. Para montar agora: `python -m robo rotina paineis`.
- **Aba Planilhas** (Dashboards): a Bárbara lê cada planilha (as reais primeiro; as de treino vêm marcadas como
  inventadas) e monta um **relatório no padrão do Power BI**: clique numa barra filtra a página (filtro cruzado), painel de
  filtros à direita, modo foco, mostrar como tabela, exportar CSV, ordenar, dica de ferramenta e as cores do tema padrão.
  Sem filtro, os cartões têm que bater com os números-âncora conferidos pelo Heitor (selo verde). A outra vista mostra
  como montar no Power BI: dicionário dos cabeçalhos, regras de negócio conferidas, modelo estrela e medidas DAX.
- **Engenharia reversa do Power BI** (documentada, com fonte oficial em cada item): `documentacao/powerbi_engenharia_reversa.md`
  e `powerbi/catalogo_powerbi.json` (49 visuais nativos, 31 interações, paleta e fontes do tema padrão).
- **Kit Power BI** (`powerbi/`): modelo estrela da empresa (schema `bi` no PostgreSQL/Neon + CSV/Excel em `powerbi/dados`),
  ~50 medidas DAX comentadas (`medidas.dax`), consultas do Power Query (`power_query.m`), tema de cores e as telas de
  referência. Passo a passo clique a clique: `powerbi/GUIA_CONSTRUCAO.md`. A cada publicação dos painéis, a Bárbara
  também refaz o modelo estrela em `logs/paineis/estrela/` (Obter dados → Pasta, para atualizar sem internet).

## 7. Logs e resumo de erros

| Onde | O quê |
|---|---|
| `Bases-Erros/<arquivo>_ERROS.txt` | Relatório legível de cada reprovado: erros, linhas e o que fazer |
| `Bases-Relatorios/resumo_ocorrencias.csv` | **Todos** os erros e avisos de todas as planilhas, um por linha: abra no Excel/Power BI para ver o que mais se repete |
| `Bases-Relatorios/<arquivo>_qualidade.xlsx` | Log de qualidade + dicionário de dados de cada aprovado |
| `logs/historico_processamentos.csv` | Uma linha por arquivo processado |
| `logs/robo.log` | Log técnico (rotaciona por dia) |
| `robo.lotes`, `robo.ocorrencias` | O mesmo, no PostgreSQL, para consultas SQL |

## 8. Consultas SQL prontas

`consultas_sql/` traz 29 consultas organizadas por problema de negócio, cada uma com pergunta, como ler o resultado e tabelas necessárias:

- **Monitoramento do robô:** cargas por dia, erros mais frequentes, reprovados, descarte na limpeza, tamanho das tabelas.
- **Qualidade dos dados:** completude por coluna, duplicidades entre arquivos, volume por arquivo, outliers.
- **NPS:** geral com **margem de erro**, mensal, por curso, distribuição, **teste de significância** entre meses, detratores para contato, ranking por UF.
- **CSAT e CES:** geral e por canal, esforço, mensal, Pareto de motivos.
- **Clientes e churn:** base ativa e churn mensal, **retenção por coorte**, tempo de vida, churn por plano.
- **Vendas e funil:** receita e crescimento, curva ABC, **RFM**, conversão do funil e por origem.

Execute pelo painel (modo **somente leitura**: nenhuma consulta altera dados) ou copie para o Power BI (PostgreSQL → Opções avançadas → Instrução SQL). Crie as suas copiando um arquivo.

## 9. Problemas comuns

| Sintoma | Solução |
|---|---|
| Arquivo parado em Bases-Limpeza | Robô pausado ou arquivo aberto no Excel (a fila mostra "Aberto em outro programa") |
| Status **Adiado** | Arquivo de saída aberto no Excel/Power BI ou PostgreSQL desligado: o robô tenta de novo sozinho |
| "Já existe um robô rodando" | Já está aberto: use o atalho (ele só mostra a janela) |
| Escritório 3D não aparece | Placa de vídeo sem WebGL: o restante do painel funciona normalmente |
| Coluna numérica virou texto | Menos de 95% dos valores eram números: use a habilidade **Converter tipo** |
| Python 3.15 / erro "Visual C++" | O `instalar.bat` já resolve: usa o 3.13 ao lado |

Ferramentas avançadas em `ferramentas/`: modo texto sem painel, status, processar uma vez, diagnosticar arrastando um arquivo, parar o robô.

## 10. Para quem for mexer no código

```
robo/
├── leitura.py, limpeza.py, validacao.py, modelagem.py, escrita.py   ← ETL
├── habilidades/     catálogo de habilidades (__init__: motor · nativas.py: 26 habilidades)
├── rh.py            fichas, níveis, permissões por risco e processo seletivo técnico
├── producao.py      portão de produção (supervisor, DBA, coordenadores)
├── quadro.py        cargos de gerente a estagiário com conferências reais e provas
├── contratacao.py   contratação automática pela liderança e experiência de 3 meses
├── canal.py         canal offline, sprints, boletim e ideias
├── ti.py            5º andar: ronda de TI e segurança
├── analise.py       2º andar · excel.py: 3º andar (entrega Excel auto-conferida)
├── agentes.py       equipe: nativos + personalizados (agentes/*.yaml)
├── banco.py         PostgreSQL em camadas (psycopg 3 + COPY)
├── consultas.py     biblioteca consultas_sql/ (execução somente leitura)
├── pipeline.py      orquestra um arquivo e emite os eventos de cada etapa
├── monitor.py       vigia a pasta (polling, robusto com OneDrive)
├── historico.py     histórico, detalhes JSON e resumo de ocorrências
└── painel/          servidor local + interface (estaticos/) + escritório 3D (Three.js embutido)
```

Testes: `.venv\Scripts\python -m pip install -r requisitos-dev.txt` e `.venv\Scripts\python -m pytest`. Para incluir os testes de PostgreSQL: `set ROBO_TESTE_PG=host=localhost port=5432 user=postgres password=SUA_SENHA`.

## 11. Nada se perde, nada fica parado (deixe ligado)

```
python -m robo inicializacao ligar    :: o robô liga junto com o Windows
python -m robo vigia ligar            :: a cada 5 min o Windows confere: se o robô caiu, religa (cada queda fica no banco)
python -m robo diagnostico            :: confere o computador inteiro e diz como corrigir cada ponto (só lê)
```

- **Tudo no banco:** log do sistema, canal, atas, RH, conhecimento, estado da TI e versões do config.yaml (sem senhas)
  entram no SQLite a cada minuto e no PostgreSQL a cada 10 min (só o que é novo). Nada disso pode ser apagado ou alterado.
- **Backup:** memória conferida (SHA-256) de hora em hora; guarda 24 h inteiras, 1 por dia por 30 dias e o 1º de cada mês
  para sempre. Para um 2º lugar (HD externo): no config.yaml, `backup: copia_extra: "E:\\Backups"`.
- **Levar a memória para outro computador:** `python -m robo importar-memoria trabalho_AAAAMMDD_HHMMSS.db.gz`.

## 11a. Status honesto e Fábrica de Planilhas

**Status honesto.** Antes, o painel dizia "trabalhando" para quem tivesse qualquer registro nas últimas 2 horas, até o
batimento automático de uma rotina, e parecia que todos trabalhavam sem estar. Agora todo processamento real abre um
**job** com as etapas e quem fez cada uma (`robo/jobs.py`):

- **trabalhando**: tem uma etapa de job aberta agora (últimos 15 minutos);
- **ativo hoje**: deixou trabalho real nas últimas 24 horas (etapa de job, treino, conversa, mentoria, lição, revisão);
- **plantão**: só a rotina automática dela rodou no prazo, o que não conta como trabalho;
- **ocioso** e **sem registro**.

O escritório 3D mostra no topo "X de Y com trabalho real agora" e há quanto tempo passou a última planilha (vermelho
acima de 60 minutos). A prova de cada pessoa está em `GET /api/prova-de-trabalho`.

**Fábrica de Planilhas** (menu Dados): Joana gera, Ruan confere o gabarito por outro caminho, Celina revisa e Teodoro
coordena. São 15 regras de negócio (NPS, CSAT/CES, churn, RFM, curva ABC, funil, folha, ponto, estoque, logística,
financeiro, leads, educação, vendas e pesquisa de mercado), com 2 mil a 20 mil linhas e a sujeira do mundo real. A
planilha `TREINO_*` entra em `Bases-Limpeza/sintetico`, passa pela esteira de verdade e sai em `Bases-Tratadas/_treino`.
Ela nunca vai para o PostgreSQL de produção nem para o histórico real, e é conferida contra o gabarito. Com planilha
real na fila, a fábrica espera. Detalhes em `MIGRACAO.md`.

## 11b. Fala natural, conversas com fato e memória da empresa

**Fala natural.** Cada funcionário fala no tom do cargo (diretor e head mais executivos, gerente e coordenador como
líderes, especialista e sênior técnicos, júnior e estagiário como aprendizes), sem listas, sem `;`, `*` ou `#` e sem frases de robô. Primeiro o robô
**apura** o fato (cálculo, consulta, registro) e só depois **redige**. A redação vem da voz determinística
(`robo/voz.py`) ou, se você ligar, de um modelo de IA (`robo/ia.py`: Ollama local, API compatível ou Claude). A IA
nunca calcula: se o texto dela citar um número que não está nos fatos, ele é descartado e a voz determinística
responde. Toda frase de IA aparece marcada como **hipótese** com o nome do modelo. No canal, o botão
**Testar conversa** mostra se há modelo ativo e por quê.

**Conversas só quando precisa.** A rotina `dialogo` (`robo/dialogo.py`) lê os fatos do dia (`robo/fatos.py`): erro
repetido no treino, rotina que falhou, planilha barrada, alerta da TI, fila travada, divergência na fábrica. Para cada
fato, quem precisa fala com quem sabe (ou com o gestor) em 2 a 4 falas, e a conversa termina num **compromisso que dá
para conferir** (refazer o caso, rodar a rotina, reenviar). Depois a rotina confere pelo número do registro se o
compromisso foi cumprido. Sem fato, ninguém conversa, e o ciclo fica registrado como "sem assunto".

**Memória da empresa.** Todo acerto e erro da esteira, da validação, do treino, do laboratório e da fábrica vira um
**aprendizado** (`robo/aprendizados.py`), com causa e correção. Antes de ler uma planilha, a esteira consulta a memória
e anota no relatório o que já deu errado em casos parecidos. A semente com 208 erros típicos entra com
`python -m robo semear-aprendizado` e nunca conta como trabalho de ninguém.

## 11c. Por que uma tabela do banco está vazia?

Rode `python -m robo cobertura-banco`. Ele conta as linhas de cada tabela do SQLite e do PostgreSQL e, para cada
tabela vazia, diz **por quê** e **o que a enche**. Exemplos: "só nasce quando o dono faz um pedido", "implementada, mas
nada a chama" ou "sem causa conhecida (investigar)". O relatório completo fica em `logs/cobertura_banco.md`. Nada é
preenchido para parecer cheio.

Onde fica cada tipo de dado no PostgreSQL:

| Schema | Natureza | O que tem |
|---|---|---|
| `bruto`, `tratado`, `analitico`, `analise` | real | só planilhas suas |
| `laboratorio`, `treino` | sintético | planilhas da Fábrica (TREINO_*), com teto de 100 MB (`fabrica.pg_treino_mb_max`) |
| `robo` | operação | memória da empresa (`robo.memoria_*`), lotes e ocorrências reais |

O diagnóstico completo da reestruturação está em `documentacao/diagnostico_reestruturacao.md`.

## 11d. Demandas: trabalho real para cada funcionário

A rotina `demandas` (a cada 30 minutos, `robo/demandas.py`) dá a cada funcionário uma tarefa que ele executa com a
**ferramenta do próprio contrato**: o cientista roda drivers, a DBA consulta o PostgreSQL, o 5º andar faz a ronda de
TI, o RH mede o desempenho. Cada demanda tem objetivo, evidência esperada e **critérios de aceitação** conferidos
sem IA. Um cálculo, por exemplo, só é aceito se bater com uma conta feita em pandas por outro caminho. Quem revisa é
sempre outra pessoa, e a conferência automática nunca sai no seu nome.

Como a distribuição funciona:
- quem está há mais tempo sem demanda recebe primeiro; ninguém tem duas abertas, nem recebe outra em menos de 24 horas;
- estagiários ficam em observação (sua regra) e o motivo fica registrado;
- demanda sem condição de rodar (sem planilha sintética, banco desligado) não vira tarefa: fica registrada como
  bloqueada, com o motivo;
- os dados são os sintéticos da fábrica; nenhuma demanda lê planilha real, publica ou altera dados;
- até 6 por ciclo e 150 por dia (`demandas: {por_ciclo, por_dia, por_pessoa_horas, intervalo_minutos}`).

Onde ver: tela **Solicitações** (origem "demanda_sintetica"), tabela `demandas_ciclos` (quem recebeu, quem foi pulado e
por quê) e `jobs` do tipo `demanda` (prova de trabalho).

## 12. Apache Airflow (opcional)

O robô agenda as próprias rotinas. Se quiser vê-las no Airflow (com histórico, retentativas e tempo limite):

```
python -m robo airflow-dag        :: gera airflow\dags\robo_empresa.py a partir das rotinas (caminhos já para o WSL)
python -m robo rotina backup      :: roda UMA rotina e registra — é o que cada tarefa do Airflow chama
```

O Airflow roda no WSL2 (Linux dentro do Windows, nada na nuvem). Passo a passo, regras de SLA e como escolher quem
agenda (`rotinas: agendador: robo | airflow`): **`documentacao/airflow.md`**. O robô e o Airflow nunca rodam a mesma
rotina ao mesmo tempo (trava entre programas; a tarefa repetida sai com código 99 e o Airflow a marca como pulada).

## 13. Acompanhar pelo celular

**O que é:** uma página no celular com o estado da empresa (robô ligado, rotinas, treino das últimas 24 h, conversas,
andares, últimas planilhas, decisões atrasadas, alertas da TI e último backup), atualizando a cada 10 segundos. Por
padrão ela **só lê**. O painel completo continua abrindo só no notebook.

**Abrir em 3 toques (depois de ligar uma vez, abaixo):**
1. No notebook, abra o painel e vá em **Gestão → No celular**. Aparece um QR code com o endereço.
2. No celular, abra a **câmera** e aponte para o QR code.
3. Toque no **link** que aparecer e entre com a senha do painel.

Para virar ícone na tela do celular: no iPhone, **Compartilhar → Adicionar à Tela de Início**. No Android, o botão
**Instalar** aparece no topo quando o navegador permite.

**Ligar (uma vez):**
1. Tenha a senha do painel definida (`python -m robo senha`). Sem senha, o celular não abre, de propósito.
2. No Prompt de Comando, na pasta do projeto: `python -m robo celular --ligar`.
3. Feche e abra o robô. Na 1ª vez o Windows pergunta sobre o firewall: marque **só "Redes privadas"**.

**Não abriu?** Rode `python -m robo diagnostico-celular`. Ele confere, em ordem, os 8 passos entre o notebook e o
celular (ligado, senha, rede de casa, servidor ouvindo, resposta pelo IP da rede, firewall, instalação e ações), diz
qual falhou e como corrigir, e mostra o QR code no próprio Prompt. Corrija sempre o **primeiro ✘**: os seguintes
costumam depender dele.

**Fora de casa:** instale o Tailscale (VPN gratuita) no notebook e no celular e use o IP `100.x.x.x` do notebook.
**Nunca** abra a porta no roteador.

**Sobre a tela offline (honesto):** a tela "sem conexão" e a instalação completa no Android exigem HTTPS. Pelo Wi-Fi de
casa o endereço é `http://`, então o navegador não liga essa parte. O resto funciona normalmente e o atalho na tela de
início também. Para ter HTTPS grátis: com o Tailscale ligado, ative uma vez "HTTPS Certificates" no site do
Tailscale (aba DNS), rode no notebook `tailscale serve --bg 8766` e use o endereço `https://…ts.net` que ele mostrar. Nenhum dado fica guardado no celular, nem com HTTPS.

**Ações pelo celular (opcional, desligadas por padrão).** Com `celular: {acoes: true}` no `config.yaml`, aparece a aba
**Ações** com quatro botões e nada além deles: pausar o robô, retomar o robô, ver o log e mandar uma planilha reprovada
de volta para a fila. Cada toque pede confirmação e fica registrado em `acessos_celular` e como job `acao_celular` em
`jobs`. Apagar, aprovar regra, rodar SQL e mudar configuração continuam só no notebook.

**Segurança:** só aceita endereços de rede privada; 5 senhas erradas bloqueiam o aparelho por 15 minutos; toda entrada
(certa ou errada) fica registrada para sempre na tabela `acessos_celular`. Desligar: `python -m robo celular --desligar`.

### App de banco no celular (ler o PostgreSQL direto)

Se você usa um app de PostgreSQL no celular, rode **uma vez** no Prompt **como Administrador**:
`python -m robo liberar-banco-celular`. Ele libera **só o usuário `robo_leitura`** (não altera nada) e **só para a rede
da sua casa**, faz uma cópia do `pg_hba.conf` antes de mexer, reinicia o serviço do PostgreSQL e cria a regra de
firewall só para "Redes privadas". No fim, imprime os campos do app:

| Campo do app | O que preencher |
|---|---|
| Name | Robô de Planilhas |
| Hostname | o IP do notebook na rede de casa (o comando mostra, ex.: 192.168.0.23) |
| Port | 5432 |
| Database | robo_dados |
| User | robo_leitura |
| Password | no Prompt: `echo %ROBO_PG_SENHA_LEITURA%` (a senha nunca fica em arquivo) |
