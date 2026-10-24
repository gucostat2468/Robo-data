# Inventário de capacidades (auditoria de 24/10/2026)

Cada linha foi conferida no **código**, nos **testes** ou na **execução real da nuvem**. Os documentos antigos
(diagnostico_geral, diagnostico_reestruturacao, auditoria_arquitetura) não foram aceitos como verdade sem essa conferência.

Estado de partida: ramo `claude/robo-planilhas-etl-n5ckuc`, sem alterações locais, igual ao GitHub (commit `bccd97a`).
Python 3.13.16. 702 testes coletados antes deste ciclo; a suíte completa passou (702 passed) antes das mudanças.

## Legenda

| Classe | Significado |
|---|---|
| **Comprovada** | implementada, testada e vista funcionando na execução real |
| **Integrada sem prova** | ligada ao fluxo, mas sem prova operacional suficiente |
| **Parcial** | parte do requisito existe |
| **Não acionada** | existe, mas nada a dispara na operação atual |
| **Ausente** | não existe |
| **Bloqueada** | depende de credencial, hardware ou decisão do dono |

## 1. Funcionários e trabalho

| Capacidade | Classe | Evidência | Lacuna / próximo teste |
|---|---|---|---|
| 5 andares, 101 funcionários, cargos e ids | Comprovada | `robo/organizacao.py`, `robo/quadro.py`; boletim da nuvem lista os 101 | — |
| Trabalho do papel por função, com rodízio | Comprovada | `demandas.candidatas`/`escolher_ferramenta`; `teste_equipe_demandas.py`; turno 30: 92 de 101 no papel, 7 estagiários observando | 2 pessoas esperavam o próximo ciclo (limite de 20 por ciclo) |
| Bloqueio com motivo registrado | Comprovada | `demandas_registro` (evento `bloqueada`/`sem_trabalho`); boletim mostra o motivo | — |
| Quatro níveis (básico → profissional) | Integrada sem prova | `demandas.NIVEIS`, `TETO_DO_CARGO`; nível profissional compõe etapas (`demandas.py:576-590`) | medir no banco quantas demandas existem por nível e se o acerto cai com o nível |
| Revisão independente | Comprovada | `demandas_avaliacoes`: o avaliador nunca é o executor nem o revisor; `teste_demandas.py` | — |
| Estagiários só observam | Comprovada | `NIVEIS_SEM_DEMANDA`; `demandas.observar` grava a observação | — |
| Fábrica sintética com gabarito | Comprovada | `robo/fabrica.py`; boletim: 10 lotes no dia, 10 conferidos com o gabarito | — |
| Drivers (Ciência de Dados) com tarefa possível e gabarito | **Corrigida neste ciclo** | turno real: o drivers do Vinícius falhou; reproduzido aqui: a NPS da fábrica só tinha a nota, sem atributos — tarefa impossível, critério inadequado. Agora a fábrica gera notas de atributo com pesos conhecidos (`regras_negocio.PESOS_NPS`), o gabarito guarda a ordem verdadeira, a demanda só nasce com atributo e o critério `primeiro_driver` reprova ranking errado | `teste_demandas.py::teste_drivers_*` |
| Código de protocolo/matrícula tratado como driver | **Corrigida neste ciclo** | `ciencia.IGNORAR_TERMOS` | `teste_codigo_de_protocolo_nao_e_driver` |
| Treino nível 1–5 com sujeira real | Comprovada | `treino_casos.py`, `laboratorio.py`; achou defeito real da limpeza (cabeçalho repetido) | desafio aberto: valor "1.234,56*" |

## 2. PostgreSQL e persistência

| Capacidade | Classe | Evidência | Lacuna / próximo teste |
|---|---|---|---|
| Levantamento de cada tabela com causa da vazia | Comprovada | `robo/cobertura_banco.py` (contagem exata `COUNT(*)`, nunca estimativa); `teste_cobertura_banco.py` | — |
| Cobertura visível fora do computador | **Corrigida neste ciclo** | o levantamento da nuvem ficava só dentro da máquina do turno; agora vai no boletim (`boletim._banco`) | conferir no boletim do próximo turno |
| Causa da vazia `aprendizados_replay` | **Corrigida neste ciclo** | dizia "nada chama"; o replay roda todo dia (`licoes.replay_diario`) | teste atualizado |
| Fonte canônica | Parcial | SQLite (`logs/trabalho.db`) é a fonte; o PostgreSQL recebe espelho incremental idempotente (`ON CONFLICT DO UPDATE`, `memoria.sincronizar_postgres`) a cada 10 min e no fim do turno, mais o instantâneo do SQLite inteiro | atraso de até 10 min; ver plano em 6.3 abaixo |
| Nada apagável | Comprovada | gatilhos de imutabilidade (`trabalho.proteger`, `memoria.py:499`); `teste_registros_permanentes.py` | — |
| Separação real × sintético | Comprovada | schemas `treino`/`laboratorio` só para lotes `TREINO_*`; `teste_cobertura_banco.py` | — |
| Conta de leitura separada | Comprovada | `nuvem.garantir_leitura` dá só SELECT | — |
| Backup e restauração | Integrada sem prova | `backup.restaurar_sqlite`, `teste_backup.py`, `teste_restaurar_memoria.py`; a nuvem restaura a memória a cada turno | teste de restauração periódica com conferência de contagens |
| Inventário do Neon real | **Bloqueada para o assistente** | a URL do banco só existe nos segredos do GitHub (correto); a auditoria vê o banco pelo boletim | — |

## 3. Aprendizado e colaboração

| Capacidade | Classe | Evidência | Lacuna |
|---|---|---|---|
| Erro → handover (recorrência e reabertura) | Comprovada | `memoria.handover` soma recorrência e reabre se o erro volta; histórico imutável `evento_handover` | — |
| Lição para os colegas da área | Comprovada | `treino.colegas_que_aprendem`; na nuvem, 526 lições novas em um ciclo de teste | medir reincidência por lição |
| Replay de regressão | Comprovada | `licoes.replay_diario` → `aprendizados.replay` | vazio sem planilha barrada guardada |
| Conversas só com fato | Comprovada | `dialogo.py` (conversa nasce de fato), `teste_dialogo.py` | — |
| IA não inventa número | Comprovada | `ia.numeros_inventados` barra número que não está nos fatos | — |

## 4. IA local

| Capacidade | Classe | Evidência | Lacuna |
|---|---|---|---|
| Ollama / provedores opcionais | Integrada, desligada por padrão | `robo/ia.py`: timeout, 1 nova tentativa, disjuntor (3 falhas = 10 min) | **Bloqueada**: o Ollama precisa ser instalado no notebook do dono; medir RAM antes de escolher o modelo |
| Fila compartilhada e limite de concorrência | Ausente | chamadas diretas | criar só quando a IA for ligada (hoje ninguém a usa na nuvem) |

## 5. Celular

| Capacidade | Classe | Evidência | Lacuna |
|---|---|---|---|
| PWA local (manifesto, service worker versionado, offline honesto, ícones) | Comprovada no código | `robo/painel/estaticos/` (`service-worker.js` `robo-celular-v1`, `offline.html`); `teste_celular_app.py` | só funciona com o notebook ligado e na mesma rede |
| Acompanhamento sem o PC | Comprovada | boletim a cada 5 min no ramo `painel-celular` + app do Claude + README no GitHub | **não é tempo real**: atraso de até 5 min, e entre turnos a empresa para (o boletim diz isso) |
| Tempo quase real (≤ 5 s) | Ausente | exige um backend sempre ligado com HTTPS | **Bloqueada por decisão do dono**: servidor contínuo custa ou exige o notebook ligado; não foi criado nada pago |
| Login do painel | Comprovada | `painel/acesso.py`: PBKDF2, cookie HttpOnly/SameSite, trava contra força bruta | — |

## 6. Qualidade contínua

| Capacidade | Classe | Evidência | Lacuna |
|---|---|---|---|
| Testes automáticos a cada mudança | **Ausente → criada neste ciclo** | só existia o workflow dos turnos; agora `.github/workflows/testes.yml` (sintaxe + importação + suíte completa com PostgreSQL descartável) | os testes do Airflow ficam de fora no GitHub (o resumo do job mostra quantos) |

## Plano gradual para o PostgreSQL ser a fonte (6.3)

Não foi feito de uma vez de propósito: trocar a fonte de verdade num patch só arrisca perder registro.

1. **Feito:** o espelho é idempotente (`ON CONFLICT`) e o turno salva ao receber SIGTERM.
2. **Próximo:** gravar no PostgreSQL logo após cada demanda concluída (não só a cada 10 min), com fila durável no
   SQLite para quando o banco cair, e reconciliação de contagens por tabela no fim do turno.
3. **Depois:** leitura do app pelo PostgreSQL via uma API do backend (nunca direto do celular).

## Backlog ordenado (impacto × risco)

1. Conferir no boletim real a cobertura de tabelas e tratar cada "sem causa registrada".
2. Medir demandas por nível e taxa de acerto por nível (prova de que o nível difícil é mais difícil).
3. Persistência imediata no PostgreSQL por demanda concluída + reconciliação (passo 2 acima).
4. Desafio "1.234,56*" na limpeza.
5. IA local: medir o notebook do dono (precisa dele).
6. Backend contínuo para tempo quase real (precisa da decisão de custo do dono).
