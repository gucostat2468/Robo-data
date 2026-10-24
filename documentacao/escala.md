# Escala: prioridade, indicador principal e decisões do dono

## Prioridade

Escalar = **mais entregas úteis e verificadas por hora de turno, dentro dos limites grátis**. Não é mais funcionários
nem mais telas. Ordem: medir → aprofundar → dado com significado → escalar.

| Fase | O que | Estado |
|---|---|---|
| 1. Medir | tempo do turno por natureza (`robo/tempo_turno.py`) e indicador principal no boletim | feito; conferir no próximo turno |
| 2. Aprofundar | projeto NPS entre andares (`robo/projetos.py`); treino saturado vira teste de regressão | feito |
| 3. Dado com significado | máscara de CPF, e-mail e telefone no espelho público; entrada de dado real | máscara feita; **dado real depende do dono** |
| 4. Escalar | mais projetos em paralelo até o limite medido | só depois de 2 semanas de medição |

## Indicador principal

**Entregas aprovadas na revisão independente por hora de turno** (demanda de trabalho ou projeto com estado
`concluida`; estudo não conta). Fica em `tempo_turnos.entregas_por_hora` e no boletim do celular.

Como ler o tempo do turno:

| Natureza | Inclui |
|---|---|
| operacional | demandas de trabalho e projetos, esteira, fábrica, painéis, modelos |
| estudo | treino, laboratório, lições, demanda de estudo |
| revisão | auditoria e o tempo do ciclo de demandas fora das demandas (cobertura, distribuição, revisão, avaliação) |
| coordenação | diálogo, PDCA, caixa do dono, alçadas, RH de desempenho, reunião, estratégia, ideias |
| manutenção | backup, cópia para o PostgreSQL, registro, ronda de TI, jornada de teste, canal, boletim |
| erro | rotina ou demanda que terminou em erro |
| parado | pausa entre as voltas do laço |
| sem_medicao | o que o cronômetro não cobriu (nunca é distribuído) |

Bloqueio e espera de dependência são **contagem**, não minutos (a demanda nem nasce).

## Achado do treino (espelho real, 24/10)

11 de 15 competências tinham **100% de acerto em todos os níveis**, inclusive o 5. Não é aprendizado: é código
determinístico resolvendo o que já resolve. Forçar 60–80% seria fingir. A competência saturada (30 acertos seguidos no
nível máximo) agora é conferida 1 vez a cada 24 h por pessoa, como teste de regressão; um erro tira a saturação. As que
discriminam de verdade continuam: conhecimento (46–83%), SQL (6–100% conforme o nível), segmentação, orquestração.

O próximo ganho real aqui é a Sala de Casos criar defeitos NOVOS (que o código ainda não trata): cada erro achado é um
defeito de verdade para corrigir.

## Decisão do dono: repositório público ou privado

O espelho (`painel-espelho`), o boletim (`painel-celular`) e os logs dos turnos ficam visíveis para qualquer pessoa
enquanto o repositório for público. Hoje não há dado real neles (conferido: só exemplos de documentação com formato
de e-mail/telefone, agora mascarados).

| | Público (hoje) | Privado |
|---|---|---|
| Minutos do GitHub Actions | sem limite nos runners padrão | 2.000 min/mês no plano Free (conferir em Settings → Billing) |
| Turnos de ~45 min por mês | contínuo (~960/mês) | ~40/mês (~1,4 por dia), descontados os testes a cada push (~7 min) |
| Dado real (mesmo anonimizado) | **não pode entrar** | pode, com anonimização (LGPD) |
| Termos do GitHub | Actions como "servidor" contínuo é zona cinzenta | idem |

Caminho recomendado: manter público só com dado sintético; dado real fica no notebook do dono (o robô local processa
e o PostgreSQL privado guarda), nunca no repositório.

## Decisão do dono: qual projeto real primeiro

NPS (o projeto já existe com dado sintético), CSAT, verbatins (texto) ou tracking de marca. O escolhido vira o
modelo dos próximos projetos, com uma base sua anonimizada (sem nome, CPF, e-mail, telefone).
