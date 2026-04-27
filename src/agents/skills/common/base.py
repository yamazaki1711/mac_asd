"""
MAC_ASD v12.0 — Skill Base Classes.

Унифицированный интерфейс для всех навыков агентов.
Каждый навык:
  - Имеет уникальный ID (например, PTO_WorkSpec)
  - Принимает структурированный вход (dict)
  - Возвращает SkillResult с результатом и метаданными
  - Может вызывать LLM через llm_engine для аналитических задач
"""

import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum


logger = logging.getLogger(__name__)


class SkillStatus(str, Enum):
    """Статус выполнения навыка."""
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"
    REJECTED = "rejected"  # Запрос отклонён (например, вне специализации)


@dataclass
class SkillResult:
    """
    Результат выполнения навыка.

    Attributes:
        status: Статус выполнения
        skill_id: ID навыка
        data: Основные данные результата
        errors: Список ошибок
        warnings: Список предупреждений
        metadata: Метаданные (время выполнения, модель и т.д.)
    """
    status: SkillStatus
    skill_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status == SkillStatus.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "skill_id": self.skill_id,
            "data": self.data,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


class SkillBase:
    """
    Базовый класс для всех навыков агентов.

    Подклассы должны реализовать:
      - skill_id: уникальный идентификатор
      - description: описание навыка
      - execute(): основная логика навыка
    """

    skill_id: str = "base"
    description: str = "Base skill"
    agent: str = "unknown"  # pto | delo | ...

    def __init__(self, llm_engine=None):
        """
        Args:
            llm_engine: Экземпляр LLMEngine для вызовов модели (опционально)
        """
        self._llm = llm_engine
        self._logger = logging.getLogger(f"skill.{self.skill_id}")

    async def execute(self, params: Dict[str, Any]) -> SkillResult:
        """
        Выполнить навык с заданными параметрами.

        Args:
            params: Входные параметры навыка (зависят от конкретного навыка)

        Returns:
            SkillResult с результатом выполнения
        """
        start_time = time.time()
        try:
            # Валидация входных данных
            validation = self.validate_input(params)
            if not validation["valid"]:
                return SkillResult(
                    status=SkillStatus.ERROR,
                    skill_id=self.skill_id,
                    errors=validation["errors"],
                )

            # Выполнение основной логики
            result = await self._execute(params)

            # Добавление метаданных
            elapsed = time.time() - start_time
            result.metadata["elapsed_sec"] = round(elapsed, 3)
            result.metadata["skill_id"] = self.skill_id
            result.metadata["agent"] = self.agent

            return result

        except Exception as e:
            self._logger.exception(f"Skill {self.skill_id} failed: {e}")
            return SkillResult(
                status=SkillStatus.ERROR,
                skill_id=self.skill_id,
                errors=[str(e)],
                metadata={"elapsed_sec": round(time.time() - start_time, 3)},
            )

    async def _execute(self, params: Dict[str, Any]) -> SkillResult:
        """Основная логика навыка. Переопределяется в подклассах."""
        raise NotImplementedError("Subclasses must implement _execute()")

    def validate_input(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Валидация входных параметров.
        Переопределяется в подклассах для специфичной валидации.

        Returns:
            {"valid": True} или {"valid": False, "errors": [...]}
        """
        return {"valid": True}

    def _llm_available(self) -> bool:
        """Проверка доступности LLM."""
        return self._llm is not None


class SkillRegistry:
    """
    Реестр навыков. Хранит все зарегистрированные навыки и позволяет
    находить их по ID или по агенту.
    """

    def __init__(self):
        self._skills: Dict[str, SkillBase] = {}

    def register(self, skill: SkillBase) -> None:
        """Зарегистрировать навык."""
        self._skills[skill.skill_id] = skill
        logger.info(f"Skill registered: {skill.skill_id} ({skill.agent})")

    def get(self, skill_id: str) -> Optional[SkillBase]:
        """Получить навык по ID."""
        return self._skills.get(skill_id)

    def list_by_agent(self, agent: str) -> List[SkillBase]:
        """Получить все навыки агента."""
        return [s for s in self._skills.values() if s.agent == agent]

    def list_all(self) -> List[SkillBase]:
        """Получить все зарегистрированные навыки."""
        return list(self._skills.values())

    def __contains__(self, skill_id: str) -> bool:
        return skill_id in self._skills
