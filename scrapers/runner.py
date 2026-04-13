import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import yaml
from scrapers.base import PropertyData
from scrapers.registry import get_scraper
from storage.database import get_connection

# Module-level state
_event_queue: Optional[asyncio.Queue] = None
_running: bool = False


def get_event_queue() -> asyncio.Queue:
    global _event_queue
    if _event_queue is None:
        _event_queue = asyncio.Queue()
    return _event_queue


def is_running() -> bool:
    return _running


def detect_changes(conn, prop: PropertyData) -> tuple:
    """
    Compare property against last historico snapshot.
    Returns (change_flag, changes_dict).
    change_flag: 'new' | 'updated' | None (unchanged)
    """
    last = conn.execute(
        "SELECT price, area_m2, land_area_m2, bedrooms, neighborhood, is_active "
        "FROM historico WHERE imovel_id=? ORDER BY scraped_at DESC LIMIT 1",
        [prop.id]
    ).fetchone()

    if last is None:
        return "new", {}

    changes = {}
    tracked = [
        ("price", prop.price),
        ("area_m2", prop.area_m2),
        ("bedrooms", prop.bedrooms),
        ("neighborhood", prop.neighborhood),
    ]
    for field_name, new_val in tracked:
        old_val = last[field_name]
        # Only flag as change if both values are not None and they differ
        if old_val is not None and new_val is not None and old_val != new_val:
            changes[field_name] = {"old": old_val, "new": new_val}

    return ("updated" if changes else None), changes


def _save_property(conn, prop: PropertyData, run_id: str,
                    change_flag: Optional[str], changes: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO imoveis (
            id, transaction_type, source_site, source_url, title, city,
            neighborhood, category, bedrooms, bathrooms, parking_spots,
            area_m2, land_area_m2, price, first_seen, last_seen, is_active
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
        ON CONFLICT(id) DO UPDATE SET
            last_seen = excluded.last_seen,
            price = excluded.price,
            title = excluded.title,
            neighborhood = excluded.neighborhood,
            bedrooms = excluded.bedrooms,
            bathrooms = excluded.bathrooms,
            parking_spots = excluded.parking_spots,
            area_m2 = excluded.area_m2,
            land_area_m2 = excluded.land_area_m2,
            is_active = 1
    """, [
        prop.id, prop.transaction_type, prop.source_site, prop.source_url,
        prop.title, prop.city, prop.neighborhood, prop.category,
        prop.bedrooms, prop.bathrooms, prop.parking_spots,
        prop.area_m2, prop.land_area_m2, prop.price,
        now, now
    ])

    if change_flag:
        conn.execute("""
            INSERT INTO historico (
                imovel_id, run_id, scraped_at, price, area_m2, land_area_m2,
                bedrooms, neighborhood, is_active, change_flag, changes_summary
            )
            VALUES (?,?,?,?,?,?,?,?,1,?,?)
        """, [
            prop.id, run_id, now,
            prop.price, prop.area_m2, prop.land_area_m2,
            prop.bedrooms, prop.neighborhood,
            change_flag, json.dumps(changes)
        ])

    # Replace images
    conn.execute("DELETE FROM imovel_imagens WHERE imovel_id=?", [prop.id])
    for i, url in enumerate(prop.images):
        conn.execute(
            "INSERT INTO imovel_imagens (imovel_id, url, position) VALUES (?,?,?)",
            [prop.id, url, i]
        )


def build_run_log_line(site_name: str, found: int, new: int,
                        updated: int, error: Optional[str]) -> str:
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    if error:
        return f"[{now}] {site_name} → ERRO: {error[:80]}"
    if new == 0 and updated == 0:
        return f"[{now}] {site_name} → {found} encontrados, 0 mudanças"
    parts = []
    if new:
        parts.append(f"{new} novos")
    if updated:
        parts.append(f"{updated} atualizados")
    return f"[{now}] {site_name} → {found} encontrados, {', '.join(parts)}"


async def run_scraping(sites_config: Optional[list] = None) -> None:
    """
    Main scraping orchestrator. Loads sites from sites.yaml if not provided.
    Streams log lines to the global event queue.
    Updates the runs table on start and completion.
    """
    global _running
    if _running:
        return
    _running = True

    queue = get_event_queue()
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        + "_" + uuid.uuid4().hex[:6]
    )
    start_time = datetime.now(timezone.utc)

    # Load sites
    if sites_config is None:
        with open("config/sites.yaml") as f:
            data = yaml.safe_load(f)
        sites_config = [s for s in data.get("sites", []) if s.get("active", True)]

    conn = get_connection()

    # Create run record
    conn.execute(
        "INSERT INTO runs (run_id, run_date, sites_scraped, status) VALUES (?,?,?,'running')",
        [run_id, start_time.isoformat(), json.dumps([s["name"] for s in sites_config])]
    )
    conn.commit()

    total_new = 0
    total_updated = 0
    total_found = 0
    log_lines = []

    try:
        for site in sites_config:
            site_new = 0
            site_updated = 0
            error_msg = None
            properties = []

            try:
                scraper = get_scraper(site)
                properties = await scraper.scrape()
                total_found += len(properties)

                for prop in properties:
                    flag, changes = detect_changes(conn, prop)
                    if flag == "new":
                        site_new += 1
                        total_new += 1
                    elif flag == "updated":
                        site_updated += 1
                        total_updated += 1
                    _save_property(conn, prop, run_id, flag, changes)

                conn.commit()

            except Exception as e:
                error_msg = str(e)[:80]

            line = build_run_log_line(
                site["name"],
                found=len(properties),
                new=site_new,
                updated=site_updated,
                error=error_msg,
            )
            log_lines.append(line)
            await queue.put(line)

    finally:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
        summary = (
            f"[{now_str}] CONCLUÍDO → {len(sites_config)} sites, "
            f"{total_found} imóveis, {total_new} novos, "
            f"{total_updated} atualizados ({duration:.0f}s)"
        )
        log_lines.append(summary)
        await queue.put(summary)
        await queue.put("__DONE__")

        conn.execute("""
            UPDATE runs SET
                status='completed', total_found=?, new_count=?,
                updated_count=?, duration_seconds=?, log=?
            WHERE run_id=?
        """, [total_found, total_new, total_updated, duration,
              "\n".join(log_lines), run_id])
        conn.commit()
        conn.close()
        _running = False
