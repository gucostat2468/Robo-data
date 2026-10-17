# Auditoria de arquitetura — Robô de Planilhas

Data: 17/10/2026 · Base auditada: branch `claude/robo-planilhas-etl-n5ckuc`, commit `930b97d`.
Método: leitura do código, execução dos 183 testes (todos passando), execução real do pipeline com PostgreSQL 16,
navegação do painel em navegador automatizado e revisão linha a linha em 5 partes (ver `documentacao/guia/`).

Classificação: **[1] implementado e comprovado · [2] implementado parcialmente · [3] existe, mas não está integrado · [4] ausente.**

## 1. Capacidades atuais

| Capacidade | Classe | Evidência |
|---|---|---|
| Pipeline ETL de planilhas (ler → limpar → validar → modelar → publicar) | [1] | `robo/pipeline.py::processar_arquivo`; testes `teste_pipeline.py`, `teste_limpeza.py`, `teste_leitura.py`; 17/17 casos difíceis em `teste_treinamento.py` |
| ELT no PostgreSQL (bruto/tratado/analítico, transação por arquivo, reconciliação) | [1] | `robo/banco.py`; `teste_banco.py` contra PostgreSQL real (9 testes) |
| Portão de produção (supervisor, quadro, checklist, releitura) | [1] | `robo/producao.py`, `robo/quadro.py::conferir`; `teste_quadro.py`, `teste_producao.py`, `teste_robustez.py` |
| Análise (NPS/CSAT/CES com margem, testes, monitoramento) | [1] | `robo/analise.py::analisar`; `teste_analise.py` |
| Entrega Excel auditável com aba Conferência | [1] | `robo/excel.py`; `teste_excel.py` recalcula no LibreOffice |
| RH: fichas, níveis, provas técnicas | [1] | `robo/rh.py::processo_seletivo`; `teste_rh.py` |
| Contratação automática de estagiários e experiência de 3 meses | [1] | `robo/contratacao.py`; `teste_contratacao.py` |
| Ronda de TI, backup do banco | [1] | `robo/ti.py`, `robo/backup.py`; `teste_ti.py`, `teste_backup.py` |
| Central de dados e Estratégia (backlog, alinhamento, avaliações, treinamentos) | [1] | `robo/central.py`, `robo/estrategia.py`; `teste_estrategia.py` |
| Escritório 3D refletindo eventos reais do pipeline | [1] | `controle._registrar_etapa` → `/api/escritorio` → `escritorio.js::iniciarEvento` |
| Canal da equipe (mensagens, filtros, sprint, boletim) | [2] | `robo/canal.py`. **Cada mensagem é respondida isoladamente:** `Canal.perguntar` (linha 172) chama `responder(texto, cfg)` sem histórico. Não há conversa com contexto, correções nem arquivo associado |
| Conversa direta com um funcionário | [2] | Só por "chamar pelo nome" no canal (`responder`, detecção de nome). A ficha (`painel.js::abrirPessoa`) não tem "pedir ajuda"; a resposta é uma apresentação genérica (`_resposta_pessoal`) |
| Calculadora sobre bases publicadas | [1] | `robo/calculos.py`; `teste_calculos.py` |
| Memória episódica (o que aconteceu) | [2] | Histórico CSV + JSON por execução (`robo/historico.py`), canal em JSONL. Não há registro de decisões, aprovações nem de tarefas do dono |
| Memória semântica/procedural (conhecimento reaproveitável) | [2] | `conhecimento/*.md`, manuais `agentes/<id>.md`, base fixa `canal.CONHECIMENTO`. Não há "solução aprovada" reaproveitável por tarefa |
| Contrato de execução por funcionário | [2] | Fichas em `rh.FICHAS`, `quadro.QUADRO`, `ti.EQUIPE_TI`: cargo, nível, responsabilidades, limites. **Faltam:** ferramentas autorizadas, entradas e saídas aceitas, regras de encaminhamento e critérios de pedir ajuda |
| Backlog de prioridades da sprint | [2] | `robo/estrategia.py`: os itens têm estado, mas **ninguém executa um item**; é só um quadro de acompanhamento |
| Rotinas automáticas (canal, TI, backup, estratégia) | [2] | Rodam dentro de `controle._laco` (linha 114). **Param quando o dono pausa o monitoramento** |
| Central de solicitações do dono (registro de todo pedido, com estados) | [4] | Não existe no código. `documentacao/pedidos_do_dono.md` é um documento manual |
| Orquestração (plano → etapas → dependências → execução → revisão → entrega) | [4] | Nenhum módulo transforma um objetivo em etapas executáveis. O único "executor" é o pipeline de planilhas |
| Aprovações do dono para ações de risco | [4] | Não há fila de aprovações. O risco por nível só existe para as habilidades (`rh.risco_de`) |
| Integração com modelo de linguagem (IA) | [4] | Nenhuma referência no código, por decisão anterior do dono ("sem API") |
| Senha no painel | [4] | `servidor.py` não tem autenticação |

## 2. Problemas estruturais

| Problema | Evidência | Risco |
|---|---|---|
| **Sem registro único de funcionários.** A lista de pessoas é montada em 4 módulos diferentes | `servidor.py` (9 referências), `canal.pessoas`, `quadro.lotacao`, `estrategia.avaliar_todos` (6 cada) | Contratar ou mudar alguém exige editar vários lugares; já gerou divergência (líder do 5º andar em dois valores, corrigido) |
| **Dependências circulares contornadas por imports locais** | 125 `from robo …` dentro de funções (rh: 29, servidor: 46, estrategia: 18, canal: 15) | Erro só aparece em tempo de execução; dificulta testar módulos isolados |
| **Persistência espalhada em arquivos JSON/JSONL** | canal (`mensagens.jsonl`), estratégia (`backlog.json`), contratação, TI, treinamento, catálogo | Sem transações entre registros relacionados; cada módulo com a sua trava |
| **Animação ociosa nas rondas do 3D** | `escritorio.js` linha 988: coordenadores caminham pela ronda mesmo sem evento | Pode parecer trabalho; precisa ser identificado como "de plantão" (já é o rótulo da lista, mas não na cena) |
| **Diagnóstico ≠ produção** | `pipeline.py`: o modo diagnóstico para antes do portão de produção | "Testar planilha" pode aprovar algo que a produção barra |
| **Desempenho** | `/api/escritorio` relê até 3.000 linhas do histórico a cada segundo; 100 mil linhas levaram 154 s no pipeline completo | Histórico grande deixa o painel pesado |
| **Segurança** | Sem autenticação; habilidades personalizadas executam código | Qualquer usuário do Windows abre o painel |
| **Lacunas de teste** | Não há teste automático do JavaScript (painel e 3D); nunca rodou no Windows real | Regressões de interface só aparecem em uso |
| **Documentação × código** | O guia foi escrito antes de várias correções; alguns números de linha estão deslocados | Baixo |

## 3. Decisões de arquitetura para a evolução

1. **Registro único de funcionários com contrato de execução** (`robo/organizacao.py`). Ele é montado a partir das
   fontes atuais (nativos, quadro, TI, canal, contratados), sem mudar nomes, cargos nem andares. Os módulos que hoje
   montam listas passam a consultá-lo.
2. **Uma única infraestrutura de trabalho** (`robo/trabalho.py`) para **conversas**, **tarefas** e **projetos**,
   usada pela ficha, pelo canal, pela central de solicitações, pelo contexto de um arquivo e pelo acompanhamento
   de uma tarefa. Nada de cinco chats.
3. **Persistência do trabalho em SQLite** (`logs/trabalho.db`). Motivo: o SQLite vem com o Python, tem transações
   ACID e funciona sem o PostgreSQL. O PostgreSQL é opcional e não pode ser o único lugar do histórico do dono.
   O PostgreSQL continua sendo o lugar dos **dados** (ELT).
4. **Orquestrador determinístico**: objetivos reconhecidos viram planos com etapas, dependências, responsáveis,
   riscos e aprovações. Cada etapa chama uma **ferramenta real** (pipeline em diagnóstico, análise, entrega Excel,
   verificação de dados pessoais, cálculo, consulta SQL somente leitura, ronda de TI). Uma etapa sem ferramenta
   fica bloqueada com a explicação; ela nunca é "concluída" de mentira.
5. **Toda resposta declara a sua natureza**: conhecimento registrado, cálculo determinístico, execução de código,
   ferramenta, hipótese ou "precisa de confirmação".
6. **IA opcional e honesta** (`robo/ia.py`): um adaptador que hoje reporta "nenhum modelo configurado". Quando houver
   modelo, ele só redige texto; cálculos continuam determinísticos.
