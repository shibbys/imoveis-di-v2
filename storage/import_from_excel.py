#!/usr/bin/env python3
"""
Import property statuses from the legacy Excel export into the current SQLite DB.

Matching key : source_url  (identical format between old and new scrapers)
What changes : status only — nothing else is touched
Statuses skipped : 'Novo' (properties start as Novo in the new DB anyway)

Usage:
    # Dry run (no changes written) — safe to run anytime
    python storage/import_from_excel.py

    # Apply changes
    python storage/import_from_excel.py --apply
"""

import argparse
import os
import sqlite3
import sys

try:
    import pandas as pd
except ImportError:
    sys.exit("Missing dependency: pip install pandas openpyxl")


EXCEL_PATH  = os.path.join(os.path.dirname(__file__), "imoveis_old.xlsx")
DB_PATH     = os.getenv("WORKSPACE", "workspaces/imoveis.db")
SKIP_STATUS = {"Novo"}   # these are left untouched in the new DB


def load_excel(path: str) -> dict:
    """Return {source_url: status} for every row where status is actionable."""
    df = pd.read_excel(path, sheet_name="imoveis", usecols=["source_url", "status"])
    df = df.dropna(subset=["source_url", "status"])
    df = df[~df["status"].isin(SKIP_STATUS)]
    return dict(zip(df["source_url"].str.strip(), df["status"].str.strip()))


def load_db(path: str) -> dict:
    """Return {source_url: {id, status}} for every property in the DB."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, source_url, status FROM imoveis").fetchall()
    conn.close()
    return {r["source_url"]: {"id": r["id"], "status": r["status"]} for r in rows}


def run(apply: bool) -> None:
    print(f"Excel  : {EXCEL_PATH}")
    print(f"DB     : {DB_PATH}")
    print(f"Mode   : {'APPLY' if apply else 'DRY RUN (use --apply to write changes)'}")
    print()

    excel = load_excel(EXCEL_PATH)
    db    = load_db(DB_PATH)

    print(f"Excel actionable rows (status != Novo) : {len(excel)}")
    print(f"DB properties                          : {len(db)}")
    print()

    updates = []   # (url, old_status, new_status)
    alerts  = []   # urls in Excel but not in DB

    for url, excel_status in excel.items():
        if url in db:
            db_status = db[url]["status"]
            if db_status != excel_status:
                updates.append((url, db_status, excel_status))
        else:
            alerts.append((url, excel_status))

    # ── Report: updates ───────────────────────────────────────────────────────
    print(f"Status to update : {len(updates)}")
    if updates:
        # Group by new status for a tidy summary
        by_status: dict = {}
        for url, old, new in updates:
            by_status.setdefault(new, []).append((url, old))
        for new_status, items in sorted(by_status.items()):
            print(f"  -> {new_status} ({len(items)})")
            for url, old in items[:3]:
                print(f"      {url[:90]}  [{old} -> {new_status}]")
            if len(items) > 3:
                print(f"      ... and {len(items) - 3} more")

    # ── Report: alerts ────────────────────────────────────────────────────────
    print()
    print(f"Alerts (in Excel, not in DB) : {len(alerts)}")
    if alerts:
        by_status2: dict = {}
        for url, status in alerts:
            by_status2.setdefault(status, []).append(url)
        for status, urls in sorted(by_status2.items()):
            print(f"  [{status}] ({len(urls)} properties not yet in DB)")
            for url in urls[:3]:
                print(f"      {url[:90]}")
            if len(urls) > 3:
                print(f"      ... and {len(urls) - 3} more")

    # ── Apply ─────────────────────────────────────────────────────────────────
    if not apply:
        print()
        print("Nothing written. Run with --apply to commit changes.")
        return

    if not updates:
        print()
        print("Nothing to update.")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        for url, _old, new_status in updates:
            conn.execute(
                "UPDATE imoveis SET status=? WHERE source_url=?",
                [new_status, url],
            )
        conn.commit()
        print()
        print(f"Done. {len(updates)} status(es) updated.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR — rolled back: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import statuses from legacy Excel export.")
    parser.add_argument("--apply", action="store_true", help="Write changes to DB (default: dry run)")
    args = parser.parse_args()
    run(apply=args.apply)
