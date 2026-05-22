"""SQLite storage for disruption snapshots."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "disruptions.db"

DISRUPTION_COLUMNS = (
    "disruption_id",
    "message_type",
    "message_category",
    "message_category_json",
    "disruption_types",
    "disruption_types_json",
    "lines",
    "lines_json",
    "station_one",
    "station_two",
    "station_three",
    "station_one_json",
    "station_two_json",
    "station_three_json",
    "bahnhof_hafas_id",
    "direction_one",
    "direction_two",
    "headline",
    "summary",
    "content_html",
    "content_icon",
    "content_json",
    "images_json",
    "individual_disruptions_json",
    "start_date",
    "end_date",
    "mod_date",
    "hide_time",
    "show_on_startpage",
    "scheduled",
    "first_line_type",
    "raw_json",
)


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _add_column(conn: sqlite3.Connection, table: str, column: str, typedef: str) -> None:
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")


def init_db(conn: sqlite3.Connection) -> None:
    migrate(conn)


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collected_at TEXT NOT NULL,
            collected_day TEXT,
            collected_hour TEXT,
            disruption_type TEXT NOT NULL,
            time_frame TEXT NOT NULL,
            total_found INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS disruptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
            disruption_id TEXT NOT NULL,
            message_type TEXT,
            disruption_types TEXT,
            lines TEXT,
            station_one TEXT,
            station_two TEXT,
            headline TEXT,
            summary TEXT,
            start_date TEXT,
            end_date TEXT,
            mod_date TEXT,
            scheduled INTEGER,
            first_line_type INTEGER,
            UNIQUE(snapshot_id, disruption_id)
        );

        CREATE TABLE IF NOT EXISTS disruption_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            disruption_row_id INTEGER NOT NULL REFERENCES disruptions(id) ON DELETE CASCADE,
            station_name TEXT NOT NULL,
            lat REAL,
            lon REAL,
            resolved_name TEXT,
            stop_id TEXT,
            hafas_id TEXT
        );

        CREATE TABLE IF NOT EXISTS geocode_cache (
            station_name TEXT PRIMARY KEY,
            lat REAL,
            lon REAL,
            resolved_name TEXT,
            stop_id TEXT,
            hafas_id TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_collected ON snapshots(collected_at);
        CREATE INDEX IF NOT EXISTS idx_disruptions_snapshot ON disruptions(snapshot_id);
        CREATE INDEX IF NOT EXISTS idx_points_station ON disruption_points(station_name);
        """
    )
    _add_column(conn, "snapshots", "collected_hour", "TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_hour ON snapshots(collected_hour)"
    )
    for col, typedef in [
        ("message_category", "TEXT"),
        ("message_category_json", "TEXT"),
        ("disruption_types_json", "TEXT"),
        ("lines_json", "TEXT"),
        ("station_three", "TEXT"),
        ("station_one_json", "TEXT"),
        ("station_two_json", "TEXT"),
        ("station_three_json", "TEXT"),
        ("bahnhof_hafas_id", "TEXT"),
        ("direction_one", "TEXT"),
        ("direction_two", "TEXT"),
        ("content_html", "TEXT"),
        ("content_icon", "TEXT"),
        ("content_json", "TEXT"),
        ("images_json", "TEXT"),
        ("individual_disruptions_json", "TEXT"),
        ("hide_time", "INTEGER"),
        ("show_on_startpage", "INTEGER"),
        ("raw_json", "TEXT"),
    ]:
        _add_column(conn, "disruptions", col, typedef)
    _add_column(conn, "disruption_points", "hafas_id", "TEXT")
    _add_column(conn, "geocode_cache", "hafas_id", "TEXT")
    conn.commit()


def get_cached_geocode(conn: sqlite3.Connection, station_name: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT lat, lon, resolved_name, stop_id, hafas_id FROM geocode_cache WHERE station_name = ?",
        (station_name,),
    ).fetchone()
    if not row or row["lat"] is None:
        return None
    return dict(row)


def set_cached_geocode(
    conn: sqlite3.Connection,
    station_name: str,
    lat: float | None,
    lon: float | None,
    resolved_name: str | None = None,
    stop_id: str | None = None,
    hafas_id: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO geocode_cache (station_name, lat, lon, resolved_name, stop_id, hafas_id, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(station_name) DO UPDATE SET
            lat = excluded.lat,
            lon = excluded.lon,
            resolved_name = excluded.resolved_name,
            stop_id = excluded.stop_id,
            hafas_id = COALESCE(excluded.hafas_id, geocode_cache.hafas_id),
            updated_at = excluded.updated_at
        """,
        (
            station_name,
            lat,
            lon,
            resolved_name,
            stop_id,
            hafas_id,
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def _record_to_row(rec: dict[str, Any]) -> tuple:
    return (
        rec["disruption_id"],
        rec["message_type"],
        rec["message_category"],
        rec["message_category_json"],
        rec["disruption_types_str"],
        rec["disruption_types_json"],
        rec["lines_str"],
        rec["lines_json"],
        rec["station_one"],
        rec["station_two"],
        rec["station_three"],
        rec["station_one_json"],
        rec["station_two_json"],
        rec["station_three_json"],
        rec["bahnhof_hafas_id"],
        rec["direction_one"],
        rec["direction_two"],
        rec["headline"],
        rec["summary"],
        rec["content_html"],
        rec["content_icon"],
        rec["content_json"],
        rec["images_json"],
        rec["individual_disruptions_json"],
        rec["start_date"],
        rec["end_date"],
        rec["mod_date"],
        rec["hide_time"],
        rec["show_on_startpage"],
        rec["scheduled"],
        rec["first_line_type"],
        rec["raw_json"],
    )


def delete_snapshot(conn: sqlite3.Connection, snapshot_id: int) -> None:
    conn.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
    conn.commit()


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for rec in records:
        by_id[rec["disruption_id"]] = rec
    return list(by_id.values())


def save_snapshot(
    conn: sqlite3.Connection,
    records: list[dict[str, Any]],
    *,
    disruption_type: str = "all",
    time_frame: str = "TODAY",
    collected_day: str | None = None,
    collected_hour: str | None = None,
) -> int:
    from collector.lifecycle import berlin_slot, berlin_today

    records = _dedupe_records(records)
    collected_at = datetime.now(timezone.utc).isoformat()
    day = collected_day or berlin_today()
    hour = collected_hour or berlin_slot()
    cur = conn.execute(
        """
        INSERT INTO snapshots (
            collected_at, collected_day, collected_hour,
            disruption_type, time_frame, total_found
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (collected_at, day, hour, disruption_type, time_frame, len(records)),
    )
    snapshot_id = cur.lastrowid

    cols = ", ".join(DISRUPTION_COLUMNS)
    placeholders = ", ".join("?" * len(DISRUPTION_COLUMNS))
    sql = f"""
        INSERT INTO disruptions (snapshot_id, {cols})
        VALUES (?, {placeholders})
    """

    for rec in records:
        dcur = conn.execute(sql, (snapshot_id, *_record_to_row(rec)))
        row_id = dcur.lastrowid
        hafas = rec.get("bahnhof_hafas_id")
        for pt in rec.get("points") or []:
            conn.execute(
                """
                INSERT INTO disruption_points (
                    disruption_row_id, station_name, lat, lon, resolved_name, stop_id, hafas_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    pt["station_name"],
                    pt.get("lat"),
                    pt.get("lon"),
                    pt.get("resolved_name"),
                    pt.get("stop_id"),
                    pt.get("hafas_id") or hafas,
                ),
            )
    conn.commit()
    return snapshot_id


def list_snapshots(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, collected_at, collected_hour, disruption_type, time_frame, total_found
        FROM snapshots ORDER BY collected_at DESC
        """
    ).fetchall()
