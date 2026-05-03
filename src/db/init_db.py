"""
ASD v12.0 — Database Initialization.

Creates tables, extensions (pgvector, pg_trgm), and graph storage.
v12.0: Added LessonLearned table for Опытный контур.
"""

import logging
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.config import settings
from src.db.models import Base

logger = logging.getLogger(__name__)

# Engine with connection pool configuration
engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,   # Recycle connections after 1 hour
    pool_pre_ping=True,   # Verify connections before use
    pool_timeout=30,      # Wait up to 30s for a connection
)
Session = sessionmaker(bind=engine)
# Alias for backward compatibility (used in ingest_blc_telegram.py, MCP tools)
SessionLocal = Session


def init_postgres():
    """Инициализация таблиц в PostgreSQL."""
    logger.info("Connecting to PostgreSQL to initialize tables...")
    try:
        # Use the module-level engine (already configured with pool parameters)
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            conn.commit()

        Base.metadata.create_all(engine)
        logger.info("PostgreSQL tables initialized successfully.")
    except Exception as e:
        logger.error("Failed to initialize PostgreSQL: %s", e)


def init_graph():
    """Инициализация хранилища локальных графов (NetworkX)."""
    graph_dir = settings.graphs_path
    logger.info("Initializing local NetworkX graph storage at %s", graph_dir)
    try:
        graph_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Graph storage initialized successfully.")
    except Exception as e:
        logger.error("Failed to initialize graph storage: %s", e)


if __name__ == "__main__":
    init_postgres()
    init_graph()
