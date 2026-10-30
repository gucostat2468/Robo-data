# Estudo antes de construir: o "novo bot" (esteira confiável + chat em linguagem natural + dashboards)

Princípio que guia tudo: **é melhor dizer "não sei" do que entregar um número errado.** Um megazord que mente é pior
que nenhum robô. Este documento junta os conceitos, as boas práticas e as decisões técnicas **antes** de uma linha
nova de código, e diz claramente o que **não** é possível.

---

## 1. Engenharia de dados: a esteira

### 1.1 Arquitetura em camadas (medalhão)

| Camada | No projeto | Regra de ouro |
|---|---|---|
| **Bronze / bruto** | `bruto` (PostgreSQL) e `original_<arquivo>` na pasta da entrega | Nunca se altera. É a prova do que chegou |
| **Prata / tratado** | `tratado` e `base_tratada.xlsx` | Tipos corretos, nomes padronizados, sem total/duplicata. Cada mudança registrada |
| **Ouro / analítico** | `analitico`, `indicadores.xlsx` | Métricas de negócio com definição única (NPS é calculado num lugar só) |

### 1.2 Boas práticas que a esteira precisa cumprir

| Prática | O que é | Como garantir |
|---|---|---|
| **Imutabilidade do bruto** | O original nunca muda | Cópia + SHA-256 no manifesto (já existe) |
| **Idempotência** | Rodar 2× a mesma planilha dá o mesmo resultado | Teste automático: duas entregas → mesmos números |
| **Contrato de dados** | O que se espera de cada base: colunas, tipos, domínios (NPS 0–10) | Arquivo de contrato por tipo de base; violação vira ERRO ou AVISO, nunca silêncio |
| **Linhagem** | De onde veio cada número | Manifesto: original → tratado → indicador, com a regra aplicada |
| **Reconciliação** | Entrada − removidas = saída; somas antes = depois | Certificado de conferência (já existe, ampliar) |
| **Observabilidade** | Saber quando e por que falhou | Log por etapa + motivo legível |
| **Fail loud** | Erro grave para a esteira, não "dá um jeito" | ERRO bloqueia publicação; o relatório diz por quê |

### 1.3 As 6 dimensões de qualidade (DAMA) e o teste de cada uma

| Dimensão | Pergunta | Teste automático |
|---|---|---|
| Completude | Está faltando dado? | % preenchido por coluna; alerta abaixo de 80% |
| Unicidade | Tem duplicado? | Chave única (ex.: id da resposta) |
| Validade | O valor é possível? | Domínio (NPS 0–10, data no passado, percentual ≤ 100) |
| Consistência | Bate com outras fontes / consigo mesmo? | Total da planilha × soma das linhas; MQL ≤ leads |
| Exatidão | É o valor certo? | Só se compara com referência (gabarito, sistema de origem) |
| Atualidade | É recente? | Data máxima × hoje; mês incompleto sinalizado (já existe) |

---

## 2. Análise de dados: regras que impedem conclusão errada

1. **Pergunta antes do número.** Toda análise começa com a decisão que ela apoia.
2. **Denominador explícito.** "% de quê?" Sempre mostrar o n (base) ao lado do percentual.
3. **Margem de erro e base mínima.** Pesquisa amostral: IC 95%; grupo < 30 não é comparado (já existe).
4. **Não somar médias nem percentuais.** NPS de dois grupos não se soma; recalcula-se na base unida.
5. **Paradoxo de Simpson.** Um resultado agregado pode inverter dentro dos grupos. Ao comparar ondas, verificar a
   composição da amostra (mix) antes de concluir.
6. **Comparabilidade.** Mesmo período, mesma régua, mesma população. Mês incompleto não compara com mês cheio.
7. **Significância ≠ relevância.** Diferença real pode ser pequena demais para importar (tamanho do efeito).
8. **Muitas comparações geram falso positivo.** Correção de Holm (já existe).
9. **Outlier não é erro automaticamente.** Sinaliza; quem decide é a pessoa.
10. **Escala da nota.** CSAT 1–5 × 1–10 não se misturam; top-2-box definido por escala.

## 3. Ciência de dados: rigor

| Risco | Explicação simples | Defesa |
|---|---|---|
| Correlação ≠ causa | "Anda junto" não é "causa" | Linguagem: "está associado a", nunca "causa" |
| Multicolinearidade | Atributos parecidos dividem a importância | VIF no driver (já existe) |
| Vazamento | Usar informação do futuro para prever o passado | Corte temporal (já existe no ML) |
| Sem baseline | Modelo "bom" que perde para a regra simples | Sempre comparar com baseline |
| Viés de seleção | Quem responde pesquisa não é igual a quem não responde | Avisar quando a taxa de resposta é baixa |
| Reprodutibilidade | Resultado que não se repete não vale | Semente fixa, versão do código no manifesto |

---

## 4. Confiabilidade: como o sistema prova o que entrega

**Regra central: a IA nunca calcula.** Quem calcula é o código determinístico e testado; a IA só **escolhe o que
perguntar ao código** e **escreve a frase** com os números que o código devolveu.

Camadas de defesa (da base para o topo):

1. **Testes com gabarito (golden datasets).** A fábrica já gera planilhas com a resposta conhecida. Métrica de
   confiabilidade publicada: "% de respostas corretas nas N planilhas de prova". Sem ≥ 99% em indicador, não sobe.
2. **Contrato de dados** por tipo de base (o que é válido).
3. **Certificado de conferência** em toda entrega (já existe: linhas, somas pandas × SQL, NPS em SQL, releitura).
4. **Camada semântica:** cada métrica tem UMA definição (NPS, CSAT, total de vendas…). O chat só pode usar
   métricas dessa lista — não inventa fórmula.
5. **Verificador da resposta do chat:** todo número no texto da IA tem que existir no resultado do código; se não
   existir, a frase é bloqueada (já existe o princípio em `ia.numeros_inventados`).
6. **Transparência:** cada resposta mostra a consulta usada (SQL) e a base (n). O usuário pode conferir.
7. **"Não sei" honesto:** pergunta fora do que os dados respondem → "esta base não tem essa informação".

## 5. Chat em linguagem natural

### 5.1 Como funciona (arquitetura)

```
Você: "como está o NPS do Sul comparado ao mês passado?"
  1. IA (intérprete) → {métrica: NPS, filtro: regiao=Sul, comparar: mês atual × anterior}
  2. Robô (código testado) → calcula NPS, margem, n, teste de diferença; gera o SQL
  3. IA (redatora) → escreve a resposta usando SÓ os números do passo 2
  4. Verificador → todo número da frase existe no passo 2? Senão, bloqueia
  5. Tela → resposta + "como calculei" (SQL, n, margem)
```

Para perguntas fora do catálogo, a IA pode **propor** um SQL (texto-para-SQL); ele roda só leitura e a resposta vem
marcada "consulta gerada pela IA — confira o SQL".

### 5.2 Privacidade

A IA **nunca recebe as linhas da sua planilha**. Recebe: nomes e tipos das colunas, a pergunta e os **resultados
agregados** (ex.: NPS 32, n 410). Em pesquisa com dado pessoal, nada pessoal sai do computador.

### 5.3 Provedores: barato, sem travar, com plano B local

| Ordem | Provedor | Custo | Limites (verificar no painel do provedor) | Papel |
|---|---|---|---|---|
| 1 | **Groq** (modelos abertos: Llama, Qwen) | Grátis | Relatado: 30 req/min e ~14.400 req/dia no plano grátis | Principal: rápido e grátis |
| 2 | **Google Gemini Flash-Lite** | Grátis | Os números variam por fonte (de ~20 a ~1.000 req/dia); o Google não publica mais uma tabela fixa | Reserva |
| 3 | **DeepSeek V4 Flash** (pago, opcional) | ~US$ 0,15–0,30 por milhão de tokens de entrada | Sem cota diária prática | Só se você autorizar o custo |
| 4 | **Ollama local** (Qwen3 8B ou 4B) | Grátis | Nenhum | Quando as APIs pararem ou sem internet |

**Custo realista do pago:** uma pergunta usa ~3 mil tokens. 1.000 perguntas ≈ 3 milhões ≈ **menos de US$ 1–2**.

**Rotação automática:** se o provedor 1 responder "limite atingido" (erro 429), passa para o 2; depois para o
local. Na prática o chat **não para** — mas nenhuma API grátis garante "sem limite".

**Espaço no computador (Ollama):** Qwen3 4B ≈ 2,5–3 GB de disco e 8 GB de RAM; Qwen3 8B ≈ 5 GB de disco e
16 GB de RAM. O programa Ollama em si é pequeno.

## 6. Dashboards: o visual certo para cada análise

| Análise | Pergunta do gestor | Visual recomendado | Evitar |
|---|---|---|---|
| NPS / CSAT geral | "Como estamos?" | Cartão com valor, margem e n + variação vs onda anterior | Velocímetro (gauge) sem meta |
| NPS por segmento | "Onde está pior?" | Barras horizontais ordenadas, com n e aviso de base pequena | Pizza; barras sem base |
| Composição P/N/D | "Por que o NPS é esse?" | Barra 100% empilhada (promotores/neutros/detratores) | Rosca com muitas fatias |
| Evolução | "Melhorou?" | Linha por mês com faixa de margem; mês incompleto tracejado | Barras 3D; eixo cortado |
| Drivers | "Onde investir?" | Matriz importância × desempenho (dispersão em quadrantes) | Ranking só de correlação |
| Vendas por grupo | "Quem vende mais?" | Barras ordenadas + Pareto (acumulado) | Treemap para poucos grupos |
| Tendência de vendas | "Como está o mês?" | Linha mensal + comparação com mesmo mês do ano anterior | Comparar mês parcial |
| Logística | "Estamos no prazo?" | Cartão % no prazo + barras por transportadora + mapa de UF (se houver) | Média de atraso sem distribuição |
| Distribuição de um valor | "Como se espalha?" | Histograma / boxplot | Média sozinha |

**Layout executivo:** linha 1 com 3–5 cartões; linha 2 com o "onde"; linha 3 com o "quando"; detalhe em outra aba.
Máximo de 6–7 visuais por página. Cores: uma cor principal, vermelho só para o que é ruim de verdade.

## 7. O que NÃO é possível (sendo honesto)

| Pedido | Realidade | Alternativa |
|---|---|---|
| "100% confiável" | Nenhum sistema é 100%. | Medir e publicar a taxa de acerto nos testes com gabarito; bloquear quando não confere |
| LLM local "pensando como você ou o Gemini" | Num notebook, um modelo de 4–8B é bem mais limitado que os modelos grandes da nuvem | Local só como reserva; ele narra os fatos que o código calculou (tarefa que modelos pequenos fazem bem) |
| API grátis "sem atingir limite" | Toda API grátis tem limite e muda sem aviso | Rotação entre provedores + local; pago opcional por centavos |
| Gerar arquivo do Power BI (.pbix) automaticamente | Formato fechado; geração automática é frágil | Dashboard HTML interativo pronto + tabelas no formato estrela para o Power BI + medidas DAX prontas |
| Mandar a base inteira para a IA analisar | Risco de privacidade e de número inventado | IA só vê agregados; cálculo sempre no código |

## 8. Plano de construção (cada fase só começa com a anterior aprovada)

| Fase | Entrega | Critério de aceite (medível) |
|---|---|---|
| 0 | **Banco de provas**: 15+ planilhas da fábrica com gabarito, rodando a cada mudança | Relatório de acerto: indicadores 100% iguais ao gabarito |
| 1 | **Contratos de dados** por tipo de base + certificado ampliado (6 dimensões DAMA) | Planilha com defeito plantado → detectado em 100% dos casos de prova |
| 2 | **Camada semântica** (catálogo de métricas e dimensões) | Cada métrica tem 1 definição, testada contra o gabarito |
| 3 | **Chat** no Estúdio: Groq → Gemini → Ollama, com verificador de números e "como calculei" | 50 perguntas de prova: 0 número inventado; respostas fora do escopo dizem "não sei" |
| 4 | **Dashboards HTML interativos** por tipo de análise (filtros, visuais da tabela da seção 6) | Revisão visual + números iguais ao indicadores.xlsx |
| 5 | **Comparação entre ondas** com teste de diferença e checagem de mix (Simpson) | Casos de prova com mudança real e com mudança de mix |

## 9. O que preciso de você para começar

1. **RAM e espaço livre em disco** do notebook (decide entre Qwen3 4B e 8B).
2. **Criar as chaves grátis** (eu nunca vejo as chaves; elas ficam numa variável do Windows):
   - Groq: console.groq.com → API Keys;
   - Google: aistudio.google.com → Get API key.
3. **Autorizar ou não** o provedor pago de reserva (DeepSeek, centavos por mês).

## Fontes consultadas (preços e limites mudam: conferir no painel de cada provedor)

- Limites do Gemini: [documentação oficial](https://ai.google.dev/gemini-api/docs/rate-limits?authuser=5),
  [medição de 2026](https://aiplug.work/en/blog/gemini-free-tier-limits), [guia 2026](https://pecollective.com/tools/gemini-free-tier-guide/)
- Preços de APIs: [morphllm](https://www.morphllm.com/llm-api-pricing), [pricepertoken](https://pricepertoken.com/),
  [klymentiev](https://klymentiev.com/blog/cheapest-llm-api), [aireiter](https://aireiter.com/blog/cheapest-llm-api)
- Modelos locais: [Hugging Face](https://huggingface.co/blog/daya-shankar/open-source-llm-models-to-run-locally),
  [morphllm Ollama](https://www.morphllm.com/best-ollama-models), [16 GB RAM](https://openclawdc.com/blog/best-local-llms-16gb-ram/)
