# Guia completo do Robô de Planilhas

Este guia explica o projeto **arquivo por arquivo e função por função**, com o intervalo de linhas de cada trecho,
em linguagem para quem está começando em programação. São cerca de 5.400 linhas, divididas em 5 partes:

| Parte | Arquivo | O que cobre |
|---|---|---|
| 1 | [01_entrada_e_tratamento.md](01_entrada_e_tratamento.md) | Como o robô liga, vigia a pasta, lê, limpa, valida, modela, publica e registra cada planilha |
| 2 | [02_banco_de_dados.md](02_banco_de_dados.md) | PostgreSQL em camadas (ELT), consultas SQL prontas e backup |
| 3 | [03_equipe_e_organizacao.md](03_equipe_e_organizacao.md) | Agentes, as 26 habilidades, RH e provas técnicas, quadro de pessoal, contratação, TI, treinamento e estratégia |
| 4 | [04_analise_excel_canal.md](04_analise_excel_canal.md) | Análise estatística (2º andar), Sala Excel (3º andar), canal da equipe, calculadora e central de dados |
| 5 | [05_painel_3d_windows_testes.md](05_painel_3d_windows_testes.md) | Painel, escritório 3D, instalação no Windows e testes automáticos |

## Como ler
- Comece pela Parte 1. Ela segue uma planilha desde que cai em Bases-Limpeza até ser publicada; o resto encaixa nela.
- Cada arquivo começa com **Para que serve** e **Onde entra no fluxo**; depois vêm as funções na ordem do arquivo.
- Cada termo técnico é explicado na primeira vez em que aparece.

## Visão geral em uma página

1. **Ligar.** `Abrir Robo de Planilhas.vbs` → `python -m robo app` → `robo/comandos.py` liga o log e o painel
   (`robo/painel/servidor.py`, só em 127.0.0.1:8799).
2. **Vigiar.** `robo/monitor.py` olha Bases-Limpeza; o arquivo só entra quando parou de mudar e não está aberto.
3. **Tratar.** `robo/pipeline.py` (o maestro) chama, em ordem: leitura → limpeza → agentes → validação →
   modelagem → conferências de produção → banco → checklist da coordenadora → publicação → releitura.
4. **Depois de publicar.** Análise (2º andar), entrega Excel (3º), governança (4º) e contratação automática.
5. **Registrar.** Histórico (CSV + JSON por execução), relatório de qualidade e, se reprovado, `_ERROS.txt`.
6. **Rotinas.** Canal (a cada minuto), ronda de TI (30 min), backup do banco (diário), avaliação técnica e
   treinamento (a cada sprint de 15 dias).

## Sobre os números de linha
O guia foi escrito em cima do código de 17/10/2026. Depois dele, a própria revisão encontrou defeitos que foram
corrigidos (lista abaixo). Nos arquivos alterados por essas correções, alguns intervalos de linha podem estar
deslocados em poucas linhas; o conteúdo explicado continua o mesmo.

## Defeitos encontrados pela revisão do guia (e já corrigidos)
- **Grave:** abas empilhadas + PostgreSQL faziam a carga do bruto entrar em laço infinito.
- Histórico aberto no Excel fazia o registro falhar; agora vai para uma fila e entra depois.
- Republicação reprovada apagava a versão boa anterior; agora ela é restaurada.
- Formato de saída inválido fazia o robô tentar para sempre; agora reprova com explicação.
- Arquivo somente leitura nunca era processado.
- Habilidade sem prova técnica passava no RH; agora bloqueia.
- Nota NPS 11 mantida no modo "aviso" virava promotor; agora não é classificada.
- Habilidade personalizada podia substituir uma nativa.
- Calculadora lia 8.5 como 85; filtro ">" em texto virava igualdade.
- Canal respondia "quantos erros tivemos" com cálculo; agora responde com os erros.
- Painel: tamanho de requisição negativo, "abrir arquivo" amplo demais, upload interrompido processado.

## Pontos conhecidos que continuam abertos (registrados, não críticos)
- `.xls` antigo é lido pelo pandas: não detecta células mescladas nem erros de fórmula como o `.xlsx`.
- O modo "Testar planilha" (diagnóstico) não roda as conferências de produção; pode aprovar algo que a produção barra.
- Agentes das fases "validação" e "modelagem" rodam depois das regras do YAML.
- Consultas SQL que fazem conta com datas podem falhar quando a coluna de data também tem hora.
- O painel ainda não tem senha (qualquer pessoa logada no Windows consegue abri-lo).
