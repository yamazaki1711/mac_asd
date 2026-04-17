import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.config import settings
from src.db.models import Base

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)

def init_postgres():
    """Инициализация таблиц в PostgreSQL."""
    logger.info("Connecting to PostgreSQL to initialize tables...")
    try:
        engine = create_engine(settings.database_url)
        # Создаем расширения vector и pg_trgm, если их нет
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
            conn.commit()
            
        Base.metadata.create_all(engine)
        logger.info("PostgreSQL tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL: {e}")

def init_graph():
    """Инициализация хранилища локальных графов (NetworkX)."""
    graph_dir = os.path.join(settings.BASE_DIR, "data", "graphs")
    logger.info(f"Initializing local NetworkX graph storage at {graph_dir}")
    try:
        os.makedirs(graph_dir, exist_ok=True)
        logger.info("Graph storage initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize graph storage: {e}")

if __name__ == "__main__":
    init_postgres()
    init_graph()
