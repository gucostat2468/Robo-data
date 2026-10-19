# Maturidade do projeto — avaliação franca (19/10/2026)

> Escrita para quem decide: o que já é profissional, o que ainda não é e o que fazer para chegar lá.
> Notas de 1 a 5: 1 = protótipo, 3 = piloto controlado, 5 = produção crítica.

## Veredito

**Pronto para um piloto controlado no seu computador. Ainda não é "produção crítica".**

O núcleo é sólido:

- ETL com transação e reprovação explícita;
- memória que o banco se recusa a apagar;
- backup conferido por SHA-256 e restauração testada;
- treino com gabarito e revisão independente;
- testes automáticos em todas as entregas.

O que falta é **infraestrutura** e **validação no seu Windows**, não mais funcionalidade:

1. Tudo roda num notebook só.
2. As partes específicas do Windows nunca rodaram num Windows de verdade.
3. Nenhuma planilha real passou pela produção ainda.

## Placar

| Dimensão | Nota | Por quê (evidência) | O que leva a 5 |
|---|---|---|---|
| Funcionalidade | 4 | ETL, PostgreSQL em camadas, 5 andares, treino adaptativo, decisões cobradas, Airflow, celular | Uso com planilhas reais por algumas semanas |
| Qualidade e testes | 4 | Mais de 400 testes automáticos, todos verdes antes de cada envio; erros do próprio robô achados pelo treino e corrigidos | Os mesmos testes rodando num Windows real |
| Dados e governança | 4,5 | Nada se apaga (gatilhos no banco); **registro total**: log do sistema, canal, atas, RH, conhecimento, estado da TI e config (sem senhas) dentro do SQLite e do PostgreSQL; dicionário gerado do código | Anonimização para ML quando entrarem dados reais de clientes |
| Segurança | 3,5 | Painel só em 127.0.0.1 com senha PBKDF2; celular só leitura, só rede privada, bloqueio após 5 erros; banco com usuário de leitura; senhas fora dos arquivos | Criptografia do disco (BitLocker); HTTPS no celular; atualização de dependências |
| Observabilidade | 4 | Ronda de TI a cada 30 min, SLA das rotinas, cada linha de log no banco, cada queda no banco (vigia), app do celular ao vivo | Alerta que chegue a você mesmo com o app fechado |
| Infraestrutura e disponibilidade | 3 | Vigia religa o robô em até 5 min (testado com queda brusca); início com o Windows; backup conferido de hora em hora; cópia automática num 2º lugar se configurada. Continua um computador só: desligado = empresa parada | Máquina sempre ligada (mini PC) com nobreak; `copia_extra` apontando para um HD externo |
| Operação no Windows | 2 | Código de Windows (setx/registro, trava msvcrt, firewall, serviço) testado só em Linux | Rodar `python -m robo diagnostico` no seu PC e me mandar o resultado |
| Escala | 2,5 | SQLite como fonte e PostgreSQL como espelho, adequado para 1 usuário e milhares de planilhas | Volume real medido; PostgreSQL como fonte principal se crescer |

## Realidade: o que é real e o que não é

- **Real:** cada ferramenta executada, cada correção com gabarito, cada nível e lição registrados, os backups, o
  espelho no PostgreSQL, as rotinas e as rondas. Tudo verificável no banco.
- **Sintético:** os dados de dentro dos casos de treino. É de propósito: a resposta certa é conhecida.
- **Os "funcionários" são papéis do código, não pessoas nem uma IA conversando.** Eles não aprendem sozinhos como
  um humano. A evolução acontece de três jeitos, todos registrados:
  1. **Nível por competência**, que define a dificuldade e o que a pessoa pode fazer.
  2. **Lições e regras aprovadas.**
  3. **Correções de código** quando o treino acha uma falha real. Três falhas da LGPD e duas de NPS já foram achadas
     e corrigidas assim.
- **As conversas entre funcionários nascem de fatos registrados**, como um erro de treino, um alarme de SLA ou uma
  mentoria. Não há conversa de enfeite.

## Riscos principais e como estão cobertos

| Risco | Probabilidade | Impacto | Cobertura hoje | Próximo passo |
|---|---|---|---|---|
| Notebook quebra ou é roubado | baixa | **altíssimo** | backup diário no mesmo disco | copiar `logs\backups_sqlite` para HD externo 1× por mês, e BitLocker |
| Parte do Windows falha na primeira execução | média | médio | `python -m robo diagnostico` aponta e diz como corrigir | rodar e me mandar a saída |
| Planilha real com formato novo | alta | baixo | reprovação explícita, sem gravar nada, e proposta de regra | acompanhar as primeiras semanas |
| Notebook desligado à noite | alta | médio | ao abrir, o robô roda primeiro o que ficou atrasado | início com o Windows ligado |
| Senha do painel vazada | baixa | médio | só rede de casa, só leitura no celular | trocar com `python -m robo senha` |

## Ritmo 24 horas e crescimento do banco

- Com o robô ligado, **15 pessoas recebem um caso a cada 2 minutos**: todas as áreas, sem parar.
  São ~10.800 tentativas por dia, cerca de 117 por pessoa.
- Cada tentativa custa ~0,2 s de processamento e ~0,7 KB no banco.
  Com o resto da memória, o banco cresce ~15 MB por dia, ou ~5,5 GB por ano.
- Os backups seguram o disco porque guardam:
  - tudo das últimas 24 h;
  - 1 por dia nos últimos 30 dias;
  - o 1º de cada mês para sempre (compactado, ~5× menor).
- O `python -m robo diagnostico` avisa quando o disco começa a apertar.
