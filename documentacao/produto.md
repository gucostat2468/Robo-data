# Robô de Planilhas — o produto

## O que é (em uma frase)

Você entrega **qualquer planilha** (vendas, financeiro, RH, logística, estoque, marketing, pesquisa…) e recebe a
esteira inteira que um time de dados faria antes do Power BI: **limpeza e padronização registradas, qualidade medida,
análise, modelo estrela com medidas DAX, Machine Learning opcional e um relatório organizado**, tudo conferido por um
certificado.

## A esteira (o que acontece, na ordem)

| Etapa | Disciplina | O que o robô faz | Prova |
|---|---|---|---|
| 1. Leitura | Engenharia | acha o cabeçalho, ignora linhas de título/total, lê .xlsx/.xls/.csv | linhas: entrada − removidas = saída |
| 2. Limpeza e padronização | Engenharia | datas, números no padrão BR, duplicatas, **grafias unificadas** ('sudeste ' = 'Sudeste') | cada mudança listada no relatório |
| 3. Qualidade (DAMA) | Engenharia | completude, unicidade, validade, consistência e atualidade por coluna, nota 0–100 | tabela no relatório e aba `qualidade_dama` |
| 4. Análise | Análise | métricas (soma × média do jeito certo), por segmento, Pareto, tendência mensal sem o mês incompleto, valores fora do padrão, diferenças reais (Holm) | somas refeitas em SQL |
| 5. Modelo estrela | Engenharia/BI | fato + uma dimensão por categoria + calendário, relações 1:* e **medidas DAX prontas** | fato com as mesmas linhas; chaves únicas |
| 6. Machine Learning (opcional) | Ciência | escolha uma coluna para prever: linha de base, validação cruzada, teste usado uma vez, divisão por tempo, checagem de vazamento, importância por permutação | veredito "vale a pena" ou "não use" |
| 7. Entrega | — | relatório HTML, planilhas, modelo Power BI, manifesto com SHA-256 | certificado de conferência |

**Machine Learning, as regras que impedem resultado mentiroso:**
- o modelo só "vale" se superar a **linha de base** (chutar a classe mais comum ou a média) no treino E no teste;
- coluna que sozinha acerta o alvo ~100% é **vazamento** (o resultado disfarçado) e é retirada, com aviso;
- com data na base, treina no passado e testa no futuro;
- base com menos de 100 linhas ou categoria com menos de 10 casos: o robô **recusa e explica**;
- dado sintético é aceito: o modelo aprende o mundo daquele dado (e isso fica registrado).

## O que vem no pacote (`Entrega_<base>_<data>/`)

| Arquivo | Para que serve |
|---|---|
| `relatorio.html` | o relatório executivo: cartões de KPI, recomendações, drivers, gráficos por segmento, diferenças reais, qualidade dos dados e metodologia. Abre com dois cliques, funciona sem internet, pode ir por e-mail |
| `indicadores.xlsx` | os números conferíveis (abas: indicadores, destaques, drivers, perfil, qualidade, logística) — base para o Power BI |
| `base_tratada.xlsx` | a base limpa (datas, números BR, duplicatas, totais removidos), pronta para o Power BI ou para cruzar com outra |
| `modelo_powerbi.xlsx` | o modelo estrela: uma aba por tabela (fato, dimensões, calendário) |
| `medidas_dax.txt` | as medidas DAX comentadas, para colar em Modelagem > Nova medida |

## Jeito mais fácil: o Estúdio (interface no navegador)

Sem pastas, sem comandos longos, sem o painel 3D.

1. Na pasta do projeto, clique na **barra de endereço** do Explorador, digite `cmd` e aperte **Enter**.
2. Digite `python -m robo estudio` e aperte **Enter**. O navegador abre sozinho em `http://127.0.0.1:8765`.
3. Aba **1. Tratar planilha**: **arraste a planilha** para o quadro (ou clique nele e escolha). Se quiser, escreva os
   segmentos (ex.: `regiao, produto`) e, para Machine Learning, a **coluna a prever** (ex.: `cancelou`).
   Clique em **Tratar e analisar**.
4. Em segundos aparecem as **recomendações**, o **relatório completo** na própria tela e os links para baixar
   `relatório (HTML)`, `indicadores.xlsx` e `base tratada.xlsx`.
5. Aba **2. SQL**: os dados **já tratados** viram a tabela `dados`, e o modelo estrela vira `fato_dados`,
   `dim_...` e `dim_calendario` (dá para praticar JOIN). Escreva, por exemplo:

   ```sql
   SELECT regiao, COUNT(*) AS respostas, ROUND(AVG(nota_nps), 1) AS nota_media
   FROM dados
   GROUP BY regiao
   ORDER BY respostas DESC
   ```

   e clique em **Executar** (ou **Ctrl+Enter**). Só leitura: `DELETE`, `DROP` e afins são recusados.
   Com o PostgreSQL do robô configurado, a lista **Consultar** também oferece o banco (sempre só leitura).
6. Para fechar: feche a janela preta (ou **Ctrl+C** nela).

**Onde fica tudo:** cada envio vira uma pasta em `Documentos\Robo de Planilhas\Entregas\Entrega_<arquivo>_<data>`
(o link **abrir a pasta** abre no Explorador). Dentro dela:

| Arquivo | O que é |
|---|---|
| `original_<arquivo>` | cópia exata do que você enviou (o seu arquivo nunca é alterado) |
| `base_tratada.xlsx` | a base limpa e padronizada |
| `indicadores.xlsx` | todos os números conferíveis (inclui qualidade, relações do Power BI e, com ML, comparação, importância e previsões do teste) |
| `modelo_powerbi.xlsx` | fato + dimensões + calendário |
| `medidas_dax.txt` | medidas DAX comentadas |
| `relatorio.html` | o relatório completo |
| `manifesto.json` | o **certificado**: as conferências e a impressão digital (SHA-256) de cada arquivo |
| `consultas_sql.sql` | cada consulta SQL que você rodou, com data, hora e resultado |

As entregas aparecem em **Entregas salvas** na própria tela: clique para abrir de novo (relatório e SQL).
Para mudar a pasta: variável de ambiente `ROBO_PASTA_ENTREGAS` ou `estudio: {pasta: ...}` no `config.yaml`.

**Certificado de conferência** (no topo do relatório e no `manifesto.json`), cada conta refeita por outro caminho:
1. linhas: entrada − removidas (totais, duplicatas, rodapé) = saída;
2. soma de cada coluna numérica: pandas × SQL;
3. NPS do relatório refeito em SQL direto na base tratada;
4. base tratada gravada e relida com o mesmo número de linhas.

**Atalho na Área de Trabalho:** rode uma vez `python -m robo estudio --atalho`. Depois é só dar dois cliques em
**Robô de Planilhas - Estúdio**.

**Validação:** a contagem de linhas no topo ("Pronto: N linhas") deve bater com a planilha original menos as linhas de
total/duplicadas que a seção "Limpeza e padronização feitas" do relatório lista.

**Segurança:** o Estúdio só atende este computador (127.0.0.1); ninguém da rede consegue abrir.

## Pelo comando (passo a passo, Windows)

**Antes da 1ª vez** (uma vez só): o projeto já precisa estar instalado no computador (é o mesmo do painel do robô).

1. Abra a pasta onde está a sua planilha no **Explorador de Arquivos**.
2. Clique na **barra de endereço** (no topo da janela), apague o que estiver escrito, digite `cmd` e aperte **Enter**.
   Abre uma janela preta (o Prompt de Comando) já nessa pasta.
3. Digite (troque pelo nome da sua planilha) e aperte **Enter**:

   ```
   python -m robo entregar "Pesquisa NPS outubro.xlsx"
   ```

4. Em alguns segundos aparece `Entrega pronta:` e o caminho da pasta, mais as recomendações.
5. Volte ao Explorador: há uma pasta nova `Entrega_...`. Abra e dê **dois cliques em `relatorio.html`**.

**Escolher os segmentos** (se o robô escolher colunas que não interessam):

```
python -m robo entregar "Pesquisa NPS outubro.xlsx" --segmentos regional,curso,canal
```

**Machine Learning** (prever uma coluna):

```
python -m robo entregar "clientes.xlsx" --alvo cancelou
```

**Salvar a entrega em outra pasta**: acrescente `--destino "C:\Users\voce\Desktop\Entregas"`.

### Como validar se deu certo

- No relatório, o cartão **NPS** deve bater com a sua conta no Excel: `% de notas 9–10 − % de notas 0–6`.
- A aba `qualidade` do `indicadores.xlsx` diz tudo o que a limpeza mexeu (linhas de total removidas, duplicatas…).
- Grupos com `*` têm menos de 30 respostas: **não compare** esses grupos.

### Erros comuns

| Mensagem | Causa | O que fazer |
|---|---|---|
| `Arquivo não encontrado` | nome digitado diferente | use aspas e confira o nome (inclusive a extensão `.xlsx`) |
| `Nenhuma coluna de NPS, CSAT ou CES reconhecida` | coluna com nome fora do padrão | renomeie para algo como `nota_nps`, `csat` ou `ces` |
| `drivers precisam de pelo menos 30` | base pequena ou sem notas de atributo | normal em base pequena: o resto do relatório continua valendo |
| O Excel não abre o `indicadores.xlsx` | arquivo aberto em outro programa | feche e gere de novo |

## Como a "empresa" se liga ao produto

Os 105 funcionários virtuais treinam todos os dias, na nuvem, com planilhas sintéticas da fábrica (15 tipos). Cada
**projeto entre andares** aprovado na revisão independente gera o mesmo pacote (`entregas` no banco) e o boletim do
celular mostra a última entrega. Ou seja: o produto é testado continuamente pelos mesmos motores que você usa.

## Critérios de qualidade (o que o produto nunca faz)

- Nunca inventa número: tudo vem da base; recomendação só sai de regra sobre os números (e diz de onde veio).
- Nunca chama de "diferença" o que pode ser acaso (teste com correção de Holm a 95%).
- Nunca compara grupo com menos de 30 respostas sem aviso.
- Nunca altera o arquivo original.
- Média sem sentido conhecido (ex.: dias de atraso por grupo) não vira "bom" ou "ruim" automaticamente.

## Roteiro do produto

| Fase | O que | Estado |
|---|---|---|
| 1 | esteira genérica: limpeza, padronização, qualidade DAMA, análise, certificado | **pronto** |
| 2 | Estúdio no navegador (upload + SQL + entregas salvas) | **pronto** |
| 3 | modelo estrela + medidas DAX para o Power BI | **pronto** |
| 4 | Machine Learning supervisionado com linha de base, vazamento e divisão por tempo | **pronto** |
| 5 | aba **3. Conversar**: perguntas em português → o código calcula → a IA escreve → verificador confere cada número (API gratuita com troca automática para LLM local) | próximo |
| 6 | dashboard HTML interativo (filtros) com o visual certo por tipo de análise | próximo |
| 7 | ML sem alvo: segmentação (clusters) e detecção de anomalias; textos livres (temas) | planejado |
| 8 | juntar várias planilhas (append por período, merge por chave com checagem de duplicidade) | planejado |
| 9 | gravar cada entrega no PostgreSQL (camadas bruto/tratado/analitico) para histórico e ML entre bases | planejado |
