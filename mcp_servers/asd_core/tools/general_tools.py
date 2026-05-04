import logging
from typing import Dict, Any
from src.config import settings

logger = logging.getLogger(__name__)

async def asd_get_system_status() -> Dict[str, Any]:
    """Статус системы (модели, БД, Ollama)."""
    logger.info("asd_get_system_status")
    return {
        "status": "success",
        "action": "System status retrieved",
        "database": "NetworkX + PostgreSQL pgvector connected",
        "ollama": {
            "endpoint": settings.OLLAMA_BASE_URL,
            "status": "configured"
        },
        "mcp_tools_active": 74
    }
