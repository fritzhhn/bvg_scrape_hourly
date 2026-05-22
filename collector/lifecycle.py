"""Track disruption visibility across periodic snapshots (20-minute slots)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")


def migrate(conn: sqlite3.Connection) -> None:
    from collector.db import migrate as migrate_db

    migrate_db(conn)

    cols = {r[1] for r in conn.execute("PRAGMA table_info(snapshots)")}
    if "collected_hour" not in cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN collected_hour TEXT")
    conn.execute(
        """
        UPDATE snapshots SET collected_day = date(collected_at)
        WHERE collected_day IS NULL
        """
    )
    conn.execute(
        """
        UPDATE snapshots SET collected_hour = strftime('%Y-%m-%dT%H', collected_at, '+1 hour')
        WHERE collected_hour IS NULL
        """
    )
    conn.commit()

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS disruption_registry (
            disruption_id TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            hours_seen INTEGER NOT NULL DEFAULT 1,
            days_seen INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            headline TEXT,
            station_one TEXT,
            lines TEXT,
            disruption_types TEXT
        );

        CREATE TABLE IF NOT EXISTS disruption_appearances (
            disruption_id TEXT NOT NULL,
            snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
            collected_day TEXT NOT NULL,
            collected_hour TEXT,
            PRIMARY KEY (disruption_id, snapshot_id)
        );

        CREATE INDEX IF NOT EXISTS idx_appearances_day ON disruption_appearances(collected_day);
        CREATE INDEX IF NOT EXISTS idx_registry_active ON disruption_registry(is_active);
        """
    )
    reg_cols = {r[1] for r in conn.execute("PRAGMA table_info(disruption_registry)")}
    if "hours_seen" not in reg_cols:
        conn.execute("ALTER TABLE disruption_registry ADD COLUMN hours_seen INTEGER NOT NULL DEFAULT 1")
    app_cols = {r[1] for r in conn.execute("PRAGMA table_info(disruption_appearances)")}
    if "collected_hour" not in app_cols:
        conn.execute("ALTER TABLE disruption_appearances ADD COLUMN collected_hour TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_appearances_hour ON disruption_appearances(collected_hour)"
    )
    conn.commit()


def berlin_today() -> str:
    return datetime.now(BERLIN).date().isoformat()


def berlin_slot() -> str:
    """Hour id for snapshot dedupe, e.g. 2026-05-22T21 (runs at :00 Berlin)."""
    now = datetime.now(BERLIN)
    return now.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H")


def berlin_hour() -> str:
    return berlin_slot()


def snapshot_exists_for_slot(conn: sqlite3.Connection, slot: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM snapshots WHERE collected_hour = ? ORDER BY id DESC LIMIT 1",
        (slot,),
    ).fetchone()
    return int(row["id"]) if row else None


def snapshot_exists_for_hour(conn: sqlite3.Connection, hour: str) -> int | None:
    return snapshot_exists_for_slot(conn, hour)


def get_last_two_snapshots(conn: sqlite3.Connection) -> tuple[sqlite3.Row | None, sqlite3.Row | None]:
    """Latest snapshot and the immediately previous one."""
    rows = conn.execute(
        """
        SELECT id, collected_at, collected_day, collected_hour, total_found
        FROM snapshots ORDER BY id DESC LIMIT 2
        """
    ).fetchall()
    if not rows:
        return None, None
    if len(rows) == 1:
        return None, rows[0]
    return rows[1], rows[0]


def disruption_ids_in_snapshot(conn: sqlite3.Connection, snapshot_id: int) -> set[str]:
    rows = conn.execute(
        "SELECT disruption_id FROM disruptions WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchall()
    return {r["disruption_id"] for r in rows}


def compare_snapshots(conn: sqlite3.Connection, prev_id: int, curr_id: int) -> dict:
    prev = disruption_ids_in_snapshot(conn, prev_id)
    curr = disruption_ids_in_snapshot(conn, curr_id)
    new_ids = curr - prev
    gone_ids = prev - curr
    continued = curr & prev

    new_rows = []
    if new_ids:
        ph = ",".join("?" * len(new_ids))
        new_rows = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT disruption_id, headline, station_one, lines, disruption_types, mod_date
                FROM disruptions WHERE snapshot_id = ? AND disruption_id IN ({ph})
                """,
                (curr_id, *new_ids),
            ).fetchall()
        ]

    gone_rows = []
    if gone_ids:
        ph = ",".join("?" * len(gone_ids))
        gone_rows = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT disruption_id, headline, station_one, lines, disruption_types, mod_date
                FROM disruptions WHERE snapshot_id = ? AND disruption_id IN ({ph})
                """,
                (prev_id, *gone_ids),
            ).fetchall()
        ]

    mod_rows = []
    if continued:
        ph = ",".join("?" * len(continued))
        prev_mod = {
            r["disruption_id"]: r["mod_date"]
            for r in conn.execute(
                f"SELECT disruption_id, mod_date FROM disruptions WHERE snapshot_id = ? AND disruption_id IN ({ph})",
                (prev_id, *continued),
            ).fetchall()
        }
        for r in conn.execute(
            f"""
            SELECT disruption_id, headline, mod_date FROM disruptions
            WHERE snapshot_id = ? AND disruption_id IN ({ph})
            """,
            (curr_id, *continued),
        ).fetchall():
            did = r["disruption_id"]
            if prev_mod.get(did) and r["mod_date"] and prev_mod[did] != r["mod_date"]:
                mod_rows.append(dict(r))

    return {
        "new": new_rows,
        "gone": gone_rows,
        "modified": mod_rows,
        "continued_count": len(continued),
        "new_count": len(new_ids),
        "gone_count": len(gone_ids),
        "modified_count": len(mod_rows),
    }


def update_lifecycle(
    conn: sqlite3.Connection,
    snapshot_id: int,
    collected_at: str,
    collected_day: str,
    collected_hour: str,
    records: list[dict],
) -> None:
    migrate(conn)
    current_ids: set[str] = set()

    for rec in records:
        did = rec["disruption_id"]
        current_ids.add(did)
        conn.execute(
            """
            INSERT OR IGNORE INTO disruption_appearances
                (disruption_id, snapshot_id, collected_day, collected_hour)
            VALUES (?, ?, ?, ?)
            """,
            (did, snapshot_id, collected_day, collected_hour),
        )
        hours = conn.execute(
            "SELECT COUNT(DISTINCT collected_hour) FROM disruption_appearances WHERE disruption_id = ?",
            (did,),
        ).fetchone()[0]
        days = conn.execute(
            "SELECT COUNT(DISTINCT collected_day) FROM disruption_appearances WHERE disruption_id = ?",
            (did,),
        ).fetchone()[0]

        existing = conn.execute(
            "SELECT disruption_id FROM disruption_registry WHERE disruption_id = ?",
            (did,),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE disruption_registry SET
                    last_seen_at = ?, hours_seen = ?, days_seen = ?, is_active = 1,
                    headline = ?, station_one = ?, lines = ?, disruption_types = ?
                WHERE disruption_id = ?
                """,
                (
                    collected_at,
                    hours,
                    days,
                    rec.get("headline"),
                    rec.get("station_one"),
                    rec.get("lines_str"),
                    rec.get("disruption_types_str"),
                    did,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO disruption_registry (
                    disruption_id, first_seen_at, last_seen_at,
                    hours_seen, days_seen, is_active,
                    headline, station_one, lines, disruption_types
                ) VALUES (?, ?, ?, 1, 1, 1, ?, ?, ?, ?)
                """,
                (
                    did,
                    collected_at,
                    collected_at,
                    rec.get("headline"),
                    rec.get("station_one"),
                    rec.get("lines_str"),
                    rec.get("disruption_types_str"),
                ),
            )

    if current_ids:
        placeholders = ",".join("?" * len(current_ids))
        conn.execute(
            f"""
            UPDATE disruption_registry SET is_active = 0
            WHERE is_active = 1 AND disruption_id NOT IN ({placeholders})
            """,
            tuple(current_ids),
        )
    conn.commit()


def load_history_stats(conn: sqlite3.Connection) -> dict:
    migrate(conn)
    timeline = [
        dict(r)
        for r in conn.execute(
            """
            SELECT collected_hour AS period, total_found AS disruptions, total_found AS reported
            FROM snapshots
            WHERE collected_hour IS NOT NULL
            ORDER BY collected_hour
            """
        ).fetchall()
    ]

    longest_active = [
        dict(r)
        for r in conn.execute(
            """
            SELECT disruption_id, headline, station_one, lines,
                   hours_seen, days_seen, first_seen_at, last_seen_at, is_active
            FROM disruption_registry
            ORDER BY hours_seen DESC, last_seen_at DESC
            LIMIT 25
            """
        ).fetchall()
    ]

    recently_ended = [
        dict(r)
        for r in conn.execute(
            """
            SELECT disruption_id, headline, station_one, lines,
                   hours_seen, days_seen, first_seen_at, last_seen_at
            FROM disruption_registry
            WHERE is_active = 0
            ORDER BY last_seen_at DESC
            LIMIT 20
            """
        ).fetchall()
    ]

    total_snapshots = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    total_registry = conn.execute("SELECT COUNT(*) FROM disruption_registry").fetchone()[0]

    return {
        "totalSnapshots": total_snapshots,
        "uniqueDisruptionsEver": total_registry,
        "timeline": timeline,
        "longestVisible": longest_active,
        "recentlyEnded": recently_ended,
    }
