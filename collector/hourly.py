#!/usr/bin/env python3
"""Periodic scrape: one snapshot per hour (Berlin, :00)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from collector.collect import run_collect
from collector.db import DEFAULT_DB, connect, delete_snapshot, migrate as migrate_db
from collector.lifecycle import (
    berlin_slot,
    compare_snapshots,
    get_last_two_snapshots,
    migrate,
    snapshot_exists_for_slot,
)

DASHBOARD_BUILDER = Path(__file__).resolve().parent.parent / "dashboard" / "build_html.py"


def run_hourly(
    *,
    db_path: Path = DEFAULT_DB,
    force: bool = False,
    skip_html: bool = False,
    rebuild_html_every: int = 1,
) -> dict:
    conn = connect(db_path)
    migrate_db(conn)
    migrate(conn)

    slot = berlin_slot()
    existing = snapshot_exists_for_slot(conn, slot)
    snapshot_count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]

    if existing and not force:
        conn.close()
        print(f"Snapshot für {slot} existiert bereits (#{existing}). Überspringen (--force).")
        if not skip_html and snapshot_count % rebuild_html_every == 0:
            _build_html()
        return {"skipped": True, "snapshot_id": existing, "slot": slot}

    if existing and force:
        delete_snapshot(conn, existing)
        print(f"Vorhandenen Snapshot #{existing} für {slot} ersetzt (--force).")

    conn.close()
    snapshot_id = run_collect(db_path, geocode=True, collected_hour=slot)

    conn = connect(db_path)
    migrate(conn)
    prev, curr = get_last_two_snapshots(conn)
    comparison = {}
    if prev and curr:
        comparison = compare_snapshots(conn, prev["id"], curr["id"])
        print(f"\nVergleich {prev['collected_hour']} → {curr['collected_hour']}:")
        print(f"  Neu:         {comparison['new_count']}")
        print(f"  Weg:         {comparison['gone_count']}")
        print(f"  Text geändert:{comparison['modified_count']}")
        print(f"  Gleich:      {comparison['continued_count']}")

    total = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    db_size = db_path.stat().st_size if db_path.exists() else 0
    conn.close()

    if not skip_html and (total % rebuild_html_every == 0 or total <= 1):
        _build_html()

    return {
        "skipped": False,
        "snapshot_id": snapshot_id,
        "slot": slot,
        "comparison": comparison,
        "total_snapshots": total,
        "db_bytes": db_size,
    }


def _build_html() -> None:
    subprocess.run([sys.executable, str(DASHBOARD_BUILDER)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="BVG-Störungs-Lauf (stündlich)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-html", action="store_true")
    parser.add_argument(
        "--rebuild-html-every",
        type=int,
        default=1,
        help="HTML alle N Läufe neu bauen (Standard: 1 = jedes Mal)",
    )
    args = parser.parse_args()
    try:
        run_hourly(
            db_path=args.db,
            force=args.force,
            skip_html=args.skip_html,
            rebuild_html_every=args.rebuild_html_every,
        )
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
