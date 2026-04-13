import pytest, os
from storage.database import init_db, get_connection, get_changes_since_review, mark_reviewed


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
    conn.commit()
    ws = conn.execute("SELECT last_reviewed_aluguel_at FROM workspace WHERE id=1").fetchone()
    assert ws[0] is not None


def test_compra_reviewed_independent(conn):
    mark_reviewed(conn, "compra")
    conn.commit()
    ws = conn.execute("SELECT last_reviewed_aluguel_at, last_reviewed_compra_at FROM workspace WHERE id=1").fetchone()
    assert ws["last_reviewed_aluguel_at"] is None
    assert ws["last_reviewed_compra_at"] is not None
