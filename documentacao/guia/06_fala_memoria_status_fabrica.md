# Parte 6 — Fala natural, conversas com fato, memória, status honesto e fábrica

Escrito em 23/10/2026, depois das Fases 1 a 5. Aqui não há números de linha: os módulos são novos e ainda mudam.
Cada seção diz **para que serve**, **onde entra no fluxo** e o que cada função faz.

## A regra que vale para tudo nesta parte

1. Primeiro se **apura** o fato (cálculo, consulta ao banco, registro de um job). Depois se **redige**.
2. Ninguém aparece trabalhando sem um registro que prove.
3. Dado sintético (`TREINO_*`) nunca se mistura com dado real.
4. Toda gravação passa por `Trabalho.tx()` e `proteger(c)`: nada é apagado.

---

## robo/ia.py — modelo de linguagem opcional

**Para que serve.** Deixar um modelo de IA *redigir* uma resposta a partir de fatos já calculados. Vem desligado.

**Onde entra.** O canal (`robo/canal.py`) chama `conversar` depois de apurar os fatos. Se não houver modelo, ou se o
texto vier com número inventado, quem fala é a voz determinística.

- `status(cfg)`: diz se há modelo ativo (`desligada`, `modelo ativo`, `modelo ausente`) e por quê. Só o Ollama, que é
  local, é consultado pela rede.
- `numeros_do_texto` / `numeros_inventados(texto, fatos)`: tiram todos os números do texto e conferem se cada um está
  nos fatos (0, 1 e 2 são liberados, porque aparecem como palavras).
- `conversar(cfg, sistema, mensagens, fatos)`: chama o provedor, tenta de novo uma vez e devolve
  `{ok, texto, modelo, natureza, aviso}`. Nunca levanta exceção.
- **Disjuntor:** 3 falhas seguidas deixam o modelo 10 minutos sem ser chamado.
- Provedores: `nenhum` (padrão), `ollama` (só 127.0.0.1), `api_compativel` (chave na variável `ROBO_IA_CHAVE`),
  `anthropic` (chave na variável `ANTHROPIC_API_KEY`).

## robo/voz.py — a voz de cada funcionário sem IA

**Para que serve.** Transformar um conteúdo já apurado em fala de gente, no tom do cargo.

- `tom_de(pid)`: executivo (diretor, head), líder (gerente, coordenador), técnico (especialista, sênior), parceiro
  (pleno), aprendiz (júnior, estagiário).
- `limpar(texto)`: tira listas, `*`, `#` e `;` (menos o `;` dentro de parênteses, que é separador de fórmula do Excel).
- `compor(cfg, pid, ato, conteudo)`: escolhe abertura e fechamento conforme o ato (status, erro, explicação…) e
  varia a frase pela contagem em `voz_falas`, para não repetir o mesmo parágrafo em 24 horas.
- `duvida_honesta(pergunta)`: quando o robô não entendeu, pergunta de volta como uma pessoa perguntaria.

## robo/fatos.py — o que aconteceu hoje

**Para que serve.** Ser a única fonte de assunto das conversas. `fatos_do_dia(cfg)` lê o banco e devolve uma lista de
fatos, cada um com um id estável (`dia:tipo:detalhe`): planilha aprovada ou reprovada, linhas processadas, erro
repetido no treino, rotina com erro, lição nova, backup, divergência da fábrica, pendência do dono, alerta da TI e
fila travada. Se uma tabela ainda não existe, o tipo correspondente é só ignorado.

## robo/dialogo.py — conversa só quando precisa

**Para que serve.** Fazer os funcionários falarem entre si apenas quando há um fato que pede conversa.

- `_roteiro(cfg, fato, gente)`: monta a conversa de 2 a 4 falas para aquele tipo de fato e o **compromisso** final,
  com o id do último registro (`depois_de`) para poder conferir depois.
- `_mentor`: quem já acertou aquela competência; se ninguém acertou, o gestor.
- `conversar_sobre(cfg, fato)`: grava as falas em `interacoes` (com `dados` = fonte e id do fato), a conversa em
  `dialogo_conversas` e espelha no canal do andar. O mesmo fato nunca gera duas conversas (`fato_id` é único).
- `verificar_compromissos(cfg)`: procura um registro novo depois de `depois_de` (por exemplo, uma tentativa de treino
  certa da mesma pessoa) e fecha a conversa como cumprida ou não cumprida, com a prova.
- `rotina(cfg)`: a cada 20 minutos, no máximo 3 conversas por ciclo e 40 por dia. Sem fato, registra o ciclo em
  `dialogo_ciclos` como "sem assunto" e devolve `None` (não conta como trabalho).

## robo/aprendizados.py — a memória da empresa

**Para que serve.** Guardar cada acerto e erro com causa e correção, para que o próximo caso parecido já comece sabendo.

- `registrar(...)`: grava um aprendizado (origem: pipeline, validacao, treino, dialogo, laboratorio, semente, replay).
- `consultar(cfg, competencia, contexto)`: devolve os aprendizados mais parecidos e registra o uso em
  `aprendizados_uso`. A esteira chama antes de ler cada planilha e escreve no relatório "Memória: …".
- `da_esteira(cfg, r, job_id)`: depois de cada planilha, registra o resultado da esteira; se foi barrada, anota quem
  barrou (`_quem_barrou`) e a correção sugerida (`_correcao_sugerida`, nunca vazia).
- `reincidencia(cfg, dias)`: erros que voltaram a acontecer.
- `replay(cfg)`: refaz erros antigos para ver se ainda acontecem e registra em `aprendizados_replay`.
- `gerar_semente` / `semear`: a semente de 208 erros típicos por categoria de habilidade. Idempotente e marcada como
  `semente`, nunca contada como trabalho.

Outros módulos que alimentam a memória: `treino.tentar`, `laboratorio`, `fabrica.conferir_pendentes` e `licoes.colher`
(que transforma erros da esteira em lições).

## robo/jobs.py — prova de trabalho

**Para que serve.** Registrar cada processamento real com etapas, responsável, início, fim e evidência.

- `abrir`, `etapa`, `fechar_etapa`, `fechar` e o atalho `with job(...)`.
- `registrar_concluido(...)`: grava de uma vez um job que já terminou (rotina que fez algo, exercício do laboratório).
- `trabalhando_agora(cfg)`: quem tem etapa aberta nos últimos 15 minutos. **Só isso é "trabalhando".**
- `marcar_abandonados`: job aberto há mais de 6 horas é fechado como abandonado pela ronda de TI.
- Gatilhos no banco impedem alterar um job ou uma etapa já fechados.

`robo/atividade_equipe.py` usa os jobs para os 5 estados: trabalhando, ativo hoje, plantão, ocioso, sem registro.

## robo/regras_negocio.py e robo/fabrica.py — fábrica de planilhas sintéticas

**Para que serve.** Gerar planilhas grandes e sujas, de 15 regras de negócio, para a empresa treinar na esteira de
verdade sem tocar no dado real.

- `regras_negocio.caso(regra, n, semente)`: gera a planilha suja; `gabarito(regra, limpo)` calcula o resultado certo
  por outro caminho.
- `fabrica.produzir_lote`: Joana gera, o arquivo `TREINO_*` entra em `Bases-Limpeza/sintetico` com o gabarito ao lado.
- `fabrica.conferir_pendentes`: Ruan confere a saída da esteira contra o gabarito e Celina revisa; divergência vira
  aprendizado e fato para conversa.
- `fabrica.rotina`: planilha real tem prioridade; um lote por vez; teto diário; para depois de 3 falhas seguidas.

## robo/diagnostico_celular.py e o app do celular (Fase 6)

**Para que serve.** Descobrir por que o celular não abre o robô e abrir em 3 toques.

- `rodar(cfg)`: 8 passos em ordem (ligado, senha, rede, servidor ouvindo, resposta pelo IP da rede, firewall,
  instalação, ações). Um passo que depende de outro que falhou aparece como "pulado", não como falha a mais.
- `qr_terminal(url)` / `qr_svg(url)`: o QR code do endereço (pacote `segno`).
- `robo/painel/celular.py` → `executar_acao(cfg, controle, acao, nome)`: as 4 ações opcionais. Cada uma grava um job
  `acao_celular` e uma linha em `acessos_celular`. A rota `/api/acao` exige sessão, o cabeçalho `X-Robo-Celular` e
  `celular.acoes: true`.
- Estáticos: `service-worker.js` (guarda só a casca do app, nunca `/api`), `offline.html`, ícones PNG
  (`ferramentas/gerar_icones_celular.py` os redesenha) e `celular_painel.js` (página "No celular" do painel).
- No painel, em telas até 520 px, cada linha de tabela vira um cartão "coluna: valor" (`rotularTabelas` em painel.js).

## Como conferir que está funcionando

- `GET /api/prova-de-trabalho`: quem trabalhou de verdade e a evidência.
- Menu Dados → Fábrica: lotes, conferências e divergências.
- Canal do andar: conversas com o fato que as originou.
- `python -m pytest -q testes/teste_fala.py testes/teste_dialogo.py testes/teste_aprendizados.py testes/teste_jobs.py testes/teste_fabrica.py testes/teste_celular_app.py`
