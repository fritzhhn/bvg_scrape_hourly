#!/usr/bin/env python3
"""Fetch current BVG disruptions and store a timestamped snapshot."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from collector.api import fetch_all_disruptions, search_station
from collector.db import DEFAULT_DB, connect, get_cached_geocode, init_db, migrate, save_snapshot, set_cached_geocode
from collector.lifecycle import berlin_slot, berlin_today, migrate as migrate_lifecycle, update_lifecycle
from collector.normalize import normalize_disruption


def geocode_stations(
    conn,
    station_names: list[str],
    *,
    hafas_by_station: dict[str, str | None] | None = None,
) -> list[dict]:
    points = []
    seen = set()
    hafas_by_station = hafas_by_station or {}
    for name in station_names:
        if not name or name in seen:
            continue
        seen.add(name)
        cached = get_cached_geocode(conn, name)
        if cached:
            points.append({"station_name": name, **cached})
            continue
        time.sleep(0.15)
        result = search_station(name)
        hafas = hafas_by_station.get(name)
        if result:
            set_cached_geocode(
                conn,
                name,
                result["lat"],
                result["lon"],
                resolved_name=result.get("resolved_name"),
                stop_id=result.get("stop_id"),
                hafas_id=hafas,
            )
            points.append({"station_name": name, "hafas_id": hafas, **result})
        else:
            set_cached_geocode(conn, name, None, None, hafas_id=hafas)
            points.append({"station_name": name, "lat": None, "lon": None, "hafas_id": hafas})
    conn.commit()
    return points


def run_collect(
    db_path: Path = DEFAULT_DB,
    disruption_type: str = "all",
    time_frame: str = "TODAY",
    *,
    collected_day: str | None = None,
    collected_hour: str | None = None,
    geocode: bool = True,
) -> int:
    conn = connect(db_path)
    init_db(conn)
    migrate(conn)
    migrate_lifecycle(conn)
    day = collected_day or berlin_today()
    hour = collected_hour or berlin_slot()

    print(f"Fetching disruptions (type={disruption_type}, timeFrame={time_frame})...")
    raw_items = fetch_all_disruptions(
        disruption_type=disruption_type,
        time_frame=time_frame,
    )
    print(f"Received {len(raw_items)} disruption reports.")

    records = []
    all_stations: set[str] = set()
    hafas_map: dict[str, str | None] = {}
    for raw in raw_items:
        rec = normalize_disruption(raw)
        for st in rec["stations"]:
            all_stations.add(st)
            if rec.get("bahnhof_hafas_id"):
                hafas_map[st] = str(rec["bahnhof_hafas_id"])
        records.append(rec)

    if geocode:
        uncached = [s for s in all_stations if not get_cached_geocode(conn, s)]
        print(f"Geocoding {len(all_stations)} stations ({len(uncached)} neu, Rest aus Cache)...")
        station_points: dict[str, dict] = {}
        for name in sorted(all_stations):
            for pt in geocode_stations(conn, [name], hafas_by_station=hafas_map):
                station_points[name] = pt
        for rec in records:
            rec["points"] = [station_points[st] for st in rec["stations"] if st in station_points]
    else:
        for rec in records:
            rec["points"] = [{"station_name": st, "hafas_id": hafas_map.get(st)} for st in rec["stations"]]

    snapshot_id = save_snapshot(
        conn,
        records,
        disruption_type=disruption_type,
        time_frame=time_frame,
        collected_day=day,
        collected_hour=hour,
    )
    snap = conn.execute(
        "SELECT collected_at FROM snapshots WHERE id = ?", (snapshot_id,)
    ).fetchone()
    update_lifecycle(conn, snapshot_id, snap["collected_at"], day, hour, records)
    conn.close()
    print(f"Saved snapshot #{snapshot_id} (slot {hour}) to {db_path}")
    return snapshot_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect BVG disruption snapshot")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--type", default="all", choices=["all", "TRAFFIC", "ELEVATOR"])
    parser.add_argument("--time-frame", default="TODAY", choices=["TODAY", "TOMORROW", "FORTNIGHT"])
    parser.add_argument("--no-geocode", action="store_true")
    args = parser.parse_args()
    try:
        run_collect(args.db, args.type, args.time_frame, geocode=not args.no_geocode)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
