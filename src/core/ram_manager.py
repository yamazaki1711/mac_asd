import psutil
import logging
import time
from typing import List, Dict
from src.config import settings
from src.core.ollama_client import ollama_client

logger = logging.getLogger(__name__)

class RamManager:
    """
    Управляет памятью (Unified Memory) на Mac Studio.
    Отслеживает лимиты и принудительно выгружает тяжелые ML-модели из Metal/RAM.
    """
    def __init__(self):
        self.total_budget_gb = settings.RAM_BUDGET_GB
        self.active_models: List[str] = []

    def get_memory_usage_gb(self) -> float:
        """Получает текущее потребление памяти Python-процессом и системой."""
        try:
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024 ** 3)
            return used_gb
        except Exception as e:
            logger.error(f"Failed to read memory: {e}")
            return 0.0

    def check_memory_health(self) -> bool:
        """Возвращает True если память в норме, False если критически мала."""
        used_gb = self.get_memory_usage_gb()
        if used_gb > self.total_budget_gb:
            logger.warning(f"CRITICAL MEMORY: Used {used_gb:.1f}GB / Budget {self.total_budget_gb}GB")
            return False
        return True

    async def unload_model(self, model_name: str):
        """
        Принудительно выгружает модель из памяти Ollama.
        Реализуется путем отправки пустого запроса с keep_alive=0.
        """
        logger.info(f"[RAM_MANAGER] Forcing unload of model: {model_name}")
        try:
            await ollama_client.generate_base(
                model=model_name,
                prompt="",
                keep_alive=0
            )
            if model_name in self.active_models:
                self.active_models.remove(model_name)
            logger.info(f"[RAM_MANAGER] Successfully unloaded {model_name}. Freed memory.")
        except Exception as e:
            logger.error(f"[RAM_MANAGER] Failed to unload {model_name}: {e}")

    async def ensure_memory_for(self, incoming_model: str, expected_cost_gb: int):
        """
        Перед загрузкой тяжелой модели проверяем, хватит ли памяти.
        Если нет — выгружаем всё, кроме базовой (или вообще всё).
        """
        used_gb = self.get_memory_usage_gb()
        available = self.total_budget_gb - used_gb
        
        if available < expected_cost_gb:
            logger.warning(f"[RAM_MANAGER] Memory tight! Free: {available:.1f}GB, Need: {expected_cost_gb}GB.")
            # Unload any active secondary model
            for model in list(self.active_models):
                if model != settings.PRIMARY_MODEL and model != incoming_model:
                    await self.unload_model(model)
                    
        self.active_models.append(incoming_model)

global_ram_manager = RamManager()
