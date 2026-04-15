import logging
from sqlalchemy import create_engine
from neo4j import GraphDatabase
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
        # Создаем расширение pgvector, если его нет
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
            
        Base.metadata.create_all(engine)
        logger.info("PostgreSQL tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL: {e}")

def init_neo4j():
    """Инициализация индексов и ограничений в Neo4j."""
    logger.info("Connecting to Neo4j to initialize indices...")
    try:
        driver = GraphDatabase.driver(
            settings.NEO4J_URI, 
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        with driver.session() as session:
            # Создаем уникальность для узлов-документов и проектов
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE")
            session.run("CREATE INDEX IF NOT EXISTS FOR (c:Chunk) ON (c.document_id)")
        driver.close()
        logger.info("Neo4j database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Neo4j: {e}")

if __name__ == "__main__":
    init_postgres()
    init_neo4j()
