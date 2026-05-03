#!/bin/bash
# MAC_ASD v12.0 — Cron wrapper for Telegram → БЛС ingest
# Usage: ./scripts/cron_ingest_telegram.sh
# Schedule: every 6 hours via crontab / Hermes cron

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXPORTS_DIR="$PROJECT_DIR/data/telegram_exports"
LOG_FILE="$PROJECT_DIR/data/telegram_ingest.log"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python3"

cd "$PROJECT_DIR"

# Check if exports exist
if [ ! -d "$EXPORTS_DIR" ] || [ -z "$(ls -A "$EXPORTS_DIR" 2>/dev/null)" ]; then
    echo "[$(date -Iseconds)] No exports found in $EXPORTS_DIR — skipping" >> "$LOG_FILE"
    exit 0
fi

echo "[$(date -Iseconds)] Starting Telegram ingest..." >> "$LOG_FILE"

PYTHONPATH=. "$VENV_PYTHON" -m src.scripts.ingest_blc_telegram \
    --batch "$EXPORTS_DIR" \
    --throttle 0.5 \
    >> "$LOG_FILE" 2>&1

echo "[$(date -Iseconds)] Ingest complete" >> "$LOG_FILE"
