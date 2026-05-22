#!/usr/bin/env python3
"""Deprecated: use collector.hourly. Wrapper ruft hourly auf (max. 1× pro Stunde)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from collector.hourly import run_hourly

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "disruptions.db"


def main() -> None:
    parser = argparse.ArgumentParser(description="(Alias) Stündlicher BVG-Lauf — nutze collector.hourly")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-html", action="store_true")
    args = parser.parse_args()
    try:
        run_hourly(db_path=args.db, force=args.force, skip_html=args.skip_html)
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
