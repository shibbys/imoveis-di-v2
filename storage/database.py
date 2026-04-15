import sqlite3
import os
from typing import Optional

# Initial site seed — loaded into the DB on first init_db() call.
# After that the DB is the source of truth; URLs/active flags are editable via UI.
# platform is never user-editable, so it is always synced from here on init.
_SITES_SEED = [
    # ── Aluguel ────────────────────────────────────────────────────────────────
    dict(name="dois_irmaos",      platform="kenlo",     transaction_type="aluguel", max_pages=20,
         url="https://www.imobiliariadoisirmaos.com.br/imoveis/para-alugar"),
    dict(name="sao_miguel",       platform="voa",       transaction_type="aluguel",
         url="https://www.saomiguelimobiliaria.com.br/imoveis/para-locacao"),
    dict(name="becker",           platform="becker",    transaction_type="aluguel",
         url="https://www.empreendimentosbecker.com.br/Imoveis/Busca/1/0?carteira=L&tipo%5B%5D=3&tipo%5B%5D=9&tipo%5B%5D=78&tipo%5B%5D=76&tipo%5B%5D=14&tipo%5B%5D=1&tipo%5B%5D=71&tipo%5B%5D=82&cidade=8&dormitorios=0&garagem=0&valor_l=0&valor_v=0&area=0&codigo="),
    dict(name="felippe_alfredo",  platform="jetimob",   transaction_type="aluguel",
         url='https://www.felippealfredoimobiliaria.com.br/alugar/apartamento?ordenacao=%22mais-recente%22&pagina=1&tipos=%22apartamento%2Ccasa%22&transacao=%22alugar%22'),
    dict(name="adriana",          platform="smartimob", transaction_type="aluguel",
         url="https://www.adrianacorretoradeimoveis.com.br/imoveis/tipo-apartamento,apartamento-terreo,casa,sobrado/cidade-dois-irmaos,morro-reuter/transacao-locacao/ordenacao-newest"),
    dict(name="investir",         platform="vista",     transaction_type="aluguel",
         url="https://www.investirimoveisdi.com.br/busca/alugar/cidade/todas/categoria/apartamento_casa-sobrado_terrenos/data/desc/1/"),
    dict(name="habbitar",         platform="jetimob",   transaction_type="aluguel",
         url="https://habbitar.com.br/alugar/imoveis?profile%5B0%5D=1&typeArea=total_area&floorComparision=equals&sort=-is_price_shown%2Cby_calculated_price&offset=1&limit=21"),
    dict(name="lis",              platform="lis",       transaction_type="aluguel",
         url="https://www.imobiliarialis.com.br/imoveis/para-alugar?ordenar=recentes"),
    dict(name="identita",         platform="imobibrasil", transaction_type="aluguel",
         url="https://www.identitaimoveis.com.br/imovel/locacao/todos/dois-irmaos"),
    dict(name="platano",          platform="smtximob",  transaction_type="aluguel",
         url="https://www.platanoimoveis.com.br/imoveis/cidade-dois-irmaos,morro-reuter/transacao-locacao"),
    dict(name="joel_blume",       platform="joelblume", transaction_type="aluguel",
         url="https://www.joelblumecorretor.com.br/imoveis/para-alugar/todos/dois-irmaos/"),
    dict(name="conecta_aluguel",  platform="conecta",   transaction_type="aluguel",
         url="https://www.conectaimoveisdi.com.br/imoveis/aluguel/dois-irmaos/-/-/-?filtros&pagination=1"),
    # ── Compra ─────────────────────────────────────────────────────────────────
    dict(name="dois_irmaos_compra",     platform="kenlo",     transaction_type="compra", max_pages=20,
         url="https://www.imobiliariadoisirmaos.com.br/imoveis/a-venda/casa/dois-irmaos?quartos=2+"),
    dict(name="sao_miguel_compra",      platform="voa",       transaction_type="compra",
         url="https://www.saomiguelimobiliaria.com.br/imoveis/?disponibilidade=a-venda&categoria=casa&cidade=dois-irmaos&bairro=&area-min=&area-max=&finalidade=Residencial&quartos=2&order=padrao"),
    dict(name="becker_compra",          platform="becker",    transaction_type="compra",
         url="https://www.empreendimentosbecker.com.br/Imoveis/Busca/1/0?carteira=V&tipo%5B%5D=1&tipo%5B%5D=71&cidade=8&dormitorios=0&garagem=0&valor_l=0&valor_v=0&area=0&codigo="),
    dict(name="felippe_alfredo_compra", platform="jetimob",   transaction_type="compra",
         url='https://www.felippealfredoimobiliaria.com.br/venda/rio-grande-do-sul/dois-irmaos/casa/com-mais-de-5-quartos?tipos=%22casa%22&quartos=%223%2C4%2C5%2C2%22&ordenacao=%22mais-recente%22&pagina=1&transacao=%22venda%22&endereco=%5B%7B%22label%22%3A%22Dois+Irm%C3%A3os+-+RS%22%2C%22valor%22%3A%7B%22cidade%22%3A7650%2C%22estado%22%3A23%7D%2C%22cidade%22%3A%22dois-irmaos%22%2C%22estado%22%3A%22rio-grande-do-sul%22%7D%5D'),
    dict(name="investir_compra",        platform="vista",     transaction_type="compra",
         url="https://www.investirimoveisdi.com.br/busca/comprar/cidade/todas/bairros/beira-rio-dois-irmaos_bela-vista-dois-irmaos_centro-dois-irmaos_floresta-dois-irmaos_industrial-dois-irmaos_moinho-velho-dois-irmaos_primavera-dois-irmaos_sao-joao-dois-irmaos_sete-de-setembro-dois-irmaos_travessao-dois-irmaos_uniao-dois-irmaos_vale-direito-dois-irmaos_vale-esquerdo-dois-irmaos_vale-verde-dois-irmaos_centro-morro-reuter_planalto-morro-reuter/categoria/casa-sobrado/quartos/2/1/"),
    dict(name="habbitar_compra",        platform="jetimob",   transaction_type="compra",
         url="https://habbitar.com.br/comprar/casa/dois-irmaos-rs?by_type_slug=casa&typeArea=built_area&floorComparision=equals&bedrooms=2&profile%5B0%5D=1&sort=-created_at%2Cid&offset=1&limit=100"),
    dict(name="lis_compra",             platform="lis",       transaction_type="compra",
         url="https://www.imobiliarialis.com.br/imoveis/a-venda/casa+chacara?quartos=2+&preco-de-venda=0~1500000"),
    dict(name="adriana_compra",         platform="smartimob", transaction_type="compra",
         url="https://www.adrianacorretoradeimoveis.com.br/imoveis/tipo-casa,sitio-chacara/cidade-dois-irmaos,morro-reuter/transacao-venda/preco-max-1500000/ordenacao-newest"),
    dict(name="identita_compra",        platform="imobibrasil", transaction_type="compra",
         url="https://www.identitaimoveis.com.br/imovel/venda/casa-sobrado/dois-irmaos/?&dormitorios=22&suites=&banheiros=&vagas=&vmi=&vma=venda0&areaMinima=venda1&areaMaxima=venda2&pag=1"),
    dict(name="platano_compra",         platform="smtximob",  transaction_type="compra",
         url="https://www.platanoimoveis.com.br/imoveis/cidade-dois-irmaos/tipo-casa,casa-em-condominio,chacara-sitio/transacao-venda"),
    dict(name="joel_blume_compra",      platform="joelblume", transaction_type="compra",
         url="https://www.joelblumecorretor.com.br/imoveis/?disponibilidade=a-venda&categoria=casa&cidade=dois-irmaos&bairro=&area-min=&area-max=&finalidade=&quartos=3&order=padr%C3%A3o"),
    dict(name="conecta_compra",         platform="conecta",   transaction_type="compra",
         url="https://www.conectaimoveisdi.com.br/imoveis/venda/dois-irmaos/-/-/casa?filtros&min=0&max=4600000&ordem=desc-inclusao&pagination=1"),
    dict(name="dmk_compra",             platform="imoview",   transaction_type="compra",
         url="https://www.dmkimoveis.com.br/venda/casa+chacara/dois-irmaos/?&pagina=1"),
    dict(name="dapper_compra",          platform="dapper",    transaction_type="compra",
         url="https://www.dapperimoveis.com.br/imoveis/vendas#tipo_negociacao=2&tipo_imovel=54,62,59&cidade=Dois%20Irm%C3%A3os&valor_ate=1500000&currentPage=1&ordem=2"),
    dict(name="munique_compra",         platform="munique",   transaction_type="compra",
         url="https://www.muniqueimoveis.com.br/busca?finalidade=venda&categorias%5B%5D=1&categorias%5B%5D=20&categorias%5B%5D=26&cidades%5B%5D=73&maxPreco=1500000"),
    dict(name="postai_compra",          platform="tecimob",   transaction_type="compra",
         url="https://www.postaiimoveis.com.br/imoveis/tipo=casa-em-condominio,casas-e-sobrados&transacao=vendas&termo=Dois%20Irm%C3%A3os"),
    dict(name="confianca_compra",       platform="tecimob",   transaction_type="compra",
         url="https://confiancadimoveis.com.br/imoveis/tipo=casas-e-sobrados%26transacao=venda%26cidade=10-dois-irmos%26valor_maximo=1500000.00/1/sort=menor-valor"),
    dict(name="confianca2_compra",      platform="tecimob",   transaction_type="compra",
         url="https://confiancadimoveis.com.br/imoveis/tipo=chacaras-fazendas-e-sitios%26transacao=venda%26cidade=10-dois-irmos%26valor_maximo=1500000/1/sort=menor-valor"),
    dict(name="larissa_compra",         platform="conecta",   transaction_type="compra",
         url="https://www.larissadillimoveis.com.br/imoveis/venda/dois-irmaos/-/-/casa"),
    dict(name="conecta_compra_morro_reuter", platform="conecta", transaction_type="compra",
         url="https://www.conectaimoveisdi.com.br/imoveis/venda/morro-reuter/-/-/casa?filtros&min=0&max=4600000&ordem=desc-inclusao&pagination=1"),
]

_DB_PATH: str = ""

# When _DB_PATH is ":memory:", we keep a single canonical in-memory connection
# alive.  get_connection(":memory:") always returns this same connection wrapped
# in a proxy that makes .close() a no-op, so callers (e.g. test fixtures)
# cannot destroy the shared database by closing their handle.
_MEMORY_CONN: Optional[sqlite3.Connection] = None


class _NoCloseProxy:
    """Thin proxy around sqlite3.Connection that silences .close() calls.

    All attribute access is forwarded to the underlying connection, which means
    callers can use it anywhere a sqlite3.Connection is expected (row_factory,
    execute, executescript, commit, etc.).  The only difference is that
    .close() is a no-op so the shared in-memory database is not destroyed when
    individual callers are done with their handle.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def close(self) -> None:  # intentional no-op
        pass

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    # sqlite3.Connection.row_factory is a data descriptor – proxy it explicitly
    @property
    def row_factory(self):
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._conn.row_factory = value


def _get_or_create_memory_conn() -> sqlite3.Connection:
    global _MEMORY_CONN
    if _MEMORY_CONN is None:
        _MEMORY_CONN = sqlite3.connect(":memory:", check_same_thread=False)
        _MEMORY_CONN.row_factory = sqlite3.Row
        _MEMORY_CONN.execute("PRAGMA foreign_keys=ON")
    return _MEMORY_CONN


def get_connection(path: Optional[str] = None) -> sqlite3.Connection:
    target = path or _DB_PATH
    if target == ":memory:":
        # Return a proxy that forwards everything to the shared connection but
        # silences .close() calls so the in-memory DB survives between setup
        # and the actual test requests.
        return _NoCloseProxy(_get_or_create_memory_conn())  # type: ignore[return-value]
    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: str, conn: Optional[sqlite3.Connection] = None) -> None:
    global _DB_PATH
    _DB_PATH = path
    if path == ":memory:":
        # Always use the canonical shared in-memory connection.
        # get_connection(":memory:") returns _MEMORY_CONN, so when the caller
        # passes conn=get_connection(":memory:"), conn IS _MEMORY_CONN.
        c = _get_or_create_memory_conn()
        # Drop all existing tables so each init_db call starts from a clean
        # slate (test isolation).
        c.execute("PRAGMA foreign_keys=OFF")
        for tbl in ("activity_log", "users", "workspace", "runs",
                    "historico", "imovel_imagens", "imoveis", "sites"):
            c.execute(f"DROP TABLE IF EXISTS {tbl}")
        c.commit()
        c.execute("PRAGMA foreign_keys=ON")
    else:
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
        c = conn if conn is not None else get_connection(path)
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
            log              TEXT DEFAULT '',
            sites_log        TEXT
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

        CREATE TABLE IF NOT EXISTS sites (
            name             TEXT PRIMARY KEY,
            url              TEXT NOT NULL,
            platform         TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            active           INTEGER NOT NULL DEFAULT 1,
            max_pages        INTEGER
        );

        INSERT OR IGNORE INTO workspace (id) VALUES (1);
    """)
    c.commit()

    # Seed sites on first init (INSERT OR IGNORE skips existing rows).
    # platform is always synced from _SITES_SEED since it is not user-editable.
    for site in _SITES_SEED:
        c.execute(
            "INSERT OR IGNORE INTO sites (name, url, platform, transaction_type, active, max_pages) "
            "VALUES (?,?,?,?,1,?)",
            [site["name"], site["url"], site["platform"],
             site["transaction_type"], site.get("max_pages")],
        )
        c.execute(
            "UPDATE sites SET platform=? WHERE name=? AND platform != ?",
            [site["platform"], site["name"], site["platform"]],
        )
    c.commit()

    # Migrations: add columns that didn't exist in older DBs
    if path != ":memory:":
        existing_cols = {r[1] for r in c.execute("PRAGMA table_info(runs)")}
        if "sites_log" not in existing_cols:
            c.execute("ALTER TABLE runs ADD COLUMN sites_log TEXT")
            c.commit()


# ── Property queries ──────────────────────────────────────────────────────────

_SORT_COLUMNS = {"first_seen", "last_seen", "price", "neighborhood", "bedrooms", "category", "area_m2"}


def get_imoveis(conn: sqlite3.Connection, transaction_type: str,
                site: str = "", status: str = "", neighborhood: str = "",
                category: str = "",
                sort: str = "first_seen", sort_dir: str = "desc",
                include_inactive: bool = False,
                change_since: str = "",
                ) -> list:
    reviewed_col = f"last_reviewed_{transaction_type}_at"
    sql = f"""
        SELECT i.*,
          (SELECT COUNT(*) FROM imovel_imagens WHERE imovel_id = i.id) AS image_count,
          CASE WHEN i.is_active = 0 THEN 'removed'
               ELSE (SELECT change_flag FROM historico
                     WHERE imovel_id = i.id
                       AND scraped_at > COALESCE(
                         (SELECT {reviewed_col} FROM workspace WHERE id=1),
                         '1970-01-01'
                       )
                     ORDER BY scraped_at DESC LIMIT 1)
          END AS latest_change_flag
        FROM imoveis i
        WHERE i.transaction_type = ?
    """
    # When filtering for removed properties, inactive rows must be included
    if not include_inactive and change_since != "removed":
        sql += " AND i.is_active = 1"
    params: list = [transaction_type]
    if site:
        sql += " AND i.source_site = ?"
        params.append(site)
    if status:
        sql += " AND i.status = ?"
        params.append(status)
    if neighborhood:
        sql += " AND i.neighborhood = ?"
        params.append(neighborhood)
    if category:
        sql += " AND i.category = ?"
        params.append(category)
    col = sort if sort in _SORT_COLUMNS else "first_seen"
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
    if change_since:
        sql = f"SELECT * FROM ({sql}) sub WHERE sub.latest_change_flag = ?"
        params.append(change_since)
        sql += f" ORDER BY {col} {direction}"
    else:
        sql += f" ORDER BY i.{col} {direction}"
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
    if transaction_type not in ("aluguel", "compra"):
        raise ValueError(f"Invalid transaction_type: {transaction_type!r}")
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
    if transaction_type not in ("aluguel", "compra"):
        raise ValueError(f"Invalid transaction_type: {transaction_type!r}")
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


def get_last_run_per_base(conn: sqlite3.Connection, limit: int = 10) -> dict:
    """
    Return the most recent run result for each base imobiliária.
    Scans the last `limit` completed runs and picks the first occurrence per base.
    Result: {base: {base, display, aluguel, compra, ts, has_error, total_duration, run_date}}
    """
    import json as _json
    rows = conn.execute(
        "SELECT run_date, sites_log FROM runs "
        "WHERE status IN ('completed','partial') AND sites_log IS NOT NULL "
        "ORDER BY run_date DESC LIMIT ?",
        [limit],
    ).fetchall()
    per_base: dict = {}
    for row in rows:
        try:
            entries = _json.loads(row["sites_log"])
        except Exception:
            continue
        run_date = row["run_date"]
        for entry in entries:
            base = entry.get("base")
            if base and base not in per_base:
                per_base[base] = {**entry, "run_date": run_date}
    return per_base


def get_last_run(conn: sqlite3.Connection) -> Optional[dict]:
    """Return the most recent completed run with sites_log parsed from JSON."""
    import json as _json
    row = conn.execute(
        "SELECT * FROM runs WHERE status != 'running' ORDER BY run_date DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    try:
        result["sites_log"] = _json.loads(result["sites_log"]) if result.get("sites_log") else []
    except Exception:
        result["sites_log"] = []
    return result


# ── Sites ────────────────────────────────────────────────────────────────────

def get_sites(conn: sqlite3.Connection, active_only: bool = False) -> list:
    sql = "SELECT * FROM sites"
    if active_only:
        sql += " WHERE active=1"
    sql += " ORDER BY transaction_type, name"
    return conn.execute(sql).fetchall()


def update_site(conn: sqlite3.Connection, name: str, url: str, active: bool) -> None:
    conn.execute(
        "UPDATE sites SET url=?, active=? WHERE name=?",
        [url, 1 if active else 0, name]
    )


def get_site_counts(conn: sqlite3.Connection) -> dict:
    """Return {site_name: count} for active imoveis."""
    rows = conn.execute(
        "SELECT source_site, COUNT(*) as cnt FROM imoveis WHERE is_active=1 GROUP BY source_site"
    ).fetchall()
    return {r["source_site"]: r["cnt"] for r in rows}


# ── Users ─────────────────────────────────────────────────────────────────────

def get_user_by_username(conn: sqlite3.Connection, username: str):
    return conn.execute("SELECT * FROM users WHERE username=?", [username]).fetchone()


def create_user(conn: sqlite3.Connection, username: str, password_hash: str) -> None:
    from datetime import datetime, timezone
    conn.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
        [username, password_hash, datetime.now(timezone.utc).isoformat()]
    )
