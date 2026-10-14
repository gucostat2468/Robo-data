# Robô de Planilhas — ETL automático no seu computador

Você solta uma planilha em **Bases-Limpeza** (no OneDrive) → o robô limpa, valida e modela os dados → se estiver **100% sem erros**, o arquivo tratado aparece em **Bases-Tratadas**. Se tiver qualquer erro, nada vai para Tratadas: o arquivo vai para **Bases-Erros** junto com um `_ERROS.txt` explicando o que corrigir e em qual linha.

Roda **só no seu computador**, em Python. Não precisa de servidor, EC2, nuvem, banco de dados nem API. O "ponto de conexão" com o OneDrive é o próprio aplicativo do OneDrive do Windows, que já sincroniza as pastas com o seu disco (o ✅ verde ao lado das pastas).

```
OneDrive/
├── Bases-Limpeza      ← você solta a planilha aqui
├── Bases-Tratadas     ← sai a planilha tratada (é daqui que o Power BI lê)
├── Bases-Erros        ← reprovadas + relatório _ERROS.txt          (criada sozinha)
├── Bases-Originais    ← backup do arquivo original, por mês         (criada sozinha)
└── Bases-Relatorios   ← log de qualidade + dicionário de dados      (criada sozinha)
```

---

## 1. Instalação (uma vez só)

1. Tenha o **Python 3.11 a 3.14** (recomendado 3.13). Versões mais novas, como a 3.15, ainda não têm as bibliotecas prontas para Windows — o `instalar.bat` detecta isso e instala a 3.13 ao lado, sem remover a sua.
   - Na primeira tela do instalador, **marque a caixa "Add python.exe to PATH"** (fica embaixo). Se esquecer, o robô não acha o Python.
   - Clique em **Install Now**.
2. Coloque a pasta deste projeto em um lugar **fora do OneDrive**, por exemplo `C:\Robo-data`.
   - Motivo: a pasta `.venv` tem milhares de arquivos pequenos e o OneDrive ficaria sincronizando à toa.
3. Abra a pasta do projeto no Explorador de Arquivos e dê **dois cliques em `instalar.bat`**.
   - Uma janela preta abre, instala as bibliotecas e, no final, mostra as pastas encontradas.
   - **Como validar:** todas as linhas devem começar com `OK`. Se aparecer `ERRO DE CONFIGURAÇÃO: Não encontrei a pasta 'Bases-Limpeza'`, veja o item 1.1.

### 1.1 Se o robô não achar a pasta Bases-Limpeza
1. No Explorador, clique com o botão direito em **Bases-Limpeza** → **Copiar como caminho**.
2. Abra o arquivo `config.yaml` (botão direito → Abrir com → Bloco de Notas).
3. Na linha `entrada: auto`, troque `auto` pelo caminho colado, trocando `\` por `/`:
   ```yaml
   entrada: "C:/Users/patri/OneDrive/Bases-Limpeza"
   ```
4. Salve (Ctrl+S) e rode `status.bat` para conferir.

## 2. Uso no dia a dia

| Quero... | Faça |
|---|---|
| Ligar o robô vendo o que ele faz | dois cliques em `iniciar_robo.bat` (fechar a janela = desligar) |
| Ligar o robô escondido | dois cliques em `iniciar_robo_oculto.vbs` |
| Que ele ligue sozinho quando eu entrar no Windows | dois cliques em `ligar_com_windows.bat` (uma vez) |
| Desligar o robô escondido | `parar_robo.bat` |
| Processar tudo agora, uma vez só | `processar_agora.bat` |
| Testar uma planilha sem gravar nada | arraste a planilha para cima de `diagnosticar.bat` |
| Ver fila, reprovados e histórico | `status.bat` |

**Importante:** o robô só processa enquanto está ligado e o computador está acordado. Se você soltar arquivos com ele desligado, eles serão processados assim que ele ligar.

## 3. O que o robô faz com cada planilha

| Etapa | O que faz | Por quê |
|---|---|---|
| Espera a sincronização | Só começa quando o arquivo para de mudar por 10 s e não está aberto no Excel | Evita ler arquivo pela metade enquanto o OneDrive baixa |
| Acha o cabeçalho | Ignora títulos e linhas soltas acima da tabela | Relatórios exportados costumam ter "Relatório X" na linha 1 |
| Erros de fórmula | `#REF!`, `#DIV/0!`, `#N/D`, `#VALOR!`… **reprovam** o arquivo | Um PROCV quebrado vira número errado no dashboard |
| Nomes de colunas | `Data de Admissão` → `data_de_admissao` | Sem acento/espaço: fórmulas DAX e Power Query mais simples |
| Textos | Tira espaços duplos; `-`, `N/A`, `null`, `sem informação` viram vazio | "Direito" e "Direito " seriam dois cursos diferentes |
| Linhas/colunas vazias | Remove | Lixo de formatação do Excel |
| Linhas de Total | Remove `Total`, `Subtotal`, `Total geral` | Senão a soma no Power BI conta em dobro |
| Tipos | `R$ 1.234,56` → 1234,56 · `45%` → 0,45 · `02/10/2026` → data | Power BI precisa de número/data de verdade para somar e filtrar |
| Códigos | CEP, CPF, matrícula, `id_*` e valores com zero à esquerda ficam **texto** | `01310` não pode virar `1310` |
| Duplicadas | Remove linhas 100% idênticas (com aviso) | Evita inflar contagens |
| Auditoria | Adiciona `_arquivo_origem` e `_processado_em` | Rastreabilidade quando o Power BI junta vários arquivos |

**ERRO × AVISO:** erro reprova (nada vai para Tratadas). Aviso não reprova, mas fica registrado em `Bases-Relatorios/<arquivo>_qualidade.xlsx` (aba `log_qualidade`).

## 4. Regras por tipo de arquivo (validação e modelagem)

No `config.yaml`, seção `regras`, você define regras para arquivos cujo **nome** segue um padrão. Exemplo para pesquisas de NPS (`nps_outubro.xlsx`, `nps_novembro.xlsx`…):

```yaml
regras:
  - padrao: "nps_*"
    colunas_obrigatorias: [id_resposta, data_resposta, nota_nps]
    nao_nulos: [id_resposta, nota_nps]          # não pode ter célula vazia
    chave_unica: [id_resposta]                  # não pode repetir
    tipos: {data_resposta: data, nota_nps: inteiro}
    faixas: {nota_nps: {min: 0, max: 10}}       # nota 11 reprova
    texto: {uf: maiusculo}
    valores_permitidos: {uf: [SP, RJ, MG]}
    modelo:                                     # modelo estrela para o Power BI
      fato: fato_nps
      dimensoes:
        dim_curso: {colunas: [curso, modalidade], chave: id_curso}
      calendario: data_resposta                 # cria dim_calendario
```

Com `modelo`, o arquivo tratado sai com uma aba por tabela (`fato_nps`, `dim_curso`, `dim_calendario`). No Power BI:
1. **Página Inicial → Obter dados → Pasta de trabalho do Excel** → escolha o arquivo em Bases-Tratadas → marque as três abas → **Carregar**.
2. Vá em **Exibição de modelo** (terceiro ícone da barra lateral esquerda).
3. Arraste `dim_curso[id_curso]` para `fato_nps[id_curso]` → cardinalidade **Um para muitos (1:\*)**, direção **Única**.
4. Arraste `dim_calendario[data]` para `fato_nps[data_resposta]` → **1:\***.
5. Clique com o botão direito em `dim_calendario` → **Marcar como tabela de datas** → coluna `data`.

**Tipos aceitos em `tipos`:** `texto`, `inteiro`, `decimal`, `data`, `datahora`.

## 5. Conectando o Power BI à saída

- **Um arquivo por tema que é substituído** (ex.: `nps.xlsx` todo mês): conecte direto ao arquivo. Como o nome de saída é igual ao de entrada, cada nova versão substitui a anterior e o **Atualizar** do Power BI já pega os dados novos.
- **Vários arquivos que se acumulam** (ex.: `nps_2026_09.xlsx`, `nps_2026_10.xlsx`): use **Obter dados → Pasta** apontando para Bases-Tratadas e **Combinar arquivos**. Por isso o relatório de qualidade fica em outra pasta (Bases-Relatorios): para não misturar com os dados.

## 6. Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| Arquivo fica parado em Bases-Limpeza | Robô desligado, ou arquivo aberto no Excel | Ligue o robô / feche o Excel |
| Log diz `ADIADO` | O arquivo tratado anterior está aberto no Excel/Power BI | Feche-o; o robô tenta de novo em ~1 min |
| `Já existe um robô rodando` | Você abriu duas vezes | Use só um (`parar_robo.bat` desliga o oculto) |
| Coluna numérica saiu como texto | Menos de 95% dos valores são números | Veja o dicionário de dados; force com `tipos:` na regra |
| Planilha com várias abas | Por padrão só a 1ª aba com dados é lida | `leitura: abas: todas` no config |

Logs detalhados: pasta `logs/` do projeto (`robo.log` e `historico_processamentos.csv` — dá para abrir o histórico no Power BI e montar um painel de monitoramento).

## 7. Para quem for mexer no código

```
robo/
├── config.py      leitura do config.yaml + descoberta do OneDrive
├── leitura.py     xlsx/xlsm (openpyxl), xls (xlrd), csv/txt (codificação e separador automáticos)
├── limpeza.py     padronização e conversão de tipos
├── validacao.py   regras de qualidade (erros bloqueantes)
├── modelagem.py   dicionário de dados, modelo estrela e calendário
├── escrita.py     gravação atômica em Excel formatado / CSV
├── pipeline.py    orquestra um arquivo (ler → limpar → validar → modelar → gravar → arquivar)
├── monitor.py     vigia a pasta (polling) + trava de instância única
├── manutencao.py  limpeza de backups/logs antigos
└── cli.py         comandos: monitorar, varrer, processar, diagnosticar, status, manutencao
```

Testes: `.venv\Scripts\python -m pip install -r requirements-dev.txt` e depois `.venv\Scripts\python -m pytest`.
