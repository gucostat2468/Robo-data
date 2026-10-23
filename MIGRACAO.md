# Migração: o que mudou no banco e como aplicar

Toda migração é **automática e idempotente**: cada módulo cria as próprias tabelas na primeira vez que roda
(`CREATE TABLE IF NOT EXISTS`) e chama `proteger(c)`, que impede apagar qualquer linha. Não existe comando manual
obrigatório. Para conferir que está tudo no lugar: `python -m robo banco-doc` (regera `documentacao/banco_de_dados.md`).

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
