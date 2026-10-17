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
3. No painel: **Configurações → Banco de dados PostgreSQL** → ligue a chave e preencha:
   servidor `127.0.0.1`, porta `5432`, banco `robo_dados`, usuário `postgres` e a senha → **Testar conexão** → **Salvar**.
4. Mais seguro (recomendado pelo time de segurança): em vez de gravar a senha no arquivo, crie a variável de ambiente
   do Windows `ROBO_PG_SENHA` (Iniciar → digite "variáveis de ambiente" → **Editar as variáveis de ambiente para sua conta**
   → **Novo** → nome `ROBO_PG_SENHA`, valor = sua senha → OK) e deixe o campo de senha vazio. Reinicie o robô.

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
