"""
PPR Generator — TTK Base Class + Registry.

Базовый класс генератора технологической карты и реестр ТТК.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type

from ..schemas import (
    PPRInput, TTKResult, TTKScope, TTKTechnology, TTKQuality, 
    TTKResources, TTKOperation, TTKQualityCheck, TTKResource,
)


# =============================================================================
# Base TTK Generator
# =============================================================================

class BaseTTKGenerator(ABC):
    """
    Базовый класс генератора технологической карты.

    Использует паттерн «шаблонный метод»: generate() вызывает 4 абстрактных шага.
    Каждый подкласс реализует специфику конкретного вида работ.
    """

    @property
    @abstractmethod
    def work_type(self) -> str:
        """Вид работ (ключ из ttk_registry)."""
        ...

    @property
    @abstractmethod
    def title(self) -> str:
        """Человекочитаемое название ТТК."""
        ...

    @abstractmethod
    def generate_scope(self, input: PPRInput) -> TTKScope:
        """Область применения: где и когда применяется, объёмы."""
        ...

    @abstractmethod
    def generate_technology(self, input: PPRInput, scope: TTKScope) -> TTKTechnology:
        """Организация и технология выполнения работ."""
        ...

    @abstractmethod
    def generate_quality(self, input: PPRInput, technology: TTKTechnology) -> TTKQuality:
        """Требования к качеству и приёмке."""
        ...

    @abstractmethod
    def generate_resources(self, input: PPRInput, technology: TTKTechnology) -> TTKResources:
        """Потребность в материально-технических ресурсах."""
        ...

    def generate(self, input: PPRInput) -> TTKResult:
        """
        Полная генерация ТТК (шаблонный метод).

        Вызывает 4 шага в фиксированном порядке:
        scope → technology → quality → resources
        """
        scope = self.generate_scope(input)
        technology = self.generate_technology(input, scope)
        quality = self.generate_quality(input, technology)
        resources = self.generate_resources(input, technology)

        # Вычисляем агрегированные метрики
        total_labor = sum(
            op.duration_hours * len(op.workers)
            for op in technology.main_operations
        )
        total_machine = sum(
            op.duration_hours
            for op in technology.main_operations
            if op.equipment
        )

        return TTKResult(
            work_type=self.work_type,
            scope=scope,
            technology=technology,
            quality=quality,
            resources=resources,
            total_labor_intensity_person_hours=round(total_labor, 1),
            total_machine_hours=round(total_machine, 1),
        )

    # ── Helper methods for subclasses ──

    def _find_work_type(self, input: PPRInput, code: str):
        """Найти WorkTypeItem по коду."""
        for wt in input.work_types:
            if wt.code == code:
                return wt
        return None

    def _filter_materials(self, input: PPRInput, keywords: List[str]) -> List:
        """Найти спецификации материалов по ключевым словам."""
        result = []
        for spec in input.material_specs:
            for kw in keywords:
                if kw.lower() in spec.name.lower():
                    result.append(spec)
                    break
        return result

    def _make_op(self, seq: int, name: str, desc: str, 
                 equipment: List[str] = None, workers: List[str] = None,
                 duration: float = 1.0, checkpoint: bool = False) -> TTKOperation:
        return TTKOperation(
            seq_number=seq, name=name, description=desc,
            equipment=equipment or [], workers=workers or [],
            duration_hours=duration, quality_checkpoint=checkpoint,
        )

    def _make_qc(self, param: str, tolerance: str, method: str,
                  instrument: str = "", frequency: str = "каждая операция",
                  gost: str = "") -> TTKQualityCheck:
        return TTKQualityCheck(
            parameter=param, tolerance=tolerance, method=method,
            instrument=instrument, frequency=frequency, gost_ref=gost,
        )

    def _worker(self, name: str, qty: float = 1) -> TTKResource:
        return TTKResource(name=name, quantity=qty, unit="чел", category="worker")

    def _machine(self, name: str, qty: float = 1) -> TTKResource:
        return TTKResource(name=name, quantity=qty, unit="шт", category="machine")

    def _material(self, name: str, qty: float = 1, unit: str = "шт") -> TTKResource:
        return TTKResource(name=name, quantity=qty, unit=unit, category="material")

    def _tool(self, name: str, qty: float = 1) -> TTKResource:
        return TTKResource(name=name, quantity=qty, unit="шт", category="tool")


# =============================================================================
# TTK Registry
# =============================================================================

class TTKRegistry:
    """
    Реестр ТТК: маппинг вид работ → генератор ТТК.

    Использует паттерн Registry: генераторы регистрируются при импорте
    и автоматически подбираются для заданных видов работ.
    """

    _generators: Dict[str, Type[BaseTTKGenerator]] = {}

    @classmethod
    def register(cls, work_type: str, generator_cls: Type[BaseTTKGenerator]):
        """Зарегистрировать генератор ТТК для вида работ."""
        cls._generators[work_type] = generator_cls

    @classmethod
    def get(cls, work_type: str) -> Optional[Type[BaseTTKGenerator]]:
        """Получить генератор по коду вида работ."""
        return cls._generators.get(work_type)

    @classmethod
    def has(cls, work_type: str) -> bool:
        return work_type in cls._generators

    @classmethod
    def list_all(cls) -> List[str]:
        return list(cls._generators.keys())

    @classmethod
    def select_for_project(cls, work_types: List[str]) -> List[BaseTTKGenerator]:
        """
        Выбрать генераторы ТТК для заданных видов работ.

        Args:
            work_types: Список кодов видов работ

        Returns:
            Инстанциированные генераторы для каждого найденного вида работ
        """
        generators = []
        for wt_code in work_types:
            gen_cls = cls._generators.get(wt_code)
            if gen_cls:
                generators.append(gen_cls())
        return generators
