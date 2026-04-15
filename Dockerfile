FROM python:3.12-slim

WORKDIR /app

# Instala dependências Python primeiro (aproveita cache de layers)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala Chromium via playwright (inclui todas as dependências de sistema)
# --with-deps roda apt-get internamente; suporte arm64 desde Playwright 1.30+
RUN playwright install --with-deps chromium

COPY . .

ENV WORKSPACE=/data/imoveis.db

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
