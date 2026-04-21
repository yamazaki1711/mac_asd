"""
MAC_ASD v11.2.2 — DB Migration: Add channel, category, weight to legal_traps.

Run once:
    python -m src.db.migrate_v1122

This adds three new columns to the `legal_traps` table:
  - channel  VARCHAR(255)  — Telegram username of the source channel
  - category VARCHAR(100)  — Source category (legal_practice, legal_news, etc.)
  - weight   INTEGER       — RAG scoring weight (0-100)
"""

import logging
from sqlalchemy import text
from src.db.init_db import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Add new columns to legal_traps table."""
    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'legal_traps'"
        ))
        existing_columns = {row[0] for row in result}

        migrations = []

        if "channel" not in existing_columns:
            migrations.append(
                "ALTER TABLE legal_traps ADD COLUMN channel VARCHAR(255)"
            )
            logger.info("Will add: channel column")

        if "category" not in existing_columns:
            migrations.append(
                "ALTER TABLE legal_traps ADD COLUMN category VARCHAR(100)"
            )
            logger.info("Will add: category column")

        if "weight" not in existing_columns:
            migrations.append(
                "ALTER TABLE legal_traps ADD COLUMN weight INTEGER DEFAULT 100"
            )
            logger.info("Will add: weight column")

        if not migrations:
            logger.info("All columns already exist. No migration needed.")
            return

        for sql in migrations:
            logger.info(f"Executing: {sql}")
            conn.execute(text(sql))

        conn.commit()
        logger.info(f"Migration complete. Applied {len(migrations)} changes.")

        # Backfill: Set weight=100 for existing rows with no weight
        conn.execute(text(
            "UPDATE legal_traps SET weight = 100 WHERE weight IS NULL"
        ))
        conn.execute(text(
            "UPDATE legal_traps SET category = 'unknown' WHERE category IS NULL"
        ))
        conn.execute(text(
            "UPDATE legal_traps SET channel = source WHERE channel IS NULL"
        ))
        conn.commit()
        logger.info("Backfill complete: existing rows updated with defaults.")


if __name__ == "__main__":
    migrate()
