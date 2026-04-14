# Imoveis DI — Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Imoveis DI Streamlit app as a FastAPI + HTMX web app with SQLite, rewritten scrapers, and full feature parity plus improvements.

**Architecture:** Single FastAPI process serving Jinja2 templates with HTMX for partial updates. SQLite as the database (one file per workspace). Scrapers rewritten around platform-level classes (Kenlo, Vista, Jetimob, Tecimob) instead of 37 site-specific files. APScheduler runs scraping in background inside the same process.

**Tech Stack:** FastAPI · Jinja2 · HTMX · Tailwind CSS (CDN) · SQLite · SQLAlchemy Core · Playwright · APScheduler · bcrypt · geopy (Nominatim) · Folium

**Spec:** `docs/superpowers/specs/2026-04-13-migracao-streamlit-para-fastapi-design.md`

---

## File Map

```
c:/dev/imoveis-di/
├── app.py                          # FastAPI instance, middleware, startup, router registration
├── manage.py                       # CLI: init-db, create-user
├── requirements.txt
├── .env.example
├── config/
│   └── sites.yaml                  # scraper site configs (ported from old project)
├── storage/
│   └── database.py                 # SQLite connection, schema DDL, all query functions
├── routers/
│   ├── auth.py                     # GET/POST /login, POST /logout
│   ├── imoveis.py                  # GET /aluguel, /compra, all /partials/imovel* routes
│   ├── scraping.py                 # POST /scraping/trigger, GET /scraping/stream (SSE)
│   └── workspace.py                # POST /workspace/reviewed/{tipo}, GET/POST /configuracoes
├── scrapers/
│   ├── base.py                     # PropertyData dataclass, BaseScraper abstract class
│   ├── runner.py                   # run_scraping(), change detection, DB writes, SSE events
│   ├── registry.py                 # maps platform name → scraper class
│   ├── platforms/
│   │   ├── kenlo.py                # Kenlo platform scraper
│   │   ├── vista.py                # Vista Soft platform scraper
│   │   ├── jetimob.py              # Jetimob platform scraper
│   │   └── tecimob.py              # Tecimob platform scraper
│   └── sites/                      # per-site overrides (only for unique behavior)
├── templates/
│   ├── base.html                   # navbar, Tailwind CDN, HTMX CDN, session user
│   ├── login.html
│   ├── aluguel.html                # filter sidebar + table area + detail panel slot
│   ├── compra.html                 # identical structure to aluguel.html
│   ├── mapa.html                   # Folium map embed
│   ├── historico.html              # runs list with stats
│   ├── configuracoes.html          # schedule, active sites
│   └── partials/
│       ├── _imovel_tabela.html     # full property table (returned by /partials/imoveis)
│       ├── _imovel_linha.html      # single table row with quick-action status buttons
│       ├── _imovel_detalhe.html    # detail panel: carousel, fields, price history, last editor
│       ├── _imovel_modal_editar.html  # edit modal: address, status, comments
│       ├── _review_banner.html     # "X novos since last review" banner
│       ├── _scraping_log.html      # live log container (populated via SSE)
│       └── _run_stats.html         # last run summary row
├── static/
│   └── app.js                      # HTMX config + carousel init (minimal)
├── workspaces/
│   └── .gitkeep
└── tests/
    ├── conftest.py                  # pytest fixtures: test DB, test client, auth helpers
    ├── test_database.py             # schema creation, CRUD queries
    ├── test_auth.py                 # login/logout, session, password hashing
    ├── test_imoveis.py              # listing routes, filter queries, status update, activity log
    ├── test_review_banner.py        # banner logic, reviewed timestamp update
    ├── test_scraping_runner.py      # change detection logic, run logging
    └── scrapers/
        ├── test_base.py             # PropertyData validation
        └── test_platforms.py        # platform scrapers with mock HTML fixtures
```

---

## Phase 1: Foundation

---

### Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `app.py`
- Create: `workspaces/.gitkeep`
- Create: `static/app.js`

- [ ] **Step 1: Create `requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
jinja2==3.1.4
python-multipart==0.0.9
itsdangerous==2.2.0
bcrypt==4.2.0
sqlalchemy==2.0.35
playwright==1.47.0
apscheduler==3.10.4
geopy==2.4.1
folium==0.17.0
pyyaml==6.0.2
python-dotenv==1.0.1
httpx==0.27.2
```

- [ ] **Step 2: Create `.env.example`**

```
WORKSPACE=workspaces/imoveis.db
SESSION_SECRET=change-this-to-a-random-string-at-least-32-chars
```

- [ ] **Step 3: Create `app.py`**

```python
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from storage.database import init_db
from routers import auth, imoveis, scraping, workspace

load_dotenv()

WORKSPACE = os.getenv("WORKSPACE", "workspaces/imoveis.db")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-in-production")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(WORKSPACE)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(imoveis.router)
app.include_router(scraping.router)
app.include_router(workspace.router)


@app.get("/")
async def root():
    return RedirectResponse(url="/aluguel")
```

- [ ] **Step 4: Create `static/app.js`**

```javascript
// HTMX configuration
document.addEventListener("DOMContentLoaded", () => {
    // Auto-submit filter forms on change
    document.querySelectorAll(".auto-filter").forEach(el => {
        el.addEventListener("change", () => {
            el.closest("form").requestSubmit();
        });
    });
});

// Image carousel
function initCarousel(id) {
    const container = document.getElementById(id);
    if (!container) return;
    const imgs = container.querySelectorAll("img");
    let current = 0;
    const show = (i) => {
        imgs.forEach((img, idx) => img.style.display = idx === i ? "block" : "none");
    };
    show(0);
    container.querySelector(".carousel-prev")?.addEventListener("click", () => {
        current = (current - 1 + imgs.length) % imgs.length;
        show(current);
    });
    container.querySelector(".carousel-next")?.addEventListener("click", () => {
        current = (current + 1) % imgs.length;
        show(current);
    });
}

// Re-init carousel after HTMX swaps
document.addEventListener("htmx:afterSwap", (e) => {
    const carousel = e.target.querySelector("[data-carousel]");
    if (carousel) initCarousel(carousel.id);
});
```

- [ ] **Step 5: Create `workspaces/.gitkeep`**

```bash
touch workspaces/.gitkeep
```

- [ ] **Step 6: Install dependencies**

```bash
pip install -r requirements.txt
playwright install chromium
```

- [ ] **Step 7: Commit**

```bash
git init
git add requirements.txt .env.example app.py static/app.js workspaces/.gitkeep
git commit -m "feat: project scaffold"
```

---

### Task 2: Database Schema

**Files:**
- Create: `storage/__init__.py`
- Create: `storage/database.py`
- Create: `tests/conftest.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Create `storage/__init__.py`** (empty file)

- [ ] **Step 2: Write the failing test**

Create `tests/conftest.py`:
```python
import pytest
import os
from fastapi.testclient import TestClient
from storage.database import init_db, get_connection

TEST_DB = ":memory:"

@pytest.fixture
def db():
    init_db(TEST_DB)
    conn = get_connection(TEST_DB)
    yield conn
    conn.close()

@pytest.fixture
def client(db):
    os.environ["WORKSPACE"] = TEST_DB
    os.environ["SESSION_SECRET"] = "test-secret"
    from app import app
    return TestClient(app, raise_server_exceptions=True)
```

Create `tests/test_database.py`:
```python
from storage.database import init_db, get_connection

def test_schema_creates_all_tables():
    conn = get_connection(":memory:")
    init_db(":memory:", conn=conn)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert tables == {"imoveis", "imovel_imagens", "historico", "runs", "workspace", "users", "activity_log"}

def test_workspace_row_initialized():
    conn = get_connection(":memory:")
    init_db(":memory:", conn=conn)
    row = conn.execute("SELECT id FROM workspace WHERE id = 1").fetchone()
    assert row is not None
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_database.py -v
```
Expected: FAIL — `storage.database` does not exist yet.

- [ ] **Step 4: Create `storage/database.py`**

```python
import sqlite3
import os
from typing import Optional

_DB_PATH: str = ""


def get_connection(path: Optional[str] = None) -> sqlite3.Connection:
    target = path or _DB_PATH
    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: str, conn: Optional[sqlite3.Connection] = None) -> None:
    global _DB_PATH
    _DB_PATH = path
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    c = conn or get_connection(path)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS imoveis (
            id               TEXT PRIMARY KEY,
            transaction_type TEXT NOT NULL,
            source_site      TEXT NOT NULL,
            source_url       TEXT NOT NULL,
            title            TEXT,
            city             TEXT,
            neighborhood     TEXT,
            category         TEXT,
            bedrooms         INTEGER,
            bathrooms        INTEGER,
            parking_spots    INTEGER,
            area_m2          REAL,
            land_area_m2     REAL,
            price            REAL,
            address          TEXT,
            comments         TEXT,
            status           TEXT DEFAULT 'Novo',
            lat              REAL,
            lng              REAL,
            first_seen       TEXT NOT NULL,
            last_seen        TEXT NOT NULL,
            is_active        INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS imovel_imagens (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            imovel_id TEXT NOT NULL,
            url       TEXT NOT NULL,
            position  INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS historico (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            imovel_id       TEXT NOT NULL,
            run_id          TEXT NOT NULL,
            scraped_at      TEXT NOT NULL,
            price           REAL,
            area_m2         REAL,
            land_area_m2    REAL,
            bedrooms        INTEGER,
            neighborhood    TEXT,
            is_active       INTEGER,
            change_flag     TEXT NOT NULL,
            changes_summary TEXT
        );

        CREATE TABLE IF NOT EXISTS runs (
            run_id           TEXT PRIMARY KEY,
            run_date         TEXT NOT NULL,
            sites_scraped    TEXT,
            total_found      INTEGER DEFAULT 0,
            new_count        INTEGER DEFAULT 0,
            updated_count    INTEGER DEFAULT 0,
            removed_count    INTEGER DEFAULT 0,
            duration_seconds REAL,
            status           TEXT DEFAULT 'running',
            log              TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS workspace (
            id                        INTEGER PRIMARY KEY DEFAULT 1,
            last_reviewed_aluguel_at  TEXT,
            last_reviewed_compra_at   TEXT,
            scraping_schedule         TEXT DEFAULT '0 7 * * *'
        );

        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            imovel_id  TEXT NOT NULL,
            user_id    INTEGER NOT NULL,
            changed_at TEXT NOT NULL,
            field      TEXT NOT NULL,
            old_value  TEXT,
            new_value  TEXT
        );

        INSERT OR IGNORE INTO workspace (id) VALUES (1);
    """)
    c.commit()


# ── Property queries ──────────────────────────────────────────────────────────

def get_imoveis(conn: sqlite3.Connection, transaction_type: str,
                site: str = "", status: str = "", neighborhood: str = "",
                category: str = "", price_min: float = 0, price_max: float = 0
                ) -> list[sqlite3.Row]:
    sql = "SELECT * FROM imoveis WHERE transaction_type = ? AND is_active = 1"
    params: list = [transaction_type]
    if site:
        sql += " AND source_site = ?"
        params.append(site)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if neighborhood:
        sql += " AND neighborhood = ?"
        params.append(neighborhood)
    if category:
        sql += " AND category = ?"
        params.append(category)
    if price_min:
        sql += " AND price >= ?"
        params.append(price_min)
    if price_max:
        sql += " AND price <= ?"
        params.append(price_max)
    sql += " ORDER BY first_seen DESC"
    return conn.execute(sql, params).fetchall()


def get_imovel(conn: sqlite3.Connection, imovel_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM imoveis WHERE id = ?", [imovel_id]).fetchone()


def get_imovel_images(conn: sqlite3.Connection, imovel_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT url FROM imovel_imagens WHERE imovel_id = ? ORDER BY position",
        [imovel_id]
    ).fetchall()


def update_imovel_status(conn: sqlite3.Connection, imovel_id: str, status: str) -> None:
    conn.execute("UPDATE imoveis SET status = ? WHERE id = ?", [status, imovel_id])
    conn.commit()


def update_imovel_fields(conn: sqlite3.Connection, imovel_id: str,
                          address: str, comments: str, lat: float | None, lng: float | None) -> None:
    conn.execute(
        "UPDATE imoveis SET address=?, comments=?, lat=?, lng=? WHERE id=?",
        [address, comments, lat, lng, imovel_id]
    )
    conn.commit()


def get_imovel_price_history(conn: sqlite3.Connection, imovel_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT scraped_at, price, change_flag FROM historico WHERE imovel_id = ? ORDER BY scraped_at",
        [imovel_id]
    ).fetchall()


def get_distinct_values(conn: sqlite3.Connection, transaction_type: str,
                         column: str) -> list[str]:
    allowed = {"source_site", "status", "neighborhood", "category"}
    if column not in allowed:
        return []
    rows = conn.execute(
        f"SELECT DISTINCT {column} FROM imoveis WHERE transaction_type = ? AND is_active = 1 AND {column} IS NOT NULL ORDER BY {column}",
        [transaction_type]
    ).fetchall()
    return [r[0] for r in rows]


# ── Activity log ──────────────────────────────────────────────────────────────

def log_activity(conn: sqlite3.Connection, imovel_id: str, user_id: int,
                  field: str, old_value: str | None, new_value: str | None) -> None:
    from datetime import datetime, timezone
    conn.execute(
        "INSERT INTO activity_log (imovel_id, user_id, changed_at, field, old_value, new_value) VALUES (?,?,?,?,?,?)",
        [imovel_id, user_id, datetime.now(timezone.utc).isoformat(), field, old_value, new_value]
    )
    conn.commit()


def get_last_activity(conn: sqlite3.Connection, imovel_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT a.changed_at, u.username FROM activity_log a
           JOIN users u ON u.id = a.user_id
           WHERE a.imovel_id = ? ORDER BY a.changed_at DESC LIMIT 1""",
        [imovel_id]
    ).fetchone()


# ── Review banner ─────────────────────────────────────────────────────────────

def get_changes_since_review(conn: sqlite3.Connection, transaction_type: str) -> dict:
    col = f"last_reviewed_{transaction_type}_at"
    ws = conn.execute(f"SELECT {col} FROM workspace WHERE id=1").fetchone()
    since = ws[0] if ws and ws[0] else "1970-01-01"
    rows = conn.execute(
        """SELECT change_flag, COUNT(*) as cnt FROM historico h
           JOIN imoveis i ON i.id = h.imovel_id
           WHERE i.transaction_type = ? AND h.scraped_at > ?
           GROUP BY change_flag""",
        [transaction_type, since]
    ).fetchall()
    return {r["change_flag"]: r["cnt"] for r in rows}


def mark_reviewed(conn: sqlite3.Connection, transaction_type: str) -> None:
    from datetime import datetime, timezone
    col = f"last_reviewed_{transaction_type}_at"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(f"UPDATE workspace SET {col} = ? WHERE id = 1", [now])
    conn.commit()


# ── Workspace / runs ──────────────────────────────────────────────────────────

def get_workspace(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute("SELECT * FROM workspace WHERE id=1").fetchone()


def update_schedule(conn: sqlite3.Connection, schedule: str) -> None:
    conn.execute("UPDATE workspace SET scraping_schedule=? WHERE id=1", [schedule])
    conn.commit()


def get_runs(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM runs ORDER BY run_date DESC LIMIT ?", [limit]
    ).fetchall()


def get_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM runs WHERE run_id=?", [run_id]).fetchone()


# ── Users ─────────────────────────────────────────────────────────────────────

def get_user_by_username(conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE username=?", [username]).fetchone()


def create_user(conn: sqlite3.Connection, username: str, password_hash: str) -> None:
    from datetime import datetime, timezone
    conn.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
        [username, password_hash, datetime.now(timezone.utc).isoformat()]
    )
    conn.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_database.py -v
```
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add storage/ tests/conftest.py tests/test_database.py
git commit -m "feat: SQLite schema and database query functions"
```

---

### Task 3: Authentication

**Files:**
- Create: `routers/__init__.py`
- Create: `routers/auth.py`
- Create: `manage.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_auth.py`:
```python
import pytest
from fastapi.testclient import TestClient
from storage.database import init_db, get_connection, create_user
import bcrypt, os

@pytest.fixture
def client_with_user():
    os.environ["WORKSPACE"] = ":memory:"
    os.environ["SESSION_SECRET"] = "test-secret"
    conn = get_connection(":memory:")
    init_db(":memory:", conn=conn)
    pw = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
    create_user(conn, "testuser", pw)
    from app import app
    return TestClient(app, raise_server_exceptions=True)

def test_login_success(client_with_user):
    r = client_with_user.post("/login", data={"username": "testuser", "password": "password123"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/aluguel"

def test_login_wrong_password(client_with_user):
    r = client_with_user.post("/login", data={"username": "testuser", "password": "wrong"}, follow_redirects=False)
    assert r.status_code == 200
    assert "Usuário ou senha incorretos" in r.text

def test_protected_route_redirects_to_login(client_with_user):
    r = client_with_user.get("/aluguel", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]

def test_logout_clears_session(client_with_user):
    client_with_user.post("/login", data={"username": "testuser", "password": "password123"})
    r = client_with_user.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    r2 = client_with_user.get("/aluguel", follow_redirects=False)
    assert r2.status_code == 303
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_auth.py -v
```
Expected: FAIL — routers not defined yet.

- [ ] **Step 3: Create `routers/__init__.py`** (empty)

- [ ] **Step 4: Create `routers/auth.py`**

```python
import os
import bcrypt
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from storage.database import get_connection, get_user_by_username

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def require_login(request: Request) -> int | None:
    """Returns user_id if logged in, else None."""
    return request.session.get("user_id")


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if require_login(request):
        return RedirectResponse(url="/aluguel", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_connection()
    user = get_user_by_username(conn, username)
    conn.close()
    if user and bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        request.session["user_id"] = user["id"]
        request.session["username"] = user["username"]
        return RedirectResponse(url="/aluguel", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Usuário ou senha incorretos"},
        status_code=200
    )


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
```

- [ ] **Step 5: Create `templates/login.html`**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Login — Imoveis DI</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 flex items-center justify-center min-h-screen">
  <div class="bg-white p-8 rounded-lg shadow-md w-full max-w-sm">
    <h1 class="text-2xl font-bold text-gray-800 mb-6 text-center">Imoveis DI</h1>
    {% if error %}
      <p class="text-red-500 text-sm mb-4 text-center">{{ error }}</p>
    {% endif %}
    <form method="post" action="/login" class="space-y-4">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Usuário</label>
        <input type="text" name="username" autofocus required
               class="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Senha</label>
        <input type="password" name="password" required
               class="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
      </div>
      <button type="submit"
              class="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 text-sm font-medium">
        Entrar
      </button>
    </form>
  </div>
</body>
</html>
```

- [ ] **Step 6: Create `manage.py`**

```python
#!/usr/bin/env python3
"""CLI for database management."""
import argparse
import bcrypt
import os
from dotenv import load_dotenv

load_dotenv()


def cmd_init_db(args):
    from storage.database import init_db
    path = args.workspace or os.getenv("WORKSPACE", "workspaces/imoveis.db")
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    init_db(path)
    print(f"Database initialized: {path}")


def cmd_create_user(args):
    from storage.database import init_db, get_connection, create_user, get_user_by_username
    path = args.workspace or os.getenv("WORKSPACE", "workspaces/imoveis.db")
    init_db(path)
    conn = get_connection(path)
    username = input("Username: ").strip()
    if get_user_by_username(conn, username):
        print(f"User '{username}' already exists.")
        return
    import getpass
    password = getpass.getpass("Password: ")
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    create_user(conn, username, pw_hash)
    conn.close()
    print(f"User '{username}' created.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default=None)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("init-db")
    sub.add_parser("create-user")
    args = parser.parse_args()
    if args.command == "init-db":
        cmd_init_db(args)
    elif args.command == "create-user":
        cmd_create_user(args)
    else:
        parser.print_help()
```

- [ ] **Step 7: Update `storage/database.py` — `get_connection` to use global path when called without args**

The `get_connection` function already supports this via the `_DB_PATH` global. Verify `init_db` sets it:
```python
# Already in database.py:
def init_db(path: str, conn=None):
    global _DB_PATH
    _DB_PATH = path  # ← this sets the global
```
No change needed.

- [ ] **Step 8: Run tests**

```bash
pytest tests/test_auth.py -v
```
Expected: 4 PASSED

- [ ] **Step 9: Commit**

```bash
git add routers/ templates/login.html manage.py
git commit -m "feat: authentication — login/logout with session cookies"
```

---

### Task 4: Base Template and Stub Routes

**Files:**
- Create: `templates/base.html`
- Create: `templates/aluguel.html`
- Create: `templates/compra.html`
- Create: `templates/mapa.html`
- Create: `templates/historico.html`
- Create: `templates/configuracoes.html`
- Create: `routers/imoveis.py`
- Create: `routers/scraping.py`
- Create: `routers/workspace.py`

- [ ] **Step 1: Create `templates/base.html`**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Imoveis DI{% endblock %}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12/dist/ext/sse.js"></script>
  <script src="/static/app.js" defer></script>
</head>
<body class="bg-gray-50 text-gray-900">

  <!-- Navbar -->
  <nav class="bg-white border-b border-gray-200 px-4 py-2 flex items-center gap-1">
    <a href="/aluguel" class="px-3 py-1.5 rounded text-sm font-medium
      {% if active_tab == 'aluguel' %}bg-blue-600 text-white{% else %}text-gray-600 hover:bg-gray-100{% endif %}">
      Aluguel
    </a>
    <a href="/compra" class="px-3 py-1.5 rounded text-sm font-medium
      {% if active_tab == 'compra' %}bg-blue-600 text-white{% else %}text-gray-600 hover:bg-gray-100{% endif %}">
      Compra
    </a>
    <a href="/mapa" class="px-3 py-1.5 rounded text-sm font-medium
      {% if active_tab == 'mapa' %}bg-blue-600 text-white{% else %}text-gray-600 hover:bg-gray-100{% endif %}">
      Mapa
    </a>
    <a href="/historico" class="px-3 py-1.5 rounded text-sm font-medium
      {% if active_tab == 'historico' %}bg-blue-600 text-white{% else %}text-gray-600 hover:bg-gray-100{% endif %}">
      Histórico
    </a>
    <a href="/configuracoes" class="px-3 py-1.5 rounded text-sm font-medium
      {% if active_tab == 'configuracoes' %}bg-blue-600 text-white{% else %}text-gray-600 hover:bg-gray-100{% endif %}">
      Configurações
    </a>
    <div class="ml-auto flex items-center gap-3 text-sm text-gray-500">
      <span>{{ username }}</span>
      <form method="post" action="/logout">
        <button class="text-gray-400 hover:text-red-500">Sair</button>
      </form>
    </div>
  </nav>

  {% block content %}{% endblock %}

</body>
</html>
```

- [ ] **Step 2: Create stub page templates**

`templates/aluguel.html`:
```html
{% extends "base.html" %}
{% block title %}Aluguel — Imoveis DI{% endblock %}
{% block content %}
<div class="p-4">
  {% include "partials/_review_banner.html" %}
  <div class="flex gap-4 mt-4">
    <!-- Filters sidebar -->
    <aside class="w-56 shrink-0">
      {% include "partials/_filters.html" %}
    </aside>
    <!-- Table + detail -->
    <div class="flex-1 min-w-0">
      <div id="tabela-container"
           hx-get="/partials/imoveis?tipo=aluguel"
           hx-trigger="load"
           hx-target="#tabela-container">
        <p class="text-gray-400 text-sm">Carregando...</p>
      </div>
    </div>
    <!-- Detail panel -->
    <aside class="w-96 shrink-0" id="detalhe-panel"></aside>
  </div>
</div>
{% endblock %}
```

`templates/compra.html`:
```html
{% extends "base.html" %}
{% block title %}Compra — Imoveis DI{% endblock %}
{% block content %}
<div class="p-4">
  {% include "partials/_review_banner.html" %}
  <div class="flex gap-4 mt-4">
    <aside class="w-56 shrink-0">{% include "partials/_filters.html" %}</aside>
    <div class="flex-1 min-w-0">
      <div id="tabela-container"
           hx-get="/partials/imoveis?tipo=compra"
           hx-trigger="load"
           hx-target="#tabela-container">
        <p class="text-gray-400 text-sm">Carregando...</p>
      </div>
    </div>
    <aside class="w-96 shrink-0" id="detalhe-panel"></aside>
  </div>
</div>
{% endblock %}
```

`templates/mapa.html`:
```html
{% extends "base.html" %}
{% block title %}Mapa — Imoveis DI{% endblock %}
{% block content %}
<div class="p-4">
  {{ map_html | safe }}
</div>
{% endblock %}
```

`templates/historico.html`:
```html
{% extends "base.html" %}
{% block title %}Histórico — Imoveis DI{% endblock %}
{% block content %}
<div class="p-4 max-w-4xl">
  <h2 class="text-lg font-semibold mb-4">Histórico de Scraping</h2>
  <table class="w-full text-sm border-collapse">
    <thead>
      <tr class="text-left border-b border-gray-200">
        <th class="py-2 pr-4">Data</th>
        <th class="py-2 pr-4">Sites</th>
        <th class="py-2 pr-4">Novos</th>
        <th class="py-2 pr-4">Atualizados</th>
        <th class="py-2 pr-4">Removidos</th>
        <th class="py-2 pr-4">Duração</th>
        <th class="py-2">Status</th>
      </tr>
    </thead>
    <tbody>
      {% for run in runs %}
      <tr class="border-b border-gray-100 hover:bg-gray-50 cursor-pointer"
          hx-get="/partials/run/{{ run.run_id }}"
          hx-target="#run-detail"
          hx-swap="innerHTML">
        <td class="py-2 pr-4">{{ run.run_date[:16] }}</td>
        <td class="py-2 pr-4">{{ run.sites_scraped | length }}</td>
        <td class="py-2 pr-4 text-green-600">{{ run.new_count }}</td>
        <td class="py-2 pr-4 text-yellow-600">{{ run.updated_count }}</td>
        <td class="py-2 pr-4 text-red-500">{{ run.removed_count }}</td>
        <td class="py-2 pr-4">{{ "%.0f"|format(run.duration_seconds or 0) }}s</td>
        <td class="py-2">
          <span class="px-2 py-0.5 rounded text-xs
            {% if run.status == 'completed' %}bg-green-100 text-green-700
            {% elif run.status == 'failed' %}bg-red-100 text-red-600
            {% else %}bg-yellow-100 text-yellow-700{% endif %}">
            {{ run.status }}
          </span>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <div id="run-detail" class="mt-6 font-mono text-xs bg-gray-900 text-green-400 p-4 rounded whitespace-pre-wrap"></div>
</div>
{% endblock %}
```

`templates/configuracoes.html`:
```html
{% extends "base.html" %}
{% block title %}Configurações — Imoveis DI{% endblock %}
{% block content %}
<div class="p-4 max-w-lg">
  <h2 class="text-lg font-semibold mb-6">Configurações</h2>
  <form hx-post="/configuracoes" hx-swap="none" class="space-y-6">
    <div>
      <label class="block text-sm font-medium mb-1">Agendamento de scraping (cron)</label>
      <input type="text" name="schedule" value="{{ workspace.scraping_schedule }}"
             class="border border-gray-300 rounded px-3 py-2 text-sm w-full">
      <p class="text-xs text-gray-400 mt-1">Ex: "0 7 * * *" = todo dia às 7h</p>
    </div>
    <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700">
      Salvar
    </button>
  </form>
  <div class="mt-8">
    <h3 class="font-medium text-sm mb-3">Scraping manual</h3>
    <button hx-post="/scraping/trigger"
            hx-target="#scraping-log"
            hx-swap="innerHTML"
            class="bg-gray-800 text-white px-4 py-2 rounded text-sm hover:bg-gray-700">
      Executar agora
    </button>
    <div id="scraping-log" class="mt-4 font-mono text-xs bg-gray-900 text-green-400 p-4 rounded min-h-20"></div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Create stub partial templates**

Create `templates/partials/_review_banner.html`:
```html
{% if changes and (changes.get('new', 0) + changes.get('updated', 0) + changes.get('removed', 0)) > 0 %}
<div id="review-banner" class="bg-blue-50 border border-blue-200 rounded px-4 py-2 flex items-center justify-between text-sm">
  <span class="text-blue-800">
    <strong>{{ changes.get('new', 0) }} novos</strong>
    · {{ changes.get('updated', 0) }} atualizados
    · {{ changes.get('removed', 0) }} removidos
    desde sua última revisão
  </span>
  <button hx-post="/workspace/reviewed/{{ tipo }}"
          hx-target="#review-banner"
          hx-swap="outerHTML"
          class="text-blue-600 hover:text-blue-800 font-medium ml-4">
    ✓ Marcar como revisado
  </button>
</div>
{% endif %}
```

Create `templates/partials/_filters.html`:
```html
<form id="filter-form"
      hx-get="/partials/imoveis"
      hx-target="#tabela-container"
      hx-trigger="change from:.auto-filter, submit">
  <input type="hidden" name="tipo" value="{{ tipo }}">
  <div class="space-y-3 text-sm">
    <div>
      <label class="block text-xs font-medium text-gray-500 mb-1">Imobiliária</label>
      <select name="site" class="auto-filter w-full border border-gray-300 rounded px-2 py-1.5 text-sm">
        <option value="">Todas</option>
        {% for s in filter_options.sites %}
        <option value="{{ s }}" {% if filters.site == s %}selected{% endif %}>{{ s }}</option>
        {% endfor %}
      </select>
    </div>
    <div>
      <label class="block text-xs font-medium text-gray-500 mb-1">Status</label>
      <select name="status" class="auto-filter w-full border border-gray-300 rounded px-2 py-1.5 text-sm">
        <option value="">Todos</option>
        {% for s in filter_options.statuses %}
        <option value="{{ s }}" {% if filters.status == s %}selected{% endif %}>{{ s }}</option>
        {% endfor %}
      </select>
    </div>
    <div>
      <label class="block text-xs font-medium text-gray-500 mb-1">Bairro</label>
      <select name="neighborhood" class="auto-filter w-full border border-gray-300 rounded px-2 py-1.5 text-sm">
        <option value="">Todos</option>
        {% for n in filter_options.neighborhoods %}
        <option value="{{ n }}" {% if filters.neighborhood == n %}selected{% endif %}>{{ n }}</option>
        {% endfor %}
      </select>
    </div>
    <div>
      <label class="block text-xs font-medium text-gray-500 mb-1">Tipo</label>
      <select name="category" class="auto-filter w-full border border-gray-300 rounded px-2 py-1.5 text-sm">
        <option value="">Todos</option>
        {% for c in filter_options.categories %}
        <option value="{{ c }}" {% if filters.category == c %}selected{% endif %}>{{ c }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="flex gap-2">
      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Preço mín</label>
        <input type="number" name="price_min" value="{{ filters.price_min or '' }}"
               class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm" placeholder="0">
      </div>
      <div>
        <label class="block text-xs font-medium text-gray-500 mb-1">Preço máx</label>
        <input type="number" name="price_max" value="{{ filters.price_max or '' }}"
               class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm" placeholder="∞">
      </div>
    </div>
  </div>
</form>
```

- [ ] **Step 4: Create stub routers**

Create `routers/imoveis.py`:
```python
import os
import folium
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from storage.database import (
    get_connection, get_imoveis, get_imovel, get_imovel_images,
    get_imovel_price_history, update_imovel_status, update_imovel_fields,
    log_activity, get_last_activity, get_distinct_values,
    get_changes_since_review, mark_reviewed, get_runs, get_run
)
from routers.auth import require_login

router = APIRouter()
templates = Jinja2Templates(directory="templates")

STATUSES = ["Novo", "Em análise", "Interessante", "Visita agendada",
            "Visitado", "Não tem interesse", "Descartado"]


def _require_auth(request: Request):
    user_id = require_login(request)
    if not user_id:
        return None
    return user_id


def _filter_options(conn, tipo: str) -> dict:
    return {
        "sites": get_distinct_values(conn, tipo, "source_site"),
        "statuses": get_distinct_values(conn, tipo, "status"),
        "neighborhoods": get_distinct_values(conn, tipo, "neighborhood"),
        "categories": get_distinct_values(conn, tipo, "category"),
    }


@router.get("/aluguel", response_class=HTMLResponse)
async def aluguel(request: Request):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    conn = get_connection()
    changes = get_changes_since_review(conn, "aluguel")
    conn.close()
    return templates.TemplateResponse("aluguel.html", {
        "request": request,
        "active_tab": "aluguel",
        "tipo": "aluguel",
        "username": request.session.get("username"),
        "changes": changes,
        "filters": {},
        "filter_options": _filter_options(get_connection(), "aluguel"),
    })


@router.get("/compra", response_class=HTMLResponse)
async def compra(request: Request):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    conn = get_connection()
    changes = get_changes_since_review(conn, "compra")
    conn.close()
    return templates.TemplateResponse("compra.html", {
        "request": request,
        "active_tab": "compra",
        "tipo": "compra",
        "username": request.session.get("username"),
        "changes": changes,
        "filters": {},
        "filter_options": _filter_options(get_connection(), "compra"),
    })


@router.get("/mapa", response_class=HTMLResponse)
async def mapa(request: Request):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    conn = get_connection()
    imoveis = get_imoveis(conn, "aluguel") + get_imoveis(conn, "compra")
    conn.close()
    m = folium.Map(location=[-29.6167, -51.0833], zoom_start=14)
    STATUS_COLORS = {
        "Novo": "blue", "Em análise": "orange", "Interessante": "green",
        "Visita agendada": "purple", "Visitado": "darkgreen",
        "Não tem interesse": "gray", "Descartado": "red"
    }
    for im in imoveis:
        if im["lat"] and im["lng"]:
            folium.Marker(
                location=[im["lat"], im["lng"]],
                popup=f'<a href="{im["source_url"]}" target="_blank">{im["title"]}</a>',
                tooltip=f'{im["source_site"]} — R$ {im["price"]:,.0f}' if im["price"] else im["source_site"],
                icon=folium.Icon(color=STATUS_COLORS.get(im["status"], "blue"))
            ).add_to(m)
    return templates.TemplateResponse("mapa.html", {
        "request": request,
        "active_tab": "mapa",
        "username": request.session.get("username"),
        "map_html": m._repr_html_(),
    })


@router.get("/historico", response_class=HTMLResponse)
async def historico(request: Request):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    conn = get_connection()
    import json
    runs_raw = get_runs(conn)
    runs = []
    for r in runs_raw:
        d = dict(r)
        d["sites_scraped"] = json.loads(d["sites_scraped"] or "[]")
        runs.append(d)
    conn.close()
    return templates.TemplateResponse("historico.html", {
        "request": request,
        "active_tab": "historico",
        "username": request.session.get("username"),
        "runs": runs,
    })


@router.get("/partials/imoveis", response_class=HTMLResponse)
async def partial_imoveis(request: Request, tipo: str = "aluguel",
                           site: str = "", status: str = "", neighborhood: str = "",
                           category: str = "", price_min: float = 0, price_max: float = 0):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    imoveis = get_imoveis(conn, tipo, site, status, neighborhood, category, price_min, price_max)
    conn.close()
    return templates.TemplateResponse("partials/_imovel_tabela.html", {
        "request": request,
        "imoveis": imoveis,
        "tipo": tipo,
        "filters": {"site": site, "status": status, "neighborhood": neighborhood,
                    "category": category, "price_min": price_min, "price_max": price_max},
    })


@router.get("/partials/imovel/{imovel_id}", response_class=HTMLResponse)
async def partial_imovel_detalhe(request: Request, imovel_id: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    imovel = get_imovel(conn, imovel_id)
    images = get_imovel_images(conn, imovel_id)
    history = get_imovel_price_history(conn, imovel_id)
    last_activity = get_last_activity(conn, imovel_id)
    conn.close()
    return templates.TemplateResponse("partials/_imovel_detalhe.html", {
        "request": request,
        "imovel": imovel,
        "images": [r["url"] for r in images],
        "price_history": history,
        "last_activity": last_activity,
        "statuses": STATUSES,
    })


@router.post("/partials/imovel/{imovel_id}/status", response_class=HTMLResponse)
async def partial_update_status(request: Request, imovel_id: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    form = await request.form()
    new_status = form.get("status", "")
    user_id = request.session["user_id"]
    conn = get_connection()
    old = get_imovel(conn, imovel_id)
    old_status = old["status"] if old else None
    update_imovel_status(conn, imovel_id, new_status)
    log_activity(conn, imovel_id, user_id, "status", old_status, new_status)
    tipo = old["transaction_type"] if old else "aluguel"
    mark_reviewed(conn, tipo)
    imovel = get_imovel(conn, imovel_id)
    conn.close()
    return templates.TemplateResponse("partials/_imovel_linha.html", {
        "request": request,
        "imovel": imovel,
        "statuses": STATUSES,
    })


@router.get("/partials/imovel/{imovel_id}/edit", response_class=HTMLResponse)
async def partial_edit_get(request: Request, imovel_id: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    imovel = get_imovel(conn, imovel_id)
    conn.close()
    return templates.TemplateResponse("partials/_imovel_modal_editar.html", {
        "request": request,
        "imovel": imovel,
        "statuses": STATUSES,
    })


@router.post("/partials/imovel/{imovel_id}/edit", response_class=HTMLResponse)
async def partial_edit_post(request: Request, imovel_id: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    form = await request.form()
    address = form.get("address", "")
    comments = form.get("comments", "")
    gmaps_url = form.get("gmaps_url", "")
    lat, lng = None, None
    if gmaps_url:
        import re
        m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", gmaps_url)
        if m:
            lat, lng = float(m.group(1)), float(m.group(2))
    elif address:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut
        try:
            gc = Nominatim(user_agent="imoveis-di/1.0")
            location = gc.geocode(address + ", Dois Irmãos, RS, Brasil", timeout=5)
            if location:
                lat, lng = location.latitude, location.longitude
        except GeocoderTimedOut:
            pass
    conn = get_connection()
    update_imovel_fields(conn, imovel_id, address, comments, lat, lng)
    imovel = get_imovel(conn, imovel_id)
    conn.close()
    return templates.TemplateResponse("partials/_imovel_detalhe.html", {
        "request": request,
        "imovel": imovel,
        "images": [],
        "price_history": [],
        "last_activity": None,
        "statuses": STATUSES,
    })


@router.get("/partials/run/{run_id}", response_class=HTMLResponse)
async def partial_run_log(request: Request, run_id: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    run = get_run(conn, run_id)
    conn.close()
    log = run["log"] if run else "Log não encontrado."
    return HTMLResponse(content=f"<pre>{log}</pre>")
```

Create `routers/scraping.py` (stub — full implementation in Task 15):
```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from routers.auth import require_login

router = APIRouter()

@router.post("/scraping/trigger", response_class=HTMLResponse)
async def trigger_scraping(request: Request):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    return HTMLResponse(content='<p class="text-yellow-400">Scraping não configurado ainda.</p>')

@router.get("/scraping/stream")
async def scraping_stream(request: Request):
    return HTMLResponse(content="", status_code=200)
```

Create `routers/workspace.py`:
```python
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from storage.database import get_connection, mark_reviewed, update_schedule, get_workspace
from routers.auth import require_login

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.post("/workspace/reviewed/{tipo}", response_class=HTMLResponse)
async def reviewed(request: Request, tipo: str):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    conn = get_connection()
    mark_reviewed(conn, tipo)
    conn.close()
    return HTMLResponse(content="")  # HTMX replaces banner with nothing


@router.get("/configuracoes", response_class=HTMLResponse)
async def configuracoes_get(request: Request):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    conn = get_connection()
    ws = get_workspace(conn)
    conn.close()
    return templates.TemplateResponse("configuracoes.html", {
        "request": request,
        "active_tab": "configuracoes",
        "username": request.session.get("username"),
        "workspace": ws,
    })

@router.post("/configuracoes")
async def configuracoes_post(request: Request, schedule: str = Form(...)):
    if not require_login(request):
        return RedirectResponse(url="/login", status_code=303)
    conn = get_connection()
    update_schedule(conn, schedule)
    conn.close()
    return RedirectResponse(url="/configuracoes", status_code=303)
```

- [ ] **Step 5: Create property table and detail partial templates**

Create `templates/partials/_imovel_tabela.html`:
```html
{% if imoveis %}
<table class="w-full text-sm border-collapse">
  <thead>
    <tr class="text-left border-b border-gray-200 text-gray-500 text-xs">
      <th class="py-2 pr-3">Imóvel</th>
      <th class="py-2 pr-3">Bairro</th>
      <th class="py-2 pr-3">Preço</th>
      <th class="py-2 pr-3">Imobiliária</th>
      <th class="py-2">Status</th>
    </tr>
  </thead>
  <tbody>
    {% for im in imoveis %}
      {% include "partials/_imovel_linha.html" %}
    {% endfor %}
  </tbody>
</table>
{% else %}
<p class="text-gray-400 text-sm mt-8 text-center">Nenhum imóvel encontrado.</p>
{% endif %}
```

Create `templates/partials/_imovel_linha.html`:
```html
<tr id="imovel-{{ im.id }}"
    class="border-b border-gray-100 hover:bg-gray-50 cursor-pointer"
    hx-get="/partials/imovel/{{ im.id }}"
    hx-target="#detalhe-panel"
    hx-swap="innerHTML">
  <td class="py-2 pr-3">
    <div class="font-medium text-gray-800 truncate max-w-xs">{{ im.title or im.category or "—" }}</div>
    <div class="text-xs text-gray-400">{{ im.category }}</div>
  </td>
  <td class="py-2 pr-3 text-gray-600">{{ im.neighborhood or "—" }}</td>
  <td class="py-2 pr-3 font-medium">
    {% if im.price %}R$ {{ "{:,.0f}".format(im.price) }}{% else %}—{% endif %}
  </td>
  <td class="py-2 pr-3 text-gray-500 text-xs">{{ im.source_site }}</td>
  <td class="py-2">
    <form hx-post="/partials/imovel/{{ im.id }}/status"
          hx-target="#imovel-{{ im.id }}"
          hx-swap="outerHTML"
          onclick="event.stopPropagation()">
      <select name="status" onchange="this.form.requestSubmit()"
              class="border border-gray-200 rounded px-1 py-0.5 text-xs bg-white">
        {% for s in statuses %}
        <option value="{{ s }}" {% if im.status == s %}selected{% endif %}>{{ s }}</option>
        {% endfor %}
      </select>
    </form>
  </td>
</tr>
```

Create `templates/partials/_imovel_detalhe.html`:
```html
<div class="bg-white rounded-lg border border-gray-200 p-4 text-sm">
  {% if images %}
  <div id="carousel-{{ imovel.id }}" data-carousel class="mb-4 relative">
    {% for url in images %}
    <img src="{{ url }}" class="w-full h-48 object-cover rounded" alt="Foto {{ loop.index }}"
         onerror="this.style.display='none'">
    {% endfor %}
    {% if images|length > 1 %}
    <button class="carousel-prev absolute left-1 top-1/2 -translate-y-1/2 bg-black/40 text-white rounded-full w-7 h-7 flex items-center justify-center text-lg">‹</button>
    <button class="carousel-next absolute right-1 top-1/2 -translate-y-1/2 bg-black/40 text-white rounded-full w-7 h-7 flex items-center justify-center text-lg">›</button>
    {% endif %}
  </div>
  <script>initCarousel("carousel-{{ imovel.id }}")</script>
  {% endif %}

  <div class="flex items-start justify-between mb-3">
    <div>
      <h3 class="font-semibold text-gray-900">{{ imovel.title or imovel.category }}</h3>
      <p class="text-gray-500 text-xs">{{ imovel.source_site }} · <a href="{{ imovel.source_url }}" target="_blank" class="text-blue-500 hover:underline">ver anúncio ↗</a></p>
    </div>
    <button hx-get="/partials/imovel/{{ imovel.id }}/edit"
            hx-target="#detalhe-panel"
            hx-swap="innerHTML"
            class="text-xs text-gray-400 hover:text-blue-500">editar</button>
  </div>

  <dl class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs mb-4">
    {% if imovel.price %}<dt class="text-gray-400">Preço</dt><dd class="font-medium">R$ {{ "{:,.0f}".format(imovel.price) }}</dd>{% endif %}
    {% if imovel.neighborhood %}<dt class="text-gray-400">Bairro</dt><dd>{{ imovel.neighborhood }}</dd>{% endif %}
    {% if imovel.category %}<dt class="text-gray-400">Tipo</dt><dd>{{ imovel.category }}</dd>{% endif %}
    {% if imovel.bedrooms %}<dt class="text-gray-400">Quartos</dt><dd>{{ imovel.bedrooms }}</dd>{% endif %}
    {% if imovel.bathrooms %}<dt class="text-gray-400">Banheiros</dt><dd>{{ imovel.bathrooms }}</dd>{% endif %}
    {% if imovel.parking_spots %}<dt class="text-gray-400">Vagas</dt><dd>{{ imovel.parking_spots }}</dd>{% endif %}
    {% if imovel.area_m2 %}<dt class="text-gray-400">Área</dt><dd>{{ imovel.area_m2 }} m²</dd>{% endif %}
    {% if imovel.land_area_m2 %}<dt class="text-gray-400">Terreno</dt><dd>{{ imovel.land_area_m2 }} m²</dd>{% endif %}
  </dl>

  {% if imovel.address %}
  <p class="text-xs text-gray-500 mb-2">📍 {{ imovel.address }}</p>
  {% endif %}

  {% if imovel.comments %}
  <p class="text-xs text-gray-600 bg-gray-50 rounded p-2 mb-3">{{ imovel.comments }}</p>
  {% endif %}

  {% if price_history %}
  <div class="mb-3">
    <p class="text-xs font-medium text-gray-500 mb-1">Histórico de preço</p>
    {% for h in price_history %}
    <div class="flex justify-between text-xs text-gray-500">
      <span>{{ h.scraped_at[:10] }}</span>
      <span>{% if h.price %}R$ {{ "{:,.0f}".format(h.price) }}{% else %}—{% endif %}</span>
      <span class="{% if h.change_flag == 'new' %}text-green-500{% elif h.change_flag == 'updated' %}text-yellow-500{% else %}text-red-400{% endif %}">{{ h.change_flag }}</span>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  {% if last_activity %}
  <p class="text-xs text-gray-400 mt-2">Última alteração: <strong>{{ last_activity.username }}</strong> · {{ last_activity.changed_at[:10] }}</p>
  {% endif %}
</div>
```

Create `templates/partials/_imovel_modal_editar.html`:
```html
<div class="bg-white rounded-lg border border-gray-200 p-4 text-sm">
  <div class="flex items-center justify-between mb-4">
    <h3 class="font-semibold">Editar imóvel</h3>
    <button hx-get="/partials/imovel/{{ imovel.id }}"
            hx-target="#detalhe-panel"
            hx-swap="innerHTML"
            class="text-gray-400 hover:text-gray-600 text-lg">✕</button>
  </div>
  <form hx-post="/partials/imovel/{{ imovel.id }}/edit"
        hx-target="#detalhe-panel"
        hx-swap="innerHTML"
        class="space-y-3">
    <div>
      <label class="block text-xs font-medium text-gray-500 mb-1">Endereço</label>
      <input type="text" name="address" value="{{ imovel.address or '' }}"
             class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm">
    </div>
    <div>
      <label class="block text-xs font-medium text-gray-500 mb-1">URL Google Maps (para coordenadas)</label>
      <input type="text" name="gmaps_url" placeholder="Cole aqui o link do Google Maps"
             class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm">
    </div>
    <div>
      <label class="block text-xs font-medium text-gray-500 mb-1">Observações</label>
      <textarea name="comments" rows="3"
                class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm">{{ imovel.comments or '' }}</textarea>
    </div>
    <div class="flex gap-2 justify-end">
      <button type="button"
              hx-get="/partials/imovel/{{ imovel.id }}"
              hx-target="#detalhe-panel"
              hx-swap="innerHTML"
              class="px-3 py-1.5 text-sm text-gray-600 border border-gray-300 rounded hover:bg-gray-50">
        Cancelar
      </button>
      <button type="submit" class="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700">
        Salvar
      </button>
    </div>
  </form>
</div>
```

- [ ] **Step 6: Verify the app starts**

```bash
python manage.py init-db
python manage.py create-user
# enter: admin / admin123
uvicorn app:app --reload
```
Open `http://localhost:8000` — should redirect to login, then to empty aluguel page after login.

- [ ] **Step 7: Commit**

```bash
git add routers/ templates/ manage.py
git commit -m "feat: core UI — property listing, filters, detail panel, edit modal, review banner"
```

---

## Phase 2: Scraper Architecture

---

### Task 5: PropertyData and BaseScraper

**Files:**
- Create: `scrapers/__init__.py`
- Create: `scrapers/base.py`
- Create: `tests/scrapers/__init__.py`
- Create: `tests/scrapers/test_base.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/scrapers/test_base.py`:
```python
from scrapers.base import PropertyData, normalize_price, normalize_area, normalize_int

def test_property_data_defaults():
    p = PropertyData(
        source_site="test", source_url="http://x.com",
        title="Casa", city="Dois Irmãos", neighborhood="Centro",
        category="Casa", transaction_type="aluguel",
    )
    assert p.images == []
    assert p.price is None
    assert p.bedrooms is None

def test_normalize_price():
    assert normalize_price("R$ 1.500,00") == 1500.0
    assert normalize_price("1500") == 1500.0
    assert normalize_price("") is None
    assert normalize_price(None) is None

def test_normalize_area():
    assert normalize_area("120 m²") == 120.0
    assert normalize_area("85,5m²") == 85.5
    assert normalize_area("") is None

def test_normalize_int():
    assert normalize_int("3 quartos") == 3
    assert normalize_int("2") == 2
    assert normalize_int("") is None
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/scrapers/test_base.py -v
```
Expected: FAIL

- [ ] **Step 3: Create `scrapers/__init__.py`** (empty)

- [ ] **Step 4: Create `scrapers/base.py`**

```python
import re
import hashlib
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Optional


@dataclass
class PropertyData:
    source_site: str
    source_url: str
    title: str
    city: str
    neighborhood: str
    category: str
    transaction_type: str  # 'aluguel' | 'compra'
    price: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    parking_spots: Optional[int] = None
    area_m2: Optional[float] = None
    land_area_m2: Optional[float] = None
    images: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        key = f"{self.source_site}::{self.source_url}"
        return hashlib.md5(key.encode()).hexdigest()[:16]


def normalize_price(value: str | None) -> Optional[float]:
    if not value:
        return None
    cleaned = re.sub(r"[R$\s]", "", str(value)).replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_area(value: str | None) -> Optional[float]:
    if not value:
        return None
    m = re.search(r"(\d+[\.,]?\d*)", str(value).replace(",", "."))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def normalize_int(value: str | None) -> Optional[int]:
    if not value:
        return None
    m = re.search(r"(\d+)", str(value))
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


class BaseScraper(ABC):
    """Abstract base for all platform scrapers."""

    def __init__(self, site_name: str, url: str, transaction_type: str,
                 max_pages: int = 30, delay_seconds: float = 2.0):
        self.site_name = site_name
        self.url = url
        self.transaction_type = transaction_type
        self.max_pages = max_pages
        self.delay_seconds = delay_seconds

    @abstractmethod
    async def scrape(self) -> list[PropertyData]:
        """Run the scraper and return all found properties."""
        ...
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/scrapers/test_base.py -v
```
Expected: 4 PASSED

- [ ] **Step 6: Commit**

```bash
git add scrapers/ tests/scrapers/
git commit -m "feat: PropertyData dataclass and BaseScraper base class"
```

---

### Task 6: Platform Scrapers (Kenlo, Vista, Jetimob, Tecimob)

**Files:**
- Create: `scrapers/platforms/__init__.py`
- Create: `scrapers/platforms/kenlo.py`
- Create: `scrapers/platforms/vista.py`
- Create: `scrapers/platforms/jetimob.py`
- Create: `scrapers/platforms/tecimob.py`
- Create: `tests/scrapers/fixtures/kenlo_listing.html` (mock HTML)
- Modify: `tests/scrapers/test_platforms.py`

- [ ] **Step 1: Create mock HTML fixture for tests**

Create `tests/scrapers/fixtures/kenlo_listing.html`:
```html
<!DOCTYPE html>
<html>
<body>
  <div class="property-card" data-url="/imovel/casa-dois-irmaos-3-quartos-120m/12345">
    <img data-src="https://cdn.kenlo.io/img1.jpg" alt="foto">
    <img data-src="https://cdn.kenlo.io/img2.jpg" alt="foto2">
    <h2 class="property-title">Casa em Dois Irmãos</h2>
    <span class="property-price">R$ 2.500,00</span>
    <span class="property-address">Centro, Dois Irmãos</span>
    <ul class="property-features">
      <li class="bedrooms">3 quartos</li>
      <li class="bathrooms">2 banheiros</li>
      <li class="area">120 m²</li>
      <li class="parking">1 vaga</li>
    </ul>
  </div>
  <div class="property-card" data-url="/imovel/apartamento-centro-2-quartos-65m/67890">
    <img data-src="https://cdn.kenlo.io/img3.jpg" alt="foto">
    <h2 class="property-title">Apartamento Centro</h2>
    <span class="property-price">R$ 1.800,00</span>
    <span class="property-address">Centro, Dois Irmãos</span>
    <ul class="property-features">
      <li class="bedrooms">2 quartos</li>
      <li class="bathrooms">1 banheiro</li>
      <li class="area">65 m²</li>
    </ul>
  </div>
  <a class="next-page" href="?page=2">Próxima</a>
</body>
</html>
```

- [ ] **Step 2: Write failing tests**

Create `tests/scrapers/test_platforms.py`:
```python
import pytest
from pathlib import Path
from bs4 import BeautifulSoup
from scrapers.platforms.kenlo import KenloScraper
from scrapers.base import normalize_price, normalize_area, normalize_int

FIXTURES = Path(__file__).parent / "fixtures"

def make_soup(filename: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / filename).read_text(encoding="utf-8"), "html.parser")

def test_kenlo_parses_properties():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    properties = scraper._parse_page(soup, "https://example.com")
    assert len(properties) == 2

def test_kenlo_extracts_price():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    props = scraper._parse_page(soup, "https://example.com")
    assert props[0].price == 2500.0
    assert props[1].price == 1800.0

def test_kenlo_extracts_images():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    props = scraper._parse_page(soup, "https://example.com")
    assert len(props[0].images) == 2
    assert "img1.jpg" in props[0].images[0]

def test_kenlo_extracts_bedrooms():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    props = scraper._parse_page(soup, "https://example.com")
    assert props[0].bedrooms == 3
    assert props[1].bedrooms == 2

def test_kenlo_extracts_area():
    soup = make_soup("kenlo_listing.html")
    scraper = KenloScraper("test_site", "https://example.com", "aluguel")
    props = scraper._parse_page(soup, "https://example.com")
    assert props[0].area_m2 == 120.0
```

- [ ] **Step 3: Run to verify failure**

```bash
pytest tests/scrapers/test_platforms.py -v
```
Expected: FAIL

- [ ] **Step 4: Create `scrapers/platforms/__init__.py`** (empty)

- [ ] **Step 5: Create `scrapers/platforms/kenlo.py`**

```python
import asyncio
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from scrapers.base import BaseScraper, PropertyData, normalize_price, normalize_area, normalize_int


class KenloScraper(BaseScraper):
    """Scraper for sites running on the Kenlo platform."""

    CARD_SELECTOR = ".property-card, [class*='imovel-card'], [class*='card-imovel']"
    NEXT_PAGE_SELECTOR = "a.next-page, a[rel='next'], .pagination .next a"

    def _parse_card(self, card, base_url: str) -> PropertyData | None:
        try:
            url_raw = (card.get("data-url") or
                       (card.find("a") or {}).get("href", ""))
            if not url_raw:
                return None
            url = url_raw if url_raw.startswith("http") else base_url.rstrip("/") + "/" + url_raw.lstrip("/")

            title = (card.select_one(".property-title, h2, h3") or {}).get_text(strip=True)

            price_el = card.select_one(".property-price, [class*='price'], [class*='valor']")
            price = normalize_price(price_el.get_text() if price_el else None)

            # Neighborhood: try address element, then breadcrumb pattern in URL
            neighborhood = ""
            addr_el = card.select_one(".property-address, [class*='address'], [class*='bairro'], [class*='endereco']")
            if addr_el:
                parts = addr_el.get_text(strip=True).split(",")
                neighborhood = parts[0].strip() if parts else ""
            if not neighborhood:
                m = re.search(r"/imovel/[^/]+-([a-z-]+)-\d+-quartos", url)
                if m:
                    neighborhood = m.group(1).replace("-", " ").title()

            # Category from title or URL
            title_lower = (title or "").lower()
            url_lower = url.lower()
            category = "Casa"
            for cat_kw, cat_name in [("apartamento", "Apartamento"), ("apto", "Apartamento"),
                                       ("terreno", "Terreno"), ("comercial", "Comercial"),
                                       ("kitnet", "Kitnet"), ("sobrado", "Sobrado")]:
                if cat_kw in title_lower or cat_kw in url_lower:
                    category = cat_name
                    break

            # Features
            bedrooms = bathrooms = parking_spots = None
            area_m2 = land_area_m2 = None

            for feat in card.select(".property-features li, [class*='feature'], [class*='caracteristica']"):
                text = feat.get_text(strip=True).lower()
                el_class = " ".join(feat.get("class", []))
                if "quarto" in text or "bedroom" in text or "bedrooms" in el_class:
                    bedrooms = normalize_int(text)
                elif "banheiro" in text or "bathroom" in text or "bathrooms" in el_class:
                    bathrooms = normalize_int(text)
                elif "vaga" in text or "parking" in text or "parking" in el_class:
                    parking_spots = normalize_int(text)
                elif "terreno" in text and "m" in text:
                    land_area_m2 = normalize_area(text)
                elif ("área" in text or "area" in text or "m²" in text or el_class == "area") and "terreno" not in text:
                    area_m2 = normalize_area(text)

            # Images: data-src first, then src
            images = []
            for img in card.find_all("img"):
                src = img.get("data-src") or img.get("src") or ""
                if src and not src.startswith("data:") and src not in images:
                    images.append(src)

            # City: default for this project
            city = "Dois Irmãos"

            return PropertyData(
                source_site=self.site_name,
                source_url=url,
                title=title,
                city=city,
                neighborhood=neighborhood,
                category=category,
                transaction_type=self.transaction_type,
                price=price,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                parking_spots=parking_spots,
                area_m2=area_m2,
                land_area_m2=land_area_m2,
                images=images,
            )
        except Exception:
            return None

    def _parse_page(self, soup: BeautifulSoup, base_url: str) -> list[PropertyData]:
        cards = soup.select(self.CARD_SELECTOR)
        results = []
        for card in cards:
            prop = self._parse_card(card, base_url)
            if prop:
                results.append(prop)
        return results

    def _get_next_page_url(self, soup: BeautifulSoup, current_url: str) -> str | None:
        el = soup.select_one(self.NEXT_PAGE_SELECTOR)
        if not el:
            return None
        href = el.get("href", "")
        if not href or href == "#":
            return None
        if href.startswith("http"):
            return href
        base = current_url.split("?")[0].split("#")[0]
        return base + href if href.startswith("?") else href

    async def scrape(self) -> list[PropertyData]:
        results = []
        current_url = self.url
        page_num = 0
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await ctx.new_page()
            while current_url and page_num < self.max_pages:
                try:
                    await page.goto(current_url, wait_until="networkidle", timeout=30000)
                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    page_results = self._parse_page(soup, current_url)
                    if not page_results:
                        break
                    results.extend(page_results)
                    current_url = self._get_next_page_url(soup, current_url)
                    page_num += 1
                    if current_url:
                        await asyncio.sleep(self.delay_seconds)
                except Exception:
                    break
            await browser.close()
        return results
```

- [ ] **Step 6: Create `scrapers/platforms/vista.py`**

Vista Soft uses different CSS classes but same structure. Copy `kenlo.py` and override selectors:

```python
from scrapers.platforms.kenlo import KenloScraper


class VistaScraper(KenloScraper):
    """Scraper for sites running on Vista Soft platform."""
    CARD_SELECTOR = ".listagem-imovel, .card-imovel, [class*='listing-item']"
    NEXT_PAGE_SELECTOR = "a.proximo, a[title='Próxima página'], .paginacao a.ativo + a"
```

- [ ] **Step 7: Create `scrapers/platforms/jetimob.py`**

```python
from scrapers.platforms.kenlo import KenloScraper


class JetimobScraper(KenloScraper):
    """Scraper for sites running on Jetimob platform."""
    CARD_SELECTOR = ".imovel-item, .property-item, [data-imovel-id]"
    NEXT_PAGE_SELECTOR = "a.page-link[aria-label='Next'], .pagination li:last-child a"
```

- [ ] **Step 8: Create `scrapers/platforms/tecimob.py`**

```python
from scrapers.platforms.kenlo import KenloScraper


class TecimobScraper(KenloScraper):
    """Scraper for sites running on Tecimob platform."""
    CARD_SELECTOR = ".item-imovel, .resultado-busca .imovel, [class*='resultado-imovel']"
    NEXT_PAGE_SELECTOR = "a.proxima-pagina, .paginacao .next"
```

- [ ] **Step 9: Install BeautifulSoup**

```bash
pip install beautifulsoup4 lxml
```

Add to `requirements.txt`:
```
beautifulsoup4==4.12.3
lxml==5.2.2
```

- [ ] **Step 10: Run tests**

```bash
pytest tests/scrapers/test_platforms.py -v
```
Expected: 5 PASSED

- [ ] **Step 11: Commit**

```bash
git add scrapers/platforms/ tests/scrapers/fixtures/ tests/scrapers/test_platforms.py requirements.txt
git commit -m "feat: platform scrapers — Kenlo, Vista, Jetimob, Tecimob"
```

---

### Task 7: Registry and sites.yaml

**Files:**
- Create: `scrapers/registry.py`
- Create: `scrapers/sites/__init__.py`
- Modify: `config/sites.yaml`

- [ ] **Step 1: Create `scrapers/registry.py`**

```python
from scrapers.base import BaseScraper
from scrapers.platforms.kenlo import KenloScraper
from scrapers.platforms.vista import VistaScraper
from scrapers.platforms.jetimob import JetimobScraper
from scrapers.platforms.tecimob import TecimobScraper

PLATFORM_MAP: dict[str, type[BaseScraper]] = {
    "kenlo": KenloScraper,
    "vista": VistaScraper,
    "jetimob": JetimobScraper,
    "tecimob": TecimobScraper,
}


def get_scraper(site: dict) -> BaseScraper:
    """
    site dict keys: name, url, platform, transaction_type,
                    max_pages (optional), delay_seconds (optional)
    """
    platform = site.get("platform", "kenlo")
    cls = PLATFORM_MAP.get(platform, KenloScraper)
    return cls(
        site_name=site["name"],
        url=site["url"],
        transaction_type=site["transaction_type"],
        max_pages=site.get("max_pages", 30),
        delay_seconds=site.get("delay_seconds", 2.0),
    )
```

- [ ] **Step 2: Port `sites.yaml` from the old project**

Copy `C:\Users\marlo\Downloads\dev\Imoveis_DI\config\sites.yaml` to `config/sites.yaml`.

Then update the format to add `platform` field to each entry. Example:
```yaml
sites:
  - name: dois_irmaos
    url: https://www.doisirmaos.com.br/busca-de-imoveis/?finalidade=aluguel
    platform: kenlo
    transaction_type: aluguel
    active: true
    max_pages: 20

  - name: becker
    url: https://www.beckerimoveis.com.br/imoveis/aluguel
    platform: vista
    transaction_type: aluguel
    active: true
```

Identify which platform each site uses by checking the old scraper file for each site and mapping to the closest platform.

- [ ] **Step 3: Create `scrapers/sites/__init__.py`** (empty, for site-specific overrides)

- [ ] **Step 4: Commit**

```bash
git add scrapers/registry.py scrapers/sites/ config/sites.yaml
git commit -m "feat: scraper registry and sites.yaml with platform declarations"
```

---

### Task 8: Scraping Runner, Change Detection, and APScheduler

**Files:**
- Create: `scrapers/runner.py`
- Modify: `routers/scraping.py`
- Modify: `app.py`
- Create: `tests/test_scraping_runner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_scraping_runner.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch
from scrapers.runner import detect_changes, build_run_log_line
from scrapers.base import PropertyData
from storage.database import init_db, get_connection

@pytest.fixture
def conn():
    c = get_connection(":memory:")
    init_db(":memory:", conn=c)
    return c

def make_property(site="test", url="http://x.com/1", price=2000.0):
    return PropertyData(
        source_site=site, source_url=url, title="Casa Teste",
        city="Dois Irmãos", neighborhood="Centro", category="Casa",
        transaction_type="aluguel", price=price,
    )

def test_detect_new_property(conn):
    prop = make_property()
    flag, changes = detect_changes(conn, prop, run_id="run1")
    assert flag == "new"
    assert changes == {}

def test_detect_unchanged_property(conn):
    prop = make_property()
    detect_changes(conn, prop, run_id="run1")
    # Second run — same price
    flag, changes = detect_changes(conn, prop, run_id="run2")
    assert flag is None  # no change

def test_detect_price_update(conn):
    prop = make_property(price=2000.0)
    detect_changes(conn, prop, run_id="run1")
    prop2 = make_property(price=2200.0)
    flag, changes = detect_changes(conn, prop2, run_id="run2")
    assert flag == "updated"
    assert changes["price"]["old"] == 2000.0
    assert changes["price"]["new"] == 2200.0

def test_build_log_line():
    line = build_run_log_line("becker", found=18, new=0, updated=0, errors=0)
    assert "becker" in line
    assert "18" in line
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_scraping_runner.py -v
```
Expected: FAIL

- [ ] **Step 3: Create `scrapers/runner.py`**

```python
import asyncio
import json
import hashlib
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import yaml
from scrapers.base import BaseScraper, PropertyData
from scrapers.registry import get_scraper
from storage.database import get_connection

# Global asyncio Queue for SSE streaming
_event_queue: asyncio.Queue | None = None
_running: bool = False


def get_event_queue() -> asyncio.Queue:
    global _event_queue
    if _event_queue is None:
        _event_queue = asyncio.Queue()
    return _event_queue


def is_running() -> bool:
    return _running


def detect_changes(conn, prop: PropertyData, run_id: str) -> tuple[str | None, dict]:
    """
    Compare property against last historico snapshot.
    Returns (change_flag, changes_dict).
    change_flag: 'new' | 'updated' | None
    """
    last = conn.execute(
        "SELECT price, area_m2, land_area_m2, bedrooms, neighborhood, is_active FROM historico WHERE imovel_id=? ORDER BY scraped_at DESC LIMIT 1",
        [prop.id]
    ).fetchone()

    if last is None:
        return "new", {}

    changes = {}
    for field, new_val in [("price", prop.price), ("area_m2", prop.area_m2),
                            ("bedrooms", prop.bedrooms), ("neighborhood", prop.neighborhood)]:
        old_val = last[field]
        if old_val != new_val and not (old_val is None and new_val is None):
            changes[field] = {"old": old_val, "new": new_val}

    return ("updated" if changes else None), changes


def _save_property(conn, prop: PropertyData, run_id: str, change_flag: str, changes: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO imoveis (id, transaction_type, source_site, source_url, title, city,
            neighborhood, category, bedrooms, bathrooms, parking_spots, area_m2, land_area_m2,
            price, first_seen, last_seen, is_active)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
        ON CONFLICT(id) DO UPDATE SET
            last_seen=excluded.last_seen, price=excluded.price, title=excluded.title,
            neighborhood=excluded.neighborhood, bedrooms=excluded.bedrooms,
            bathrooms=excluded.bathrooms, parking_spots=excluded.parking_spots,
            area_m2=excluded.area_m2, land_area_m2=excluded.land_area_m2, is_active=1
    """, [prop.id, prop.transaction_type, prop.source_site, prop.source_url, prop.title,
          prop.city, prop.neighborhood, prop.category, prop.bedrooms, prop.bathrooms,
          prop.parking_spots, prop.area_m2, prop.land_area_m2, prop.price, now, now])

    if change_flag:
        conn.execute("""
            INSERT INTO historico (imovel_id, run_id, scraped_at, price, area_m2, land_area_m2,
                bedrooms, neighborhood, is_active, change_flag, changes_summary)
            VALUES (?,?,?,?,?,?,?,?,1,?,?)
        """, [prop.id, run_id, now, prop.price, prop.area_m2, prop.land_area_m2,
              prop.bedrooms, prop.neighborhood, change_flag, json.dumps(changes)])

    # Images: replace all images for this property
    conn.execute("DELETE FROM imovel_imagens WHERE imovel_id=?", [prop.id])
    for i, url in enumerate(prop.images):
        conn.execute("INSERT INTO imovel_imagens (imovel_id, url, position) VALUES (?,?,?)",
                     [prop.id, url, i])

    conn.commit()


def build_run_log_line(site_name: str, found: int, new: int, updated: int, errors: int) -> str:
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    parts = [f"[{now}] {site_name} → {found} encontrados"]
    if new or updated:
        parts.append(f"{new} novos, {updated} atualizados")
    else:
        parts.append("0 mudanças")
    if errors:
        parts.append(f"{errors} erros")
    return ", ".join(parts[:1] + [", ".join(parts[1:])])


async def run_scraping(sites_config: list[dict] | None = None) -> None:
    global _running
    if _running:
        return
    _running = True
    queue = get_event_queue()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    start = datetime.now(timezone.utc)
    conn = get_connection()

    # Load sites
    if sites_config is None:
        with open("config/sites.yaml") as f:
            data = yaml.safe_load(f)
        sites_config = [s for s in data.get("sites", []) if s.get("active", True)]

    conn.execute(
        "INSERT INTO runs (run_id, run_date, sites_scraped, status) VALUES (?,?,?,'running')",
        [run_id, start.isoformat(), json.dumps([s["name"] for s in sites_config])]
    )
    conn.commit()

    total_new = total_updated = total_found = 0
    log_lines = []

    for site in sites_config:
        site_new = site_updated = 0
        try:
            scraper = get_scraper(site)
            properties = await scraper.scrape()
            total_found += len(properties)
            for prop in properties:
                flag, changes = detect_changes(conn, prop, run_id)
                if flag == "new":
                    site_new += 1
                    total_new += 1
                elif flag == "updated":
                    site_updated += 1
                    total_updated += 1
                _save_property(conn, prop, run_id, flag, changes)
            line = build_run_log_line(site["name"], len(properties), site_new, site_updated, 0)
        except Exception as e:
            line = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {site['name']} → ERRO: {str(e)[:80]}"

        log_lines.append(line)
        await queue.put(line)

    duration = (datetime.now(timezone.utc) - start).total_seconds()
    summary = (f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] CONCLUÍDO → "
               f"{len(sites_config)} sites, {total_found} imóveis, "
               f"{total_new} novos, {total_updated} atualizados ({duration:.0f}s)")
    log_lines.append(summary)
    await queue.put(summary)
    await queue.put("__DONE__")

    conn.execute("""
        UPDATE runs SET status='completed', total_found=?, new_count=?, updated_count=?,
            duration_seconds=?, log=? WHERE run_id=?
    """, [total_found, total_new, total_updated, duration, "\n".join(log_lines), run_id])
    conn.commit()
    conn.close()
    _running = False
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_scraping_runner.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Update `routers/scraping.py` with full SSE implementation**

```python
import asyncio
import json
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from routers.auth import require_login
from scrapers.runner import run_scraping, get_event_queue, is_running

router = APIRouter()


@router.post("/scraping/trigger", response_class=HTMLResponse)
async def trigger_scraping(request: Request, background_tasks: BackgroundTasks):
    if not require_login(request):
        return HTMLResponse(status_code=401)
    if is_running():
        return HTMLResponse(content='<p class="text-yellow-400">Scraping já em execução.</p>')
    background_tasks.add_task(run_scraping)
    return HTMLResponse(content="""
        <div hx-ext="sse" sse-connect="/scraping/stream" sse-swap="message"
             hx-target="this" hx-swap="beforeend"
             class="font-mono text-xs text-green-400">
          <p>Iniciando scraping...</p>
        </div>
    """)


@router.get("/scraping/stream")
async def scraping_stream(request: Request):
    if not require_login(request):
        return HTMLResponse(status_code=401)

    queue = get_event_queue()

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                if msg == "__DONE__":
                    yield {"data": "✓ Concluído"}
                    break
                yield {"data": f"<p>{msg}</p>"}
            except asyncio.TimeoutError:
                yield {"data": ""}  # keepalive

    return EventSourceResponse(event_generator())
```

Add `sse-starlette` to `requirements.txt`:
```
sse-starlette==2.1.3
```

```bash
pip install sse-starlette
```

- [ ] **Step 6: Add APScheduler to `app.py`**

```python
# Add to imports in app.py:
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from storage.database import get_workspace

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(WORKSPACE)
    # Start APScheduler with schedule from workspace config
    conn = get_connection()
    ws = get_workspace(conn)
    conn.close()
    schedule = ws["scraping_schedule"] if ws and ws["scraping_schedule"] else "0 7 * * *"
    parts = schedule.split()
    if len(parts) == 5:
        scheduler.add_job(
            run_scraping, CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4]
            ), id="scraping", replace_existing=True
        )
    scheduler.start()
    yield
    scheduler.shutdown()
```

Import `run_scraping` at the top of `app.py`:
```python
from scrapers.runner import run_scraping
```

- [ ] **Step 7: Run all tests**

```bash
pytest tests/ -v
```
Expected: all PASSED

- [ ] **Step 8: Commit**

```bash
git add scrapers/runner.py routers/scraping.py app.py requirements.txt tests/test_scraping_runner.py
git commit -m "feat: scraping runner, change detection, APScheduler, SSE live log"
```

---

## Phase 3: Validation and Deployment Prep

---

### Task 9: End-to-End Smoke Test

**Files:**
- Create: `tests/test_imoveis.py`
- Create: `tests/test_review_banner.py`

- [ ] **Step 1: Write integration tests**

Create `tests/test_imoveis.py`:
```python
import pytest, bcrypt, os
from fastapi.testclient import TestClient
from storage.database import init_db, get_connection, create_user

@pytest.fixture
def client():
    os.environ["WORKSPACE"] = ":memory:"
    os.environ["SESSION_SECRET"] = "test"
    conn = get_connection(":memory:")
    init_db(":memory:", conn=conn)
    pw = bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode()
    create_user(conn, "u", pw)
    from app import app
    c = TestClient(app)
    c.post("/login", data={"username": "u", "password": "pw"})
    return c

def test_aluguel_page_loads(client):
    r = client.get("/aluguel")
    assert r.status_code == 200

def test_compra_page_loads(client):
    r = client.get("/compra")
    assert r.status_code == 200

def test_partial_imoveis_empty(client):
    r = client.get("/partials/imoveis?tipo=aluguel")
    assert r.status_code == 200
    assert "Nenhum imóvel" in r.text

def test_historico_page_loads(client):
    r = client.get("/historico")
    assert r.status_code == 200

def test_configuracoes_page_loads(client):
    r = client.get("/configuracoes")
    assert r.status_code == 200
```

Create `tests/test_review_banner.py`:
```python
import pytest, os, bcrypt
from storage.database import init_db, get_connection, create_user, get_changes_since_review, mark_reviewed

@pytest.fixture
def conn():
    c = get_connection(":memory:")
    init_db(":memory:", conn=c)
    return c

def test_no_changes_returns_empty_dict(conn):
    result = get_changes_since_review(conn, "aluguel")
    assert result == {}

def test_mark_reviewed_updates_timestamp(conn):
    mark_reviewed(conn, "aluguel")
    ws = conn.execute("SELECT last_reviewed_aluguel_at FROM workspace WHERE id=1").fetchone()
    assert ws[0] is not None

def test_compra_reviewed_independent(conn):
    mark_reviewed(conn, "compra")
    ws = conn.execute("SELECT last_reviewed_aluguel_at, last_reviewed_compra_at FROM workspace WHERE id=1").fetchone()
    assert ws["last_reviewed_aluguel_at"] is None
    assert ws["last_reviewed_compra_at"] is not None
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/ -v --tb=short
```
Expected: all PASSED

- [ ] **Step 3: Manual smoke test**

```bash
python manage.py init-db
python manage.py create-user
# username: admin, password: admin123
uvicorn app:app --reload
```

- Open `http://localhost:8000` → redirects to `/login`
- Login with admin/admin123 → lands on `/aluguel`
- Click each nav tab — all load without errors
- Go to `/configuracoes` → click "Executar agora" → SSE log appears
- Go to `/historico` → empty table initially, fills after scraping

- [ ] **Step 4: Commit**

```bash
git add tests/test_imoveis.py tests/test_review_banner.py
git commit -m "test: integration tests for property listing and review banner"
```

---

### Task 10: Deployment Configuration

**Files:**
- Create: `.gitignore`
- Create: `Procfile` (optional, for process managers)
- Create: `docs/deploy.md`

- [ ] **Step 1: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
workspaces/*.db
.playwright/
```

- [ ] **Step 2: Create deployment instructions**

Create `docs/deploy.md`:
```markdown
# Deploy — Oracle Cloud ARM

## 1. Server setup

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv git
```

## 2. Clone and install

```bash
git clone <repo> /opt/imoveis-di
cd /opt/imoveis-di
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
playwright install-deps chromium
```

## 3. Configure environment

```bash
cp .env.example .env
# Edit .env:
# WORKSPACE=workspaces/imoveis.db
# SESSION_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
```

## 4. Initialize and create user

```bash
python manage.py init-db
python manage.py create-user
```

## 5. Run with systemd

Create `/etc/systemd/system/imoveis-di.service`:
```ini
[Unit]
Description=Imoveis DI
After=network.target

[Service]
WorkingDirectory=/opt/imoveis-di
EnvironmentFile=/opt/imoveis-di/.env
ExecStart=/opt/imoveis-di/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=on-failure
User=ubuntu

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable imoveis-di
sudo systemctl start imoveis-di
```
```

- [ ] **Step 3: Final test run**

```bash
pytest tests/ -v
```
Expected: all PASSED

- [ ] **Step 4: Final commit**

```bash
git add .gitignore docs/deploy.md
git commit -m "chore: gitignore and deployment documentation"
```

---

## Self-Review

### Spec coverage check

| Spec requirement | Task |
|---|---|
| FastAPI + HTMX + Jinja2 + Tailwind | Task 1, 4 |
| SQLite with 6 tables | Task 2 |
| Auth: login/logout/session | Task 3 |
| manage.py CLI (init-db, create-user) | Task 3 |
| Aluguel/Compra listing pages | Task 4 |
| Filterable property table (HTMX partials) | Task 4 |
| Property detail panel with carousel | Task 4 |
| Status update + activity_log | Task 4 |
| Review banner per category | Task 4 |
| Edit modal + geocoding (Nominatim + Google Maps URL) | Task 4 |
| Map tab (Folium) | Task 4 |
| History tab | Task 4 |
| Settings/configuracoes tab | Task 4 |
| PropertyData + BaseScraper | Task 5 |
| Platform scrapers (Kenlo, Vista, Jetimob, Tecimob) | Task 6 |
| Registry + sites.yaml platform field | Task 7 |
| Runner with change detection | Task 8 |
| APScheduler integration | Task 8 |
| SSE live log | Task 8 |
| Multi-tenancy (workspace per SQLite file) | Task 2 (schema), Task 10 (deploy) |
| Image carousel (multiple images) | Task 4 (template), Task 6 (scraper) |
| Geocoding via Google Maps URL | Task 4 |
| "Last reviewed" per category banner | Task 2 (query), Task 4 (UI) |
| Workspace schedule config | Task 4 (configuracoes), Task 8 (APScheduler) |
| Deployment docs | Task 10 |

All spec requirements covered. ✓
