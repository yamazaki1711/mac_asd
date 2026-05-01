"""
PPR Generator — Event Bus.

Асинхронная событийная система для отслеживания прогресса генерации ППР.
Позволяет фронтенду (API) получать обновления о статусе генерации в реальном времени.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class PPRStage(str, Enum):
    INPUT_ANALYSIS = "input_analysis"
    SECTIONS_GENERATING = "sections_generating"
    TTK_GENERATING = "ttk_generating"
    GRAPHICS_GENERATING = "graphics_generating"
    COMPILING = "compiling"
    DONE = "done"
    ERROR = "error"


@dataclass
class PPREvent:
    stage: PPRStage
    progress_pct: float  # 0.0 - 100.0
    message: str
    section_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


Callback = Callable[[PPREvent], Any]


class PPRBus:
    """
    Событийная шина PPR Generator.

    Подписчики получают события о:
    - Начале/окончании каждого этапа
    - Прогрессе генерации разделов
    - Предупреждениях и ошибках
    """

    def __init__(self):
        self._subscribers: List[Callback] = []
        self._events: List[PPREvent] = []

    def subscribe(self, callback: Callback):
        self._subscribers.append(callback)

    def emit(self, event: PPREvent):
        self._events.append(event)
        logger.info(f"[PPR:{event.stage.value}] {event.progress_pct:.0f}% — {event.message}")
        for cb in self._subscribers:
            try:
                cb(event)
            except Exception as e:
                logger.error(f"Event callback failed: {e}")

    def emit_sync(self, stage: PPRStage, progress_pct: float, message: str, **details):
        """Синхронная эмиссия события (для использования в асинхронных контекстах)."""
        self.emit(PPREvent(stage=stage, progress_pct=progress_pct, message=message, details=details))

    def get_history(self) -> List[PPREvent]:
        return list(self._events)

    def clear(self):
        self._events.clear()
