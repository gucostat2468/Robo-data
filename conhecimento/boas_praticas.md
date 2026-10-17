# Manual de boas práticas da empresa

Este manual vale para todos os andares. Ele é lido pelo canal: pergunte, por exemplo, "qual a boa prática para chave única?".

## Princípios da casa
- **Certo antes de rápido.** Nenhum dado vai para produção sem conferência de quem não fez o trabalho (quatro olhos).
- **Nada some em silêncio.** Toda linha removida, todo valor esvaziado e toda aba ignorada aparece no relatório com o motivo.
- **Erro é informação.** Arquivo barrado vai para Bases-Erros com o _ERROS.txt dizendo a linha e o que corrigir.
- **Honestidade com o dono.** Se não sabemos, dizemos que não sabemos. Número com base pequena sempre vem com aviso.
- **Tudo local.** Nenhum dado sai do computador da empresa.

## Engenharia de dados: ingestão
- Só processe o arquivo quando ele parar de mudar (o OneDrive ainda pode estar sincronizando).
- Nunca altere a planilha original: ela vai para Bases-Originais (aprovada) ou Bases-Erros (reprovada).
- Guarde de onde veio cada linha: arquivo, aba e número da linha no Excel.
- Leia o valor calculado das fórmulas e trate #REF!, #DIV/0! e #N/D como erro — o número certo não existe.

## Engenharia de dados: cabeçalhos e estrutura
- Procure o cabeçalho de verdade: relatórios trazem título, data e filtros antes da tabela.
- Cabeçalho em duas linhas: use o grupo de cima só para diferenciar nomes repetidos (atendimento_nota, produto_nota).
- Células mescladas na vertical valem para todas as linhas do bloco.
- Abas com o mesmo cabeçalho são o mesmo dado (uma por mês): empilhe e registre a aba de origem.
- Abas diferentes (instruções, resumo) não entram, mas são citadas no relatório.
- Mesma informação com nomes diferentes em cada arquivo: declare **sinônimos** na regra, nunca renomeie no escuro.

## Qualidade de dados: limpeza
- Padronize nomes de colunas: minúsculas, sem acento, com "_".
- Números: aceite 1.234,56 / 1,234.50 / R$ / % / (negativo) — e avise quando um valor não puder ser convertido.
- Datas: aceite os formatos comuns e o número de data do Excel, mas só numa coluna que já é de datas.
- Códigos (CEP, matrícula, CPF) continuam texto: zero à esquerda é informação.
- Remova linhas de total e subtotal para não somar duas vezes — e confirme que "Total Express" é nome, não total.
- Duplicidade: defina a chave (ex.: id_resposta). Linha idêntica em tudo é removida; chave repetida com dados diferentes é erro.

## Qualidade de dados: validação
- Regras objetivas no config.yaml: colunas obrigatórias, tipos, faixas (nota de 0 a 10), não nulos e chave única.
- Qualquer erro reprova o arquivo inteiro: publicar metade de uma base é pior que não publicar.
- Conciliação: linhas lidas = linhas publicadas + linhas removidas com motivo.

## Modelagem para Power BI
- Modelo estrela: uma tabela fato (os eventos) e dimensões (quem, onde, quando).
- Relacionamento 1 para muitos, filtro em direção única, da dimensão para a fato.
- Toda chave da fato precisa existir na dimensão (integridade referencial).
- Tabela calendário contínua para análises de tempo.
- Prefira medidas DAX a colunas calculadas para números que somam ou fazem média.

## Banco de dados (PostgreSQL)
- Camadas: bruto (como veio), tratado (aprovado) e analítico (regras de negócio em SQL).
- Uma transação por arquivo: ou entra inteiro, ou nada entra.
- Reconcilie as contagens dentro do banco antes do commit.
- Consultas do painel são somente leitura e têm tempo máximo.
- Senha fora do arquivo: variável de ambiente ROBO_PG_SENHA.

## Análise de dados e estatística
- Todo indicador com base (n) e margem de erro.
- Base mínima de 30 respostas por segmento; entre 30 e 100, leia como tendência.
- Diferença "real" só com teste estatístico (95% de confiança) e correção para muitas comparações (Holm).
- Significativo não quer dizer importante: olhe também o tamanho da diferença.
- Correlação não prova causa.
- Compare cargas da mesma base ao longo do tempo para achar variações fora do normal.

## Pesquisa de mercado e Customer Insights
- NPS = % promotores (9–10) − % detratores (0–6). CSAT = top-2-box. CES = % que achou fácil.
- Escala escrita (Muito satisfeito… Muito insatisfeito) vira nota de 1 a 5 antes de calcular.
- Não pondere sem plano de ponderação definido antes da coleta.
- Questionário: objetivo, decisão, público, amostra, duração e hipóteses antes da primeira pergunta.
- Evite pergunta dupla, pergunta que induz e escala sem ponto neutro quando a neutralidade é legítima.

## Trade marketing
- Share sempre no mesmo período e recorte (loja, canal, região).
- Preço médio = faturamento ÷ unidades (nunca média simples de preços).
- Sell-in subindo com sell-out parado = estoque encalhando.

## Excel profissional
- Número calculado é fórmula viva, nunca valor colado.
- Toda entrega tem aba Conferência comparando cada fórmula com o valor recalculado.
- Formate todo número (milhar, %, decimal) e congele o cabeçalho das abas grandes.
- PROCX (ou ÍNDICE + CORRESP) no lugar de PROCV; SEERRO só quando o erro é esperado.

## Visualização e dashboards
- KPIs no topo, tendência no meio, detalhe embaixo (leitura em Z).
- Barras horizontais para comparar categorias; linhas para tempo; cascata para explicar variação.
- Evite pizza com mais de 3 fatias e gráficos 3D.
- Cor para destacar o que importa, não para enfeitar.

## Ciência de dados e machine learning
- Só modele com histórico limpo e chave estável (ex.: ID de cliente).
- Separe dados de treino e de teste; nunca avalie no mesmo dado que treinou.
- Comece pelo modelo mais simples que resolve (regressão logística antes de rede neural).
- Explique o modelo para o negócio: quais variáveis pesam e quanto ele erra.

## Segurança e LGPD
- Painel só na própria máquina; nenhum dado vai para a nuvem.
- Dado pessoal (e-mail, CPF, telefone) só é publicado quando há necessidade; senão, anonimize.
- Código novo de habilidade é revisado antes de rodar.
- Texto que começa com "=" nunca vira fórmula (proteção contra injeção de fórmulas).

## Operação, sprints e pessoas
- Sprint de 15 dias: cada pessoa conta o que fez, o que foi bom, o que travou e o backlog.
- Prioridade = impacto × urgência ÷ esforço; cada gerente assume as 3 prioridades do seu andar.
- Avaliação técnica e treinamento com planilhas difíceis a cada sprint.
- Estagiário trabalha em observação e tem 3 meses de experiência; só o dono promove.
- Problema achado em produção vira caso de treinamento, para nunca mais acontecer.
