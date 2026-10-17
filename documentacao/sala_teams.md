# Sala de reunião — engenharia reversa do Microsoft Teams

Objetivo: reproduzir, no painel local, a experiência de reunião do Teams, com os funcionários do robô como participantes.
Tudo local, sem nuvem e sem API externa.

## 1. O que o Teams tem (pesquisa)

Barra de controles de uma reunião do Teams:

- **Chat**
- **Pessoas**: participantes, convidar e remover, ver mãos levantadas.
- **Levantar a mão**: a fila mostra quem levantou primeiro.
- **Reagir**: Curtir, Amei, Aplausos, Risada, Surpresa.
- **Exibir**: Galeria, Palestrante, Modo foco e Fixar/Destacar alguém.
- **Câmera**, **Microfone** e **Compartilhar** (tela, janela ou conteúdo).
- **Mais**: gravar e transcrever, anotações, Copilot, salas simultâneas, legendas.
- **Sair** ou **Encerrar a reunião**.

Depois da reunião vem o **Recap**: gravação, transcrição, anotações, tarefas e quem falou.

Fontes:

- [Usar os controles da reunião no Teams](https://support.microsoft.com/en-US/teams/meetings/use-meeting-controls-in-microsoft-teams)
- [Levantar a mão e reações](https://support.microsoft.com/office/a8323a40-3d07-4129-934b-305370a36e21)
- [Controles de reunião — Findlay](https://helpdesk.findlay.edu/support/solutions/articles/13000112248-microsoft-teams-meeting-controls)
- [Controles de reunião — Pace](https://helpdesk.pace.edu/TDClient/213/Portal/KB/Article/14134/Microsoft-Teams-Meeting-Controls)
- [Recap no Teams](https://support.microsoft.com/en-US/teams/meetings/recap-in-microsoft-teams)
- [Meeting recap](https://support.microsoft.com/office/meeting-recap-in-microsoft-teams-c2e3a0fe-504f-4b2c-bf85-504938f110ef)
- [Layouts de reunião](https://support.microsoft.com/topic/95aaeaf8-0f22-46cf-a6f9-34ca9b04a1b2)
- [Layouts simplificados (fim do Modo Juntos)](https://elevenforum.com/t/goodbye-together-mode-hello-simplified-meeting-layouts-in-microsoft-teams.46832/)

## 2. A tecnologia por trás do Teams

| Camada | No Teams | Por que existe |
|---|---|---|
| Áudio e vídeo | **WebRTC** (getUserMedia captura câmera e microfone; RTP/SRTP transporta, criptografado) | Tempo real no navegador |
| Conexão | **ICE / STUN / TURN** acham um caminho entre redes. Quando não há caminho direto, o TURN retransmite. | Atravessar roteadores e firewalls |
| Muitos participantes | **SFU** (Selective Forwarding Unit): cada um envia um fluxo ao servidor, que repassa sem misturar | 100+ pessoas sem cada um mandar para todos |
| Qualidade adaptável | **Simulcast / SVC**: o mesmo vídeo em várias resoluções; o SFU escolhe por participante | Rede ruim não derruba a reunião |
| Chat, reações, mão levantada | Mensagens de sinalização (WebSocket/HTTPS) ligadas ao chat da reunião | Estado compartilhado por todos |
| Transcrição, recap, Copilot | Serviços de nuvem (fala→texto e LLM) | Exigem nuvem e licença |

Fontes:

- [O que é um SFU](https://getstream.io/blog/what-is-a-selective-forwarding-unit-in-webrtc/)
- [Fluxo WebRTC com o Teams](https://dev.to/rajdev_singh_998/the-full-webrtc-connection-flow-and-what-actually-happens-when-the-other-end-is-mircosoft-teams-1am4)
- [Como Meet, Zoom e Teams aguentam 100 pessoas](https://blog.stackademic.com/how-google-meet-zoom-and-teams-handle-100-people-on-a-video-call-5d1157c5f6ae)

## 3. O que fizemos igual, e como

Os participantes da sala são **funcionários do robô** (código), não pessoas em outros computadores. Por isso não existe
fluxo de vídeo entre máquinas, nem SFU, nem TURN: só há um ser humano (você), no seu computador.

| Recurso do Teams | Na nossa sala | Tecnologia | Onde fica registrado |
|---|---|---|---|
| Galeria / Palestrante / Fixar | Botão ▦/◱ e 📌 em cada tela | Layout no navegador | — (preferência de tela) |
| Indicador "falando" | Contorno roxo em quem respondeu por último | Mensagens da conversa | `mensagens` |
| Levantar a mão (fila) | A mão sobe **sozinha** só com motivo real. Você clica em **Dar a palavra** e a pessoa fala com os dados. | `sala.levantar_maos` / `dar_palavra` | `sala_eventos` (mao_levantada, palavra) |
| Reações | 👍 ❤️ 👏 😂 😮 em cada fala | `sala.reagir` | `sala_eventos` (reacao) |
| Pessoas: convidar/remover | Qualquer funcionário entra e se apresenta pelo contrato. Quem conduz não pode ser removido. | `sala.convidar` / `remover` | `sala_eventos` |
| Compartilhar | Raio-X, scorecard, PDCA, laboratório ou a última base vão para o palco | `sala.compartilhar` | `sala_eventos` + mensagem |
| Chat da reunião | Fala com quem você clicar ou citar pelo nome | `sala.falar` → atendimento | `mensagens` |
| Anotações | Bloco de notas da reunião | `sala.anotar` (guarda o texto e o hash) | `sala_eventos` (notas) |
| Pauta | Itens com marcar/desmarcar | `sala.pauta` | `sala_eventos` |
| Tarefas | Viram **solicitações reais** na central, com plano, revisor e aprovação | `orquestrador.criar` | `solicitacoes` + `sala_eventos` |
| Cronômetro | Tempo desde a abertura | navegador | — |
| Câmera | A sua câmera aparece na sua tela; **a imagem não sai do computador** | WebRTC `getUserMedia` (local) | nada é gravado |
| Ler em voz alta | As falas dos funcionários são lidas em voz alta | `speechSynthesis` do navegador (voz do Windows, local) | — |
| Encerrar + Recap | Duração, quem falou, mãos atendidas e sem palavra, tarefas, pauta, o que foi compartilhado, reações, anotações e transcrição | `sala.encerrar` | `salas_encerradas` + `logs/reunioes/sala_<id>.md` |

Outras regras:

- **Imutável.** `sala_eventos` e `salas_encerradas` têm gatilhos no banco que recusam apagar (e, nos eventos, alterar).
- **Encerrada é encerrada.** Depois de encerrar, ninguém fala mais na sala.
- **Separada da reunião semanal.** A ata da sala fica fora da tabela `reunioes`, que é da reunião semanal da liderança. Misturar fazia a rotina semanal achar que já tinha rodado; esse erro foi encontrado no teste de navegador e corrigido.

## 4. O que NÃO dá para fazer igual sem nuvem (honesto)

| Recurso | Por quê | Alternativa local |
|---|---|---|
| Você **falar** e o sistema transcrever | O reconhecimento de fala do navegador (Web Speech API) manda o áudio para servidores do Google ou da Microsoft | Digitar; um motor offline (ex.: Vosk) pode ser instalado depois, se você quiser |
| Gravação de vídeo da reunião | Não há vídeo de outras pessoas para gravar | A transcrição completa e o recap ficam salvos |
| Copilot (resumo por IA) | Exige LLM em nuvem | O recap é montado a partir do que foi registrado: nada inventado |
| Salas simultâneas | Só há um ser humano na reunião | Abra outra sala por andar |

## 5. Como testamos todos os botões

Um roteiro de navegador (Playwright + Chromium) faz o caminho completo. Qualquer erro de JavaScript ou resposta HTTP 5xx conta como falha.

1. Entra com a senha.
2. Abre as 20 páginas do painel.
3. Na sala: abre a reunião do 1º andar e o painel Pessoas.
4. Dá a palavra a quem levantou a mão.
5. Convida e remove participante; reage 👏.
6. Compartilha o Raio-X e para de compartilhar.
7. Alterna galeria e palestrante; fixa e desafixa.
8. Liga e desliga a câmera e a leitura em voz.
9. Fala com a diretora clicando na tela dela.
10. Salva a pauta, marca um item, salva as anotações e cria uma tarefa.
11. Encerra e confere o recap.

Erros que o roteiro achou e que já foram corrigidos:

- **Página da sala sumia do menu.** Uma função com nome repetido em dois arquivos `.js` derrubava o arquivo inteiro. Agora existe um teste automático que proíbe nomes globais repetidos.
- **Recap gravado no lugar errado.** A ata da sala ia para a tabela `reunioes` (da reunião semanal) e quebrava a página Memória.
- **Avisos 401 antes do login.** O painel agora pergunta primeiro se precisa de senha.
