# Inteligência própria: o primeiro modelo de ML da empresa

## O que existe agora (conferido em código e testes)

| Peça | Onde | Prova |
|---|---|---|
| Equipe de AI Engineering (4 papéis, dentro dos 5 andares) | `robo/lideranca.py` | provas técnicas no RH (`lideranca.provas`) |
| Ciclo de vida do modelo | `robo/modelos_ml.py` | `testes/teste_modelos_ml.py` (11 testes) |
| Rotina `modelos` (sombra, monitoramento, retreino, avaliação, promoção) | `robo/rotinas.py`, fluxo `robo_horario` | roda nos turnos da nuvem |
| Demandas do papel para os 4 | `robo/demandas.py` (`ml_treinar`, `ml_avaliar`, `ml_registro`, `ml_portfolio`) | `teste_ferramentas_da_equipe_rodam_com_contrato` |
| Boletim do celular e `python -m robo modelos` | `robo/boletim.py`, `robo/comandos.py` | `teste_boletim_mostra_a_inteligencia_propria_sem_inventar` |

**Sem biblioteca nova.** A regressão logística está escrita em numpy, que já vem com o pandas. scikit-learn e PyTorch
só entram quando um caso de uso provar que precisam. Deep learning não foi adicionado: não há ainda dado nem caso que
mostre vantagem sobre um modelo simples.

## A equipe (ninguém aprova o próprio trabalho)

| Quem | Cargo | Andar | Responde a | Faz | Não faz |
|---|---|---|---|---|---|
| Rebeca | Líder de Engenharia de IA e ML | 2º | Rogério (diretor de Analytics) | backlog de modelos, critérios de promoção | não treina, não aprova |
| Leandro | Engenheiro de ML Sênior | 2º | Rebeca | dataset versionado, baseline, candidato, experimento | não avalia nem promove o próprio modelo |
| Fabiana | Engenheira de Avaliação e Segurança de IA | 4º | head de Governança | refaz as métricas do arquivo e do dataset, por outro caminho, e decide | não avalia o que treinou, não promove |
| Jonas | Engenheiro de MLOps | 5º | Henrique (Python) | checksums, promoção do aprovado, sombra, monitoramento, rollback | não promove sem aprovação de outra pessoa |

A Natália, o Vinícius, a Carolina e o Lucas continuam com a estatística aplicada (drivers, segmentação, anomalias). A equipe
nova não duplica o trabalho deles: ela cuida de modelos que **aprendem parâmetros** com os registros da empresa.

## O 1º caso de uso: risco de a demanda não ser concluída

- **Alvo:** a demanda sintética termina parcial ou com falha. O rótulo vem dos critérios de aceitação
  determinísticos e da revisão independente. Estudo por bloqueio fica de fora.
- **Atributos:** só o que se sabe quando a demanda nasce: ferramenta, nível, andar, senioridade, nº de etapas e o
  histórico de falhas da pessoa e da ferramenta **até aquele momento**. Sem vazamento: o teste
  `teste_sem_vazamento_e_corte_temporal` confere.
- **Corte temporal:** os 70% mais antigos treinam, os 15% seguintes escolhem o ajuste e os 15% mais novos dão a nota final.
- **Baseline:** taxa de falha por ferramenta × nível no treino (suavizada).
- **Métricas:** log loss, Brier e AUC. O avaliador confere a AUC por um 2º método (todos os pares).

### Critérios para aprovar (`CRITERIOS`)

| Critério | Regra |
|---|---|
| Dados mínimos | 60 demandas rotuladas; teste com 20 ou mais |
| Bater o baseline | log loss do candidato menor que o do baseline no teste |
| Bater a referência atual | log loss menor que o do modelo em uso no mesmo teste |
| Separação mínima | AUC de 0,55 ou mais |
| Reprodutível | retreinar com os mesmos dados dá os mesmos pesos |
| Íntegro | checksums do artefato e do dataset conferem |

### Estados do modelo (derivados dos eventos, nada se altera nem se apaga)

`candidato` → `aprovado` ou `reprovado` → `referencia` → `substituido` (ou de volta a `referencia` por rollback).

### Uso: SOMBRA

O modelo de referência pontua cada demanda **nova**, isto é, nascida depois do dataset dele. O resultado vai para
`ml_inferencias`, e o monitoramento compara o previsto com o que aconteceu. **Nenhuma decisão da empresa usa esse
número.** Ligá-lo a uma escolha real (por exemplo, dar revisão extra às demandas de alto risco) é decisão do dono.

## Tabelas (todas só de inclusão e espelhadas no PostgreSQL pela cópia da memória)

`ml_datasets`, `ml_experimentos`, `ml_modelos`, `ml_modelos_eventos`, `ml_inferencias`. Os arquivos (dataset e pesos)
ficam em `logs/ml/`; o banco guarda o caminho, o checksum e a linhagem (dataset → experimento → modelo → eventos).

## O que isto NÃO é

- Não é a memória da empresa (lições, handovers): aquilo recupera conhecimento; isto aprende parâmetros.
- Não é um modelo de linguagem. A conversa natural continua dependendo da IA opcional (`robo/ia.py`, desligada por
  padrão). Sem ela, o trabalho das ferramentas e dos modelos segue igual.

## Backlog do líder (estado real)

| Caso | Estado | Por que ML |
|---|---|---|
| risco_demanda | implementado (sombra) | depende da combinação de ferramenta, nível, pessoa e histórico |
| proximo_treino | planejado | precisa medir antes e depois de cada intervenção |
| classe_de_erro | planejado | texto livre; começar por palavras-chave e regressão, antes de rede neural |
| atraso_rotina | em espera | poucos atrasos registrados: uma regra (SLA) resolve melhor por enquanto |

Caminho de longo prazo, nesta ordem: modelos especializados → ajuste fino de modelo aberto (com autorização, hardware e
custo medidos) → modelo de linguagem próprio só com dados, hardware e orçamento que o justifiquem.
