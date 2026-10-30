# Robô de Planilhas — o produto

## O que é (em uma frase)

Você entrega uma planilha de pesquisa (NPS, CSAT, CES) ou de entregas (prazo e atraso) e recebe, em segundos, o que um
analista sênior entregaria ao gestor: **base tratada, indicadores com margem de erro, o que mais pesa na nota,
diferenças reais entre grupos e recomendações**, num relatório que abre em qualquer navegador.

## Para quem e por quê

| | |
|---|---|
| **Usuário** | analista de Customer Insights que recebe bases de pesquisa e precisa apresentar resultado rápido e certo |
| **Dor** | horas limpando base, calculando NPS por segmento e montando slide; risco de comunicar "diferença" que é acaso |
| **Valor** | minutos em vez de horas; estatística correta por padrão (margem de erro, base mínima, correção de Holm) |
| **Privacidade** | roda no SEU computador: a base nunca vai para a nuvem nem para o GitHub (o repositório é público) |

## O que vem no pacote (`Entrega_<base>_<data>/`)

| Arquivo | Para que serve |
|---|---|
| `relatorio.html` | o relatório executivo: cartões de KPI, recomendações, drivers, gráficos por segmento, diferenças reais, qualidade dos dados e metodologia. Abre com dois cliques, funciona sem internet, pode ir por e-mail |
| `indicadores.xlsx` | os números conferíveis (abas: indicadores, destaques, drivers, perfil, qualidade, logística) — base para o Power BI |
| `base_tratada.xlsx` | a base limpa (datas, números BR, duplicatas, totais removidos), pronta para o Power BI ou para cruzar com outra |

## Jeito mais fácil: o Estúdio (interface no navegador)

Sem pastas, sem comandos longos, sem o painel 3D.

1. Na pasta do projeto, clique na **barra de endereço** do Explorador, digite `cmd` e aperte **Enter**.
2. Digite `python -m robo estudio` e aperte **Enter**. O navegador abre sozinho em `http://127.0.0.1:8765`.
3. Aba **1. Tratar planilha**: **arraste a planilha** para o quadro (ou clique nele e escolha). Se quiser, escreva os
   segmentos (ex.: `regiao, curso`). Clique em **Tratar e analisar**.
4. Em segundos aparecem as **recomendações**, o **relatório completo** na própria tela e os links para baixar
   `relatório (HTML)`, `indicadores.xlsx` e `base tratada.xlsx`.
5. Aba **2. SQL**: os dados **já tratados** viram a tabela `dados`. Escreva, por exemplo:

   ```sql
   SELECT regiao, COUNT(*) AS respostas, ROUND(AVG(nota_nps), 1) AS nota_media
   FROM dados
   GROUP BY regiao
   ORDER BY respostas DESC
   ```

   e clique em **Executar** (ou **Ctrl+Enter**). Só leitura: `DELETE`, `DROP` e afins são recusados.
   Com o PostgreSQL do robô configurado, a lista **Consultar** também oferece o banco (sempre só leitura).
6. Para fechar: feche a janela preta (ou **Ctrl+C** nela).

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
| MVP | pacote de entrega (pesquisa + logística) por comando | **pronto** |
| 2 | botão "Gerar entrega" no painel (sem digitar comando) | próximo |
| 3 | comparação entre ondas (esta pesquisa × a anterior) no relatório | próximo |
| 4 | verbatins (respostas abertas): temas e sentimento | depende de IA local (Ollama) no seu notebook |
| 5 | modelo do Power BI (.pbit) lendo `indicadores.xlsx` | planejado |
