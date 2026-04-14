# Design: Migração Imoveis DI — Streamlit → FastAPI + HTMX

**Data:** 2026-04-13  
**Status:** Aprovado  
**Projeto origem:** `C:\Users\marlo\Downloads\dev\Imoveis_DI`  
**Projeto destino:** `c:\dev\imoveis-di`

---

## Contexto

O app atual é um sistema de monitoramento imobiliário para Dois Irmãos/RS construído em Streamlit. Funciona, mas tem limitações sérias:

- Streamlit oferece pouco controle sobre customização visual
- Excel + GCS como banco é lento e frágil
- 37 scrapers customizados com alto custo de manutenção
- Scrapers perdem campos importantes (bairro, banheiros, vagas, área do terreno)
- Estado complexo: async + threads + reruns do Streamlit
- Agendamento via GitHub Actions (externo ao app)

O objetivo é reconstruir o app com uma stack mais simples, rápida e controlável, mantendo todas as funcionalidades existentes e corrigindo os problemas acima.

---

## Stack Escolhida

| Camada | Tecnologia |
|---|---|
| Backend | FastAPI |
| Templates | Jinja2 |
| Interatividade frontend | HTMX |
| Estilo | Tailwind CSS (via CDN) |
| Banco de dados | SQLite |
| ORM | SQLAlchemy (core, não ORM completo) |
| Scrapers | Python + Playwright (reescrito) |
| Agendamento | APScheduler (embutido no FastAPI) |
| Autenticação | Sessão via cookie (Starlette SessionMiddleware + bcrypt) |
| Mapa | Folium |
| Hospedagem | Oracle Cloud Always Free (ARM, 4 cores, 24GB RAM) |

**Desenvolvimento local:** `uvicorn app:app --reload` — idêntico à produção, sem configuração especial.

---

## Arquitetura Geral

```
Oracle Cloud ARM VM
│
└── FastAPI (único processo)
    ├── APScheduler (scraping agendado em background)
    ├── Rotas HTML (Jinja2 templates)
    ├── Rotas HTMX (partials HTML)
    ├── SSE endpoint (log em tempo real)
    └── SQLite (imoveis.db)
```

Um único processo Python gerencia tudo. Sem GitHub Actions, sem serviços externos além do Playwright para scraping.

---

## Modelo de Dados (SQLite)

### `imoveis`
Estado atual de cada imóvel. Chave primária é MD5(source_site + source_url).

```sql
id               TEXT PRIMARY KEY
transaction_type TEXT              -- 'aluguel' | 'compra'
source_site      TEXT
source_url       TEXT
title            TEXT
city             TEXT
neighborhood     TEXT
category         TEXT              -- Casa, Apartamento, Terreno, etc.
bedrooms         INTEGER
bathrooms        INTEGER
parking_spots    INTEGER
area_m2          REAL              -- área construída
land_area_m2     REAL              -- área do terreno
price            REAL
address          TEXT              -- preenchido manualmente pelo usuário
comments         TEXT
status           TEXT
lat              REAL
lng              REAL
first_seen       TEXT              -- ISO datetime
last_seen        TEXT
is_active        INTEGER           -- 0 | 1
```

### `imovel_imagens`
Todas as imagens de cada imóvel. `position = 0` é a capa.

```sql
id         INTEGER PRIMARY KEY AUTOINCREMENT
imovel_id  TEXT
url        TEXT
position   INTEGER
```

Imagens servidas por URL direta da fonte (sem download local). O carrossel no painel de detalhe usa essas URLs.

### `historico`
Snapshot de cada mudança detectada por run.

```sql
id              INTEGER PRIMARY KEY AUTOINCREMENT
imovel_id       TEXT
run_id          TEXT
scraped_at      TEXT
price           REAL
area_m2         REAL
land_area_m2    REAL
bedrooms        INTEGER
neighborhood    TEXT
is_active       INTEGER
change_flag     TEXT    -- 'new' | 'updated' | 'removed'
changes_summary TEXT    -- JSON: {"price": {"old": 3800, "new": 3900}}
```

### `runs`
Log de cada execução de scraping.

```sql
run_id           TEXT PRIMARY KEY
run_date         TEXT
sites_scraped    TEXT     -- JSON array de nomes
total_found      INTEGER
new_count        INTEGER
updated_count    INTEGER
removed_count    INTEGER
duration_seconds REAL
status           TEXT     -- 'running' | 'completed' | 'failed'
log              TEXT     -- resumo: uma linha por site + linha final
```

**Formato do log (sucinto):**
```
[07:01:02] dois_irmaos → 23 encontrados, 2 novos, 1 atualizado
[07:01:15] becker → 18 encontrados, 0 mudanças
[07:01:18] felippe_alfredo → ERRO: timeout após 3 tentativas
[07:01:45] CONCLUÍDO → 12 sites, 187 imóveis, 4 novos, 2 atualizados (43s)
```

### `workspace`
Linha única. Estado global do workspace.

```sql
id                         INTEGER PRIMARY KEY  -- sempre 1
last_reviewed_aluguel_at   TEXT
last_reviewed_compra_at    TEXT
scraping_schedule          TEXT    -- cron expression, ex: "0 7 * * *"
```

`last_reviewed_*` é atualizado automaticamente toda vez que o usuário muda o status de um imóvel na aba correspondente. O botão "Marcar como revisado" também atualiza manualmente.

### `users`
Autenticação simples por workspace.

```sql
id            INTEGER PRIMARY KEY AUTOINCREMENT
username      TEXT UNIQUE
password_hash TEXT    -- bcrypt
created_at    TEXT
```

### `activity_log`
Rastreamento de quem alterou o quê e quando.

```sql
id          INTEGER PRIMARY KEY AUTOINCREMENT
imovel_id   TEXT
user_id     INTEGER
changed_at  TEXT
field       TEXT        -- 'status' | 'comments' | 'address' | etc.
old_value   TEXT
new_value   TEXT
```

**Total: 6 tabelas.**

---

## Multi-tenancy

Modelo "workspace por arquivo SQLite". Cada workspace é um `.db` independente:

```
workspaces/
├── familia.db
└── outro.db
```

O workspace ativo é definido por variável de ambiente:

```bash
WORKSPACE=workspaces/familia.db uvicorn app:app
```

Usuários de um mesmo workspace compartilham o mesmo banco. Para um workspace independente, basta criar um novo `.db` e rodar uma instância separada do app.

**Bootstrap do primeiro usuário:**
```bash
python manage.py create-user --workspace workspaces/familia.db
```

---

## Autenticação

- Login via `POST /login` (formulário HTML)
- Senha armazenada com bcrypt
- Sessão por cookie assinado (Starlette `SessionMiddleware`)
- Middleware verifica sessão em todo request — redireciona para `/login` se ausente
- Logout via `POST /logout` limpa o cookie

---

## Estrutura de Rotas

### Páginas completas
```
GET  /login
POST /login
POST /logout
GET  /                    → redireciona para /aluguel
GET  /aluguel
GET  /compra
GET  /mapa
GET  /historico
GET  /configuracoes
```

### Partials HTMX (retornam fragmentos HTML)
```
GET  /partials/imoveis                    → tabela filtrada
GET  /partials/imovel/{id}               → painel de detalhe
POST /partials/imovel/{id}/status        → atualiza status
GET  /partials/imovel/{id}/edit          → modal de edição
POST /partials/imovel/{id}/edit          → salva edição (inclui geocodificação)
GET  /partials/imovel/{id}/geocode       → geocodifica endereço → retorna lat/lng
POST /scraping/trigger                   → dispara scraping manual
GET  /scraping/stream                    → SSE: log em tempo real
POST /workspace/reviewed/{tipo}          → marca aba como revisada
```

**Geocodificação:** ao salvar endereço no modal de edição, o backend chama Nominatim (OpenStreetMap, gratuito, 1 req/s) para converter o endereço em coordenadas e salvar `lat/lng` no imóvel. Também aceita URL do Google Maps para extração direta de coordenadas (sem chamada externa).

---

## Layout e Componentes Frontend

### Layout geral (aluguel/compra)
```
┌─────────────────────────────────────────────────┐
│  NAVBAR: [Aluguel] [Compra] [Mapa] [Histórico]  │
│          [Configurações] ─────────── [user] [↩] │
├─────────────────────────────────────────────────┤
│  BANNER (condicional)                           │
│  "12 novos · 3 atualizados · 1 removido         │
│   desde sua última revisão (há 3 dias)" [✓ OK]  │
├──────────────┬──────────────────────────────────┤
│              │                                  │
│   FILTROS    │   TABELA DE IMÓVEIS              │
│              │   (atualiza via HTMX)            │
│  Imobiliária │                                  │
│  Status      ├──────────────────────────────────┤
│  Bairro      │                                  │
│  Tipo        │   PAINEL DE DETALHE              │
│  Preço       │   (abre ao clicar numa linha)    │
│              │   • carrossel de imagens         │
│              │   • dados completos              │
│              │   • histórico de preço           │
│              │   • última alteração: quem/quando│
└──────────────┴──────────────────────────────────┘
```

**Filtros disponíveis:** Imobiliária, Status, Bairro, Tipo de imóvel, Faixa de preço.  
*(Quartos e metragem removidos dos filtros por dados não confiáveis — podem ser adicionados no futuro.)*

### Templates
```
templates/
├── base.html
├── login.html
├── aluguel.html
├── compra.html
├── mapa.html
├── historico.html
├── configuracoes.html
└── partials/
    ├── _imovel_tabela.html
    ├── _imovel_linha.html
    ├── _imovel_detalhe.html
    ├── _imovel_modal_editar.html
    ├── _review_banner.html
    ├── _scraping_log.html
    └── _run_stats.html
```

---

## Arquitetura dos Scrapers

### Estrutura de arquivos
```
scrapers/
├── base.py           # BaseScraper, PropertyData
├── platforms/
│   ├── kenlo.py
│   ├── vista.py
│   ├── jetimob.py
│   └── tecimob.py
├── sites/            # overrides para sites com comportamento único
├── registry.py
└── runner.py         # orquestrador + APScheduler + SSE
```

De ~37 arquivos customizados para ~10. Novos sites na mesma plataforma = apenas entrada em `sites.yaml`.

### `PropertyData`
```python
@dataclass
class PropertyData:
    source_site: str
    source_url: str
    title: str
    city: str
    neighborhood: str
    category: str
    transaction_type: str   # 'aluguel' | 'compra'
    price: float | None
    bedrooms: int | None
    bathrooms: int | None
    parking_spots: int | None
    area_m2: float | None
    land_area_m2: float | None
    images: list[str]       # todas as imagens; índice 0 = capa
```

### Estratégia de extração
Cada campo tem cadeia de fallback, tornando os scrapers resilientes a variações de layout:

```
neighborhood → meta tag → breadcrumb → título → URL → None
area_m2      → ficha técnica → regex no título → regex na descrição → None
land_area_m2 → "área do terreno" na ficha → regex "terreno" → None
images       → data-src → src → background-image → data-bg → []
```

### `sites.yaml` com plataforma declarada
```yaml
- name: dois_irmaos
  url: https://...
  platform: kenlo
  transaction_type: aluguel
  active: true
```

### Runner
- APScheduler executa `run_scraping()` conforme `workspace.scraping_schedule`
- Trigger manual via `POST /scraping/trigger` chama a mesma função
- Sites executam sequencialmente (respeita rate limits e evita detecção)
- Falha em um site não interrompe os demais
- Progresso enviado via SSE ao browser em tempo real

---

## Fluxos Principais

### Fluxo de scraping
```
APScheduler / trigger manual
→ runner cria run_id
→ para cada site: scraper → PropertyData[]
→ compara com historico → detecta new/updated/removed
→ salva em imoveis, historico, imovel_imagens
→ event_queue → SSE → browser (log em tempo real)
→ fim: atualiza runs com resumo
```

### Fluxo de atualização de status
```
Usuário clica em status
→ POST /partials/imovel/{id}/status
→ UPDATE imoveis SET status
→ INSERT activity_log
→ UPDATE workspace.last_reviewed_{tipo}_at
→ retorna _imovel_linha.html atualizada
→ HTMX substitui só aquela linha
```

### Fluxo do banner de revisão
```
GET /aluguel
→ conta mudanças em historico desde last_reviewed_aluguel_at
→ se > 0: renderiza banner com contagens por tipo
→ [✓ OK] → POST /workspace/reviewed/aluguel → remove banner via HTMX
```

---

## Estrutura do Projeto

```
c:/dev/imoveis-di/
├── app.py                    # instância FastAPI, routers, middleware
├── manage.py                 # CLI: create-user, init-db
├── requirements.txt
├── config/
│   └── sites.yaml
├── scrapers/
│   ├── base.py
│   ├── runner.py
│   ├── registry.py
│   ├── platforms/
│   └── sites/
├── storage/
│   └── database.py           # conexão SQLite, queries
├── routers/
│   ├── auth.py
│   ├── imoveis.py
│   ├── scraping.py
│   └── workspace.py
├── templates/
│   ├── base.html
│   └── partials/
├── static/
│   └── app.js                # mínimo: inicialização HTMX + carrossel
├── workspaces/
│   └── .gitkeep
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-04-13-migracao-streamlit-para-fastapi-design.md
```

---

## O que Não Está no Escopo

- Deduplicação automática de imóveis (manutenção de grupos fica como está)
- Notificações (email/push) para novos imóveis
- API pública read-only
- Download/cache local de imagens
- Filtros por quartos e metragem (dados não confiáveis por ora)
