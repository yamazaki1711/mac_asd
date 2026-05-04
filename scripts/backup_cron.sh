#!/usr/bin/env bash
# =============================================================================
# MAC_ASD v13.0 — Cron Backup Script (P0, May 2026)
#
# Запускать ежечасно через cron:
#   0 * * * * /home/oleg/MAC_ASD/scripts/backup_cron.sh >> /home/oleg/MAC_ASD/backups/backup.log 2>&1
#
# Политика: 24 часовых + 7 дневных + 4 недельных
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
LOG_FILE="$BACKUP_DIR/backup.log"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
HOUR=$(date +"%H")
DOW=$(date +"%u")   # 1=Mon, 7=Sun
DOM=$(date +"%d")

mkdir -p "$BACKUP_DIR/hourly" "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

echo "[$TIMESTAMP] Starting backup..."

# ── Run single backup via Python service ────────────────────────────────────

cd "$PROJECT_DIR"
PYTHONPATH="$PROJECT_DIR" python -m src.core.backup --rotate 2>&1 | tee -a "$LOG_FILE"

# ── Cleanup old backup logs (keep 90 days) ─────────────────────────────────

find "$BACKUP_DIR" -name "*.log" -mtime +90 -delete 2>/dev/null || true

echo "[$TIMESTAMP] Backup complete."
