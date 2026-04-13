from storage.database import init_db, get_connection


def test_schema_creates_all_tables():
    conn = get_connection(":memory:")
    init_db(":memory:", conn=conn)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall() if row[0] != 'sqlite_sequence'}
    assert tables == {"imoveis", "imovel_imagens", "historico", "runs", "workspace", "users", "activity_log"}


def test_workspace_row_initialized():
    conn = get_connection(":memory:")
    init_db(":memory:", conn=conn)
    row = conn.execute("SELECT id FROM workspace WHERE id = 1").fetchone()
    assert row is not None


def test_get_imoveis_empty():
    conn = get_connection(":memory:")
    init_db(":memory:", conn=conn)
    from storage.database import get_imoveis
    result = get_imoveis(conn, "aluguel")
    assert result == []


def test_get_distinct_values_empty():
    conn = get_connection(":memory:")
    init_db(":memory:", conn=conn)
    from storage.database import get_distinct_values
    result = get_distinct_values(conn, "aluguel", "source_site")
    assert result == []


def test_mark_reviewed_updates_timestamp():
    conn = get_connection(":memory:")
    init_db(":memory:", conn=conn)
    from storage.database import mark_reviewed
    mark_reviewed(conn, "aluguel")
    row = conn.execute("SELECT last_reviewed_aluguel_at FROM workspace WHERE id=1").fetchone()
    assert row[0] is not None


def test_changes_since_review_empty():
    conn = get_connection(":memory:")
    init_db(":memory:", conn=conn)
    from storage.database import get_changes_since_review
    result = get_changes_since_review(conn, "aluguel")
    assert result == {}
