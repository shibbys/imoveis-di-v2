import asyncio
import json
import re
import sys
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta

_BRT = timezone(timedelta(hours=-3))  # Brasília Time (UTC-3)
from typing import Callable, Optional

from scrapers.base import PropertyData
from scrapers.enrichment import enrich_properties_batch
from scrapers.registry import get_scraper
from storage.database import get_connection, get_sites

# Module-level state
_event_queue: Optional[asyncio.Queue] = None
_running: bool = False
_running_since: Optional[datetime] = None
_running_label: str = ""


def get_event_queue() -> asyncio.Queue:
    global _event_queue
    if _event_queue is None:
        _event_queue = asyncio.Queue()
    return _event_queue


def is_running() -> bool:
    return _running


def get_running_info() -> Optional[dict]:
    """Returns info about the current run, or None if not running."""
    if not _running or _running_since is None:
        return None
    elapsed = int((datetime.now(tz=_BRT) - _running_since).total_seconds())
    minutes, seconds = divmod(elapsed, 60)
    elapsed_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
    return {"label": _running_label, "elapsed": elapsed_str}


def _base_name(site_name: str) -> str:
    """Strip _aluguel / _compra suffix to get the imobiliária base name."""
    return re.sub(r"_(compra|aluguel)$", "", site_name)


def _site_display(base: str) -> str:
    return base.replace("_", " ").title()


def _sort_sites(sites: list) -> list:
    """Group sites by base imobiliária; aluguel before compra within each group."""
    tt_order = {"aluguel": 0, "compra": 1}
    return sorted(sites, key=lambda s: (
        _base_name(s["name"]),
        tt_order.get(s.get("transaction_type", ""), 2),
    ))


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
        if old_val is not None and new_val is not None and old_val != new_val:
            changes[field_name] = {"old": old_val, "new": new_val}

    return ("updated" if changes else None), changes


def _save_property(conn, prop: PropertyData, run_id: str,
                    change_flag: Optional[str], changes: dict) -> None:
    now = datetime.now(_BRT).isoformat()
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

    conn.execute("DELETE FROM imovel_imagens WHERE imovel_id=?", [prop.id])
    for i, url in enumerate(prop.images):
        conn.execute(
            "INSERT INTO imovel_imagens (imovel_id, url, position) VALUES (?,?,?)",
            [prop.id, url, i]
        )


def build_run_log_line(site_name: str, found: int, new: int,
                        updated: int, removed: int = 0,
                        error: Optional[str] = None) -> str:
    now = datetime.now(_BRT).strftime("%H:%M:%S")
    if error:
        return f"[{now}] {site_name} -> ERRO: {error[:80]}"
    if new == 0 and updated == 0 and removed == 0:
        return f"[{now}] {site_name} -> {found} encontrados, 0 mudancas"
    parts = []
    if new:
        parts.append(f"{new} novos")
    if updated:
        parts.append(f"{updated} atualizados")
    if removed:
        parts.append(f"{removed} removidos")
    return f"[{now}] {site_name} -> {found} encontrados, {', '.join(parts)}"


async def _scraping_body(
    put_event: Callable[[str], None],
    conn,
    run_id: str,
    sites_config: list,
    start_time,
) -> None:
    """
    Core scraping logic. Decoupled from the event queue so it can run in any
    event loop (including a dedicated ProactorEventLoop thread on Windows).
    put_event() is a sync callback — emits JSON-serialised event dicts.
    """
    global _running

    total_new = 0
    total_updated = 0
    total_removed = 0
    total_found = 0
    error_count = 0
    log_lines = []

    # Pre-compute which transaction types are expected per base imobiliária
    base_expected_tt: dict = defaultdict(set)
    base_display_map: dict = {}
    for site in sites_config:
        base = _base_name(site["name"])
        base_expected_tt[base].add(site.get("transaction_type", "aluguel"))
        base_display_map[base] = _site_display(base)

    # Accumulate per-base results for persistent sites_log
    base_results: dict = {}
    base_done_tt: dict = defaultdict(set)

    try:
        for site in sites_config:
            base = _base_name(site["name"])
            tt = site.get("transaction_type", "aluguel")
            display = base_display_map[base]

            if base not in base_results:
                base_results[base] = {
                    "base": base, "display": display,
                    "aluguel": None, "compra": None,
                    "ts": None, "has_error": False, "total_duration": 0,
                }

            put_event(json.dumps({
                "type": "site_start",
                "base": base, "display": display,
                "transaction_type": tt,
            }))

            site_new = 0
            site_updated = 0
            site_removed = 0
            error_msg = None
            properties = []
            site_t0 = time.monotonic()

            try:
                scraper = get_scraper(site)
                properties = await scraper.scrape()
                total_found += len(properties)

                new_ids: set[str] = set()
                for prop in properties:
                    flag, changes = detect_changes(conn, prop)
                    if flag == "new":
                        site_new += 1
                        total_new += 1
                        new_ids.add(prop.id)
                    elif flag == "updated":
                        site_updated += 1
                        total_updated += 1
                    _save_property(conn, prop, run_id, flag, changes)

                scraped_ids = {prop.id for prop in properties}
                active_rows = conn.execute(
                    "SELECT id FROM imoveis WHERE source_site=? AND is_active=1",
                    [site["name"]]
                ).fetchall()
                for row in active_rows:
                    if row["id"] not in scraped_ids:
                        now = datetime.now(_BRT).isoformat()
                        conn.execute(
                            "UPDATE imoveis SET is_active=0, last_seen=? WHERE id=?",
                            [now, row["id"]]
                        )
                        conn.execute("""
                            INSERT INTO historico (
                                imovel_id, run_id, scraped_at, price, area_m2, land_area_m2,
                                bedrooms, neighborhood, is_active, change_flag, changes_summary
                            )
                            SELECT id, ?, ?, price, area_m2, land_area_m2,
                                   bedrooms, neighborhood, 0, 'removed', '{}'
                            FROM imoveis WHERE id=?
                        """, [run_id, now, row["id"]])
                        site_removed += 1
                        total_removed += 1

                conn.commit()

                # Enrichment phase: fetch full gallery for new (or all if forced)
                force = site.get("force_images", False)
                enrich_props = properties if force else [p for p in properties if p.id in new_ids]
                if enrich_props:
                    enrich_items = [
                        {
                            "id": p.id,
                            "site_name": p.source_site,
                            "platform": site.get("platform", ""),
                            "url": p.source_url,
                        }
                        for p in enrich_props
                    ]
                    enrich_total = len(enrich_items)
                    put_event(json.dumps({
                        "type": "enrich_start",
                        "base": base, "display": display,
                        "total": enrich_total,
                    }))

                    def _on_progress(imovel_id: str, current: int, total: int) -> None:
                        put_event(json.dumps({
                            "type": "enrich_progress",
                            "base": base,
                            "current": current,
                            "total": total,
                        }))

                    enriched = await enrich_properties_batch(enrich_items, _on_progress)

                    enriched_count = 0
                    for imovel_id, images in enriched.items():
                        if images:
                            conn.execute(
                                "DELETE FROM imovel_imagens WHERE imovel_id=?", [imovel_id]
                            )
                            for i, url in enumerate(images):
                                conn.execute(
                                    "INSERT INTO imovel_imagens (imovel_id, url, position) VALUES (?,?,?)",
                                    [imovel_id, url, i],
                                )
                            enriched_count += 1
                    conn.commit()

                    put_event(json.dumps({
                        "type": "enrich_done",
                        "base": base, "display": display,
                        "enriched": enriched_count,
                        "total": enrich_total,
                    }))

            except Exception as e:
                error_msg = str(e)[:120]
                error_count += 1

            duration = round(time.monotonic() - site_t0, 1)
            ts = datetime.now(_BRT).strftime("%H:%M:%S")

            site_result = {
                "found": len(properties),
                "new": site_new,
                "updated": site_updated,
                "removed": site_removed,
                "duration": duration,
                "error": error_msg,
            }

            base_results[base][tt] = site_result
            base_results[base]["total_duration"] = round(
                base_results[base]["total_duration"] + duration, 1
            )
            if error_msg:
                base_results[base]["has_error"] = True
            if base_results[base]["ts"] is None:
                base_results[base]["ts"] = ts

            base_done_tt[base].add(tt)

            put_event(json.dumps({
                "type": "site_done",
                "base": base, "display": display,
                "transaction_type": tt,
                **site_result,
                "ts": ts,
            }))

            # Emit base_done once all expected transaction types are finished
            if base_done_tt[base] >= base_expected_tt[base]:
                br = base_results[base]
                put_event(json.dumps({
                    "type": "base_done",
                    "base": base, "display": display,
                    "has_error": br["has_error"],
                    "total_duration": br["total_duration"],
                }))

            log_lines.append(build_run_log_line(
                site["name"],
                found=len(properties),
                new=site_new,
                updated=site_updated,
                removed=site_removed,
                error=error_msg,
            ))

    finally:
        duration = (datetime.now(_BRT) - start_time).total_seconds()
        now_str = datetime.now(_BRT).strftime("%H:%M:%S")
        summary = (
            f"[{now_str}] CONCLUIDO -> {len(sites_config)} sites, "
            f"{total_found} imoveis, {total_new} novos, "
            f"{total_updated} atualizados, {total_removed} removidos ({duration:.0f}s)"
        )
        log_lines.append(summary)

        put_event(json.dumps({
            "type": "done",
            "total_found": total_found,
            "total_new": total_new,
            "total_updated": total_updated,
            "total_removed": total_removed,
            "duration": round(duration),
            "ts": now_str,
        }))

        if error_count == len(sites_config):
            final_status = "failed"
        elif error_count > 0:
            final_status = "partial"
        else:
            final_status = "completed"

        conn.execute("""
            UPDATE runs SET
                status=?, total_found=?, new_count=?,
                updated_count=?, removed_count=?, duration_seconds=?, log=?, sites_log=?
            WHERE run_id=?
        """, [final_status, total_found, total_new, total_updated, total_removed,
              duration, "\n".join(log_lines), json.dumps(list(base_results.values())), run_id])
        conn.commit()
        conn.close()
        _running = False
        _running_since = None
        _running_label = ""


async def run_scraping(sites_config: Optional[list] = None) -> None:
    """
    Main scraping orchestrator. Loads active sites from the database if not provided.
    Streams structured JSON events to the global event queue.

    On Windows, uvicorn may run SelectorEventLoop which blocks Playwright's
    subprocess creation. The workaround: run _scraping_body in a daemon thread
    with a dedicated ProactorEventLoop, pushing events back to the main loop
    via call_soon_threadsafe.
    """
    global _running, _running_since, _running_label
    if _running:
        return
    _running = True
    _running_since = datetime.now(tz=_BRT)

    # Build a readable label from sites_config (set before actual scraping starts)
    if sites_config is not None:
        types = {s.get("transaction_type", "") for s in sites_config}
        if len(sites_config) == 1:
            _running_label = sites_config[0].get("name", "").replace("_", " ").title()
        elif types == {"aluguel"}:
            _running_label = "Aluguel"
        elif types == {"compra"}:
            _running_label = "Compra"
        else:
            _running_label = "Tudo"
    else:
        _running_label = "Tudo"

    main_loop = asyncio.get_running_loop()
    queue = get_event_queue()

    def put_event(item: str) -> None:
        main_loop.call_soon_threadsafe(queue.put_nowait, item)

    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        + "_" + uuid.uuid4().hex[:6]
    )
    start_time = datetime.now(_BRT)

    if sites_config is None:
        cfg_conn = get_connection()
        rows = get_sites(cfg_conn, active_only=True)
        cfg_conn.close()
        sites_config = [dict(row) for row in rows]

    # Sort: group by base imobiliária, aluguel before compra
    sites_config = _sort_sites(sites_config)

    conn = get_connection()
    conn.execute(
        "INSERT INTO runs (run_id, run_date, sites_scraped, status) VALUES (?,?,?,'running')",
        [run_id, start_time.isoformat(), json.dumps([s["name"] for s in sites_config])]
    )
    conn.commit()

    if sys.platform == "win32":
        def _thread() -> None:
            loop = asyncio.ProactorEventLoop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    _scraping_body(put_event, conn, run_id, sites_config, start_time)
                )
            finally:
                loop.close()

        threading.Thread(target=_thread, daemon=True, name="scraping").start()
    else:
        await _scraping_body(put_event, conn, run_id, sites_config, start_time)
