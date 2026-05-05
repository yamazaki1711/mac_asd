#!/bin/bash
# MAC_ASD v13.0 — Cron: Telegram → YAML → PostgreSQL domain_traps
# Schedule: every 6 hours via Hermes cron
# Usage: ./scripts/cron_ingest_telegram.sh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_FILE="$PROJECT_DIR/data/telegram_ingest.log"

log() {
    echo "[$(date -Iseconds)] $1" | tee -a "$LOG_FILE"
}

log "=== Starting Telegram ingest cycle ==="

# Step 1: Fetch new messages from Telegram (incremental)
log "Step 1/3: Fetching new Telegram messages..."
cd "$PROJECT_DIR"
PYTHONPATH=. timeout 900 "$VENV_PYTHON" scripts/telegram_kb_ingest.py >> "$LOG_FILE" 2>&1 || {
    log "WARNING: telegram_kb_ingest.py failed (exit $?)"
}

# Step 2: Sync YAML → PostgreSQL domain_traps
log "Step 2/3: Syncing YAML → PostgreSQL..."
PYTHONPATH=. timeout 300 "$VENV_PYTHON" scripts/ingest_blc_telegram.py >> "$LOG_FILE" 2>&1 || {
    log "WARNING: ingest_blc_telegram.py failed (exit $?)"
}

# Step 3: Verify
log "Step 3/3: Verifying PostgreSQL..."
count=$(PGPASSWORD=asd_password psql -h localhost -U asd_user -d asd_db -t -c "SELECT COUNT(*) FROM domain_traps;" 2>/dev/null | tr -d ' ')
log "PostgreSQL domain_traps: $count entries"
log "=== Cycle complete ==="
