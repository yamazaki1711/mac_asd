"""
ASD v11.0 — Model Router.

Routes task types to appropriate models based on current profile configuration.
Delegates model selection to Settings.get_model_config().

Usage:
    from src.core.model_router import model_router
    model_name = model_router.get_model_for_task("legal_analysis")
"""

import logging
from typing import Dict, Optional

from src.config import settings

logger = logging.getLogger(__name__)


class ModelRouter:
    """
    Маршрутизатор моделей ASD v11.0.

    Определяет, какой агент (и соответственно модель) обрабатывает
    конкретный тип задачи. Конфигурация моделей берётся из профиля
    (dev_linux / mac_studio) через Settings.get_model_config().

    Дополнительная функция — определяет необходимость Thinking Mode
    для сложных аналитических задач.
    """

    # Mapping: task_type → agent_name
    TASK_TO_AGENT: Dict[str, str] = {
        # Юридическая экспертиза
        "legal_analysis": "legal",
        "contract_review": "legal",
        "normative_search": "legal",
        "claim_generation": "legal",
        "protocol_generation": "legal",

        # Сметные расчёты
        "estimate_creation": "smeta",
        "estimate_compare": "smeta",
        "rate_lookup": "smeta",
        "lsr_creation": "smeta",

        # ПТО / Vision
        "ocr": "pto",
        "drawing_analysis": "pto",
        "vision": "pto",
        "vor_extraction": "pto",
        "vor_check": "pto",
        "pd_analysis": "pto",

        # Закупки
        "tender_search": "procurement",
        "profitability_analysis": "procurement",
        "price_parsing": "procurement",

        # Логистика
        "logistics_rfq": "logistics",
        "vendor_sourcing": "logistics",
        "quote_comparison": "logistics",

        # Делопроизводитель
        "classification": "archive",
        "registration": "archive",
        "summary": "archive",
        "letter_generation": "archive",

        # Оркестратор
        "routing": "pm",
        "verdict": "pm",
    }

    # Tasks requiring Thinking Mode (extended reasoning)
    THINKING_TASKS = {
        "legal_analysis",
        "contract_review",
        "pd_analysis",
        "estimate_compare",
        "vor_check",
    }

    def get_model_for_task(self, task_type: str) -> str:
        """
        Возвращает название модели для конкретного типа задачи.

        Args:
            task_type: Тип задачи (e.g. "legal_analysis", "vor_extraction")

        Returns:
            Model identifier string (e.g. "qwen3:32b" or "mlx-community/Qwen3-32B-Instruct-4bit")
        """
        agent = self.TASK_TO_AGENT.get(task_type)
        if not agent:
            logger.warning(f"Unknown task type: {task_type}. Defaulting to 'smeta' agent.")
            agent = "smeta"

        config = settings.get_model_config(agent)
        return config["model"]

    def get_engine_for_task(self, task_type: str) -> str:
        """
        Возвращает движок (ollama/mlx) для конкретного типа задачи.

        Args:
            task_type: Тип задачи

        Returns:
            Engine name: "ollama" or "mlx"
        """
        agent = self.TASK_TO_AGENT.get(task_type, "smeta")
        config = settings.get_model_config(agent)
        return config["engine"]

    def get_agent_for_task(self, task_type: str) -> str:
        """
        Возвращает имя агента для типа задачи.

        Args:
            task_type: Тип задачи

        Returns:
            Agent name (e.g. "legal", "pto")
        """
        return self.TASK_TO_AGENT.get(task_type, "smeta")

    def should_use_thinking(self, task_type: str) -> bool:
        """
        Определяет, нужен ли режим рассуждения (Thinking Mode) для задачи.
        Thinking Mode замедляет ответ, но повышает качество аналитики.
        """
        return task_type in self.THINKING_TASKS


model_router = ModelRouter()
