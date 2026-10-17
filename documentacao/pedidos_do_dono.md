# Pedidos do dono — acompanhamento

Todo pedido feito na conversa, com a situação real. Atualizado em 17/10/2026.
Legenda: ✅ feito e testado · 🟡 feito em parte · ⏳ pendente

| # | Pedido | Situação | Onde está |
|---|---|---|---|
| 1 | ETL automático de Bases-Limpeza para Bases-Tratadas, só sem erros, tudo em Python, local | ✅ | `robo/pipeline.py` e etapas |
| 2 | App de uso próprio, sem nuvem (EC2 etc.) | ✅ | tudo roda em 127.0.0.1 |
| 3 | Interface gráfica caprichada (UI/UX) | ✅ | `robo/painel/` |
| 4 | PostgreSQL (ELT) | ✅ | `robo/banco.py` |
| 5 | Onde colocar o PostgreSQL real | ✅ | Configurações → Banco de dados; variável `ROBO_PG_SENHA` |
| 6 | Ver funcionando em tempo real | ✅ | vídeo enviado; Central de dados ao vivo |
| 7 | 2º andar no escritório, navegação fluida entre andares | ✅ | `escritorio.js` (hoje 5 andares) |
| 8 | RH profissional, meritocracia técnica, sêniores que contratam pleno/júnior/estagiário | ✅ | `robo/rh.py`, `robo/quadro.py` |
| 9 | Canal com a equipe, filtros e caixa de texto que entende o dono | ✅ | `robo/canal.py`, página Canal |
| 10 | Sprint de 15 dias (feito, bom, travou, backlog) | ✅ | canal + página Estratégia |
| 11 | Alguém para dar ideias | ✅ | Iara (`canal.ideias`) |
| 12 | Supervisor de planilhas, pessoa do PostgreSQL, coordenadores conferindo antes da produção | ✅ | `robo/producao.py` |
| 13 | Organização com boas práticas de engenharia, análise e ciência de dados | ✅ | `conhecimento/boas_praticas.md`, aba Boas práticas |
| 14 | Sala Excel de especialistas (trade e pesquisa) com supervisor ex-Microsoft que responde no chat e coordena a limpeza | ✅ | `robo/excel.py`; Ricardo barra o que o Excel corromperia |
| 15 | Sem API, sem internet, nenhum agente dormindo | ✅ | canal offline; estado "de plantão" |
| 16 | Falar em português | ✅ | — |
| 17 | Repositório e arquivos com nomes em português | 🟡 | tudo renomeado; o nome do repositório no GitHub ("Robo-data") só pode ser trocado por você em Settings |
| 18 | Todos os andares lotados, do gerente ao estagiário, com escopo por senioridade | ✅ | 5 andares, 52 pessoas no quadro + contratados |
| 19 | Andares contratando sempre, com habilidades e manuais .md, também de forma automática | ✅ | `robo/contratacao.py`, página Equipe |
| 20 | Andar de TI, AWS, dev, DevOps, infra e segurança | ✅ | `robo/ti.py` (AWS consultiva, sem nuvem) |
| 21 | Quais linguagens, se é seguro, se é produto profissional | ✅ | respondido na conversa e no guia |
| 22 | Líderes com autonomia para contratar estagiários; experiência de 3 meses | ✅ | `contratacao.avaliar_experiencias` |
| 23 | Painel de dados em tempo real (erros, acertos, planilhas erradas) | ✅ | página Central de dados |
| 24 | Estratégia: sprints com prioridades alinhadas, testes técnicos e treinamentos | ✅ | página Estratégia |
| 25 | Equipe preparada para qualquer cálculo, cabeçalho, variável, segmentação, erro | ✅ | centro de treinamento (17 casos difíceis), calculadora |
| 26 | Explicação de tudo, linha por linha | ✅ | `documentacao/guia/` |
| 27 | Texto único descrevendo o projeto (para outra IA) | ✅ | enviado na conversa |
| 28 | Senha no painel | ⏳ | oferecido; ainda não feito |
| 29 | Backup automático do banco | ✅ | `robo/backup.py` |
| 30 | Teste de volume | 🟡 | 100 mil linhas em 154 s (ok); 300 mil interrompido por reinício da máquina de testes |
| 31 | Rodar no Windows do dono | ⏳ | depende de você: `instalar.bat` |
