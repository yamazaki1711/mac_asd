"""
MAC_ASD v12.0 — Конфигурация с поддержкой профилей.

Profiles:
    dev_linux  — Linux + Ollama (разработка, RTX 5060 8GB)
    mac_studio — Mac Studio M4 Max 128GB + MLX (продакшен)
    deepseek   — DeepSeek API (OpenAI-совместимый, временный мост для разработки)

Model Lineup (mac_studio):
    Llama 3.3 70B 4-bit   → Руководитель проекта / PM (оркестратор)
    Gemma 4 31B 4-bit     → ПТО + Юрист + Сметчик + Закупщик + Логист (shared, 128K контекст)
    Gemma 4 E4B 4-bit     → Делопроизводитель (лёгкий MoE, быстрая)
    bge-m3                → Embeddings

Model Lineup (deepseek):
    deepseek-chat         → Все агенты (DeepSeek-V3, 128K контекст)
    deepseek-reasoner     → PM (DeepSeek-R1, reasoning)
    bge-m3 (Ollama)       → Embeddings (DeepSeek не предоставляет эмбеддинги)

Usage:
    export ASD_PROFILE=deepseek
    export DEEPSEEK_API_KEY=sk-...
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
    # RTX 5060 8GB VRAM — Gemma 3 12B q4 (~7.5GB, 32K контекст)
    # Все агенты разделяют одну модель для экономии VRAM.
    # bge-m3 — на CPU (Ollama загружает в системную RAM).
    "dev_linux": {
        "pm":          {"engine": "ollama", "model": "gemma3:12b"},
        "pto":         {"engine": "ollama", "model": "gemma3:12b"},
        "smeta":       {"engine": "ollama", "model": "gemma3:12b"},
        "legal":       {"engine": "ollama", "model": "gemma3:12b"},
        "procurement": {"engine": "ollama", "model": "gemma3:12b"},
        "logistics":   {"engine": "ollama", "model": "gemma3:12b"},
        "archive":     {"engine": "ollama", "model": "gemma3:12b"},
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
    "deepseek": {
        # PM — DeepSeek-R1 (reasoning) для принятия решений
        "pm":          {"engine": "deepseek", "model": "deepseek-reasoner"},
        # Агенты — DeepSeek-V3 (128K контекст, быстрый)
        "pto":         {"engine": "deepseek", "model": "deepseek-chat"},
        "smeta":       {"engine": "deepseek", "model": "deepseek-chat"},
        "legal":       {"engine": "deepseek", "model": "deepseek-chat"},
        "procurement": {"engine": "deepseek", "model": "deepseek-chat"},
        "logistics":   {"engine": "deepseek", "model": "deepseek-chat"},
        "archive":     {"engine": "deepseek", "model": "deepseek-chat"},
        # Embeddings — bge-m3 через Ollama (DeepSeek не предоставляет эмбеддинги)
        "embed":       {"engine": "ollama",   "model": "bge-m3"},
        # Vision — Gemma 4 31B через Ollama Cloud Free (DeepSeek не поддерживает VLM)
        "vision":      {"engine": "ollama",   "model": "gemma4:31b-cloud"},
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
    PROJECT_NAME: str = "MAC_ASD"
    VERSION: str = "12.0"

    # --- Profile ---
    ASD_PROFILE: str = os.getenv("ASD_PROFILE", "dev_linux")

    # --- LLM: Ollama ---
    llm_base_url: str = "http://127.0.0.1:11434"
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"

    # --- LLM: DeepSeek ---
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

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

    # Redis УДАЛЁН в v12.0 — заменён на in-process кэширование (cachetools)
    # Причина: single-user Mac Studio, Redis избыточен, экономия 2GB RAM

    # --- Performance ---
    RAM_BUDGET_GB: int = int(os.getenv("RAM_BUDGET_GB", "78"))

    # --- Google Workspace ---
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(Path(__file__).parent.parent / "credentials" / "google_service_account.json"),
    )
    GOOGLE_DRIVE_PROJECTS_FOLDER: str = os.getenv("GOOGLE_DRIVE_PROJECTS_FOLDER", "")
    GOOGLE_DRIVE_TEMPLATES_FOLDER: str = os.getenv("GOOGLE_DRIVE_TEMPLATES_FOLDER", "")
    GOOGLE_DRIVE_CONTRACTS_FOLDER: str = os.getenv("GOOGLE_DRIVE_CONTRACTS_FOLDER", "")
    GOOGLE_DOCS_AOSR_TEMPLATE: str = os.getenv("GOOGLE_DOCS_AOSR_TEMPLATE", "")
    GOOGLE_DOCS_AOOK_TEMPLATE: str = os.getenv("GOOGLE_DOCS_AOOK_TEMPLATE", "")
    GOOGLE_DOCS_PROTOCOL_TEMPLATE: str = os.getenv("GOOGLE_DOCS_PROTOCOL_TEMPLATE", "")
    GOOGLE_SHEETS_VOR_TEMPLATE: str = os.getenv("GOOGLE_SHEETS_VOR_TEMPLATE", "")
    GOOGLE_SHEETS_ESTIMATE_TEMPLATE: str = os.getenv("GOOGLE_SHEETS_ESTIMATE_TEMPLATE", "")
    GOOGLE_DRIVE_VOR_FOLDER: str = os.getenv("GOOGLE_DRIVE_VOR_FOLDER", "")

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
            "embed": self.MODEL_EMBED,
        }

        override = override_map.get(agent)
        if override:
            # Override specified — keep profile's engine but use custom model
            profile_config = PROFILE_MODELS.get(self.ASD_PROFILE, PROFILE_MODELS["dev_linux"])
            default_engine = profile_config.get(agent, {}).get("engine", "ollama")
            return {"engine": default_engine, "model": override}

        # Use profile defaults
        profile_config = PROFILE_MODELS.get(self.ASD_PROFILE, PROFILE_MODELS["dev_linux"])
        return profile_config.get(agent, {"engine": "ollama", "model": "gemma4:31b-cloud"})

    @property
    def google_configured(self) -> bool:
        """True если файл Google-кредов существует."""
        return Path(self.GOOGLE_APPLICATION_CREDENTIALS).exists()

    def get_drive_folder(self, folder_type: str) -> str:
        """Возвращает ID папки Google Drive по типу."""
        folder_map = {
            "vor": self.GOOGLE_DRIVE_VOR_FOLDER,
            "projects": self.GOOGLE_DRIVE_PROJECTS_FOLDER,
            "templates": self.GOOGLE_DRIVE_TEMPLATES_FOLDER,
            "contracts": self.GOOGLE_DRIVE_CONTRACTS_FOLDER,
        }
        return folder_map.get(folder_type, "")

    def get_docs_template(self, template_type: str) -> str:
        """Возвращает ID шаблона Google Docs по типу."""
        template_map = {
            "aosr": self.GOOGLE_DOCS_AOSR_TEMPLATE,
            "aook": self.GOOGLE_DOCS_AOOK_TEMPLATE,
            "protocol": self.GOOGLE_DOCS_PROTOCOL_TEMPLATE,
        }
        return template_map.get(template_type, "")

    @property
    def is_mac_studio(self) -> bool:
        """True если запущено на Mac Studio (профиль mac_studio)."""
        return self.ASD_PROFILE == "mac_studio"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
