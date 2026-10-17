# Parte 3 — A equipe: agentes, habilidades, RH, quadro de pessoal, contratação, TI, treinamento e estratégia

O Robô de Planilhas é organizado como uma empresa num prédio. Cada "pessoa" é uma função de código que executa ou confere algo de verdade, e o RH aplica provas técnicas (casos com resposta conhecida) antes de qualquer um trabalhar. Resumo do organograma, com nomes e cargos tirados do código:

- **1º andar · Engenharia de dados.** Os 7 agentes nativos da linha de produção (`robo/agentes.py`): Rita (Recepção), Leo (Leitura), Lia (Limpeza), Otto (Auditoria/Validação), Ana (Modelagem), Beto (Banco de dados) e Duda (Publicação). Conferem o trabalho deles: Saulo (Supervisor de Planilhas), Dora (DBA PostgreSQL) e Carla (Coordenadora de Engenharia, que assina a liberação), todos em `robo/producao.py`. O quadro de `robo/quadro.py` acrescenta Marcelo (Gerente de Engenharia), Júlia e Rafael (plenos), Bruno e Camila (juniores) e Théo (estagiário). Os agentes personalizados, como a Tina do arquivo `agentes/tina_contatos.yaml`, também entram aqui, pois o andar padrão é 1.
- **2º andar · Análise.** Marcos (Coordenador de Análise, em `producao.py`); os analistas Bia, Caio, Davi, Eva e Fábio (de `robo/analise.py`, que tem as provas em `rh.py`); Patrícia (Gerente de Analytics e Customer Insights); Sérgio e Larissa (plenos); Igor (júnior) e Manu (estagiária).
- **3º andar · Sala Excel.** Ricardo (Gerente da Sala Excel); os especialistas Pedro, Lúcia, Tânia e Gabriel (de `robo/excel.py`); Sílvia (Coordenadora); Hugo (pleno); Paula (júnior) e Enzo (estagiário).
- **4º andar · Diretoria, governança e canal.** Renata (Gerente de Operações e Governança); Helena (Coordenadora de RH), Iara (Inovação, sênior) e Nina (Assistente júnior do canal), de `robo/canal.py`; Vitor (pleno, LGPD) e Lara (estagiária de documentação).
- **5º andar · TI** (`robo/ti.py`). Gustavo (Gerente de TI), Fernanda (Coordenadora de DevOps/SRE), Wagner (Segurança, sênior), Marina (Cloud AWS, especialista e só consultiva), Diego e Rodrigo (plenos), Letícia (júnior) e Caíque (estagiário).

Acima de todos está **você, o dono** (`"dono"` no código). Você é gestor direto dos gerentes e é quem decide promoções.

> **Como ler esta parte.** Cada arquivo tem "Para que serve", "Onde entra no fluxo" e, depois, cada bloco do código em ordem, com os números de linha. Termos técnicos são explicados na primeira vez que aparecem. Ao final de cada arquivo há a seção "Erros que este arquivo evita".

---

## robo/agentes.py

- **Para que serve.** Define quem são os agentes da linha de produção, em que ordem trabalham e com quais habilidades. Lê os agentes personalizados da pasta `agentes/` (um arquivo YAML por pessoa), valida a configuração, aplica a regra do estagiário (só observa) e executa as habilidades de cada um sobre a planilha. É também quem grava, edita e "demite" agentes quando você mexe no painel.
- **Onde entra no fluxo.** Quem chama: `robo/pipeline.py` (funções `obter_equipe` e `_tratar`, que chamam `equipe.executar("limpeza" | "validacao" | "modelagem", ...)`), o painel (`robo/painel/servidor.py`) e `robo/contratacao.py`. Quem é chamado: o catálogo de habilidades (`robo/habilidades`), o RH (`robo/rh.py`, para o processo seletivo e a ficha) e `robo/relatorio.py` (para o relatório do estagiário).

### Docstring do módulo (linhas 1–25)
- Linhas 1–19: uma *docstring* é o texto entre três aspas no topo do arquivo, que serve de manual. Esta mostra o formato do YAML de um agente. *YAML* é um formato de texto para configuração, legível por pessoas, em que cada linha é `chave: valor`. Os campos são `id`, `nome`, `papel`, `descricao`, `cor`, `posicao` (depois de quem ele trabalha), `ordem`, `ativo`, `aplicar_em` (quais arquivos ele trata) e `habilidades`.
- Linhas 18–19: os 7 nativos sempre existem. Só três deles (limpeza, validacao e modelagem) aceitam habilidades extras.
- Linhas 21–24: a ordem dentro de cada tabela. Limpeza nativa → habilidades da Lia → agentes "limpeza"; validação nativa → habilidades do Otto → agentes "validacao"; habilidades da Ana → agentes "modelagem" → modelagem nativa. Note que, na modelagem, os agentes extras trabalham **antes** da nativa, porque a nativa transforma a tabela em fato e dimensões e depois disso não dá mais para mexer na tabela única.

### Imports (linhas 27–40)
- Linha 27: `from __future__ import annotations` faz o Python tratar as anotações de tipo (como `-> list[str]`) só como texto. Assim elas funcionam em versões diferentes do Python.
- Linhas 29–33: bibliotecas padrão. `fnmatch` compara nomes de arquivo com curingas como `nps_*`; `logging` grava mensagens no log; `re` cuida de *regex* (expressões regulares, uma linguagem de padrões de texto, como "começa com letra minúscula"); `deepcopy` faz uma cópia completa de um dicionário, para que mudar a cópia não mude o original; `Path` representa caminhos de pasta e arquivo.
- Linhas 35–36: `pandas` (tabelas, os *DataFrames*) e `yaml` (leitura e escrita de YAML).
- Linha 38: importa o pacote de habilidades com o apelido `catalogo_habilidades`.
- Linha 40: cria o "gravador" de log chamado `"robo"`.

### Constantes (linhas 42–45)
- Linha 42: `POSICOES` são os três pontos da linha de produção onde um agente extra pode trabalhar.
- Linha 43: `RE_ID` é o padrão de um id válido: começa com letra minúscula, seguida de 1 a 39 letras, números ou `_` (de 2 a 40 caracteres no total). Assim o id serve como nome de arquivo sem risco.
- Linha 44: `ANDAR_MAXIMO = 9`. O prédio pode crescer até o 9º andar.
- Linha 45: o manual de um agente tem no máximo 50.000 caracteres.

### NATIVOS e IDS_NATIVOS (linhas 47–69)
- Linhas 47–68: a lista dos 7 nativos, cada um como um dicionário (um conjunto de pares chave → valor). Rita/recepcao, Leo/leitura, Lia/limpeza, Otto/validacao, Ana/modelagem, Beto/banco e Duda/publicacao. `aceita_habilidades` só é `True` para Lia, Otto e Ana. A descrição do Otto diz a regra-chave: "Qualquer erro barra o arquivo inteiro".
- Linha 69: `IDS_NATIVOS` é o *conjunto* (`set`, uma coleção sem repetição e de busca rápida) dos ids nativos, usado para proibir que um agente personalizado "roube" um desses nomes.

### class ErroAgente (linhas 72–73)
- Uma *exceção* é um "alarme" que o Python dispara quando algo dá errado e que interrompe o caminho normal até alguém tratá-lo. `ErroAgente` é o alarme específico para configuração de agente inválida. O painel o captura e mostra a mensagem para você.

### _padrao_agente (linhas 76–93)
- Linhas 77–79: monta um agente com todos os campos preenchidos com valores padrão: cor cinza, posição `limpeza`, ordem 50, ativo, `aplicar_em ["*"]` (todos os arquivos), nível `pleno`, andar 1, `contratado_por: "dono"` etc.
- Linha 80: por cima do padrão, aplica o que veio do YAML, ignorando valores vazios (`None`). Um campo em branco no arquivo não apaga o padrão.
- Linhas 81–84: compatibilidade. Arquivos antigos usavam `skills` em vez de `habilidades`. Se só existir `skills`, ele é copiado e depois removido.
- Linhas 85–86: se `aplicar_em` veio como texto (`"nps_*, csat_*"`), vira lista separada por vírgulas. Se ficar vazia, volta a ser `["*"]`.
- Linha 87: mantém só as habilidades que são dicionários e descarta lixo.
- Linhas 88–92: em cada habilidade, troca a chave antiga `skill` por `habilidade` e garante `ativo: True` e `parametros: {}` quando faltam.
- Linha 93: devolve o agente normalizado.

### validar_agente (linhas 96–133)
Devolve uma lista de problemas. Lista vazia significa agente válido.
- Linhas 98–113: as checagens que valem só para personalizados (`nativo=False`): id no padrão `RE_ID`, id que não seja de nativo, nome preenchido, posição entre as três permitidas, cor no formato `#RRGGBB` e andar entre 1 e 9. O `try/except` das linhas 109–113 pega andar que não é número (`TypeError`/`ValueError`) e o transforma em problema legível, em vez de deixar o programa quebrar.
- Linha 114: importa o RH aqui dentro (*import tardio*), porque `rh.py` também importa coisas deste arquivo. Importar no topo criaria um ciclo.
- Linhas 115–117: o nível tem de ser um dos cinco do RH (estagiário a especialista).
- Linhas 118–122: para cada habilidade configurada, procura no catálogo (`REGISTRO`). Se o nome não existe, registra o problema e passa para a próxima (`continue`).
- Linhas 123–127: confere os parâmetros com `preparar_parametros` (tipos, obrigatórios). Se houver erro, a mensagem vira problema.
- Linhas 128–132: **regra de senioridade.** Se a habilidade está ativa, calcula o risco dela com os parâmetros escolhidos (`rh.risco_de`) e pergunta ao RH se o nível permite (`rh.nivel_permite`). Um júnior com "remover linhas", por exemplo, recebe: "promova o agente ou passe a tarefa a um sênior". O porquê: tarefa que apaga dado só pode ficar com quem tem senioridade, da mesma forma que numa empresa o estagiário não exclui registros do CRM.

### _diferencas (linhas 136–154)
Compara a tabela antes e depois e resume em português o que mudaria. É usada no relatório do estagiário e na contratação automática.
- Linhas 138–139: mudança na quantidade de linhas ("100 → 98 linhas").
- Linhas 140–145: colunas novas ("criaria …") e colunas que sumiram ("removeria …").
- Linhas 146–151: para as colunas comuns e as linhas que existem nas duas versões (`intersection` dos índices), conta as células diferentes. Dois vazios são tratados como iguais (`a.isna() & b.isna()`), porque em pandas `NaN == NaN` é falso.
- Linhas 152–154: junta as partes com "; " ou devolve "nenhuma alteração".

### class Equipe (linhas 157–324)
Uma *classe* é um molde que junta dados e funções (os *métodos*). `Equipe` guarda todos os agentes carregados.

#### __init__ (linhas 158–164)
- Linhas 159–160: guarda a pasta de agentes e, se houver, a de habilidades personalizadas.
- Linhas 161–163: listas e dicionários vazios para os personalizados, para as habilidades extras dos três nativos e para os problemas por agente.
- Linha 164: já carrega tudo do disco.

#### carregar (linhas 167–198)
- Linhas 168–169: primeiro (re)carrega as habilidades personalizadas (`.py`), para que os agentes as encontrem no catálogo.
- Linhas 170–173: zera o estado. Se a pasta não existe, termina.
- Linhas 174–179: para cada `*.yaml` em ordem alfabética, lê com `yaml.safe_load`. O `safe_load` só lê dados, nunca executa código escondido no arquivo. YAML quebrado vira problema "arquivo YAML inválido", e o robô continua.
- Linhas 180–186: arquivo com nome de nativo. Se for de um dos três que aceitam habilidades (`limpeza.yaml`, por exemplo), aproveita só a lista de habilidades, valida como nativo e guarda em `habilidades_nativos`. Outros nativos são ignorados (`continue`).
- Linha 187: monta o agente personalizado. O id vem do YAML ou, na falta dele, do nome do arquivo.
- Linhas 188–193: valida. Se está válido e ativo, aplica o **processo seletivo técnico** do RH. Se reprovar, o problema é "não aprovado no processo seletivo técnico" com os bloqueios.
- Linhas 194–196: registra os problemas e adiciona o agente à lista **mesmo com problema**, para que ele apareça no painel com o motivo. Na execução ele é pulado (linhas 229–232).
- Linhas 197–198: ordena por posição (limpeza, validação, modelagem), depois por `ordem`, depois por nome.

#### lista (linhas 200–217)
Monta a lista completa, na ordem de trabalho, para o painel e o escritório 3D.
- Linhas 204–207: para cada nativo, uma cópia com `nativo: True`, as habilidades extras e os problemas.
- Linhas 208–209: os personalizados daquela posição, com `nativo: False` e o manual.
- Linhas 210–212: cada um recebe a "ficha" profissional do RH (`rh.ficha`).
- Linhas 213–216: na modelagem os extras vão **antes** do nativo; nas outras posições, depois.

#### executar (linhas 220–251)
É o coração da execução. Recebe a posição, a tabela (`df`), o relatório (`rel`), o nome da tabela, o nome do arquivo e, opcionalmente, `ao_etapa`, um aviso para o escritório 3D.
- Linhas 221–223: acha o nativo da posição e roda primeiro as habilidades extras dele (por exemplo, as que você deu à Lia).
- Linhas 224–228: percorre os personalizados. Pula quem é de outra posição ou está inativo, e quem não se aplica a este arquivo (o `fnmatch` compara o nome do arquivo, em minúsculas, com cada padrão de `aplicar_em`).
- Linhas 229–232: agente com configuração inválida não trabalha, e isso vira **ERRO** no relatório, o que barra o arquivo. O porquê: um agente quebrado não pode passar em silêncio, ou você acharia que a tarefa foi feita.
- Linhas 233–237: avisa o escritório 3D ("agente:tina começou"). Se o aviso falhar, ignora (`except Exception: pass`), porque animação não pode derrubar o processamento.
- Linhas 238–246: **modo observação do estagiário.** As habilidades dele rodam numa **cópia** (`df.copy()`) e com um relatório separado (`rel_obs`). Os achados que não são INFO são coletados, e no relatório principal entra só um INFO: "Estagiário X em observação (nada foi alterado): …", com o resumo de `_diferencas`. O `continue` garante que a tabela verdadeira siga intacta. O porquê: o estagiário está aprendendo. Ele mostra o que faria e você decide se promove; até lá, nenhum dado publicado depende dele.
- Linhas 247–250: os demais níveis trabalham na tabela real, e fica registrado "Agente X concluiu N habilidade(s): 100 → 98 linhas".
- Linha 251: devolve a tabela (possivelmente alterada).

#### _executar_habilidades (linhas 253–262)
- Linhas 254–256: pula habilidade inativa.
- Linhas 257–260: cada habilidade pode ter o próprio `aplicar_em`. Se não casar com o arquivo, ela é pulada.
- Linha 261: delega ao catálogo (`executar_habilidade`), que valida os parâmetros, roda e captura erros.

#### salvar (linhas 265–292)
Chamado pelo painel e pela contratação.
- Linhas 266–269: descobre se é nativo. Nativo que não aceita habilidades (Rita, Leo, Beto, Duda) recusa a edição.
- Linhas 270–273: normaliza e valida. Qualquer problema vira `ErroAgente` com todas as mensagens.
- Linhas 274–277: processo seletivo antes de gravar. O nativo é avaliado como `"especialista"`, para que o risco não o barre. Reprovou, não grava.
- Linha 278: cria a pasta se preciso.
- Linhas 279–285: nativo grava só `habilidades`. Personalizado grava a lista fixa de campos, na ordem que aparece no arquivo.
- Linhas 286–288: escreve o YAML com um comentário no topo. `allow_unicode` mantém os acentos e `sort_keys=False` mantém a ordem.
- Linhas 289–290: se veio um manual, grava também.
- Linhas 291–292: recarrega tudo (as provas e a ordem ficam atualizadas) e devolve o agente.

#### salvar_manual (linhas 294–304)
- Linhas 296–297: id fora do padrão é recusado (proteção contra nomes de arquivo maliciosos, como `../../`).
- Linhas 298–304: corta em 50.000 caracteres e grava `agentes/<id>.md`. Texto vazio apaga o manual existente.

#### manual (linhas 306–310)
- Lê `agentes/<id>.md` se o id for válido e o arquivo existir; senão devolve texto vazio.

#### excluir (linhas 312–324)
- Linhas 313–314: nativo não pode ser excluído; você só pode tirar as habilidades dele.
- Linhas 315–317: o arquivo precisa existir.
- Linhas 318–323: não apaga de verdade. Move o `.yaml` e o `.md` para `agentes/_excluidos/` (uma lixeira), e assim dá para recuperar.
- Linha 324: recarrega.

**Erros que este arquivo evita**
- Agente com id, cor, posição, andar ou nível inválidos entrando na linha de produção.
- Júnior ou pleno executando tarefa de risco acima do seu nível.
- Estagiário alterando dado publicado (ele trabalha numa cópia).
- Agente quebrado "fingindo" que trabalhou (vira ERRO e barra o arquivo).
- YAML malformado derrubando o robô (vira problema listado no painel).
- Exclusão irreversível (vai para a lixeira `_excluidos`).
- Agente aplicado em planilhas que não são dele (filtro `aplicar_em`).

---

## robo/habilidades/__init__.py

- **Para que serve.** É o "catálogo de cursos" da empresa: define o que é uma habilidade (uma tarefa de tratamento de dados com nome, descrição, conhecimento e parâmetros), registra todas num catálogo central, converte e valida o que você preencheu no formulário e executa a habilidade de forma segura. Também carrega as habilidades que você mesmo escreve em `habilidades_personalizadas/`.
- **Onde entra no fluxo.** Quem chama: `robo/agentes.py` (validação e execução), `robo/rh.py` (provas), `robo/contratacao.py` (teste numa cópia) e o painel (`catalogo()` monta a tela). Quem é chamado: `robo/limpeza.py` (`normalizar_nome_coluna`) e, no fim, `robo/habilidades/nativas.py`, que preenche o catálogo.

### Docstring (linhas 1–19)
- Linhas 3–5: a habilidade é uma função `f(df, parametros, contexto) -> df`, ou seja, recebe a tabela e devolve a tabela. Os metadados permitem ao painel montar o formulário sozinho.
- Linhas 7–18: exemplo completo de habilidade personalizada (`marcar_vip`).

### Imports (linhas 21–31)
- Linha 23: `importlib.util` carrega um arquivo `.py` a partir do caminho dele.
- Linha 25: `dataclass`, `asdict` e `field`. Uma *dataclass* é uma classe "ficha cadastral": você lista os campos e o Python cria sozinho o construtor e a comparação.
- Linha 27: `Any` e `Callable` são anotações de tipo ("qualquer coisa" e "algo que pode ser chamado como função").

### TIPOS_PARAMETRO (linha 33)
- Os 10 tipos de campo que um formulário de habilidade aceita: `coluna`, `colunas`, `texto`, `numero`, `inteiro`, `booleano`, `escolha`, `lista`, `mapa` e `expressao`.

### ErroHabilidade e ErroColunaAusente (linhas 36–41)
- Linhas 36–37: exceção para configuração inválida, com mensagem clara.
- Linhas 40–41: subtipo para "a planilha não tem a coluna". É separado para permitir o comportamento "opcional": pular sem reprovar.

### class Param (linhas 44–59)
- Linhas 44–53: a dataclass de um parâmetro, com `nome`, `tipo`, `rotulo` (o texto do formulário), `obrigatorio`, `padrao`, `opcoes` (para `escolha`), `ajuda` e `existente`. `existente=False` indica uma coluna que **será criada**, que portanto não precisa existir antes. `field(default_factory=list)` dá a cada parâmetro a sua própria lista vazia, em vez de todos compartilharem a mesma.
- Linhas 55–59: `__post_init__` roda logo depois da criação. Recusa tipo desconhecido e torna o parâmetro opcional quando ele tem valor padrão, porque se existe padrão ninguém precisa preencher.

### class Habilidade (linhas 62–76)
- Linhas 62–71: a ficha da habilidade: `id`, `nome`, `categoria`, `descricao`, `funcao` (o código), `parametros`, `conhecimento` (quando usar e cuidados) e `origem` (`"nativa"` ou `"personalizada"`).
- Linhas 73–76: `metadados()` devolve tudo como dicionário (os parâmetros via `asdict`) para o painel. A função não vai junto.

### REGISTRO e ERROS_CARGA (linhas 79–80)
- `REGISTRO` é o catálogo central, de id para Habilidade. `ERROS_CARGA` lista os arquivos personalizados que não carregaram, para mostrar no painel.

### habilidade (linhas 83–89) — o decorador
- Um *decorador* é uma função que "embrulha" outra. Escrever `@habilidade(...)` em cima de `def minha(df, p, ctx)` executa `habilidade(...)(minha)`.
- Linhas 85–88: `decorar` recebe a função, descobre a origem (se o módulo da função não começa com `robo.`, ela é personalizada), registra no `REGISTRO` e devolve a função intacta.
- Na prática: basta escrever o `@habilidade` para a tarefa aparecer no catálogo.

### class Contexto (linhas 93–131)
O que a habilidade enxerga além da tabela: onde registrar ocorrências e de quem é a tarefa.
- Linhas 96–97: guarda o relatório, a tabela, o arquivo, o agente e o nome da habilidade.
- Linhas 99–100: `_msg` acrescenta "— Tina (Contatos) · E-mail" ao fim de cada mensagem, para você saber quem disse o quê.
- Linhas 102–109: `erro`, `aviso` e `info` repassam ao relatório com a assinatura. Um **erro reprova o arquivo**; aviso e info não.
- Linhas 111–131: `tratar_invalidos` é o padrão único para valores inválidos, usado por quase todas as habilidades de qualidade.
  - Linhas 114–117: a máscara (uma série de Verdadeiro/Falso dizendo quais linhas são inválidas) tem os vazios tratados como "não inválido". Se não há inválido, nada a fazer.
  - Linhas 118–119: monta até 5 exemplos com o número da linha do Excel e o valor original.
  - Linhas 120–123: `erro` reprova; `aviso` mantém e registra.
  - Linhas 124–127: `vazio` apaga só o valor (vira `pd.NA`, o "vazio" do pandas) e registra aviso "(esvaziados)".
  - Linhas 128–130: `remover` apaga a linha inteira e registra aviso "(linhas removidas)". Esse texto é importante: o Supervisor Saulo procura "linha… removid" para aceitar a remoção (ver `producao.py`).

### ACAO_INVALIDOS (linhas 134–136)
- Um parâmetro pronto e reutilizado: "O que fazer com valores inválidos", com padrão `erro` e opções `erro / aviso / vazio / remover`. Por padrão a postura é a mais segura: reprovar.

### _como_lista (linhas 140–145)
- Aceita lista ou texto separado por vírgula ou quebra de linha e devolve uma lista sem itens vazios. Exemplo: `"email, telefone"` vira `["email", "telefone"]`.

### _como_mapa (linhas 148–158)
- Aceita dicionário ou texto com uma linha por par `original=oficial`. Exemplo: `"online=EAD\npresencial=Presencial"` vira `{"online": "EAD", "presencial": "Presencial"}`. O `split("=", 1)` divide só no primeiro `=`.

### preparar_parametros (linhas 161–209)
Converte o que você digitou no tipo certo e valida. Quando algo está errado, dispara `ErroHabilidade` com uma mensagem clara.
- Linha 163: importa a função que padroniza nomes de coluna ("Nota NPS" vira `nota_nps`).
- Linhas 166–173: para cada parâmetro, pega o valor (ou o padrão). Vazio e obrigatório gera o erro "parâmetro obrigatório … não preenchido". Vazio e opcional fica com o padrão.
- Linhas 174–194: a conversão por tipo. `coluna` e `colunas` são padronizadas como nome de coluna, e por isso você pode digitar "E-mail" e ele acha `e_mail`. `numero` e `inteiro` aceitam vírgula decimal. `booleano` aceita "sim", "s", "true", "1" e "yes". `lista` e `mapa` usam os auxiliares acima. `escolha` precisa estar nas opções.
- Linhas 195–196: falha de conversão vira "valor inválido em 'X'". O `from e` guarda a causa original para o log.
- Linhas 198–208: se as colunas da planilha foram informadas, confere que as colunas usadas existem. Pula as `existente=False` (que serão criadas). Se faltar coluna, dispara `ErroColunaAusente`.

### executar_habilidade (linhas 213–237)
- Linhas 214–218: habilidade que não existe no catálogo vira ERRO, e a tabela volta como estava.
- Linha 219: cria o Contexto.
- Linhas 220–225: prepara os parâmetros conferindo as colunas e roda a função numa **cópia** (`df.copy()`). Se a função não devolver uma tabela, isso é erro.
- Linhas 226–231: coluna ausente. Se a habilidade está marcada `opcional`, vira só INFO ("pulada nesta planilha"). Senão vira ERRO, com a dica de limitar o agente por arquivo ou marcar como opcional.
- Linhas 232–233: outros problemas de configuração viram ERRO.
- Linhas 234–236: qualquer falha inesperada do código é registrada no log com o rastro completo e vira ERRO "Falha ao executar: …".
- Linha 237: em qualquer erro, devolve a tabela **original**. Uma habilidade que quebrou nunca deixa a tabela "pela metade".

### carregar_personalizadas (linhas 240–259)
- Linhas 242–244: limpa os erros antigos e remove do catálogo as personalizadas carregadas antes, para não sobrar versão velha.
- Linhas 248–250: percorre os `.py` da pasta. Arquivos que começam com `_` são ignorados, e é por isso que `_exemplo_habilidade.py` nunca entra.
- Linhas 251–255: carrega o arquivo como módulo. Ao executar o arquivo, o `@habilidade` registra a habilidade.
- Linhas 256–258: arquivo com defeito não derruba o robô; o erro vai para `ERROS_CARGA` e para o log.

### catalogo (linhas 262–263)
- Lista os metadados de todas as habilidades, ordenados: primeiro as nativas, depois por categoria e nome.

### Import final (linha 266)
- Importa `nativas` no fim do arquivo. Ao ser importado, ele executa todos os `@habilidade` e preenche o catálogo. Fica no fim porque `nativas.py` precisa de `Param` e `habilidade`, que só existem depois das linhas acima. O comentário `noqa` cala o verificador de estilo.

**Erros que este arquivo evita**
- Parâmetro obrigatório em branco, número digitado com vírgula, opção inexistente.
- Habilidade tentando usar uma coluna que a planilha não tem (vira erro claro ou é pulada, se opcional).
- Habilidade que quebra deixando a tabela pela metade (sempre volta a original).
- Arquivo personalizado com defeito derrubando o robô.
- Mensagens sem autor (toda ocorrência diz o agente e a habilidade).

---

## robo/habilidades/nativas.py

- **Para que serve.** É o catálogo das 26 habilidades que já vêm com o robô, como padronizar texto, validar CPF, classificar NPS e anonimizar. Cada uma traz o campo "conhecimento", que diz quando usar e quais são os cuidados, como um manual de boas práticas de pesquisa e de Power BI.
- **Onde entra no fluxo.** É importado no fim de `robo/habilidades/__init__.py`. As funções são chamadas por `executar_habilidade` sempre que um agente (Lia, Otto, Ana ou um personalizado) tem a habilidade configurada. O risco de cada uma está em `rh.RISCO_BASE`, e as provas em `rh.PROVAS_HABILIDADES`.

> Em todas as habilidades, `df` é a tabela, `p` são os parâmetros já convertidos e `ctx` é o Contexto. O índice das linhas é o número da linha no Excel, e por isso os exemplos dizem "linha 5".

### Imports (linhas 1–13)
- Linha 1: a docstring.
- Linhas 5–10: `hashlib` (para criar códigos irreversíveis, o *hash*), `re`, `datetime`, `numpy` (matemática vetorial) e `pandas`.
- Linha 12: de `robo/limpeza.py` vêm `_converter` (conversão de tipo no padrão brasileiro), `_detectar_decimal` (descobre se o decimal é vírgula ou ponto), `normalizar_nome_coluna` e `sem_acento`.
- Linha 13: as ferramentas do catálogo.

### Categorias e palavras minúsculas (linhas 15–23)
- Linhas 15–21: os nomes das 7 categorias do catálogo: Padronização, Documentos e contato, Qualidade e validação, Enriquecimento, Pesquisa e Customer Insights, Estrutura e Privacidade (LGPD).
- Linha 23: preposições e artigos que ficam minúsculos no modo título ("Maria **da** Silva").

### _chave (linhas 26–27)
- Transforma um valor em "chave de comparação": sem acento, sem espaços nas pontas e em minúsculas. Exemplo: `" São Paulo "` vira `"sao paulo"`.

### _digitos (linhas 30–35)
- Linhas 31–32: vazio devolve `""`.
- Linhas 33–34: um número como `1234567890.0` (o Excel guarda CPF como número decimal) vira inteiro, para não ganhar ".0".
- Linha 35: tira tudo o que não é dígito (`\D` é "não dígito" em regex). Exemplo: `"(11) 98765-4321"` vira `"11987654321"`.

### _numerica (linhas 38–41)
- Exige que a coluna seja numérica. Se for texto, dispara um erro que sugere usar "Converter tipo" antes. Devolve a coluna como `float64` (número decimal).

---

### 1. padronizar_texto — "Padronizar textos" (linhas 45–70)
- **O que faz:** deixa textos no mesmo formato.
- **Parâmetros:** `colunas`; `modo` (`maiusculo`, `minusculo`, `titulo` [padrão], `frase` ou `nenhum`); `remover_acentos` (padrão Não).
- **Risco (rh.py):** baixo.
- **Conhecimento:** sem padronização, o Power BI mostra três barras para "SÃO PAULO", "são paulo" e "Sao Paulo".
- Linhas 57–59: `titulo` põe tudo em minúsculas e capitaliza cada palavra, exceto as preposições (e só a partir da segunda palavra, `i` > 0).
- Linhas 61–63: um dicionário de funções escolhe a transformação conforme o modo. `lambda` é uma função curta escrita numa linha só.
- Linhas 64–66: aplica só a valores de texto (números e vazios ficam como estão) e, se pedido, remove acentos.
- Linhas 67–69: conta quantos mudaram e registra INFO.
- **Antes/depois:** `"MARIA DA SILVA"` (título) vira `"Maria da Silva"`; `"sp"` (maiúsculo) vira `"SP"`.

### 2. mapear_valores — "De-para de valores" (linhas 73–109)
- **O que faz:** troca valores por uma versão oficial.
- **Parâmetros:** `coluna`; `mapa` (uma linha por par `original=oficial`); `nao_mapeados` (`manter` [padrão], `aviso`, `erro` ou `vazio`).
- **Risco:** médio, porque altera o conteúdo.
- Linhas 88–89: as chaves do mapa e os valores oficiais viram "chaves de comparação" (sem acento e sem maiúsculas).
- Linhas 92–101: percorre os valores. Vazio continua vazio. Se a chave casa, troca e conta (`trocados += mapa[k] != v` soma 1 só se o valor de fato mudou).
- Linhas 102–104: grava a coluna nova e registra quantos foram trocados.
- Linha 105: "fora" são os valores que não estão nem no de-para nem entre os oficiais.
- Linhas 106–108: se a ação não é `manter`, usa `tratar_invalidos`.
- **Antes/depois:** `["A Distância", "online"]` com o mapa `a distancia=EAD, online=EAD` vira `["EAD", "EAD"]`. Com `nao_mapeados=erro`, um "Híbrido" fora da lista **reprova** o arquivo, e é assim que um valor novo nunca passa despercebido.

### 3. converter_tipo — "Converter tipo" (linhas 112–130)
- **O que faz:** força colunas para `texto`, `inteiro`, `decimal`, `data` ou `datahora`.
- **Parâmetros:** `colunas`; `tipo` (obrigatório); `invalidos`.
- **Risco:** médio.
- Linhas 124–125: converte usando a mesma função da limpeza nativa, informando o separador decimal detectado.
- Linhas 126–127: inválido é o que tinha valor e virou vazio após a conversão.
- Linhas 128–129: trata os inválidos, com exemplos mostrando o valor **original**.
- **Antes/depois:** `"R$ 1.234,56"` (decimal) vira `1234.56`; `"dez"` (inteiro) **reprova** com "Valores que não são 'inteiro'".

### 4. arredondar — "Arredondar números" (linhas 133–142)
- **Parâmetros:** `colunas`; `casas` (padrão 2).
- **Risco:** médio, porque altera valores.
- Linhas 140–141: exige coluna numérica e arredonda.
- **Conhecimento:** arredonde no final. Somar valores já arredondados acumula diferenças de centavos.
- **Antes/depois:** `1.23456` vira `1.23`.

### Auxiliares _cpf_valido e _cnpj_valido (linhas 146–163)
- Linhas 147–148: CPF precisa ter 11 dígitos e não pode ter todos iguais ("111.111.111-11" passaria na conta, mas não existe).
- Linhas 149–152: o cálculo oficial dos dois dígitos verificadores. Para o 10º dígito, multiplica os 9 primeiros pelos pesos 10 a 2; para o 11º, os 10 primeiros pelos pesos 11 a 2. O dígito é `(soma × 10 mod 11) mod 10`.
- Linhas 157–162: o CNPJ (14 dígitos) usa os pesos da Receita. O dígito é 0 se o resto for menor que 2; senão, `11 − resto`.

### 5. normalizar_documento — "CPF / CNPJ" (linhas 166–200)
- **Parâmetros:** `colunas`; `tipo` (`auto` [padrão], `cpf` ou `cnpj`); `formato` (`digitos` [padrão] ou `formatado`); `invalidos`.
- **Risco:** baixo.
- Linhas 183–186: extrai os dígitos. Vazio fica vazio e não conta como inválido.
- Linha 187: no `auto`, mais de 11 dígitos é tratado como CNPJ.
- Linhas 188–190: se faltam até 3 dígitos, completa com zeros à esquerda (`zfill`). Isso recupera o zero que o Excel "comeu".
- Linhas 191–196: valida e, se válido e com `formatado`, aplica a máscara `000.000.000-00` ou `00.000.000/0000-00`.
- Linhas 197–199: grava a coluna como texto (`object`) e trata os inválidos.
- **Antes/depois:** `"52998224725"` (formatado) vira `"529.982.247-25"`; `1234567890.0` vira `"01234567890"`; `"52998224724"` (dígito errado) **reprova**; `"11.222.333/0001-81"` vira `"11222333000181"`.
- **Cuidado (LGPD):** CPF é dado pessoal. Se a base vai circular, combine com Anonimizar.

### 6. validar_email — "E-mail" (linhas 203–217)
- **Parâmetros:** `colunas`; `invalidos`.
- **Risco:** baixo; sobe para médio com `invalidos=vazio` e para alto com `remover` (regra de `rh.risco_de`).
- Linha 211: o padrão "algo sem espaço e sem @, um @, algo, um ponto e ao menos 2 letras".
- Linha 214: minúsculas, sem espaços nas pontas e sem espaços no meio.
- Linhas 215–216: inválido é o que não casa com o padrão.
- **Antes/depois:** `" Ana@X.COM "` vira `"ana@x.com"`; `"ana.x.com"` (sem @) **reprova**.
- **Cuidado:** a validação é só de formato; não garante que a caixa de e-mail existe.

### 7. normalizar_telefone — "Telefone (Brasil)" (linhas 220–253)
- **Parâmetros:** `colunas`; `formato` (`formatado` [padrão] ou `digitos`); `ddd_padrao` (opcional); `invalidos`.
- **Risco:** baixo.
- Linha 232: os dígitos do DDD padrão.
- Linha 237: dígitos do telefone sem zeros à esquerda (tira o "0" de "011…").
- Linhas 241–242: com 12 ou 13 dígitos começando por 55, remove o código do país.
- Linhas 243–244: número sem DDD (8 ou 9 dígitos) recebe o DDD padrão, se ele foi informado.
- Linha 245: válido é fixo de 10 dígitos ou celular de 11 com o terceiro dígito igual a 9.
- Linhas 247–248: formata como `(11) 98765-4321`.
- **Antes/depois:** `"+55 (11) 98765-4321"` vira `"(11) 98765-4321"`; `"123"` **reprova**.

### 8. normalizar_cep — "CEP" (linhas 256–279)
- **Parâmetros:** `colunas`; `invalidos`.
- **Risco:** baixo.
- Linhas 271–272: 7 dígitos ganham o zero à esquerda.
- Linhas 273–275: válido é ter 8 dígitos, e a saída é `00000-000`.
- **Antes/depois:** `1310100` vira `"01310-100"`.

### 9. validar_regex — "Validar formato (expressão regular)" (linhas 283–299)
- **Parâmetros:** `coluna`; `padrao` (a regex); `mensagem` (padrão "Valor fora do padrão esperado"); `invalidos`.
- **Risco:** baixo.
- Linhas 293–296: compila a regex. Uma regex mal escrita vira erro de configuração.
- Linha 298: usa `search`, que procura o padrão em qualquer ponto do texto. Por isso o conhecimento lembra: use `^` e `$` para exigir o valor inteiro.
- **Antes/depois:** com `^[A-Z]{2}\d{6}$`, `"AB123456"` passa e `"X1"` **reprova** (1 inválido).

### 10. validar_datas — "Validar datas" (linhas 302–327)
- **Parâmetros:** `coluna`; `nao_futuras` (padrão Sim); `minima` e `maxima` (dd/mm/aaaa, opcionais); `invalidos`.
- **Risco:** baixo.
- Linhas 314–315: a coluna precisa já ser data.
- Linhas 318–319: data maior que agora é marcada.
- Linhas 320–326: aplica os limites mínimo (`lt`, menor que) e máximo (`gt`, maior que).
- Linha 327: trata os inválidos, ignorando vazios.
- **Antes/depois:** `[2020-01-01, 2099-01-01]` reprova só a de 2099.

### 11. checar_duplicados — "Duplicidade por chave" (linhas 330–351)
- **Parâmetros:** `colunas` (a chave); `acao` (`erro` [padrão], `aviso`, `manter_primeiro` ou `manter_ultimo`).
- **Risco:** baixo com erro/aviso; **alto** com `manter_*`, porque apaga linhas.
- Linha 339: `keep=False` marca **todas** as linhas repetidas.
- Linhas 342–346: com `erro` ou `aviso`, registra com exemplos e não mexe. O `getattr(ctx, acao)` chama `ctx.erro` ou `ctx.aviso` pelo nome.
- Linhas 347–351: senão, remove as repetições mantendo a primeira ou a última, e registra "Duplicidades removidas…" (o texto que o Saulo reconhece).
- **Antes/depois:** ids `["1", "1"]` com notas `[5, 9]` e `manter_ultimo` fica só a linha com nota 9, a resposta mais recente (o padrão de mercado em pesquisa).

### 12. completude_minima — "Completude mínima" (linhas 354–370)
- **Parâmetros:** `colunas`; `minimo_pct` (padrão 95); `acao` (`erro` ou `aviso`).
- **Risco:** baixo.
- Linhas 364–369: calcula a % preenchida de cada coluna. Abaixo do mínimo, registra erro ou aviso.
- **Antes/depois:** `[1, vazio, vazio, vazio]` (25%) com mínimo 90 **reprova**. O porquê: 40% de notas vazias gera indicador enviesado.

### 13. outliers — "Valores atípicos" (linhas 373–402)
- **Parâmetros:** `coluna`; `metodo` (`iqr` [padrão] ou `zscore`); `limite` (padrão 1,5); `acao` (`sinalizar` [padrão], `aviso`, `erro` ou `remover`).
- **Risco:** baixo; alto com `remover`.
- Linhas 389–392: no IQR (intervalo interquartil), Q1 e Q3 são os quartis de 25% e 75%. Fora é o que fica abaixo de `Q1 − 1,5×IQR` ou acima de `Q3 + 1,5×IQR`.
- Linhas 393–395: no z-score, mede quantos desvios-padrão o valor está da média. Se o desvio for zero, ninguém é outlier.
- Linhas 397–401: `sinalizar` cria a coluna `<coluna>_outlier` com Sim/Não e não apaga nada.
- **Antes/depois:** `[10, 11, 12, 13, 9, 10, 1000]` gera `v_outlier` = "Sim" só para o 1000.
- **Cuidado:** outlier não é sinônimo de erro (pode ser um cliente grande de verdade).

### 14. filtrar_linhas — "Filtrar linhas" (linhas 405–429)
- **Parâmetros:** `condicao` (uma expressão como `nota_nps >= 0 and status == 'Concluída'`); `acao` (`remover` [padrão], `aviso` ou `erro`).
- **Risco:** **alto** com remover; baixo com aviso/erro.
- Linhas 414–417: converte colunas `Int64` (inteiro que aceita vazio) para decimal, porque o `eval` do pandas lida mal com elas, e avalia a condição. Condição mal escrita vira erro de configuração.
- Linhas 418–419: garante uma série de Verdadeiro/Falso.
- Linhas 421–425: `remover` mantém só as linhas que atendem e registra "N linha(s) removida(s) pelo filtro".
- Linhas 426–429: `aviso`/`erro` só registram.
- **Antes/depois:** `s != 'teste'` sobre `["ok", "teste"]` deixa 1 linha.

### 15. preencher_vazios — "Preencher vazios" (linhas 433–469)
- **Parâmetros:** `colunas`; `metodo` (`valor`, `anterior`, `media`, `mediana` ou `moda`); `valor` (quando o método é valor).
- **Risco:** médio; **alto** com média, mediana ou moda (imputação estatística).
- Linhas 449–458: com valor fixo, ele é obrigatório. Se a coluna for numérica, o valor precisa ser número.
- Linhas 459–460: `anterior` copia o valor de cima (`ffill`), ideal para células mescladas.
- Linhas 461–463: média ou mediana.
- Linhas 464–467: moda (o valor mais frequente).
- Linha 468: sempre registra **aviso**, porque preencher é inventar dado.
- **Antes/depois:** `["A", vazio, "B"]` com anterior vira `["A", "A", "B"]`.
- **Cuidado importante:** preencher notas de pesquisa com média inventa respostas.

### 16. coluna_calculada — "Coluna calculada" (linhas 472–488)
- **Parâmetros:** `nova_coluna` (criada, `existente=False`); `expressao`.
- **Risco:** médio.
- Linhas 482–486: converte `Int64` para decimal e calcula com `eval`. Fórmula inválida vira erro.
- **Conhecimento:** use para medidas de linha. Razões de total (% de promotores) devem ser medidas DAX, senão a média das razões fica errada no total.
- **Antes/depois:** `q=[2,3]`, `p=[1.5,2.0]` e `t = q * p` dá `[3.0, 6.0]`.

### 17. classificar_faixas — "Faixas" (linhas 491–515)
- **Parâmetros:** `coluna`; `nova_coluna`; `limites` (em ordem crescente); `rotulos` (um a mais que os limites).
- **Risco:** médio.
- Linhas 504–511: valida que os limites são números, que estão em ordem e que a quantidade de rótulos está certa.
- Linha 513: `pd.cut` com `right=False` faz cada limite **iniciar** a faixa seguinte. Os extremos vão de −∞ a +∞.
- **Antes/depois:** idades `[17, 18, 30]`, limites `18, 25` e rótulos `<18, 18-24, 25+` dão `["<18", "18-24", "25+"]`.

### 18. extrair_data — "Partes da data" (linhas 518–547)
- **Parâmetros:** `coluna`; `partes` (padrão `ano, mes, ano_mes`; também aceita `mes_nome`, `trimestre`, `dia_semana` e `semana_ano`).
- **Risco:** baixo.
- Linhas 529–530: exige coluna de data.
- Linhas 531–542: nomes dos meses e dias em português e um "gerador" (função) por parte.
- Linhas 543–546: parte desconhecida vira erro. Cada parte cria `<coluna>_<parte>`.
- **Antes/depois:** `2026-10-17` gera `d_ano = 2026` e `d_ano_mes = "2026-10"`.
- **Conhecimento:** num Power BI com modelo estrela, prefira a `dim_calendario`.

### 19. dividir_coluna — "Dividir coluna" (linhas 550–562)
- **Parâmetros:** `coluna`; `separador`; `novas_colunas`.
- **Risco:** médio.
- Linha 559: divide em no máximo N partes. A última recebe o restante. `regex=False` faz o separador ser lido literalmente.
- Linhas 560–561: cada nova coluna recebe a parte, sem espaços nas pontas. Se a parte não existir, fica vazia.
- **Antes/depois:** `"São Paulo - SP"` com `" - "` dá cidade `"São Paulo"` e uf `"SP"`.

### 20. juntar_colunas — "Juntar colunas" (linhas 565–575)
- **Parâmetros:** `colunas`; `separador` (padrão espaço); `nova_coluna`.
- **Risco:** baixo.
- Linhas 571–574: junta os valores não vazios de cada linha (`axis=1` significa "por linha").
- **Antes/depois:** `a=["X","Y"]`, `b=["1", vazio]` e separador `/` dão `["X/1", "Y"]`.

### 21. classificar_nps — "Classificar NPS" (linhas 579–603)
- **Parâmetros:** `coluna` (nota de 0 a 10); `nova_coluna` (padrão `grupo_nps`); `invalidos` (padrão erro).
- **Risco:** baixo.
- Linhas 592–594: inválida é a nota fora de 0–10 ou não inteira, como 7,5.
- Linhas 595–597: 9–10 Promotor, 7–8 Neutro, 0–6 Detrator (metodologia Bain/Reichheld). `np.select` testa as condições em ordem.
- Linhas 598–602: calcula e registra o NPS da base: `100 × (promotores − detratores) / respostas`.
- **Antes/depois:** `[10, 9, 8, 7, 6, 0]` dá `[Promotor, Promotor, Neutro, Neutro, Detrator, Detrator]`; a nota 11 **reprova**.
- O conhecimento inclui a medida DAX pronta para o Power BI.

### 22. classificar_csat — "Classificar CSAT (top-2-box)" (linhas 606–623)
- **Parâmetros:** `coluna`; `escala` (`5` [padrão], `7` ou `10`); `nova_coluna` (padrão `satisfeito`); `invalidos`.
- **Risco:** baixo.
- Linhas 619–620: inválida é a nota menor que 1 ou maior que a escala.
- Linha 622: "Sim" se a nota está entre as duas mais altas (`>= escala − 1`).
- **Antes/depois:** na escala 5, `[5, 4, 3]` dá `["Sim", "Sim", "Não"]`.

### 23. categorizar_texto — "Codificar verbatins por tema" (linhas 626–666)
- **Parâmetros:** `coluna`; `temas` (`Tema=palavra1, palavra2`); `nova_coluna` (padrão `tema`); `multiplos` (padrão Sim); `sem_tema` (padrão "Outros").
- **Risco:** médio.
- Linhas 641–647: para cada tema, monta uma regex com `\b(palavra1|palavra2)`. O `\b` é "início de palavra", e é por isso que "atend" pega atendimento e atendente. Sem nenhum tema configurado, é erro.
- Linhas 649–658: para cada comentário (sem acento e em minúsculas), lista os temas que casam. Nenhum vira "Outros"; com `multiplos`, junta os temas com "; ".
- Linhas 660–665: registra quantos foram codificados e a % sem tema. Acima de 30% gera **aviso** "revise as palavras-chave".
- **Antes/depois:** `["Mensalidade cara", "Atendente demorou", "Adorei"]` dá `["Preço", "Atendimento", "Outros"]`.
- **Cuidado:** não entende ironia nem negação ("não é caro" conta como Preço).

### 24. selecionar_colunas — "Selecionar colunas" (linhas 670–681)
- **Parâmetros:** `modo` (`excluir` [padrão] ou `manter`); `colunas`.
- **Risco:** **alto**, porque some com dados.
- Linhas 678–680: `manter` fica com as colunas pedidas **mais** as de auditoria (que começam com `_`), para nunca perder a rastreabilidade.
- Linha 681: `excluir` remove as colunas listadas.
- **Antes/depois:** `a, obs` excluindo `obs` deixa só `a`.

### 25. renomear_colunas — "Renomear colunas" (linhas 684–695)
- **Parâmetros:** `mapa` (`atual=novo`).
- **Risco:** médio.
- Linhas 691–694: padroniza os nomes dos dois lados e exige que as colunas atuais existam.
- **Antes/depois:** `vlr` vira `valor`.

### 26. anonimizar — "Anonimizar dados pessoais" (linhas 699–735)
- **Parâmetros:** `colunas`; `metodo` (`hash` [padrão], `mascarar` ou `remover`); `sal` (a chave secreta, opcional).
- **Risco:** **alto**, porque altera dado de forma irreversível.
- Linhas 713–715: hash sem chave gera aviso, porque um hash de CPF sem chave pode ser revertido testando todos os CPFs possíveis.
- Linhas 717–719: `remover` apaga a coluna.
- Linhas 720–722: `hash` aplica SHA-256 sobre `sal|valor-normalizado` e guarda os 16 primeiros caracteres. O mesmo CPF vira sempre o mesmo código (com a mesma chave), o que permite contar e cruzar bases sem expor ninguém.
- Linhas 724–733: `mascarar`. E-mail vira `a***@dominio`; os demais valores mostram só o último quarto (no mínimo 2 caracteres).
- **Antes/depois:** dois `"52998224725"` com sal `"k"` viram o mesmo código e nenhum é igual ao original; `"ana@x.com"` mascarado vira `"a***@x.com"`.

**Erros que este arquivo evita**
- Mesma categoria com grafias diferentes no Power BI (padronizar e de-para).
- Cruzamento por CPF, CEP ou telefone que falha por pontuação ou zero perdido.
- CPF ou CNPJ digitado errado passando batido (dígito verificador).
- E-mails inválidos derrubando a taxa de entrega de pesquisa.
- Notas de NPS ou CSAT fora da escala distorcendo o indicador.
- Duplicidade inflando contagens.
- Dado pessoal circulando sem necessidade (anonimizar).
- Remoção silenciosa (toda remoção é registrada com quantidade e exemplos).

---

## robo/rh.py

- **Para que serve.** É o RH da empresa: define os níveis (estagiário a especialista), o risco de cada habilidade, o que cada nível pode fazer e, principalmente, o **processo seletivo técnico**. Cada habilidade e cada pessoa do prédio tem provas com resposta conhecida, que executam o código de verdade. Também guarda a "ficha profissional" de cada pessoa (cargo, metodologias, limites e gestor).
- **Onde entra no fluxo.** Quem chama: `agentes.py` (validação, `carregar`, `salvar`, `lista`), `producao.py` (`agentes_reprovados_no_rh`, usado pela Carla), `estrategia.py` (avaliações de sprint) e o painel (fichas). Quem é chamado: os módulos de cada andar (`leitura`, `limpeza`, `validacao`, `modelagem`, `banco`, `escrita`, `monitor`, `analise`, `excel`, `producao`, `quadro`, `ti` e `canal`), cujas funções reais as provas executam.

### Docstring (linhas 1–18)
- Linhas 3–7: ninguém trabalha sem passar nas provas.
- Linhas 9–14: o que cada nível faz. **Estagiário** em modo observação; **júnior** só risco baixo; **pleno** baixo e médio; **sênior** e **especialista**, todos os riscos.
- Linhas 16–17: transparência. Os agentes são programas *determinísticos* (mesma entrada, mesma saída); o "conhecimento" deles é metodologia codificada, não uma IA que opina.

### Imports (linhas 20–27)
- Linha 22: `io` (não usado neste arquivo).
- Linha 23: `tempfile` cria pastas temporárias que somem sozinhas.
- Linha 24: `lru_cache` é um *cache*, uma memória que guarda o resultado de uma função para não recalcular. Aqui as provas rodam uma vez por sessão.

### Níveis, riscos e áreas (linhas 29–39)
- Linha 29: `NIVEIS`, os cinco níveis de quem executa habilidades.
- Linhas 30–31: os nomes bonitos, incluindo Coordenador(a) e Gerente.
- Linhas 32–33: `RISCO_MAXIMO` por nível. O estagiário aparece com `"alto"`. Parece estranho, mas é proposital: como ele **só observa numa cópia**, pode "praticar" qualquer tarefa sem risco nenhum. Júnior vai até baixo; pleno até médio; os demais até alto.
- Linhas 34–35: `CARGOS_GESTAO`. Coordenador e gerente não executam habilidades nos dados; respondem por pessoas, metas e liberação.
- Linhas 36–37: a ordem dos riscos (0, 1, 2) e os nomes com acento.
- Linhas 38–39: as 7 áreas do organograma.

### RISCO_BASE (linhas 42–51)
- Linhas 43–46: **baixo**, para o que só valida ou padroniza formato (texto, documento, e-mail, telefone, CEP, regex, datas, completude, NPS, CSAT, partes da data, juntar, duplicados, outliers).
- Linhas 47–49: **médio**, para o que altera conteúdo (de-para, converter, arredondar, faixas, coluna calculada, dividir, codificar texto, renomear, preencher vazios).
- Linha 50: **alto**, para o que some com dados (filtrar, selecionar colunas, anonimizar).

### risco_de (linhas 54–66)
O risco **com os parâmetros escolhidos**:
- Linha 57: parte do risco base (o desconhecido vale médio).
- Linhas 58–59: se o parâmetro manda **remover** inválidos ou a ação é remover/manter_primeiro/manter_ultimo, o risco vira **alto**. Apagar linha é sempre alto.
- Linhas 60–61: `invalidos=vazio` sobe o baixo para médio, porque apagar um valor já é alteração.
- Linhas 62–63: preencher com média, mediana ou moda é alto, porque altera indicadores.
- Linhas 64–65: filtrar só com aviso ou erro é baixo, porque não remove nada.

### nivel_permite (linhas 69–70)
- O risco da tarefa precisa ser menor ou igual ao risco máximo do nível. Um nível desconhecido vale médio.

### _df (linhas 74–77)
- Monta uma tabela de prova cujo índice começa em 2, imitando o Excel (a linha 1 é o cabeçalho). Assim as mensagens "linha 2" batem com o Excel.

### PROVAS_HABILIDADES (linhas 80–148)
Cada prova é uma tupla `(descrição, tabela, parâmetros, verificação)`. A verificação é uma função que recebe a tabela de saída `d` e o relatório `r`. Em cada habilidade há um **caso bom** (o resultado certo) e, quase sempre, um **erro plantado** (que precisa ser pego):

| Habilidade (linhas) | Caso bom | Erro plantado / caso difícil |
|---|---|---|
| padronizar_texto (81–84) | "MARIA DA SILVA" vira "Maria da Silva" | "sp" vira "SP" |
| mapear_valores (85–89) | "A Distância" e "online" viram "EAD" | "Híbrido" fora da lista com `nao_mapeados=erro` precisa reprovar |
| converter_tipo (90–93) | "R$ 1.234,56" vira 1234,56 | "dez" como inteiro precisa reprovar |
| arredondar (94) | 1,23456 vira 1,23 | — |
| normalizar_documento (95–100) | CPF válido formatado sem erro; CNPJ vira dígitos | zero perdido (1234567890.0 vira "01234567890"); dígito verificador errado reprova |
| validar_email (101–103) | " Ana@X.COM " vira "ana@x.com" | sem @ reprova |
| normalizar_telefone (104–106) | "+55 (11) 98765-4321" vira "(11) 98765-4321" | "123" reprova |
| normalizar_cep (107) | 1310100 vira "01310-100" | — |
| validar_regex (108–109) | "AB123456" passa | "X1" reprova, exatamente 1 erro |
| validar_datas (110–111) | 2020 passa | 2099 reprova, exatamente 1 |
| checar_duplicados (112–115) | `manter_ultimo` fica com a nota 9 | chave repetida reprova |
| completude_minima (116–117) | — | 25% preenchido com mínimo 90 reprova |
| outliers (118–119) | 10 é "Não" | 1000 é "Sim" |
| filtrar_linhas (120) | linha "teste" removida | — |
| preencher_vazios (121–122) | "anterior" preenche a célula mesclada | — |
| coluna_calculada (123–124) | q × p = [3, 6] | — |
| classificar_faixas (125–127) | 18 entra em "18-24" | 17 é "<18" |
| extrair_data (128–129) | ano 2026 e ano_mes "2026-10" | — |
| dividir_coluna (130–131) | "São Paulo - SP" | — |
| juntar_colunas (132–133) | vazio ignorado ("Y") | — |
| classificar_nps (134–137) | 10, 9 / 8, 7 / 6, 0 nos grupos certos | nota 11 reprova |
| classificar_csat (138) | top-2-box 5, 4 Sim e 3 Não | — |
| categorizar_texto (139–141) | Preço, Atendimento | "Adorei" vira "Outros" |
| selecionar_colunas (142–143) | exclui `obs` | — |
| renomear_colunas (144) | vlr vira valor | — |
| anonimizar (145–147) | hash igual para o mesmo CPF e diferente do original | máscara do e-mail "a***@x.com" |

### _rodar_caso (linhas 151–161)
- Linhas 154–156: cria um relatório de prova e roda a habilidade **pelo mesmo caminho da produção** (`executar_habilidade`).
- Linhas 157–158: aplica a verificação. Se falhar, o motivo são os erros do relatório ou "resultado diferente do esperado".
- Linhas 159–160: uma exceção também reprova, com o tipo e a mensagem.

### _provas_habilidade_cache (linhas 164–167)
- `@lru_cache` guarda o resultado por habilidade. O resultado é convertido em tuplas porque o cache exige valores que não mudam.

### provas_da_habilidade (linhas 170–177)
- Linhas 173–176: habilidade **personalizada** usa as provas que o autor colocou em `funcao.provas` (se houver) e roda sempre, sem cache.
- Linha 177: nativa usa o cache e devolve dicionários novos.

### Provas dos agentes nativos (linhas 181–270)
Cada função monta um caso real e devolve uma lista de pares `(descrição, passou?)`.
- **_prova_leitura (181–195), Leo:** cria um Excel com título na linha 1, linha vazia, cabeçalho na 3 e `#REF!` na 4, e um CSV em Windows-1252 com `;`. Exige achar o cabeçalho abaixo do título, preservar a linha 4 do Excel, **não deixar o #REF! sumir** e ler "João" corretamente.
- **_prova_limpeza (198–211), Lia:** tabela com "Total", duplicata exata, "N/A", moeda e matrícula "00123". Exige o nome padronizado `valor_r`, 1234,56 como número, zeros preservados, linha de Total removida (para não somar em dobro no Power BI), duplicata removida (3 linhas) e N/A virando vazio.
- **_prova_validacao (214–224), Otto:** regra com obrigatórias, chave única e faixa 0–10. O caso ruim 1 tem id repetido e nota 11; o ruim 2 não tem a coluna "nota"; o caso bom r3 está correto. Exige barrar os dois ruins e **aprovar** o bom. Isso garante que ele não barra tudo por excesso de zelo.
- **_prova_modelagem (227–237), Ana:** gera fato e `dim_curso`. A dimensão não pode repetir (2 cursos), o *merge* (a junção de tabelas pela chave) não pode perder linha, e o calendário de 2026 precisa ter 365 dias.
- **_prova_banco (240–247), Beto:** inteiro vira `bigint`, data vira `date`, vazio vira NULL, e 12.0 numa coluna de texto vira "12" (sem ".0").
- **_prova_publicacao (250–258), Duda:** grava Excel e CSV, relê de forma idêntica e não deixa arquivo temporário `~robo_tmp` (gravação atômica).
- **_prova_recepcao (261–270), Rita:** ignora `~$base.xlsx` (o arquivo de bloqueio do Excel aberto) e `desktop.ini`, aceita `base.xlsx` e confere que dá para abrir.

### _base_nps (linhas 273–280)
- Gera 400 respostas sorteadas com semente fixa (o sorteio é sempre igual, portanto reprodutível). Com `medicina_ruim=True`, metade das notas de Medicina é trocada por 0–5: um **efeito real plantado**.

### _prova_analistas (linhas 283–312)
- Linhas 287–289: NPS de `[10,10,9,8,7,6,0,10]`: 4 promotores (p = 0,5) e 2 detratores (d = 0,25) dão NPS 25. A margem de 95% deve bater com `1,96 × √((p + d − (p − d)²)/n)`.
- Linhas 290–298: roda perfil, indicadores, estatística, foto (snapshot), monitoramento e resumo numa base com efeito (a) e numa sem efeito (b). Também remove a coluna "curso" (m) para testar o alerta.
- Linhas 299–312: as provas por analista. **Bia** reconhece a categoria e calcula o p75. **Caio** acerta NPS, margem e coluna. **Davi** aplica a correção de Holm certa, **acha Medicina** (o efeito real) e **não inventa diferença** na base sem efeito. **Eva** percebe a coluna que sumiu e compara o indicador entre cargas. **Fábio** cita a margem no resumo e separa "Diferenças reais" de acaso.

### _ConexaoFalsa (linhas 315–323)
- Imita o PostgreSQL. Cada `execute` devolve a próxima contagem da lista, ou 0 se a consulta tiver `LEFT JOIN` (a checagem de chaves órfãs). Assim dá para testar a DBA sem banco instalado.

### _prova_dba (linhas 326–337), Dora
- Espera 10 linhas na fato. Com as contagens [5, 10] tudo bate e ela aprova. Com [5, 9] uma linha "se perdeu" e ela precisa disparar `ErroCargaDados`, ou seja, **desfazer a carga**.

### _prova_supervisor (linhas 340–355), Saulo
- A tabela bruta tem 3 linhas e a publicada tem 2. No caso bom, existe "Linhas duplicadas removidas" com quantidade 1 e ele aceita. No caso ruim, sem registro, ele precisa **barrar** a linha que sumiu sem explicação.

### _prova_coordenadores (linhas 358–370)
- **Carla:** libera com checklist verde e **não libera** com um item vermelho que bloqueia.
- **Marcos:** um destaque significativo com base 12 (abaixo de 30) precisa reprovar a revisão e listar a ressalva "base menor".

### _prova_excel (linhas 373–398), Sala Excel
- Gera uma entrega real com curso "B*" (curinga) e "=C" (tentativa de fórmula).
- **Ricardo:** 15 ou mais conferências e aba Resumo. **Pedro:** escapa os curingas do CONT.SES (`"B~*"`) e acerta a base de A (2). **Lúcia:** NPS em fórmula (`B8-B9`) com valor esperado 0. **Tânia:** 2 SOMASES por loja, e a soma de L2 igual a 60. **Gabriel:** o texto "=C" fica como **texto** (sem *injeção de fórmula*, quando um texto malicioso vira fórmula ao abrir o Excel) e a primeira aba é Resumo.

### PROVAS_NATIVAS (linhas 401–403)
- Liga cada id à sua função de prova.

### _provas_nativas_cache (linhas 406–451)
Roda **todas** as provas do prédio uma vez por sessão (graças ao cache):
- Linhas 409–414: provas dos nativos, do supervisor e da DBA. Se a função de prova quebrar, a pessoa fica reprovada em "Execução das provas".
- Linhas 415–422: Sala Excel. Se quebrar, os 5 ficam reprovados.
- Linhas 423–429: coordenadores.
- Linhas 430–436: analistas (os ids levam o prefixo `analise_`).
- Linhas 438–450: quadro de pessoal, TI e canal. As provas são *somadas* às que já existiam (`resultado[destino] + [...]`). O `removesuffix("_canal")` permite que uma prova do canal se junte à da mesma pessoa.
- O porquê de tratar exceções: uma prova que quebra **nunca** pode virar "aprovado".

### processo_seletivo (linhas 454–476)
- Linha 456: começa com as provas da própria função da pessoa.
- Linhas 459–466: para cada habilidade ativa, roda as provas e prefixa com `[id]`. Habilidade sem prova vira **pendência**.
- Linhas 467–470: se o nível não permite o risco, vira pendência "não pode usar".
- Linhas 471–476: **bloqueios** são as provas reprovadas mais as pendências de nível. As demais pendências viram **ressalvas** (não bloqueiam). Aprovado significa nenhum bloqueio.

### FICHAS (linhas 480–621)
A ficha de cada pessoa que não está no quadro de `quadro.py` nem no de `ti.py`. Campos: `cargo`, `nivel`, `area`, `metodologias`, `responsabilidades`, `criterios` e `limites`. Destaques:
- Linhas 481–487, Rita: Analista Sênior de Ingestão. Limite: "Não abre nem altera o conteúdo das planilhas".
- Linhas 488–492, Leo: Engenheiro Sênior de Extração. Não interpreta tipos.
- Linhas 493–500, Lia: **Especialista** em Qualidade (DAMA-DMBOK), com limiar de 95% para conversão. "Não inventa valores".
- Linhas 501–505, Otto: Auditor Sênior, princípio tudo-ou-nada. "Não corrige dados: só aprova ou barra".
- Linhas 506–511, Ana: Arquiteta Sênior (Kimball). Não cria medidas de negócio.
- Linhas 512–517, Beto: PostgreSQL e ELT, arquitetura medalhão. "Nunca apaga tabelas (DROP)".
- Linhas 518–521, Duda: gravação atômica. "Não publica nada com erro".
- Linhas 522–527, Saulo: princípio dos quatro olhos. "Não executa etapas: só confere".
- Linhas 528–532, Dora: reconciliação antes do *commit* (a confirmação final de uma transação no banco).
- Linhas 533–537, Carla: gate de produção. "Só libera com 100% do checklist verde".
- Linhas 538–542, Marcos: revisão por pares. "Não altera números: aponta ressalvas".
- Linhas 543–551, Ricardo: Gerente da Sala Excel, ex-Microsoft. Também coordena a limpeza no que o Excel corromperia (IDs de 16+ dígitos, textos acima de 32.767 caracteres, mais de 1.048.576 linhas, datas antes de 1900).
- Linhas 552–560, Helena: Coordenadora de RH. "Não contrata por indicação: só por prova".
- Linhas 561–567, Iara: Inovação, no máximo 3 ideias por sprint. Não implementa sozinha.
- Linhas 568–573, Nina: Assistente Júnior do canal. "Não inventa resposta", só encaminha.
- Linhas 574–594, Pedro, Lúcia, Tânia e Gabriel: especialistas da Sala Excel.
- Linhas 595–620, Bia, Caio, Davi, Eva e Fábio: os analistas do 2º andar. Por exemplo, Davi: "Correlação não é causa".

### _poder_de_bloqueio (linhas 624–629)
- Estagiário, nível que não bloqueia, ou cargo sem função: "Não bloqueia: relata para quem decide".
- Fases engenharia e publicação: "Pode bloquear a publicação".
- Demais fases: "Achado vira ressalva", porque o dado já está publicado.

### _nome_pessoa (linhas 632–644)
- Transforma um id em "Nome (Cargo)", procurando na TI, no quadro e no canal. Se der erro, devolve o próprio id.

### ficha (linhas 647–683)
- Linha 649: parte da ficha fixa (FICHAS).
- Linhas 651–658: pessoa da **TI** monta a ficha a partir de `ti.EQUIPE_TI`, com o limite "Não bloqueia planilhas: alerta no canal #ti".
- Linhas 659–664: pessoa do **quadro** monta a ficha a partir de `quadro.QUADRO`, com o poder de bloqueio.
- Linhas 665–676: **agente personalizado**. As metodologias são as categorias das habilidades dele; o limite é o risco máximo do nível; se for estagiário, acrescenta "trabalha em observação".
- Linhas 677–679: preenche o gestor ("Você (dono)" ou o nome do gestor).
- Linhas 680–682: guarda o nível técnico, troca pelo nome bonito e anexa o resultado do processo seletivo.

**Erros que este arquivo evita**
- Pessoa trabalhando sem ter provado que sabe (as provas executam o código real).
- Júnior executando tarefa de risco alto.
- Prova que quebra sendo contada como aprovada.
- Avaliador que barra tudo (há sempre um caso bom que precisa passar).
- Estatística que "inventa" diferença (a prova sem efeito real).
- Carga no banco com linha perdida (prova da DBA).
- Injeção de fórmula no Excel (prova do Gabriel).

---

## robo/producao.py

- **Para que serve.** É o portão de produção. Cada agente confere a própria etapa, mas aqui **quem não executou** confere o conjunto antes de publicar: Saulo concilia linhas e chaves, Dora reconcilia no banco e Carla assina a liberação. No 2º andar, Marcos revisa as análises e só aponta ressalvas, porque o dado já está publicado.
- **Onde entra no fluxo.** Quem chama: `robo/pipeline.py` (`processar_arquivo`). `conferencia_supervisor` roda logo após o tratamento, `checklist_engenharia` antes da publicação, `checklist_analise` depois da análise e `tabela_checklist` no relatório de qualidade. A reconciliação da Dora fica em `robo/banco.py` (`reconciliar`). Quem é chamado: `rh` e `limpeza`.

### Docstring (linhas 1–11)
- Os quatro conferentes e o princípio dos "quatro olhos": **quem faz não é quem aprova**. O porquê: quem fez tende a não ver o próprio erro, como numa auditoria contábil.

### Imports (linhas 13–19)
- `re`, `pandas` e `normalizar_nome_coluna`.

### SUPERVISORES (linhas 21–34)
- Os cartões de Saulo (supervisor, 1º andar, faz ronda), Dora (DBA, 1º andar), Carla (coordenadora, 1º andar, faz ronda) e Marcos (coordenador, 2º andar, faz ronda). São usados no escritório 3D e na lotação.

### RE_REMOCAO (linha 36)
- Uma regex que reconhece mensagens de remoção: "linha… removid", "duplicidade… removid" ou "removid… linha", sem diferenciar maiúsculas. É assim que o Saulo sabe que uma remoção **tem motivo registrado**.

### _item (linhas 39–40)
- Acrescenta um item ao checklist: nome, ok, detalhe e se bloqueia.

### conferencia_supervisor (linhas 43–86), Saulo
- Linhas 46–51: para cada aba bruta, acha a tabela tratada correspondente.
- Linhas 52–56: **conciliação de linhas.** Perdidas = lidas − publicadas. Explicadas = soma das quantidades nas ocorrências daquela tabela cuja mensagem casa com `RE_REMOCAO` e **não** contém "teria", o que exclui simulações. Precisam ser iguais: toda linha que sumiu precisa ter motivo.
- Linha 57: a tabela precisa ter dados.
- Linhas 58–60: os nomes de coluna precisam estar em `snake_case` (minúsculas e `_`) e ser únicos.
- Linhas 62–72: para cada dimensão (exceto o calendário), a chave precisa ser única e não vazia, e toda chave da fato precisa existir na dimensão (sem chaves "órfãs"). Uma chave órfã faz o Power BI mostrar "(Em branco)".
- Linhas 73–76: com modelo estrela, a fato precisa ter o mesmo número de linhas da base (a modelagem não perdeu nem duplicou).
- Linhas 77–79: as colunas de auditoria `_arquivo_origem` e `_processado_em` precisam existir nas fatos.
- Linhas 81–85: item que falha e bloqueia vira **ERRO** "Supervisor de planilhas barrou: …". Tudo OK vira INFO.

### agentes_reprovados_no_rh (linhas 89–91)
- Lista os ids com alguma prova reprovada no cache do RH.

### checklist_engenharia (linhas 94–114), Carla
- Linha 99: a equipe precisa estar aprovada no RH. Se alguém do prédio foi reprovado, **nada é liberado**. O porquê: não se publica com um profissional que falhou na prova.
- Linhas 100–101: nenhum agente com configuração inválida.
- Linhas 102–104: a auditoria não pode ter erros (desconsiderando os que vieram do próprio Saulo ou da equipe, que já estão nos itens seguintes).
- Linhas 105–106: a conferência do Saulo precisa estar aprovada.
- Linhas 107–110: as conferências dos plenos e juniores (do `quadro.py`) que bloqueiam precisam estar OK.
- Linhas 111–112: com banco habilitado, a reconciliação da Dora precisa ter passado.
- Linhas 113–114: liberado só se **todos** os itens estiverem OK.

### checklist_analise (linhas 117–137), Marcos
- Linhas 119–120: sem análise, nada a revisar.
- Linhas 123–131: resumo escrito; todos os analistas concluíram; todo indicador com `n` e margem; nenhum destaque significativo com base abaixo do mínimo. Todos os itens têm `bloqueia=False`.
- Linhas 132–135: inclui as conferências do 2º andar (Sérgio, Larissa, Igor), exceto as dos estagiários.
- Linhas 136–137: devolve o resultado, os itens e a lista de ressalvas.
- O porquê de nunca bloquear: a análise roda **depois** da publicação. Barrar ali não desfaria nada; o certo é avisar antes de alguém apresentar o número.

### tabela_checklist (linhas 140–148)
- Junta os checklists numa tabela (responsável, item, status OK/FALHOU, detalhe, bloqueia) para a aba `checklist_producao` do relatório de qualidade.

**Erros que este arquivo evita**
- Linhas que somem sem explicação entre a planilha original e a publicada.
- Chaves órfãs entre fato e dimensão (o "(Em branco)" no Power BI).
- Modelagem que duplica ou perde linhas.
- Colunas com nomes quebrados ou repetidos.
- Publicar com alguém reprovado no RH ou com um agente mal configurado.
- Apresentar destaque estatístico com base pequena.

---

## robo/quadro.py

- **Para que serve.** É o quadro de pessoal completo, do gerente ao estagiário, em todos os andares. "Ninguém é decorativo": cada cargo tem uma conferência própria, executada em todo arquivo, e uma prova técnica (um caso bom que deve passar e um caso ruim que precisa ser pego). Também define o que cada nível decide, executa e não faz.
- **Onde entra no fluxo.** Quem chama: `robo/pipeline.py`, por meio de `_conferencias_equipe`, que chama `quadro.conferir(fase, ctx)` nas fases `engenharia`, `publicacao`, `analise`, `excel`, `governanca` e `fim`, e de `manchete`. `rh.py` chama `provas_quadro`, e o painel usa `QUADRO`, `POR_ID`, `ESCOPO_NIVEL` e `lotacao`. Quem é chamado: `limpeza`, `analise` (`chave_base`), `excel` (`Entrega`) e `openpyxl` (leitura dos arquivos gravados).

### Docstring (linhas 1–24)
- Linhas 6–16: o escopo por senioridade e o **porquê** de cada regra:
  - **Gerente:** responde por metas, prazos e manchete; não executa nem aprova o próprio trabalho.
  - **Coordenador:** é o portão; pode **bloquear**.
  - **Especialista/Sênior:** executa as etapas críticas e revisa.
  - **Pleno:** faz a segunda conferência independente. No 1º andar **bloqueia**; no 2º e no 3º, vira ressalva.
  - **Júnior:** checagens objetivas de lista fechada. Também bloqueia no 1º andar, "porque o que ele confere são regras objetivas (não opinião)".
  - **Estagiário:** observa; nunca altera e nunca bloqueia.
- Linhas 18–23: as fases em que cada conferência roda.

### Imports (linhas 26–37)
- `json`, `random` (sorteio), `re`, `dataclass`/`field`, `datetime`, `Path`, `pandas` e `normalizar_nome_coluna`.

### ESCOPO_NIVEL (linhas 39–55)
- Para cada nível: nome, o que **decide**, se **bloqueia**, o que **executa** e o que **não faz**. Gerente e estagiário têm `bloqueia: False`.

### AUDITORIA (linha 57)
- As colunas técnicas de rastreio (`_arquivo_origem`, `_processado_em`, `_aba_origem`, `_linha_origem`), ignoradas em algumas checagens.

### Contexto (linhas 60–71)
- A dataclass com tudo o que as conferências enxergam: arquivo, configuração, regra, tabelas brutas, tabelas analisáveis (tratadas, antes da modelagem), tabelas finais, arquivos gravados, análise, entrega Excel e duração. É diferente do `Contexto` das habilidades.

### conf_tipos (linhas 75–91), Júlia (pleno, 1º andar)
- Linha 78: lê os tipos exigidos pela regra (`tipos:`).
- Linhas 79–88: para cada coluna com tipo, confere o tipo real. `inteiro` significa número sem casas decimais; `decimal` e `numero` significam numérico; `data`, data de verdade; `texto`, não numérico (ou totalmente vazio).
- Linhas 89–90: divergência vira achado "deveria ser X, saiu como Y".
- **Prova (linha 599):** o caso bom tem `nota_nps` inteira e passa. O erro plantado é a nota convertida em texto, que precisa ser pega.

### conf_espacos (linhas 94–109), Bruno (júnior)
- Linhas 98–101: nenhuma linha 100% vazia (desconsiderando as colunas de auditoria).
- Linhas 102–108: nenhum texto com espaço sobrando nas pontas.
- **Prova (linha 600):** o texto limpo passa; `"A "` precisa ser pego.

### conf_auditoria (linhas 112–124), Camila (júnior)
- Linhas 114–115: se as colunas de auditoria estão desligadas na configuração, não há o que conferir.
- Linhas 117–123: nas fatos, `_arquivo_origem` precisa ser o arquivo atual e `_processado_em` não pode estar vazio.
- **Prova (linhas 601–602):** a origem correta passa; `"outro.xlsx"` precisa ser pego.

### conf_amostra (linhas 127–146), Théo (estagiário)
- Linhas 129–131: só funciona se a regra tiver `chave_unica`.
- Linha 133: um sorteio com semente igual ao nome do arquivo. É reprodutível: o mesmo arquivo dá sempre a mesma amostra.
- Linhas 134–145: sorteia até 5 chaves publicadas e procura cada uma, como texto, na planilha original. Tira o ".0" de números. Se não achar, relata "pode ser só formatação".
- **Prova (linhas 603–604):** chaves 1, 2 e 3 existem na origem; com a origem 7, 8 e 9 ele precisa relatar.

### conf_releitura (linhas 149–178), Rafael (pleno, fase publicação)
- Linhas 152–156: o arquivo gravado precisa existir.
- Linhas 157–169: no `.xlsx`, abre só para leitura, acha a aba de cada tabela (o Excel limita nomes de aba a 31 caracteres, daí o `nome[:31]`), conta as linhas sem o cabeçalho e compara com o esperado. O `finally` garante que o arquivo é fechado mesmo com erro.
- Linhas 170–177: no `.csv`, acha a tabela pelo nome, relê como texto (`sep=None` descobre o separador) e compara as linhas.
- O porquê: é a verificação *read-after-write* (ler depois de escrever). Se o disco gravou errado, o pipeline apaga os arquivos e reprova.
- **Prova (linhas 605–611):** grava `bom` (3 linhas) e confere que está íntegro; depois espera 4 linhas e precisa acusar o arquivo com linha a menos.

### conf_sla (linhas 181–184), Marcelo (gerente de Engenharia, fase fim)
- Lê `quadro.sla_segundos` (padrão 120). Se o processamento demorou mais, gera o achado. Gerente não bloqueia: vira aviso e entra na sprint.
- **Prova (linhas 667–670):** com meta de 60 s, 10 s não reclama e 90 s aponta.

### _df_da_coluna (linhas 188–192)
- Acha a coluna em qualquer tabela analisável.

### conf_recalculo (linhas 195–213), Sérgio (pleno, 2º andar)
- Linhas 198–206: para o NPS do segmento "Total", pega as notas.
- Linhas 207–209: recalcula **à mão**, sem reaproveitar o código do Caio: promotores ≥ 9 e detratores ≤ 6.
- Linhas 210–212: diferença maior que 0,051 ponto ou `n` diferente vira achado.
- O porquê: é a dupla checagem independente. Se o código do Caio tiver bug, o do Sérgio, escrito de outro jeito, não terá o mesmo bug.
- **Prova (linhas 613–617):** notas 10, 7 e 2 dão NPS 0 com n = 3 e passa; o relatório adulterado com 12,0 precisa ser pego.

### conf_base_minima (linhas 216–221), Larissa (pleno)
- Todo indicador com `n` abaixo do mínimo (padrão 30) precisa estar marcado `base_pequena`.
- **Prova (linhas 618–619):** a base 3 sinalizada passa; a base 3 sem aviso precisa ser pega.

### conf_faixas (linhas 224–237), Igor (júnior)
- NPS entre −100 e 100; outros indicadores entre 0 e 100; margem não negativa; percentuais de promotores, neutros e detratores entre 0 e 100.
- **Prova (linhas 620–621):** os valores possíveis passam; NPS 140 precisa ser pego.

### conf_recontagem (linhas 240–249), Manu (estagiária)
- Para cada indicador "Total", reconta as respostas preenchidas e compara com o `n` do relatório. Só relata.
- **Prova (linhas 622–623):** a recontagem 3 = 3 passa; com n = 9 ela relata.

### manchete (linhas 252–266), Patrícia (gerente de Analytics)
- Linhas 256–261: pega o primeiro indicador geral e escreve "NPS geral 0.0 (±80.0, n=3)".
- Linhas 262–265: acrescenta a primeira diferença real (o destaque significativo).
- Linha 266: sem indicador, diz com honestidade "base sem indicador reconhecido — só perfil e qualidade".
- **Prova (linhas 624–625):** a manchete tem "n=3" e "±"; sem indicador, diz isso.

### _abrir_entrega (linhas 270–274)
- Abre o Excel entregue pela Sala Excel, se ele existir.

### conf_integridade_excel (linhas 277–293), Sílvia (coordenadora da Sala Excel)
- Linha 282: as abas Resumo, Dados e Conferência são obrigatórias.
- Linhas 283–284: não pode haver vínculo externo (fórmula apontando para outro arquivo).
- Linhas 285–292: nenhuma fórmula com `#REF!` ou `[1]` (a marca de referência externa). A aba Dados é pulada porque contém dados, não fórmulas.
- **Prova (linhas 641–642):** a entrega real passa; a "sabotada" (com `=#REF!+1` em Indicadores!B5) precisa ser pega.

### conf_formulas_vivas (linhas 296–312), Hugo (pleno)
- Na aba Conferência, a partir da linha 5, as colunas C (valor da fórmula) e E (status) precisam ser fórmulas, e a D (esperado) precisa ser número.
- O porquê: se alguém digitar o número por cima da fórmula, a conferência deixa de conferir.
- **Prova (linhas 643–644):** na sabotada, C5 = 2 foi digitado por cima e precisa ser pego.

### conf_formatos (linhas 315–334), Paula (júnior)
- Linhas 321–330: nas abas Plano tabular, Indicadores e Trade, toda célula com fórmula precisa de formato numérico (não pode ser "General").
- Linhas 331–333: Dados e Conferência precisam ter o cabeçalho congelado.
- **Prova (linhas 645–646):** a sabotada tem B6 em General e a Conferência descongelada, e ela precisa achar pelo menos 2 problemas.

### conf_amostra_conferencias (linhas 337–353), Enzo (estagiário)
- Sorteia 3 linhas da Conferência, extrai a referência `'Aba'!B8` e confere que a célula existe e é fórmula.
- **Prova (linhas 647–648):** a entrega boa sem relato passa. Na sabotada, só se exige que ele execute sem quebrar.

### conf_compatibilidade_excel (linhas 356–380), Ricardo (gerente da Sala Excel, fase engenharia, **bloqueia**)
- Linhas 360–363: mais de 1.048.575 linhas de dados (mais o cabeçalho, o limite de 1.048.576) ou mais de 16.384 colunas.
- Linhas 366–370: números com 16 dígitos ou mais. O Excel arredonda (guarda só 15 dígitos significativos), e se for um ID deveria ser texto.
- Linhas 371–374: datas antes de 1900, que o Excel não mostra.
- Linhas 375–379: textos com mais de 32.767 caracteres, que o Excel corta.
- O porquê de um gerente bloquear aqui: o que ele barra são limites objetivos do Excel, não opinião (ver a linha 536).
- **Prova (linhas 663–665):** a base normal passa; o ID `1234567890123456` como número precisa ser barrado.

### Regex de dados pessoais (linhas 384–386)
- `RE_EMAIL`, `RE_CPF` (com ou sem pontuação) e `RE_TEL` (DDD, 9 opcional, 8 dígitos).

### conf_dados_pessoais (linhas 389–404), Vitor (pleno, LGPD)
- Para cada coluna publicada (fora as de auditoria), examina até 200 valores. Se 60% ou mais casam com e-mail, CPF ou telefone, aponta "parece X sem anonimização" e recomenda a habilidade `anonimizar`.
- **Prova (linhas 650–652):** a base sem dado pessoal passa; a coluna `contato` com e-mails precisa ser pega.

### registrar_catalogo (linhas 407–425), Lara (estagiária de documentação)
- Linhas 411–415: lê `logs/catalogo_dados.json`. Se estiver corrompido, recomeça vazio.
- Linhas 416–420: para cada tabela, registra a base, a tabela, o último arquivo, a data, as linhas e o tipo de cada coluna.
- Linhas 421–424: grava de forma **atômica**: escreve num `.tmp` e depois troca de nome. Se faltar energia no meio, o arquivo antigo continua inteiro.
- Linha 425: não gera achados.
- **Prova (linhas 654–661):** a tabela aparece como `prova.base`, com `nota_nps` do tipo `Int64`.

### _p (linhas 429–434) e _frase (linhas 437–439)
- `_p` monta o cartão de uma pessoa. `papel` é a parte do cargo antes de " — ". `nao_faz` usa o padrão do nível se não for informado. A `descricao` é tirada da docstring da função, depois do ":".
- `_frase` junta os espaços e põe a primeira letra em maiúscula.

### QUADRO (linhas 442–518)
- **1º andar (444–467):** Marcelo (gerente, fase fim, `conf_sla`), Júlia (pleno, `conf_tipos`), Rafael (pleno, fase publicação, `conf_releitura`), Bruno (júnior, `conf_espacos`), Camila (júnior, `conf_auditoria`) e Théo (estagiário, `conf_amostra`). O gestor de cada um aparece no campo `gestor`: Júlia e Rafael respondem à Carla, Bruno e Camila à Júlia, e Théo ao Rafael.
- **2º andar (469–487):** Patrícia (gerente, sem função de conferência; a manchete é chamada à parte), Sérgio (pleno), Larissa (pleno), Igor (júnior) e Manu (estagiária).
- **3º andar (489–504):** Sílvia (coordenadora, responde ao Ricardo), Hugo (pleno), Paula (júnior) e Enzo (estagiário).
- **4º andar (506–517):** Renata (gerente de Operações, sem função), Vitor (pleno, responde à Helena) e Lara (estagiária, responde ao Vitor).

### POR_ID (linha 520) e GESTORES_EXISTENTES (linhas 523–532)
- `POR_ID` permite achar uma pessoa pelo id. `GESTORES_EXISTENTES` completa o organograma de quem vive em outros módulos. Por exemplo, Carla responde ao Marcelo; Saulo, Dora e os nativos respondem à Carla; Beto responde à Dora; os analistas, ao Marcos; Marcos, à Patrícia; Ricardo, ao dono; Helena e Iara, à Renata; Nina, à Helena.

### CONFERENCIAS_EXTRAS (linhas 537–540)
- A conferência do Ricardo, que não está no `QUADRO` para não duplicar no organograma. Roda na fase engenharia com `bloqueia: True`.

### lotacao (linhas 543–561)
- Junta todas as pessoas de todos os módulos com o andar delas e agrupa por andar e nível. Serve para provar que todo andar está completo, do gerente ao estagiário.

### conferir (linhas 564–577)
- Linhas 567–569: roda só as pessoas daquela fase que têm função.
- Linhas 570–573: se a conferência quebrar, o achado é "não consegui concluir". O comentário explica: uma conferência que quebra **não pode virar "aprovado"**.
- Linhas 574–576: `ok` = sem achados. `bloqueia` = a regra do nível (ou a explícita) **e** não ser estagiário. Os achados são limitados a 20.
- Quem transforma o achado em ERRO ou AVISO é o `pipeline._conferencias_equipe`. Com `bloquear=True` (fases engenharia e publicação), achado de quem bloqueia vira ERRO; o do estagiário vira sempre "Em observação (não bloqueia)".

### _ctx_prova (linhas 581–582) e provas_quadro (linhas 585–671)
- Linhas 588–597: monta a base `bom` (3 respostas corretas), a regra (nota inteira, chave `id_resposta`) e as versões "ruins": nota em texto, curso com espaço, origem trocada e bruto com chaves diferentes. A função `c(...)` cria o contexto.
- Linhas 599–671: as provas de cada cargo, já descritas acima em cada conferência. As da Sala Excel (626–648) geram uma entrega real com `Entrega` e depois uma cópia sabotada com 4 defeitos: número digitado em C5, cabeçalho descongelado, `#REF!` em B5 e B6 sem formato.

**Erros que este arquivo evita**
- Tipo errado na coluna (a nota como texto quebra a média no Power BI).
- Espaços invisíveis criando categorias "duplicadas" ("A" e "A ").
- Linha sem rastreabilidade de origem.
- Arquivo gravado diferente do aprovado.
- NPS do relatório diferente do recalculado; base pequena sem aviso; valores impossíveis.
- Entrega Excel com fórmula quebrada, vínculo externo, número digitado por cima ou sem formato.
- ID de 16 dígitos arredondado pelo Excel; texto cortado; datas que o Excel não mostra.
- Dado pessoal publicado sem intenção.
- Conferência que quebra sendo contada como aprovada.

---

## robo/contratacao.py

- **Para que serve.** Faz a contratação automática: o prédio contrata sozinho quando os dados mostram uma necessidade real. Por exemplo, chegou uma coluna de e-mail sem ninguém tratando. O contratado sempre entra como estagiário, só observa, e passa por 3 meses de experiência; no fim, a liderança recomenda efetivar ou desligar com base em dados.
- **Onde entra no fluxo.** Quem chama: `robo/pipeline.py`, depois de publicar com sucesso, com `registrar_observacoes`, `avaliar_experiencias` e `avaliar`, nessa ordem. O painel chama `contratar_manual` quando você contrata pela tela. Quem é chamado: `agentes` (`Equipe.salvar`, `excluir`, `_diferencas`), `habilidades`, `relatorio`, `analise.chave_base`, `pipeline.obter_equipe` e `canal` (anúncios).

### Docstring (linhas 1–19)
- Os 6 passos: reconhecer → testar numa cópia → contratar estagiário → contratação feita pela liderança → passar no processo seletivo e anunciar no #rh → experiência de 90 dias.
- **Porquês:**
  - Testar antes evita "contratar à toa".
  - Começar como estagiário garante que nada nos dados muda sem você.
  - Os líderes só contratam estagiários: júnior para cima é decisão sua, porque júnior **altera dados**.
  - A experiência de 3 meses dá tempo de observar arquivos suficientes para uma decisão com evidência.
  - Desligar um estagiário "sai sem deixar rastro nos dados, porque nunca alterou nada".
- Linhas 17–18: os limites configuráveis.

### Imports e constantes (linhas 21–55)
- Linha 35: `PADRAO`, com máximo de 12 contratados automáticos, 5 observações mínimas e 90 dias.
- Linha 37: `LIDER_DO_ANDAR` (1 Carla, 2 Marcos, 3 Sílvia, 4 Helena, 5 Gustavo).
- Linhas 40–51: `DEMANDAS`, cada uma com o tipo, a habilidade que resolve, a regex do **nome** da coluna, a regex do **valor**, o cargo e a cor.
  - E-mail: nome `email`/`e_mail`; valor com @.
  - Telefone: nome telefone/fone/celular/whatsapp/tel; valor **só com DDD entre parênteses**.
  - Documento: nome cpf/cnpj/documento/doc; valor **só formatado**.
  - CEP: nome cep/codigo_postal; valor `00000-000`.
  - O porquê dos valores "inequívocos": um número solto como 11987654321 poderia ser qualquer coisa.
- Linhas 53–54: os nomes dos estagiários.
- Linha 55: as colunas de auditoria, que nunca disparam contratação.

### _config, _arquivo_estado, _estado, _salvar_estado (linhas 58–78)
- `_config` mistura o padrão com o `config.yaml`. O estado fica em `logs/contratacao.json` (lido com tolerância a arquivo corrompido e gravado de forma atômica via `.tmp`).

### reconhecer (linhas 81–99)
- Linhas 86–87: data ou booleano nunca é reconhecido.
- Linhas 88–89: coluna numérica só é reconhecida **pelo nome**.
- Linhas 90–94: o nome da coluna casa? Então é essa a demanda.
- Linhas 95–98: com pelo menos 5 valores, 60% ou mais no formato inequívoco também reconhece.

### parametros (linhas 102–108)
- Monta os parâmetros seguros: `colunas: [coluna]` e, se a habilidade tiver o parâmetro `invalidos`, `aviso`. Assim o contratado nunca reprova o arquivo nem apaga dado.

### precisa (linhas 111–131)
- Linhas 116–118: roda a habilidade numa cópia só da coluna.
- Linhas 119–121: se deu erro de configuração ou falha, a habilidade não se aplica e não há contratação.
- Linhas 122–126: mede a mudança e conta os inválidos (incluindo valores que seriam apagados).
- Linhas 127–128: mais da metade "inválida" significa que a coluna não é desse tipo, e contratar seria um erro.
- Linhas 129–131: devolve a evidência (por exemplo, "alteraria 3 célula(s); Telefone inválido…"). Se nada mudaria, devolve vazio.

### _ja_coberto (linhas 134–141)
- Já existe agente com essa habilidade, nessa coluna, aplicado a essa base (ou a tudo)? Então não contrata em duplicidade.

### avaliar (linhas 144–194)
- Linhas 146–148: desligado ou sem tabelas, termina.
- Linhas 152–155: carrega a equipe, conta os automáticos atuais e monta o padrão `base*`.
- Linhas 157–166: para cada coluna (fora as de auditoria e respeitando o máximo), reconhece, verifica se já está coberta e testa a necessidade.
- Linha 167: quem contrata é sempre o líder do 1º andar (Carla), porque o contratado vai para a limpeza.
- Linhas 168–170: escolhe o primeiro nome livre e monta o id (`auto_email_base_coluna`), limpo e cortado em 40 caracteres.
- Linhas 171–184: a ficha: nível **estagiario**, mentor `limpeza`, andar 1, `contratado_por: automatico`, datas de início e fim da experiência, posição limpeza, ordem 60, aplicado só à base, a habilidade marcada **opcional** e um manual em Markdown explicando "por que fui contratado" e a experiência.
- Linhas 185–189: `equipe.salvar` aplica a validação e o **processo seletivo**. Se reprovar, registra no log e não contrata.
- Linhas 190–193: anuncia no #rh e no #engenharia: "Nada muda nos dados até você promover".

### registrar_observacoes (linhas 197–214)
- Para cada estagiário, procura no relatório a mensagem "Estagiário X em observação". Se achar, soma uma observação; se nos exemplos houver "Falha ao executar", soma uma falha. Grava o estado.

### avaliar_experiencias (linhas 217–252)
- Linhas 226–229: só estagiários com a experiência vencida e ainda não avaliados.
- Linhas 230–232: as observações, as falhas e o líder que contratou.
- Linhas 233–237: com 5 observações ou mais e zero falhas, **recomenda efetivar** como Júnior. Não promove sozinho: anuncia o passo a passo para você.
- Linhas 238–247: senão, **desliga** (`excluir` move para a lixeira) e anuncia o motivo.
- Linhas 248–252: marca como avaliado e grava.

### _anunciar (linhas 255–263)
- Posta no #rh e, se pedido, num segundo canal. Se o canal falhar, o erro vai só para o log de depuração.

### contratar_manual (linhas 266–277)
- Estagiário contratado por você também ganha os 90 dias de experiência. Salva com `contratado_por: dono` (passando pelo processo seletivo) e anuncia as boas-vindas.

### resumo (linhas 280–281)
- A configuração somada ao estado, para o painel.

**Erros que este arquivo evita**
- Coluna de contato ou documento publicada sem ninguém tratando.
- Contratar à toa (só com evidência testada numa cópia).
- Contratar o especialista errado (mais de 50% "inválido" indica que a coluna não é daquele tipo).
- Contratação automática que altera dados sem a sua decisão.
- Contratados duplicados e excesso de contratações (máximo de 12).
- Estagiário eterno: a experiência termina com uma decisão baseada em dados.

---

## robo/ti.py

- **Para que serve.** É o 5º andar: cuida da **máquina e do programa**, não dos dados. Uma "ronda de TI" confere dependências, disco e pastas, erros no log, segurança, prontidão para a nuvem e tamanho dos logs, e avisa no canal #ti só o que piorou. Tudo é local; a arquiteta de cloud é apenas consultiva.
- **Onde entra no fluxo.** Quem chama: `robo/painel/controle.py` (a cada `ti.intervalo_minutos`, padrão 30), o painel (botão de ronda, última ronda), `central.py`, `estrategia.py` (alertas viram itens do backlog) e `rh.py` (`provas_ti`). Quem é chamado: `config`, `painel.servidor`, `banco` e `canal`.

### Docstring e imports (linhas 1–29)
- Linha 24: `importlib.metadata` lê a versão instalada de cada biblioteca.
- Linha 27: `RAIZ_PROJETO`, a pasta do projeto.

### Constantes (linhas 31–33)
- Linha 31: intervalo de 30 minutos; disco mínimo de 2 GB; crítico abaixo de 0,5 GB; alerta a partir de 5 erros no log.
- Linha 32: Python suportado de 3.11 a 3.14.
- Linha 33: PostgreSQL 13 ou superior para o Amazon RDS.

### _c (linhas 36–37)
- Mistura o padrão com o `config.yaml → ti`.

### chk_dependencias (linhas 41–60), Diego (dev pleno)
- Linhas 44–46: a versão do Python precisa estar na faixa.
- Linhas 47–59: lê `requisitos.txt` e, para cada linha `nome>=versão`, confere se está instalado e se a versão não está abaixo do mínimo. Se estiver, sugere rodar `instalar.bat`.

### _versao (linhas 63–64)
- Transforma "2.10.1" em `(2, 10, 1)`, para comparar números e não texto (como texto, "2.10" seria menor que "2.9").

### chk_disco_e_pastas (linhas 67–88), Rodrigo (infra pleno)
- Linhas 71–79: em cada pasta de trabalho, cria e apaga um arquivo temporário `~robo_ti_` para testar a permissão de escrita.
- Linhas 80–87: mede o espaço livre no disco das planilhas. Abaixo de 0,5 GB é CRÍTICO; abaixo de 2 GB, pouco espaço.

### chk_erros_no_log (linhas 91–109), Letícia (dev júnior)
- Lê `logs/robo.log` e conta as linhas "| ERROR" ou "| CRITICAL" das últimas 24 horas. Uma data que não dá para ler é contada como erro, por precaução. Com 5 ou mais, gera alerta.

### chk_seguranca (linhas 112–141), Wagner (segurança sênior)
- Linhas 115–118: o código do painel precisa estar preso a `127.0.0.1` (só a própria máquina). Senão, ficaria visível na rede.
- Linhas 119–120: senha do PostgreSQL gravada no `config.yaml` gera alerta. O certo é usar a variável de ambiente `ROBO_PG_SENHA`.
- Linhas 121–136: calcula a "impressão digital" (hash SHA-256) de cada `.py` personalizado e compara com a ronda anterior. Arquivo novo ou alterado gera alerta "confirme que foi você", porque é código que roda no robô. A primeira ronda só registra.
- Linhas 137–140: no Linux/Mac, `config.yaml` gravável por qualquer usuário gera alerta.

### chk_cloud (linhas 144–157), Marina (cloud, consultiva)
- Sem banco habilitado, nada a avaliar. Com banco, consulta `SHOW server_version`; abaixo da versão 13, recomenda atualizar antes de pensar em nuvem.

### chk_tamanho_logs (linhas 160–170), Caíque (estagiário de DevOps)
- Soma a pasta de logs. Com 500 MB ou mais, aponta os 3 maiores arquivos.

### EQUIPE_TI, POR_ID, GESTORES (linhas 173–214)
- Gustavo (gerente, sem função), Fernanda (coordenadora, sem função própria; ela "assina" a ronda), Wagner, Marina (com o limite "Não envia nada para a nuvem: o sistema é 100% local por decisão do dono"), Diego, Rodrigo, Letícia e Caíque.
- Linhas 213–214: Gustavo responde ao dono; Fernanda e Marina ao Gustavo; Wagner, Diego e Rodrigo à Fernanda; Letícia ao Diego; Caíque ao Rodrigo.

### _arq_estado, _ler_estado, _salvar_estado (linhas 218–234)
- O estado fica em `logs/ti/estado.json`, com gravação atômica.

### ronda (linhas 237–272)
- Linhas 240–249: roda cada verificação e mede o tempo. Se uma verificação quebrar, vira o achado "não consegui concluir".
- Linha 250: **críticos** são os achados de todos, **exceto do estagiário**.
- Linhas 251–252: saudável = sem críticos. A "assinatura" é da Fernanda.
- Linhas 253–259: compara com os alertas já avisados. Só os **novos** são anunciados.
- Linhas 260–271: posta cada alerta novo no #ti, em nome de quem achou. Se antes havia alertas e agora não há, a Fernanda posta "tudo normalizado".
- O porquê: não repetir o mesmo alerta a cada 30 minutos (alerta repetido vira ruído e passa a ser ignorado).

### ultima_ronda (linhas 275–276)
- Devolve a última ronda gravada.

### provas_ti (linhas 280–327)
Monta um ambiente falso numa pasta temporária:
- **Wagner (293–297, 316–317):** o sistema limpo não alerta; `nova.py` precisa ser pego; a senha "123" precisa ser pega.
- **Rodrigo (298–301, 318):** com o mínimo minúsculo não alerta; com o mínimo de 1 bilhão de GB vira "CRÍTICO".
- **Letícia (302–307, 319):** 6 erros agora geram alerta; um log com INFO não gera.
- **Caíque (308, 323–324):** logs pequenos não geram relato.
- **Diego (320–321):** o ambiente real com as dependências corretas e a comparação de versões certa ("2.10.1" > "2.9.9").
- **Marina (322):** sem banco, nada a avaliar; lê "16.4 (Ubuntu)" como 16.
- **Fernanda e Gustavo (309–314, 325–326):** a ronda com disco "cheio" não pode sair saudável (r1); a segunda ronda igual não gera alerta novo (r2); depois de normalizar, a ronda sai toda verde (r3).

**Erros que este arquivo evita**
- Robô rodando com Python ou bibliotecas incompatíveis.
- Disco cheio ou pasta sem permissão travando a publicação.
- Erros de programa acumulando sem ninguém ver.
- Painel exposto na rede, senha em texto puro, código novo desconhecido rodando.
- Banco desatualizado para uma futura migração.
- Logs crescendo sem controle.
- Excesso de alertas repetidos (só o que piorou é anunciado).

---

## robo/treinamento.py

- **Para que serve.** É o centro de treinamento: gera na hora 17 planilhas difíceis (cabeçalho fora do lugar, células mescladas, várias abas, datas misturadas, CSV de outro sistema, arquivo corrompido…), roda **o robô de verdade** numa pasta temporária e compara o resultado com o esperado. Caso que falha é defeito real a corrigir, não "nota baixa". Nada toca as suas pastas, o banco ou o histórico.
- **Onde entra no fluxo.** Quem chama: `robo/estrategia.py` (`treinar_todos`, `trilhas`, `_automaticos`) e, por meio dele, o painel e a rotina de sprint. Quem é chamado: `robo/pipeline.processar_arquivo` (o pipeline completo) e `robo/config.carregar_config`.

### Docstring e imports (linhas 1–24)
- Linha 14: `csv` grava CSVs. Linha 24: `openpyxl.Workbook` cria planilhas Excel.

### Caso (linhas 27–35)
- A dataclass de um caso: `id`, `titulo`, `problema` (o que acontece na vida real), `responsaveis` (quem precisa dominar), `gerar` (cria o arquivo), `verificar` (devolve a lista de falhas) e `regra` (uma regra opcional do `config`).

### _xlsx (linhas 38–55)
- Cria um Excel com as linhas dadas. Opcionalmente mescla faixas, cria abas extras e oculta algumas.

### _tabela (linhas 58–64) e _aprovado (linhas 67–71)
- `_tabela` pega a tabela pelo nome ou a primeira.
- `_aprovado` devolve uma falha se o status não for "sucesso", com os 2 primeiros erros.

### Os casos (linhas 75–378)
Cada par `_c_*` (gera) e `_v_*` (verifica):
- **cabecalho_baixo (75–91):** título, data e filtros antes do cabeçalho na 7ª linha; 40 linhas. Espera as colunas `id`, `loja`, `nota_nps` e 40 linhas.
- **cabecalho_duas_linhas (94–108):** grupos mesclados "Atendimento" e "Produto" sobre "Nota". Espera `atendimento_nota` e `produto_nota`.
- **mesclado_vertical (111–127):** a região aparece uma vez para 3 lojas. Espera a região preenchida em todas, 3 por região.
- **varias_abas (130–149):** Jan, Fev e Mar (20 linhas cada), uma aba de Instruções e uma "Base antiga" oculta (com id 999). Espera 60 linhas empilhadas, a coluna `_aba_origem` e nenhum 999.
- **numeros_misturados (152–171):** "R$ 1.234,56", "12,5%", "0,35" e "(150,00)". Espera 1234,56; 0,125; 0,35; −150.
- **numeros_us (174–188):** CSV com "1,234.50". Espera 1234,5.
- **datas_misturadas (191–212):** 6 formatos, incluindo o número de série do Excel (45692) e "6 de fevereiro de 2025". Espera as 6 datas certas.
- **totais (215–233):** subtotais, "TOTAL GERAL" e uma loja chamada "Total Express". Espera 11 linhas e soma 1080. O porquê: nem tudo que começa com "Total" é total.
- **csv_latin1 (236–251):** Windows-1252 com `;`. Espera "São João" e o código "00001" como texto.
- **nps_pergunta (254–274):** a pergunta inteira como cabeçalho. Espera NPS, CSAT e segmentação por região.
- **escala_texto (277–294):** "Muito satisfeito… Muito insatisfeito". Espera CSAT top-2-box de 40%.
- **cabecalho_sujo (297–310):** quebra de linha, símbolos, coluna sem nome e "Nota" repetida. Espera `nome_do_cliente`, `valor_r`, `desconto`, `nota` e `nota_2`.
- **erro_formula (313–324):** `#DIV/0!` na linha 8. Espera **reprovação** apontando a "linha 8".
- **so_cabecalho (327–334):** só o cabeçalho. Espera reprovação.
- **corrompido (337–348):** bytes que não são um Excel. Espera reprovação com a mensagem "corromp"/"não pôde ser aberto", e o robô não pode cair.
- **ids_e_booleanos (351–365):** matrícula "000001" e CEP "00001-000" preservados.
- **regra_flexivel (368–378):** cabeçalhos "Cod. Resposta", "NOTA (0-10)" e "Data Resp.". Com os sinônimos da regra, espera `id_resposta`, `nota_nps` e `data_resposta`.

### CASOS e POR_ID (linhas 381–425)
- A lista dos 17 casos, com título, problema e responsáveis (por exemplo, `["leitura"]` ou `["limpeza", "supervisor"]`). Só `regra_flexivel` traz uma regra própria (linhas 420–423).

### rodar (linhas 429–458)
- Linhas 436–445: para cada caso, cria uma pasta temporária com `OneDrive/Bases-Limpeza` e uma configuração isolada: banco **desligado** e contratação automática **desligada**.
- Linhas 446–452: gera o arquivo, processa no pipeline real e verifica. Se o robô quebrar, a falha é "o robô quebrou".
- Linhas 453–458: guarda cada resultado e o resumo (total, aprovados, tempo).

### registrar (linhas 461–465) e historico (linhas 468–479)
- Acrescenta uma linha em `logs/rh/treinamentos.jsonl`. *JSONL* é um arquivo em que cada linha é um registro JSON. `historico` lê as últimas linhas e pula as corrompidas.

**Erros que este arquivo evita**
- Robô "engessado", que só funciona com a planilha perfeita.
- Regressões: uma mudança no código que quebra um caso que antes funcionava aparece no treinamento seguinte.
- Treinar em produção (tudo roda em pasta temporária, sem banco nem contratação).

---

## robo/estrategia.py

- **Para que serve.** É a gestão da empresa: mantém um backlog priorizado da sprint (a lista do que precisa ser feito), alinha as 3 prioridades de cada andar com o gerente, reaplica as avaliações técnicas de todo o quadro e roda os treinamentos. Itens automáticos nascem dos dados e se fecham sozinhos quando o problema some.
- **Onde entra no fluxo.** Quem chama: `robo/painel/controle.py`, que verifica a `rotina` a cada hora em segundo plano (a rotina só faz a avaliação a cada 15 dias), e o painel (backlog, alinhamento, avaliações, trilhas). Quem é chamado: `historico`, `ti`, `treinamento`, `rh`, `pipeline`, `canal`, `analise`, `excel`, `producao` e `quadro`.

### Docstring e imports (linhas 1–29)
- Linha 6: prioridade = impacto × urgência ÷ esforço.
- Linhas 7–8: itens automáticos se fecham sozinhos "com essa observação, para ninguém ser enganado".
- Linha 25: `threading` (execução em paralelo). A trava evita que duas gravações simultâneas corrompam o backlog.

### Constantes (linhas 31–35)
- Status: a_fazer, fazendo, travado e feito.
- `LIDER_ANDAR`: 1 Carla, 2 Marcos, 3 Sílvia, 4 Helena, 5 Fernanda.
- `GERENTE_ANDAR`: 1 Marcelo, 2 Patrícia, 3 Ricardo, 4 Renata, 5 Gustavo.
- `_trava`: um *lock*, uma "chave do banheiro" que só uma tarefa segura por vez.

### _pasta, _agora, prioridade (linhas 38–49)
- A pasta `logs/estrategia`, a data e hora atual e a fórmula de prioridade (esforço mínimo 1, para não dividir por zero).

### ler_backlog e _salvar (linhas 53–65)
- Lê `backlog.json` (vazio se não existir ou estiver corrompido) e grava de forma atômica.

### salvar_item (linhas 68–100)
- Linhas 70–72: um item novo precisa de título.
- Linhas 73–79: sob a trava, procura pelo id ou cria um item do dono.
- Linhas 80–89: atualiza o título, o motivo e o responsável (até 500 caracteres); impacto, urgência e esforço limitados de 1 a 5; andar de 1 a 9.
- Linhas 90–94: mudança de status entra no histórico ("A fazer → Fazendo").
- Linhas 95–99: completa os padrões, recalcula a prioridade e grava.

### excluir_item (linhas 103–106)
- Remove pelo id, sob a trava.

### _automaticos (linhas 109–195)
O que os dados de hoje dizem que precisa ser feito. Cada item tem uma `chave` estável, para não duplicar:
1. **Linhas 115–130:** o erro que se repete nas reprovações dos últimos 15 dias (números trocados por "N" para agrupar). Com 2 ou mais repetições, vira "Eliminar na origem", com a Carla.
2. **Linhas 131–142:** os alertas da ronda de TI (exceto os do estagiário). CRÍTICO tem urgência 5.
3. **Linhas 143–150:** os casos de treinamento que falharam viram "Corrigir o robô para…", com impacto 5.
4. **Linhas 151–157:** quem foi reprovado na avaliação técnica vira "Treinar X até passar", com o líder do andar.
5. **Linhas 158–168:** experiência de estagiário terminando em até 15 dias.
6. **Linhas 169–185:** os alertas de "atenção" do monitoramento das análises (os últimos 30 arquivos, um por base).
7. **Linhas 186–194:** no máximo 2 ideias da Iara, para manter o foco.

### sincronizar (linhas 198–227)
- Linhas 205–212: item automático que já existe é mantido e tem o motivo atualizado. Se tinha sido "resolvido sozinho" e o problema voltou, ele volta para "A fazer".
- Linhas 213–217: item novo ganha um id derivado da chave (hash), para ser estável.
- Linhas 218–223: item automático cuja condição sumiu é marcado como "feito", com `resolvido_sozinho` e a nota no histórico.
- Linhas 224–227: recalcula as prioridades e grava. **Não mexe em itens do dono.**

### alinhamento (linhas 230–245)
- Para cada andar (1 a 5, mais os que existirem nos itens), pega as 3 prioridades abertas mais altas, o nome do gerente e a quantidade de itens travados.

### avaliar_todos (linhas 249–284)
- Linha 260: limpa o cache das provas nativas para reaplicar do zero.
- Linhas 261–270: monta a lista de todas as pessoas de todos os andares e pega a ficha (com as provas) de cada uma.
- Linhas 271–277: os agentes personalizados ativos passam pelo `processo_seletivo`.
- Linhas 278–284: grava em `logs/rh/avaliacoes.jsonl`.

### ler_avaliacoes (linhas 287–297), treinar_todos (linhas 300–304), trilhas (linhas 307–320)
- `trilhas` mostra, por pessoa, os casos de treinamento sob sua responsabilidade e quantos ela "domina" no último treinamento.

### rotina (linhas 323–341)
- Linhas 325–329: se a última avaliação tem menos de 15 dias, só sincroniza o backlog.
- Linhas 330–340: senão, avalia todos, treina, sincroniza e a Helena posta o resultado no #rh ("Os casos que falharam viraram prioridade na sprint").

**Erros que este arquivo evita**
- Problemas recorrentes esquecidos (o erro repetido vira item do backlog).
- Backlog desatualizado (itens se fecham sozinhos e reabrem se o problema voltar).
- Avaliações viciadas pelo cache (o cache das provas nativas é limpo a cada sprint).
- Gravação simultânea corrompendo o backlog (a trava e a gravação atômica).
- Falta de foco (3 prioridades por andar, 2 ideias por vez).

---

## habilidades_personalizadas/_exemplo_habilidade.py

- **Para que serve.** É o modelo para você criar a sua própria habilidade. Como o nome começa com `_`, ele **nunca é carregado** (ver `carregar_personalizadas`, linhas 249–250 de `habilidades/__init__.py`); para usar, copie com outro nome.
- **Onde entra no fluxo.** Uma cópia (por exemplo, `marcar_vip.py`) é carregada por `carregar_personalizadas`, chamado em `Equipe.carregar`, e aparece no catálogo do painel.

### Docstring (linhas 1–12)
- Linhas 3–6: os passos (copiar, ajustar, salvar).
- Linhas 8–11: as regras de ouro. Receber `df`, `p` e `ctx`; devolver **sempre** a tabela; usar `ctx.erro` para reprovar, `ctx.aviso` para alertar e `ctx.info` para documentar.

### Import (linha 14)
- `Param` e o decorador `habilidade`.

### Decorador (linhas 17–27)
- id `marcar_vip`, nome, categoria "Minhas habilidades", descrição, dois parâmetros (a coluna de valor e o limite numérico, com padrão 1000) e o conhecimento.

### marcar_vip (linhas 28–32)
- Linha 29: converte a coluna para decimal.
- Linha 30: cria `vip` = "Sim" se o valor for maior ou igual ao limite; senão "Não".
- Linha 31: registra quantos VIPs há.
- Linha 32: devolve a tabela.
- **Antes/depois:** valores `[500, 1500]` com limite 1000 dão `vip = ["Não", "Sim"]`.

**Erros que este arquivo evita**
- Modelos de exemplo rodando em produção por engano (o `_` no início do nome).
- Habilidades que esquecem de devolver a tabela (a regra de ouro, verificada também em `executar_habilidade`).

---

## agentes/tina_contatos.yaml

- **Para que serve.** É um agente personalizado de exemplo, **ativo**: a Tina, Analista Pleno de Dados de Contato. Ela padroniza e-mails e telefones para o *closed loop* com detratores (ligar de volta para quem deu nota baixa) e cria a coluna `grupo_nps`, só nos arquivos que começam com `nps_`.
- **Onde entra no fluxo.** É lido por `Equipe.carregar` (`robo/agentes.py`), passa por `validar_agente` e `rh.processo_seletivo`, e é executado por `Equipe.executar("limpeza", ...)` logo depois da limpeza nativa da Lia (posição `limpeza`, ordem 10).

### Linhas 1–2: comentários
- Explicam que as habilidades são opcionais: se a planilha não tiver a coluna, a habilidade pula sem reprovar.

### Linhas 3–15: identificação
- `id: tina_contatos` (igual ao nome do arquivo), `nome: Tina`, `papel`, `descricao` e `cor` laranja.
- `posicao: limpeza`, `ordem: 10` (antes dos contratados automáticos, que usam 60) e `ativo: true`.
- `nivel: pleno`, ou seja, pode usar riscos baixo e médio. `area` e `cargo` aparecem na ficha.
- `aplicar_em: [nps_*]`: só arquivos de NPS.

### Linhas 16–22: validar_email
- `opcional: true`; colunas `[email]`; `invalidos: vazio`. Um e-mail inválido é apagado e registrado como aviso. Pelo `rh.risco_de`, `vazio` sobe o risco de baixo para **médio**, o que o nível pleno permite.

### Linhas 23–29: normalizar_telefone
- `formato: formatado`; `invalidos: aviso`. O telefone inválido é mantido e registrado. Risco baixo.

### Linhas 30–34: classificar_nps
- `coluna: nota_nps`, sem `invalidos`, portanto vale o padrão **erro**: nota fora de 0–10 reprova o arquivo. Risco baixo.

**Erros que este arquivo evita**
- Lista de contato com e-mail ou telefone em formato inconsistente indo para o call center.
- Reprovar bases de NPS que simplesmente não têm coluna de e-mail ou telefone (as habilidades são opcionais).
- Nota de NPS impossível passando para o indicador (o padrão é erro).
- Aplicar o tratamento de contato em bases que não são de pesquisa (`aplicar_em: nps_*`).
