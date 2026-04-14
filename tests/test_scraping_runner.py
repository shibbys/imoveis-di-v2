import pytest
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
        source_site=site,
        source_url=url,
        title="Casa Teste",
        city="Dois Irmãos",
        neighborhood="Centro",
        category="Casa",
        transaction_type="aluguel",
        price=price,
    )


def test_detect_new_property(conn):
    prop = make_property()
    flag, changes = detect_changes(conn, prop)
    assert flag == "new"
    assert changes == {}


def test_detect_unchanged_property(conn):
    prop = make_property()
    # First detection → new
    detect_changes(conn, prop)
    # Insert into historico to simulate a previous run
    conn.execute(
        "INSERT INTO historico (imovel_id, run_id, scraped_at, price, area_m2, land_area_m2, bedrooms, neighborhood, is_active, change_flag, changes_summary) "
        "VALUES (?,?,?,?,?,?,?,?,1,'new','{}') ",
        [prop.id, "run_old", "2024-01-01T00:00:00", prop.price, prop.area_m2, prop.land_area_m2, prop.bedrooms, prop.neighborhood]
    )
    conn.commit()
    # Second detection with same data → None (no change)
    flag, changes = detect_changes(conn, prop)
    assert flag is None
    assert changes == {}


def test_detect_price_update(conn):
    prop_old = make_property(price=2000.0)
    # Insert previous snapshot
    conn.execute(
        "INSERT INTO historico (imovel_id, run_id, scraped_at, price, area_m2, land_area_m2, bedrooms, neighborhood, is_active, change_flag, changes_summary) "
        "VALUES (?,?,?,?,?,?,?,?,1,'new','{}') ",
        [prop_old.id, "run_old", "2024-01-01T00:00:00", 2000.0, None, None, None, "Centro"]
    )
    conn.commit()
    # Now detect with updated price
    prop_new = make_property(price=2200.0)
    flag, changes = detect_changes(conn, prop_new)
    assert flag == "updated"
    assert changes["price"]["old"] == 2000.0
    assert changes["price"]["new"] == 2200.0


def test_build_log_line_with_changes():
    line = build_run_log_line("becker", found=18, new=2, updated=1, error=None)
    assert "becker" in line
    assert "18" in line
    assert "2" in line


def test_build_log_line_no_changes():
    line = build_run_log_line("becker", found=18, new=0, updated=0, error=None)
    assert "becker" in line
    assert "0 mudancas" in line


def test_build_log_line_error():
    line = build_run_log_line("becker", found=0, new=0, updated=0, error="timeout")
    assert "becker" in line
    assert "ERRO" in line
    assert "timeout" in line


def test_removed_property_detection(db):
    """Properties active in DB but absent from scrape results get marked removed."""
    from scrapers.runner import _save_property
    from scrapers.base import PropertyData
    # Insert a property
    prop = PropertyData(
        source_site="test_site", source_url="http://x.com/1",
        title="Casa", city="DI", neighborhood="N", category="Casa",
        transaction_type="aluguel", price=1000.0,
        bedrooms=2, bathrooms=1, parking_spots=0,
        area_m2=80.0, land_area_m2=None, images=[]
    )
    _save_property(db, prop, "run1", "new", {})
    db.commit()

    # Simulate a new run for the same site with NO properties
    scraped_ids = set()
    active_rows = db.execute(
        "SELECT id FROM imoveis WHERE source_site=? AND is_active=1",
        ["test_site"]
    ).fetchall()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    removed = 0
    for row in active_rows:
        if row["id"] not in scraped_ids:
            db.execute("UPDATE imoveis SET is_active=0, last_seen=? WHERE id=?", [now, row["id"]])
            db.execute("""
                INSERT INTO historico (imovel_id, run_id, scraped_at, price, area_m2, land_area_m2,
                    bedrooms, neighborhood, is_active, change_flag, changes_summary)
                SELECT id, 'run2', ?, price, area_m2, land_area_m2,
                    bedrooms, neighborhood, 0, 'removed', '{}'
                FROM imoveis WHERE id=?
            """, [now, row["id"]])
            removed += 1
    db.commit()

    assert removed == 1
    row = db.execute("SELECT is_active FROM imoveis WHERE id=?", [prop.id]).fetchone()
    assert row["is_active"] == 0
    hist = db.execute(
        "SELECT change_flag FROM historico WHERE imovel_id=? AND run_id='run2'",
        [prop.id]
    ).fetchone()
    assert hist["change_flag"] == "removed"


def test_build_log_line_with_removed():
    from scrapers.runner import build_run_log_line
    line = build_run_log_line("site", found=10, new=0, updated=0, removed=2)
    assert "2 removidos" in line
