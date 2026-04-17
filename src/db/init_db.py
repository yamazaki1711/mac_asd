"""
ASD v11.0 — Database Initialization.

Creates tables, extensions (pgvector, pg_trgm), and graph storage.
"""

import logging
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.config import settings
from src.db.models import Base

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Engine & Sessions
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)
# Alias for backward compatibility (used in ingest_blc_telegram.py, MCP tools)
SessionLocal = Session


def init_postgres():
    """Инициализация таблиц в PostgreSQL."""
    logger.info("Connecting to PostgreSQL to initialize tables...")
    try:
        engine = create_engine(settings.database_url)
        # Создаем расширения vector и pg_trgm, если их нет
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            conn.commit()

        Base.metadata.create_all(engine)
        logger.info("PostgreSQL tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL: {e}")


def init_graph():
    """Инициализация хранилища локальных графов (NetworkX)."""
    graph_dir = settings.graphs_path
    logger.info(f"Initializing local NetworkX graph storage at {graph_dir}")
    try:
        graph_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Graph storage initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize graph storage: {e}")


if __name__ == "__main__":
    init_postgres()
    init_graph()
