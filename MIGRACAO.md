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
