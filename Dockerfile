# Robô de Planilhas em contêiner (Docker, Google Cloud Run, máquina Ubuntu).
# Roda "python -m robo servico": turnos de trabalho + saúde SOMENTE LEITURA em /saude na porta $PORT.
# NÃO publica o painel. Nenhuma senha aqui: o banco vem de variáveis de ambiente (ROBO_PG_URL ou
# DB_USER/DB_PASS/DB_NAME + INSTANCE_CONNECTION_NAME), entregues pelo Secret Manager ou pelo "docker run -e".
# Guia e custos: documentacao/nuvem_google.md

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

WORKDIR /app

# dependências primeiro (camada reaproveitada quando só o código muda)
COPY requisitos.txt .
RUN pip install -r requisitos.txt

# usuário sem privilégio: o processo nunca roda como root
RUN useradd --create-home --uid 10001 robo
COPY --chown=robo:robo . .
USER robo

EXPOSE 8080
CMD ["python", "-m", "robo", "servico", "--pasta", "/tmp/empresa"]
