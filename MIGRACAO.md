# Migração: o que mudou no banco e como aplicar

Toda migração é **automática e idempotente**: cada módulo cria as próprias tabelas na primeira vez que roda
(`CREATE TABLE IF NOT EXISTS`) e chama `proteger(c)`, que impede apagar qualquer linha. Não existe comando manual
obrigatório. Para conferir que está tudo no lugar: `python -m robo banco-doc` (regera `documentacao/banco_de_dados.md`).

## Fase 1 — fala natural (23/10/2026)

| Tabela | Para que serve | Regra |
|---|---|---|
| `voz_falas` | quantas vezes cada frase da voz determinística já foi usada (para variar e não repetir o mesmo parágrafo em 24 h) | só de inclusão |

`interacoes` e o canal passaram a guardar `natureza` (`regra` ou `hipotese`) e `modelo` (nome do modelo de IA, ou vazio).
A IA continua **desligada por padrão** (`ia: {provedor: nenhum}`); chave de API só em variável de ambiente.

## Fases 2 e 3 — conversa com fato e memória da empresa (23/10/2026)

| Tabela | Para que serve | Regra |
|---|---|---|
| `aprendizados` | cada acerto ou erro: quem, competência, ação, causa, correção, evidência e origem (pipeline, validacao, treino, dialogo, laboratorio, semente, replay) | só de inclusão; gatilho bloqueia UPDATE |
| `aprendizados_uso` | toda vez que alguém consultou a memória antes de agir | só de inclusão |
| `aprendizados_replay` | resultado de refazer um erro antigo para ver se ele ainda acontece | só de inclusão |
| `dialogo_conversas` | conversa entre funcionários nascida de um fato (`fato_id` único), com o compromisso e se foi cumprido | registro com situação (aberto → cumprido/nao_cumprido), a linha nunca some |
| `dialogo_ciclos` | cada vez que a rotina de conversa rodou, inclusive quando não havia assunto | só de inclusão |

Coluna nova: `interacoes.dados` (JSON com a fonte e o id do fato). Linhas antigas recebem
`{"fonte": "registro anterior a 23/10/2026"}`. O texto da conversa agora é guardado inteiro (antes era cortado em 2.000
caracteres).

Comando novo (opcional, idempotente): `python -m robo semear-aprendizado` carrega `dados/semente_aprendizado.json`
(208 erros típicos por categoria de habilidade, origem `semente`). Rodar duas vezes não duplica nada. A semente
**nunca conta como trabalho real** nem como acerto de ninguém.

Rotina nova: `dialogo` (a cada 20 min, no máximo 3 conversas por ciclo e 40 por dia). Fluxo do Airflow: `robo_dialogo`.

## Fase 4 — status honesto (23/10/2026)

| Tabela | Para que serve | Regra |
|---|---|---|
| `jobs` | um processamento real: planilha (real ou sintética), rodada de treino, exercício do laboratório, rotina que fez algo | só de inclusão; job fechado nunca muda (gatilho) |
| `jobs_etapas` | cada etapa de um job, com quem fez, início, fim, ok e evidência | só de inclusão; etapa fechada nunca muda (gatilho) |

Mudança de regra: "trabalhando" agora exige uma etapa de job aberta nos últimos 15 minutos. Rotina automática, ronda
de TI e aviso no canal contam só como **plantão**. Nova rota: `GET /api/prova-de-trabalho`.

## Fase 5 — Fábrica de Planilhas (23/10/2026)

| Tabela | Para que serve | Regra |
|---|---|---|
| `fabrica_lotes` | cada planilha sintética: regra de negócio, semente, linhas, nível, quem gerou, conferiu e revisou, gabarito e conferência final | registro com situação (a linha nunca some) |

Pastas novas (criadas sozinhas): `Bases-Limpeza/sintetico` (entrada da fábrica, com `TREINO_*.gabarito.json`),
`Bases-Tratadas/_treino`, `Bases-Originais/_treino`, `Bases-Erros/_treino`, `Bases-Relatorios/_treino`.

Configuração (opcional, `config.yaml`):

```yaml
fabrica:
  habilitada: true          # false desliga
  intervalo_minutos: 30
  teto_por_dia: 24
  linhas_min: 2000
  linhas_max: 20000
  fila_vazia_minutos: 10    # espera depois da última planilha real antes de assumir
  regras_extra: null        # caminho de um .json com regras novas (ver robo/regras_negocio.py)
```

Mudança na limpeza: a lista padrão de identificadores ganhou chaves de negócio (nota fiscal, NF, pedido, título,
protocolo, SKU, chamado). Com isso, a cópia exata de uma nota fiscal passa a ser removida.

## Fase 6 — celular de verdade (23/10/2026)

Nenhuma tabela nova. A tabela `acessos_celular` passa a receber o evento `acao` (com a ação e o resultado), e cada ação
pelo celular grava um job fechado em `jobs` (tipo `acao_celular`, origem `dono`).

Configuração nova (opcional): `celular: {acoes: false}`. Com `true`, libera só 4 ações: reprocessar um reprovado,
pausar, retomar e ver o log.

Comando novo: `python -m robo diagnostico-celular` (só lê; `--salvar-qr` grava `logs/celular_qr.svg`). Rota nova no
painel: `GET /api/celular/diagnostico`. Pacote novo em `requisitos.txt`: `segno` (QR code, só Python). Sem ele, o
endereço aparece por escrito. Rode `instalar.bat` de novo para instalar.

## Cobertura do banco e dado sintético no PostgreSQL (23/10/2026)

| Onde | O que muda | Regra |
|---|---|---|
| SQLite `cobertura_persistencia` | tabela nova: cada levantamento de cobertura, tabela por tabela, com a causa de cada vazia | só de inclusão (gatilho bloqueia UPDATE) |
| PostgreSQL `laboratorio` | passa a receber a cópia bruta das planilhas da fábrica: `laboratorio.treino_<regra>` | só dado sintético, marcado por `_arquivo_origem` (TREINO_*) e `_lote_id` |
| PostgreSQL `treino` | passa a receber o tratado (`treino.treino_<regra>`), `treino.lotes`, `treino.ocorrencias` e a análise (`treino.resumo`, `indicadores`, `destaques`, `alertas`, `perfil`) | só dado sintético |

Os schemas já existiam (criados pelo instalador) e estavam vazios: **nada é apagado nem alterado** nos schemas de
produção (`bruto`, `tratado`, `analitico`, `analise`, `robo`). Os modelos SQL (`modelos_sql/`) continuam rodando só
sobre o real. Reverter: `fabrica: {pg_treino_mb_max: 0}` no `config.yaml` para de carregar dado sintético (a planilha
continua tratada em `Bases-Tratadas/_treino`).

Configuração nova (opcional): `fabrica.pg_treino_mb_max` (padrão 100). Ao atingir, a planilha sintética deixa de subir
ao banco, com aviso no relatório de qualidade. Nada é apagado para abrir espaço.

Comando novo: `python -m robo cobertura-banco` (só conta; gera `logs/cobertura_banco.md` e `.json`).
Turno da nuvem: agora roda a esteira (planilhas da fábrica) e grava o levantamento de cobertura a cada salvamento.

## Demandas para todos os funcionários (23/10/2026)

| Tabela | O que muda | Regra |
|---|---|---|
| `demandas_ciclos` (nova) | cada ciclo da distribuição: elegíveis, atribuídas, concluídas, bloqueadas e o detalhe de quem foi pulado e por quê | só de inclusão |
| `solicitacoes`, `etapas`, `eventos` | passam a receber as demandas (origem `demanda_sintetica`, modelo `demanda:<ferramenta>`) e as planilhas da fábrica processadas (origem `sintetica`) | as mesmas regras de antes: nada se apaga |
| `jobs` | novo tipo `demanda` (uma por demanda executada) | job fechado não muda |

Mudanças de comportamento:
- o pós-processamento de cada planilha (solicitação automática, memória e aprendizado) saiu do painel para
  `robo/pos_processamento.py` e passou a rodar também na nuvem;
- planilha da fábrica (TREINO_*) gera solicitação com origem `sintetica` e **não** gera proposta de regra nem
  handover (antes, no notebook, gerava como se fosse real);
- o revisor de uma demanda nunca é quem executou nem "dono": se o gestor for o dono, quem revisa é `casos_revisor`.

Configuração nova (opcional): `demandas: {habilitada: true, intervalo_minutos: 30, por_ciclo: 6, por_dia: 150,
por_pessoa_horas: 24}`. Desligar: `demandas: {habilitada: false}`.

## Equipe de demandas e níveis (23/10/2026)

| Tabela | O que é | Regra |
|---|---|---|
| `demandas_registro` (nova) | cada decisão da distribuição sobre uma pessoa: atribuída, treinamento, pulada, bloqueada, reatribuída ou sem trabalho, com nível, motivo e quem decidiu | só de inclusão |
| `demandas_avaliacoes` (nova) | avaliação independente (Bento) de uma demanda concluída, com veredito e achados | só de inclusão; uma por demanda |
| `jobs` | novo tipo `ciclo_demandas` (uma por ciclo, com uma etapa de cada função) | job fechado não muda |

Funcionários novos (5, 4º andar): `dem_coordenador`, `dem_gerador`, `dem_distribuidor`, `dem_cobertura`,
`dem_avaliador`. O quadro passou de 93 para 98. A rotina `demandas` passou da Planejadora de Treino para a
Coordenadora de Demandas.

Mudanças de comportamento:
- demanda pode ter várias etapas (níveis médio a profissional), com dependências e repasse registrado;
- demanda bloqueada vira demanda de treinamento (consulta ao conhecimento da área), com o bloqueio registrado;
- demanda aberta há mais de 6 h é cancelada pela Cobertura, com o motivo, e a pessoa volta para a fila.

Configuração (opcional): `demandas: {horas_sem_atividade: 48, horas_abandono: 6, avaliacoes_por_ciclo: 3}`.
Comando novo: `python -m robo cobertura-demandas [--dias 7]` (sai com código 1 se a cobertura estiver incompleta).

