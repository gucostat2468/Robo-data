# Manual do trabalho de cada ferramenta (consultado pelo nome exato da ferramenta; fica fora da busca geral)

Uma seção por trabalho da empresa. Cada uma diz o método, quando o trabalho está pronto, os erros mais comuns e
como conferir. O texto descreve o que a ferramenta faz de fato no código (robo/ferramentas.py e os módulos que ela
chama): se a ferramenta não faz alguma coisa, a seção diz que não faz.

## Diagnosticar planilha: Pipeline em modo diagnóstico + conferências do 1º andar
- **Método:** roda a esteira inteira sem gravar (leitura, cabeçalho real, limpeza, tipos, validação), e o 1º andar
  confere o resultado. Nada vai para Bases-Tratadas: é um diagnóstico.
- **Pronto quando:** diz se a planilha seria aprovada, quantas linhas sairiam e cada erro com a linha do Excel.
- **Erros comuns:** contar Total, Subtotal, rodapé ou cabeçalho repetido como dado (inflam a contagem); aprovar
  planilha com #REF!/#DIV/0! (o número certo não existe e ela tem que ser barrada).
- **Como conferir:** linhas de saída = linhas de dado do arquivo menos duplicatas exatas; nenhuma célula de erro de
  fórmula aprovada.

## Calcular: Cálculo sobre base publicada ou arquivo da conversa
- **Método:** entende a pergunta (soma, média, mediana, NPS, contagem; "por" um ou dois segmentos; filtros "onde
  coluna = valor"), limpa a base pelo mesmo caminho da esteira e calcula em pandas.
- **Pronto quando:** devolve a tabela de valores por grupo e diz qual base e qual coluna usou.
- **Erros comuns:** grupo que não existe (cabeçalho repetido virando categoria); média com vazios contados como zero;
  NPS com nota fora de 0–10 ou com o código 99 ("não sabe") dentro da base.
- **Como conferir:** refazer a conta por outro caminho (laço simples) a partir da base limpa; os grupos têm que ser
  exatamente os da coluna de segmento.

## Perfil e indicadores: Perfil das colunas, NPS/CSAT/CES com margem e testes
- **Método:** perfil de cada coluna (tipo, vazios, distintos) e os indicadores de pesquisa: NPS = % promotores (9–10)
  menos % detratores (0–6), com neutros (7–8) no denominador; margem de erro e base n.
- **Pronto quando:** cada indicador vem com a base (n) e a margem; base pequena (n < 30) vem com aviso.
- **Erros comuns:** tirar neutros do denominador; tratar 99 como nota; destacar diferença entre segmentos sem teste.
- **Como conferir:** recontar promotores, neutros e detratores na base limpa e refazer a fórmula.

## Verificar dados pessoais: Procura e-mail, CPF e telefone (LGPD)
- **Método:** varre colunas e textos livres atrás de e-mail, CPF (com dígito verificador) e telefone.
- **Pronto quando:** lista as colunas com dado pessoal e onde está cada achado.
- **Erros comuns:** chamar de CPF um número com dígito verificador inválido (isca); não ver e-mail escondido no meio
  de um comentário.
- **Como conferir:** validar o dígito verificador de cada CPF achado; procurar "@" nos textos livres.

## Drivers do indicador: O que mais influencia NPS/CSAT (correlação, regressão, VIF)
- **Método:** correlação de cada variável com o indicador, regressão e VIF para não confundir variáveis parecidas.
- **Pronto quando:** devolve a ordem dos drivers com o tamanho do efeito.
- **Erros comuns:** tratar correlação como causa; ignorar variáveis colineares (VIF alto).
- **Como conferir:** o 1º driver tem que se manter quando se tira a variável colinear.

## Segmentação: Grupos de clientes parecidos (k-means com silhueta)
- **Método:** padroniza as colunas e roda k-means para vários k; escolhe o k pela silhueta.
- **Pronto quando:** devolve o número de grupos e o perfil de cada um.
- **Erros comuns:** achar um grupo a mais quando os grupos estão próximos (silhueta parecida entre dois k); deixar
  uma coluna de ruído pesar igual às outras.
- **Como conferir:** a silhueta do k escolhido tem que ser claramente maior que a do vizinho; perfis distintos.
- **Limite conhecido:** com grupos muito próximos (treino nível 5) a escolha do k ainda erra às vezes.

## Anomalias: Valores fora do padrão com a linha de origem
- **Método:** regra de Tukey (fora de 1,5 × IQR além dos quartis) por coluna numérica, com a linha do Excel.
- **Pronto quando:** lista cada valor fora do padrão com a linha de origem, sem excluir nada.
- **Erros comuns:** excluir o valor em vez de marcar; não olhar anomalias para baixo.
- **Como conferir:** recalcular quartis e limites e conferir cada linha apontada.

## Consulta SQL: Consulta da biblioteca em transação somente leitura
- **Método:** roda uma consulta da biblioteca (consultas_sql/) ou um SQL livre de leitura, em transação somente
  leitura, com tempo limite de 60 s.
- **Pronto quando:** devolve as linhas e diz que nada foi alterado.
- **Erros comuns:** consulta sobre tabela que ainda não tem dado (a tela mostra ○ e o motivo); SQL com comando que
  altera dados (é recusado).
- **Como conferir:** a mesma consulta devolve o mesmo resultado rodando de novo; a transação é sempre desfeita.

## Exercício de SQL: Consulta no PostgreSQL sobre um lote da fábrica, conferida contra o gabarito
- **Método:** quatro níveis sobre um lote real do schema treino: contagem; soma, média e NPS; GROUP BY com
  participação por janela; reconciliação bruto × tratado × registro da carga com CTE.
- **Pronto quando:** o resultado do banco bate com o gabarito do lote.
- **Erros comuns:** contar o lote bruto em vez do tratado; esquecer o filtro do arquivo de origem.
- **Como conferir:** linhas tratadas = gabarito; brutas = registro da carga.

## Teste de restauração do backup: Restaura o último backup numa pasta temporária e confere integridade e tabelas
- **Método:** descompacta o backup mais novo, roda o integrity_check e compara o número de tabelas com o banco vivo.
- **Pronto quando:** diz se o backup volta inteiro.
- **Erros comuns:** confiar num backup antigo demais (muito menos tabelas que o banco vivo).
- **Como conferir:** integridade "ok" e diferença de tabelas pequena.

## Prontidão para servidor: Dockerfile, porta por variável, segredos fora do repositório
- **Método:** confere Dockerfile, usuário sem root, porta pela variável PORT, turno da nuvem e config.yaml fora do
  repositório.
- **Pronto quando:** cada item aparece com sim ou não.
- **Como conferir:** ler o Dockerfile (linha USER) e o .gitignore.

## Saúde do PostgreSQL: Espaço contra o limite, linhas mortas, conexões e consultas presas
- **Método:** mede o tamanho do banco contra o limite do plano gratuito, tabelas com muitas linhas mortas, conexões e
  consultas paradas há mais de 5 minutos. Só lê.
- **Erros comuns:** esquecer que o plano gratuito tem limite (alerta com 80%).

## Segredos no repositório: Senha, token e chave escritos nos arquivos do projeto
- **Método:** procura URL de banco com senha, token do Telegram, chave de API e senha escrita nos arquivos
  versionados. Mostra arquivo e linha, nunca o segredo.
- **Erros comuns:** acusar molde de documentação (usuario:senha@host) como segredo.

## Ronda de TI: Verificações de saúde do computador e do robô
- **Método:** cada pessoa do 5º andar roda a sua verificação (disco, pastas, dependências, segurança, logs, SLA,
  backup, nuvem). Só o achado de quem não é estagiário conta como crítico.
- **Pronto quando:** diz o que está verde e o que precisa de ação, com o responsável.

## SLA das rotinas (Airflow): Rotinas atrasadas, com erro ou lentas, pelos registros
- **Método:** atrasada = sem verificação há mais de 1,5 × o intervalo; com erro = a última execução falhou; lenta =
  muito acima do tempo normal dela.
- **Erros comuns:** alarme falso para erro já resolvido (a execução seguinte deu certo), lentidão antiga ou rotina com
  histórico curto.

## Desempenho: Acertos, erros e situação de cada pessoa
- **Método:** conta acertos e erros dos últimos 7 dias e aplica a exigência de cada cargo.
- **Erros comuns:** contar experiência que não é acerto nem erro; usar janela errada.

## People analytics: Indicadores de pessoas
- **Método:** quadro por andar e nível, aprovação nas provas técnicas e trabalho registrado por pessoa.

## Recrutamento e seleção: Contratações, experiências e efetivações
- **Método:** vagas abertas, pessoas em experiência de 3 meses e decisões de efetivação.

## Treinamento e desenvolvimento: Rodada de estudo e planos 70-20-10
- **Método:** quem errou na semana ganha plano 70-20-10 (70% prática, 20% com colega, 10% estudo).

## Revisão de biblioteca: Guardas de comportamento de pandas, numpy, openpyxl…
- **Método:** cada especialista roda as guardas da biblioteca dele (comportamentos que, se mudarem numa versão nova,
  quebram a esteira).

## Revisar caso de treino: Integridade, reprodutibilidade e conferência de um caso
- **Método:** confere três coisas: o conteúdo é o mesmo que foi gravado (sha), gerado de novo pela semente sai igual,
  e o gabarito confere por outro caminho. Ninguém revisa o caso que criou.
- **Erros comuns:** reusar caso cuja verdade mudou (janela de dias, quadro de pessoas, rotinas novas): deve ser
  encerrado, não usado.

## Reunião ao vivo: Situação de agora do andar: certo, errado, andamento, plano e PDCA
- **Método:** junta o que deu certo, errado, o que está em andamento e o plano de ação com responsável e prazo.

## Scorecard da diretoria: Indicadores da área com meta e farol
- **Método:** indicadores da área calculados dos registros, com meta e farol (verde, amarelo, vermelho).

## Auditoria por amostragem: O head refaz por outro caminho uma amostra das entregas
- **Método:** sorteia entregas da semana e refaz por outro caminho; divergência vira achado.

## Estratégia Python: Desempenho por volume, projeção e dívida técnica
- **Método:** mede o tempo da esteira por volume de linhas, projeta para volumes maiores e lista dívida técnica.

## Raio-X da empresa: Como a empresa está agora, com números de todos os registros
- **Método:** resumo de todos os registros (treino, demandas, rotinas, lições), sem estimativa.

## Organização: Quem faz o quê, por andar e nível
- **Método:** lê o quadro único de funcionários: andar, nível, área e trabalho do papel.

## Ideias para o futuro: Propostas tiradas da memória de todos, com o dado de origem
- **Método:** lê a memória da empresa (erros que se repetem, lições, handovers) e propõe melhorias, cada uma com o
  registro que a originou.
- **Pronto quando:** toda ideia cita o dado de origem; ideia sem dado de origem não entra.
