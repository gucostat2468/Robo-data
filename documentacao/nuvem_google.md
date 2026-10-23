# Robô de Planilhas no Google Cloud (Cloud Run + Cloud SQL): o que ficou pronto e o que custa

Pedido do dono: rodar a empresa no desenho que o assistente do Google Cloud montou (Cloud Run `flexible-app`,
Cloud SQL PostgreSQL 15 `flexible-db`, Secret Manager `flexible-db-pass`, balanceador global com CDN).

**Nada foi criado no Google Cloud.** Nenhum comando `gcloud` foi rodado, nenhuma conta foi usada, nenhum recurso pago
existe. O que foi feito é o projeto ficar **pronto** para rodar lá no dia em que você autorizar.

## 1. O que ficou pronto no código

| Peça | Arquivo | O que faz |
|---|---|---|
| Contêiner | `Dockerfile` | Python 3.13 slim, usuário sem root (uid 10001), porta pela variável `PORT` (padrão 8080) |
| O que fica fora da imagem | `.dockerignore` | `config.yaml`, `logs/`, `.git`, testes, memória local |
| Banco por variáveis | `robo/nuvem.py` → `url_do_ambiente` | `DB_USER`, `DB_PASS`, `DB_NAME` + `INSTANCE_CONNECTION_NAME` → conecta pelo Unix socket `/cloudsql/<instância>` (sem IP público). Sem a instância, usa `DB_HOST`/`DB_PORT`. Continua aceitando `ROBO_PG_URL` (o caminho grátis de hoje) |
| Modo servidor | `robo/servico.py` → `python -m robo servico` | turnos um atrás do outro + `GET /saude` somente leitura na porta `PORT` |
| Instância única | `robo/servico.py` | trava no PostgreSQL (`pg_try_advisory_lock`): uma segunda instância fica em espera e não trabalha |
| Vigilância | Heloísa (Head de AWS) | a cada ronda confere: Dockerfile existe, não roda como root, porta por variável, `config.yaml` fora do repositório, dependências com versão |

## 2. Três correções ao desenho do assistente (antes de qualquer gasto)

1. **Máximo de instâncias: 1, não 10.** A memória da empresa é um instantâneo do banco local salvo no PostgreSQL.
   Duas instâncias trabalhando juntas gravariam dois futuros diferentes e uma apagaria o trabalho da outra.
   O código já se protege (trava de instância única), mas a configuração certa é `--max-instances=1`.
2. **Não publique o painel.** O desenho põe um balanceador **externo** com CDN na frente. O serviço só expõe
   `/saude` (somente leitura, sem segredo); o painel da empresa **não** está no contêiner. Se um dia quiser o painel
   na internet, é outro projeto, com login de verdade (Identity-Aware Proxy), e precisa da sua autorização.
3. **Sem balanceador e sem CDN.** Não há página pública para acelerar. O balanceador global é a peça que mais custa
   sem trazer nada para este caso.

## 3. Custos (estimativa, confira na calculadora oficial antes de decidir)

Valores aproximados de tabela pública, região us-central1, em dólar por mês. **Preço muda; confira em
cloud.google.com/products/calculator antes de qualquer decisão.**

| Recurso | Configuração | Custo aproximado/mês |
|---|---|---|
| Cloud SQL PostgreSQL | menor máquina compartilhada, 10 GB | US$ 10 a 15 |
| Cloud Run | 1 instância sempre ligada (min 1), 1 vCPU, 512 MB, CPU sempre alocada | US$ 40 a 70 |
| Balanceador externo + CDN | 1 regra de encaminhamento | cerca de US$ 18 + tráfego |
| Secret Manager | 1 segredo, poucos acessos | centavos |
| **Total do desenho original** | | **cerca de US$ 70 a 100/mês** |
| Desenho corrigido (sem balanceador, Cloud Run como *job* por hora, Neon grátis no lugar do Cloud SQL) | 20 min por hora | passa da cota grátis do Cloud Run (cerca de 240 h de CPU/mês contra cerca de 50 h grátis): ainda pago |

**Conclusão honesta:** qualquer versão que trabalhe 24 h no Google Cloud **custa dinheiro**. A sua regra é
"nuvem paga, não". O caminho que já roda **grátis** é o de hoje: GitHub Actions (um turno por hora) + PostgreSQL Neon
gratuito. Por isso nada foi criado no Google.

## 4. Se um dia você autorizar (passo a passo, para você executar)

Só faça com o orçamento aprovado e um alerta de gasto criado antes (Faturamento → Orçamentos e alertas).

1. Instale o Google Cloud SDK no Windows e rode `gcloud auth login`.
2. Ative as APIs: `gcloud services enable run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com`.
3. Crie a senha no Secret Manager (`flexible-db-pass`), **nunca** no código.
4. Publique **sem** acesso público e com no máximo uma instância:

```
gcloud run deploy flexible-app --source . --region=us-central1 ^
  --no-allow-unauthenticated --min-instances=1 --max-instances=1 --no-cpu-throttling ^
  --add-cloudsql-instances=PROJETO:us-central1:flexible-db ^
  --set-env-vars=DB_USER=robo_app,DB_NAME=robo_dados,INSTANCE_CONNECTION_NAME=PROJETO:us-central1:flexible-db ^
  --update-secrets=DB_PASS=flexible-db-pass:latest
```

5. Confira a saúde (com o seu login): `gcloud run services proxy flexible-app --region=us-central1` (em versões antigas do SDK: `gcloud beta run services proxy`) e abra
   `http://localhost:8080/saude`.
6. **Desligue o turno do GitHub Actions** antes (Actions → "Empresa na nuvem (turnos)" → Disable workflow):
   os dois trabalhando no mesmo banco seria o mesmo problema das duas instâncias.

## 5. Testar o contêiner no seu computador, de graça

Com Docker Desktop instalado:

```
docker build -t robo-planilhas .
docker run --rm -p 8080:8080 -e ROBO_PG_URL="postgresql://..." robo-planilhas
```

Depois abra `http://localhost:8080/saude`.

## 6. Plano de volta

Se algo der errado no Google: apague o serviço do Cloud Run (`gcloud run services delete flexible-app`) e reative o
workflow do GitHub. A memória está no PostgreSQL e o próximo turno continua do último instantâneo: nada se perde.
