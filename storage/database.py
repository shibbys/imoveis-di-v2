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
    if path != ":memory:" and os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
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
                ) -> list:
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


def get_imovel(conn: sqlite3.Connection, imovel_id: str):
    return conn.execute("SELECT * FROM imoveis WHERE id = ?", [imovel_id]).fetchone()


def get_imovel_images(conn: sqlite3.Connection, imovel_id: str) -> list:
    return conn.execute(
        "SELECT url FROM imovel_imagens WHERE imovel_id = ? ORDER BY position",
        [imovel_id]
    ).fetchall()


def update_imovel_status(conn: sqlite3.Connection, imovel_id: str, status: str) -> None:
    conn.execute("UPDATE imoveis SET status = ? WHERE id = ?", [status, imovel_id])


def update_imovel_fields(conn: sqlite3.Connection, imovel_id: str,
                          address: str, comments: str,
                          lat: Optional[float], lng: Optional[float]) -> None:
    conn.execute(
        "UPDATE imoveis SET address=?, comments=?, lat=?, lng=? WHERE id=?",
        [address, comments, lat, lng, imovel_id]
    )


def get_imovel_price_history(conn: sqlite3.Connection, imovel_id: str) -> list:
    return conn.execute(
        "SELECT scraped_at, price, change_flag FROM historico WHERE imovel_id = ? ORDER BY scraped_at",
        [imovel_id]
    ).fetchall()


def get_distinct_values(conn: sqlite3.Connection, transaction_type: str,
                         column: str) -> list:
    allowed = {"source_site", "status", "neighborhood", "category"}
    if column not in allowed:
        return []
    rows = conn.execute(
        f"SELECT DISTINCT {column} FROM imoveis WHERE transaction_type = ? "
        f"AND is_active = 1 AND {column} IS NOT NULL ORDER BY {column}",
        [transaction_type]
    ).fetchall()
    return [r[0] for r in rows]


# ── Activity log ──────────────────────────────────────────────────────────────

def log_activity(conn: sqlite3.Connection, imovel_id: str, user_id: int,
                  field: str, old_value: Optional[str], new_value: Optional[str]) -> None:
    from datetime import datetime, timezone
    conn.execute(
        "INSERT INTO activity_log (imovel_id, user_id, changed_at, field, old_value, new_value) "
        "VALUES (?,?,?,?,?,?)",
        [imovel_id, user_id, datetime.now(timezone.utc).isoformat(), field, old_value, new_value]
    )


def get_last_activity(conn: sqlite3.Connection, imovel_id: str):
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


# ── Workspace / runs ──────────────────────────────────────────────────────────

def get_workspace(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM workspace WHERE id=1").fetchone()


def update_schedule(conn: sqlite3.Connection, schedule: str) -> None:
    conn.execute("UPDATE workspace SET scraping_schedule=? WHERE id=1", [schedule])


def get_runs(conn: sqlite3.Connection, limit: int = 50) -> list:
    return conn.execute(
        "SELECT * FROM runs ORDER BY run_date DESC LIMIT ?", [limit]
    ).fetchall()


def get_run(conn: sqlite3.Connection, run_id: str):
    return conn.execute("SELECT * FROM runs WHERE run_id=?", [run_id]).fetchone()


# ── Users ─────────────────────────────────────────────────────────────────────

def get_user_by_username(conn: sqlite3.Connection, username: str):
    return conn.execute("SELECT * FROM users WHERE username=?", [username]).fetchone()


def create_user(conn: sqlite3.Connection, username: str, password_hash: str) -> None:
    from datetime import datetime, timezone
    conn.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
        [username, password_hash, datetime.now(timezone.utc).isoformat()]
    )
