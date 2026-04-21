"""
АСД v11.3 — Конфигурация с поддержкой профилей.

Profiles:
    dev_linux  — Linux + Ollama (разработка, RTX 5060 8GB)
    mac_studio — Mac Studio M4 Max 128GB + MLX (продакшен)

Model Lineup (mac_studio):
    Llama 3.3 70B 4-bit   → Hermes / PM (оркестратор)
    Gemma 4 31B 4-bit     → ПТО + Юрист + Сметчик + Закупщик + Логист (shared, 128K контекст)
    Gemma 4 E4B 4-bit     → Делопроизводитель (лёгкий MoE, быстрая)
    bge-m3                → Embeddings

Usage:
    export ASD_PROFILE=mac_studio
    python -m src.main
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic_settings import BaseSettings


# =============================================================================
# Model mappings per profile
# =============================================================================
PROFILE_MODELS: Dict[str, Dict[str, Dict[str, str]]] = {
    "dev_linux": {
        "pm":          {"engine": "ollama", "model": "qwen3:32b"},
        "pto":         {"engine": "ollama", "model": "qwen3:32b"},
        "smeta":       {"engine": "ollama", "model": "qwen3:32b"},
        "legal":       {"engine": "ollama", "model": "qwen3:32b"},
        "procurement": {"engine": "ollama", "model": "qwen3:32b"},
        "logistics":   {"engine": "ollama", "model": "qwen3:32b"},
        "archive":     {"engine": "ollama", "model": "qwen3:8b"},
        "embed":       {"engine": "ollama", "model": "bge-m3"},
        "vision":      {"engine": "ollama", "model": "minicpm-v"},
    },
    "mac_studio": {
        # PM — Llama 3.3 70B (оркестратор, всегда загружен)
        "pm":          {"engine": "mlx",    "model": "mlx-community/Llama-3.3-70B-Instruct-4bit"},
        # ПТО / Юрист / Сметчик / Закупщик / Логист — Gemma 4 31B (shared, 128K контекст, VLM)
        "pto":         {"engine": "mlx-vlm","model": "mlx-community/gemma-4-31b-it-4bit"},
        "smeta":       {"engine": "mlx-vlm","model": "mlx-community/gemma-4-31b-it-4bit"},
        "legal":       {"engine": "mlx-vlm","model": "mlx-community/gemma-4-31b-it-4bit"},
        "procurement": {"engine": "mlx-vlm","model": "mlx-community/gemma-4-31b-it-4bit"},
        "logistics":   {"engine": "mlx-vlm","model": "mlx-community/gemma-4-31b-it-4bit"},
        # Делопроизводитель — Gemma 4 E4B (лёгкий MoE)
        "archive":     {"engine": "mlx",    "model": "mlx-community/gemma-4-e4b-it-4bit"},
        # Embeddings — bge-m3 (через Ollama или MLX-Embeddings)
        "embed":       {"engine": "ollama", "model": "bge-m3"},
        # Vision — Gemma 4 31B (нативный VLM, тот же что ПТО)
        "vision":      {"engine": "mlx-vlm","model": "mlx-community/gemma-4-31b-it-4bit"},
    },
}


def _detect_project_root() -> Path:
    """Автоопределение корня проекта (где лежит README.md и .git)."""
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / "README.md").exists() and (parent / ".git").exists():
            return parent
    # Fallback: 3 уровня вверх от src/config.py → project_root/src/config.py
    return current.parent.parent


class Settings(BaseSettings):
    # --- Project Info ---
    PROJECT_NAME: str = "ASD_v11"
    VERSION: str = "11.3"

    # --- Profile ---
    ASD_PROFILE: str = os.getenv("ASD_PROFILE", "dev_linux")

    # --- LLM: Ollama ---
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # --- LLM: Model overrides (optional) ---
    MODEL_PM: Optional[str] = os.getenv("MODEL_PM")
    MODEL_PTO: Optional[str] = os.getenv("MODEL_PTO")
    MODEL_SMETA: Optional[str] = os.getenv("MODEL_SMETA")
    MODEL_LEGAL: Optional[str] = os.getenv("MODEL_LEGAL")
    MODEL_PROCUREMENT: Optional[str] = os.getenv("MODEL_PROCUREMENT")
    MODEL_LOGISTICS: Optional[str] = os.getenv("MODEL_LOGISTICS")
    MODEL_ARCHIVE: Optional[str] = os.getenv("MODEL_ARCHIVE")
    MODEL_EMBED: Optional[str] = os.getenv("MODEL_EMBED", "bge-m3")
    MODEL_VISION: Optional[str] = os.getenv("MODEL_VISION")

    # --- Paths ---
    BASE_DIR: str = os.getenv("BASE_DIR", str(_detect_project_root()))
    WIKI_PATH: str = os.getenv("WIKI_PATH", "")  # auto if empty
    ARTIFACTS_PATH: str = os.getenv("ARTIFACTS_PATH", "")  # auto if empty

    # --- Databases ---
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "oleg")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "asd_password")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "asd_db")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5433"))

    # Redis УДАЛЁН в v11.3 — заменён на in-process кэширование (cachetools)
    # Причина: single-user Mac Studio, Redis избыточен, экономия 2GB RAM

    # --- Performance ---
    RAM_BUDGET_GB: int = int(os.getenv("RAM_BUDGET_GB", "78"))

    # -------------------------------------------------------------------------
    # Computed properties
    # -------------------------------------------------------------------------

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def wiki_path(self) -> Path:
        """Resolved path to Obsidian Wiki."""
        if self.WIKI_PATH:
            return Path(self.WIKI_PATH)
        return Path(self.BASE_DIR) / "docs" / "wiki"

    @property
    def artifacts_path(self) -> Path:
        """Resolved path to Artifact Store."""
        if self.ARTIFACTS_PATH:
            return Path(self.ARTIFACTS_PATH)
        return Path(self.BASE_DIR) / "data" / "artifacts"

    @property
    def graphs_path(self) -> Path:
        """Resolved path to NetworkX graph storage."""
        return Path(self.BASE_DIR) / "data" / "graphs"

    def get_model_config(self, agent: str) -> Dict[str, str]:
        """
        Возвращает конфигурацию модели для конкретного агента.

        Args:
            agent: Имя агента (pm, pto, smeta, legal, procurement, logistics, archive, embed, vision)

        Returns:
            {"engine": "ollama"|"mlx"|"mlx-vlm", "model": "model_name"}

        Example (mac_studio):
            >>> settings.get_model_config("legal")
            {"engine": "mlx-vlm", "model": "mlx-community/gemma-4-31b-it-4bit"}
        """
        # Check for explicit override
        override_map = {
            "pm": self.MODEL_PM,
            "pto": self.MODEL_PTO,
            "smeta": self.MODEL_SMETA,
            "legal": self.MODEL_LEGAL,
            "procurement": self.MODEL_PROCUREMENT,
            "logistics": self.MODEL_LOGISTICS,
            "archive": self.MODEL_ARCHIVE,
            "vision": self.MODEL_VISION,
        }

        override = override_map.get(agent)
        if override:
            # Override specified — keep profile's engine but use custom model
            profile_config = PROFILE_MODELS.get(self.ASD_PROFILE, PROFILE_MODELS["dev_linux"])
            default_engine = profile_config.get(agent, {}).get("engine", "ollama")
            return {"engine": default_engine, "model": override}

        # Use profile defaults
        profile_config = PROFILE_MODELS.get(self.ASD_PROFILE, PROFILE_MODELS["dev_linux"])
        return profile_config.get(agent, {"engine": "ollama", "model": "qwen3:32b"})

    @property
    def is_mac_studio(self) -> bool:
        """True если запущено на Mac Studio (профиль mac_studio)."""
        return self.ASD_PROFILE == "mac_studio"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
