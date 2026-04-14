# Imoveis DI

Monitor de imóveis para Dois Irmãos e Morro Reuter. Agrega listagens de múltiplas imobiliárias, detecta novos imóveis e variações de preço, e oferece uma interface web para acompanhamento.

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | FastAPI + Uvicorn |
| Scraping | Playwright (Chromium headless) + BeautifulSoup4 |
| Banco de dados | SQLite (por workspace) |
| Frontend | HTMX + Tailwind CSS (CDN) |
| Agendamento | APScheduler (cron) |
| Imagens de galeria | Enrichment assíncrono pós-scraping |

---

## Rodando em desenvolvimento

### Pré-requisitos

- Python 3.11+
- pip (ou [uv](https://github.com/astral-sh/uv))

### Instalação

```bash
git clone <repo-url>
cd imoveis-di

python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
```

### Configuração

Crie o `.env` na raiz do projeto:

```bash
cp .env.example .env   # ou crie manualmente
```

Variáveis disponíveis:

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `WORKSPACE` | `workspaces/imoveis.db` | Caminho para o arquivo SQLite |
| `SESSION_SECRET` | *(dev: valor fixo)* | Chave de sessão — **obrigatória em produção** |
| `ENV` | `development` | Defina `production` para exigir `SESSION_SECRET` |

### Inicialização

```bash
python manage.py init-db      # cria schema SQLite e importa sites.yaml
python manage.py create-user  # cria o primeiro usuário
```

### Rodando

```bash
uvicorn app:app --reload
```

Acesse: http://localhost:8000

---

## Gerenciamento do banco

### Limpar imóveis (começar do zero)

Preserva usuários, sites e configurações. Remove tudo o mais.

```bash
python -c "
import sqlite3, os
db = os.getenv('WORKSPACE', 'workspaces/imoveis.db')
conn = sqlite3.connect(db)
conn.execute('DELETE FROM imovel_imagens')
conn.execute('DELETE FROM historico')
conn.execute('DELETE FROM runs')
conn.execute('DELETE FROM imoveis')
conn.execute(\"UPDATE workspace SET last_reviewed_aluguel_at=NULL, last_reviewed_compra_at=NULL\")
conn.commit()
conn.close()
print('Banco limpo.')
"
```

### Adicionar usuário

```bash
python manage.py create-user
# ou em workspace específico:
python manage.py --workspace workspaces/outro.db create-user
```

### Novo workspace (outro cliente / outra cidade)

Cada workspace é um `.db` independente com seus próprios usuários, sites e imóveis.

```bash
python manage.py --workspace workspaces/outro.db init-db
python manage.py --workspace workspaces/outro.db create-user
WORKSPACE=workspaces/outro.db uvicorn app:app --port 8001
```

---

## Sites e plataformas suportadas

Os sites são configurados em `config/sites.yaml` e importados automaticamente no `init-db`. Após isso, a fonte de verdade é o banco — alterações feitas via interface de Configurações são persistidas no SQLite.

| Plataforma | Arquivo |
|-----------|---------|
| Kenlo | `scrapers/platforms/kenlo.py` |
| Vista Soft | `scrapers/platforms/vista.py` |
| Jetimob | `scrapers/platforms/jetimob.py` |
| Tecimob | `scrapers/platforms/tecimob.py` |
| Smartimob | `scrapers/platforms/smartimob.py` |
| Voa | `scrapers/platforms/voa.py` |
| ImobiBrasil | `scrapers/platforms/imobibrasil.py` |
| Becker | `scrapers/platforms/becker.py` |
| Conecta | `scrapers/platforms/conecta.py` |
| Munique | `scrapers/platforms/munique.py` |

Enrichment de imagens (galeria completa) é configurado em `scrapers/enrichment.py` com seletores CSS por site e por plataforma.

### Adicionar imobiliária

1. Adicionar entrada em `config/sites.yaml`
2. Se a plataforma já é suportada, basta configurar a URL
3. Se for plataforma nova: criar scraper em `scrapers/platforms/` herdando de `BaseScraper`, registrar em `scrapers/registry.py`
4. Adicionar seletor CSS de galeria em `scrapers/enrichment.py` (`_BY_SITE` ou `_BY_PLATFORM`)

---

## Scraping

### Via interface web (Configurações)

- **▶ Tudo** — todos os sites ativos
- **▶ Aluguel / ▶ Compra** — filtra por tipo de transação
- **▶** (por imobiliária) — roda apenas aquele site
- **↻** (por imobiliária) — roda + força re-download de imagens de todos os imóveis

O progresso aparece em tempo real na tabela via SSE.

### Via terminal

```bash
python -c "
import asyncio
from scrapers.runner import run_scraping
asyncio.run(run_scraping())
"
```

---

## Testes

```bash
pytest
```

Os testes usam banco SQLite in-memory e não requerem internet.

---

## Deploy em produção

Ver [docs/deploy.md](docs/deploy.md) para o guia completo, incluindo:

- Setup do servidor (Ubuntu/Debian ARM ou x86)
- Alternativas ao Oracle Cloud Free
- Caddy como reverse proxy com HTTPS automático
- Arquivos systemd para imoveis-di, n8n e dashboard de finanças
- Configuração multi-app num único servidor

---

## Estrutura do projeto

```
imoveis-di/
├── app.py                  # Entry point FastAPI
├── manage.py               # CLI: init-db, create-user
├── config/
│   └── sites.yaml          # Configuração inicial dos sites
├── routers/
│   ├── auth.py             # Login/logout
│   ├── imoveis.py          # Listagem, filtros, status, mapa
│   ├── scraping.py         # Trigger scraping + SSE stream
│   └── workspace.py        # Configurações de sites e agenda
├── scrapers/
│   ├── base.py             # BaseScraper + PropertyData
│   ├── enrichment.py       # Enrichment de imagens pós-scraping
│   ├── registry.py         # Mapeamento plataforma → classe
│   ├── runner.py           # Orquestrador: scraping + enrichment + SSE
│   └── platforms/          # Um arquivo por plataforma
├── storage/
│   └── database.py         # SQLite: schema, queries, CRUD
├── templates/              # Jinja2 + HTMX
│   └── partials/           # Componentes reutilizáveis
├── static/
│   └── app.js              # JS: carrossel, filtros, SSE handling
├── tests/                  # pytest
├── docs/
│   └── deploy.md           # Guia completo de deploy
└── workspaces/             # Arquivos .db (git-ignorado)
```
