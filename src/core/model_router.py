import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ModelRouter:
    """
    Маршрутизатор моделей АСД v11.0.
    Выбирает оптимальную модель Ollama на основе типа задачи и доступных ресурсов.
    """

    MODELS = {
        "LARGE": "gemma-4-31b:q8_0",      # Основная тяжелая модель (Юрист, Сметчик)
        "MEDIUM": "qwen2.5:32b",          # Shared модель (Логист, Закупщик)
        "SMALL": "gemma-4-9b",            # Легкая модель (Делопроизводитель, Классификация)
        "VISION": "minicpm-v",            # Модель для OCR и анализа чертежей
        "EMBED": "bge-m3"                 # Векторная модель
    }

    def __init__(self):
        # В будущем здесь будет интеграция с RAMManager для проверки свободной памяти
        pass

    def get_model_for_task(self, task_type: str, thinking: bool = False) -> str:
        """Возвращает название модели для конкретной задачи."""
        
        # Юридическая экспертиза и сложные расчеты
        if task_type in ["legal_analysis", "estimate_creation", "contract_review"]:
            return self.MODELS["LARGE"]
            
        # Работа со снабжением и тендерами (Shared Qwen)
        if task_type in ["logistics_rfq", "tender_search", "price_parsing"]:
            return self.MODELS["MEDIUM"]
            
        # OCR и Визуальный анализ
        if task_type in ["ocr", "drawing_analysis", "vision"]:
            return self.MODELS["VISION"]
            
        # Простые задачи, классификация и регистрация
        if task_type in ["classification", "registration", "summary"]:
            return self.MODELS["SMALL"]
            
        # По умолчанию возвращаем Medium
        return self.MODELS["MEDIUM"]

    def should_use_thinking(self, task_type: str) -> bool:
        """Определяет, нужен ли режим рассуждения (Thinking Mode) для задачи."""
        critical_tasks = [
            "legal_analysis", 
            "contract_review", 
            "pd_analysis", 
            "estimate_compare"
        ]
        return task_type in critical_tasks

model_router = ModelRouter()
