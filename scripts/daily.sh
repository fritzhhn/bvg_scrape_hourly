#!/bin/bash
# Täglicher Lauf für cron/launchd — loggt nach data/logs/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data/logs
LOG="data/logs/daily-$(date +%Y-%m-%d).log"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY=python3; fi
{
  echo "=== $(date -Iseconds) ==="
  "$PY" -m collector.daily
} >> "$LOG" 2>&1
