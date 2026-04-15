FROM python:3.12-slim

WORKDIR /app

# Instala dependências Python primeiro (aproveita cache de layers)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# apt-get update necessário antes do playwright instalar as dependências de sistema
RUN apt-get update && \
    playwright install-deps chromium && \
    playwright install chromium && \
    rm -rf /var/lib/apt/lists/*

COPY . .

ENV WORKSPACE=/data/imoveis.db

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
