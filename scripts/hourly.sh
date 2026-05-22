#!/bin/bash
# Stündlicher Lauf für cron/launchd
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data/logs
LOG="data/logs/hourly-$(date +%Y-%m-%d).log"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY=python3; fi
{
  echo "=== $(date -Iseconds) ==="
  "$PY" -m collector.hourly
} >> "$LOG" 2>&1
