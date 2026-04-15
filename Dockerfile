FROM python:3.12-slim

WORKDIR /app

# Instala dependências Python primeiro (aproveita cache de layers)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala o chromium do sistema (Debian 12 Bookworm, arm64) — puxa todas as
# libs necessárias como dependência. Depois playwright install chromium baixa
# o binário gerenciado sem tentar instalar pacotes de sistema (evita conflito
# com nomes de fonte renomeados no Bookworm: ttf-unifont → fonts-unifont).
RUN apt-get update && \
    apt-get install -y --no-install-recommends chromium && \
    playwright install chromium && \
    rm -rf /var/lib/apt/lists/*

COPY . .

ENV WORKSPACE=/data/imoveis.db

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
