import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # --- Project Info ---
    PROJECT_NAME: str = "ASD_v11_MacStudio"
    VERSION: str = "11.0.0-alpha"
    
    # --- LLM / Ollama Configuration ---
    # Временная настройка для работы через облако, пока нет Mac Studio
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    PRIMARY_MODEL: str = "gemma4:31b-cloud" # Основной интеллект
    STREAMING_DEFAULT: bool = True
    
    # --- Databases ---
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "oleg")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "asd_password")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "asd_db")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = os.getenv("POSTGRES_PORT", 5433)
    
    @property
    def database_url(self) -> str:
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "asd_secret")
    
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # --- Paths ---
    BASE_DIR: str = "/home/oleg/MAC_ASD"
    WIKI_PATH: str = os.path.join(BASE_DIR, "data/wiki")
    ARTIFACTS_PATH: str = os.path.join(BASE_DIR, "data/artifacts")
    
    # --- Performance ---
    # Лимит памяти для RAM Manager (на будущее для Mac Studio)
    RAM_BUDGET_GB: int = 120 

settings = Settings()
