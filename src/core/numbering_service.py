"""
ASD v13.0 — NumberingService (Сквозная нумерация документов).

Автономный модуль нумерации документов по проекту.
Хранит состояние в JSON-файле для персистентности между сессиями.

Используется:
  - DeloAgent (регистрация входящих документов)
  - OutputPipeline (нумерация исходящих документов)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


@dataclass
class DocumentNumber:
    """Номер документа в системе нумерации заказчика."""
    prefix: str       # "АОСР", "КС2", "КС3", "ВХ", "ИСХ"
    project_code: str  # Код проекта у заказчика (напр. "СК-2025")
    sequence: int      # Порядковый номер
    suffix: str = ""   # Доп. суффикс (напр. "/1" для доработки)

    def __str__(self) -> str:
        base = f"{self.prefix}-{self.project_code}-{self.sequence:04d}"
        return base + self.suffix if self.suffix else base


class NumberingService:
    """
    Сквозная нумерация документов по проекту.

    Хранит состояние в ~/.hermes/asd_numbering.json.
    Поддерживает атомарное обновление счётчиков.
    """

    _instance = None
    _state: Dict[str, Dict[str, int]] = {}  # {project_code: {prefix: last_seq}}

    def __init__(self, state_file: str = ""):
        self.state_file = Path(state_file or os.path.expanduser("~/.hermes/asd_numbering.json"))
        self._load()

    def _load(self) -> None:
        try:
            if self.state_file.exists():
                with open(self.state_file) as f:
                    self._state = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.debug("Failed to load numbering state: %s", e)
            self._state = {}

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self._state, f, indent=2)

    def next_number(self, project_code: str, prefix: str) -> DocumentNumber:
        """Выдать следующий номер для префикса в проекте."""
        if project_code not in self._state:
            self._state[project_code] = {}
        if prefix not in self._state[project_code]:
            self._state[project_code][prefix] = 0
        self._state[project_code][prefix] += 1
        self._save()
        return DocumentNumber(
            prefix=prefix,
            project_code=project_code,
            sequence=self._state[project_code][prefix],
        )

    def get_last_number(self, project_code: str, prefix: str) -> int:
        """Получить последний выданный номер (без инкремента)."""
        return self._state.get(project_code, {}).get(prefix, 0)

    def set_last_number(self, project_code: str, prefix: str, number: int) -> None:
        """Установить счётчик (для ручной коррекции)."""
        if project_code not in self._state:
            self._state[project_code] = {}
        self._state[project_code][prefix] = number
        self._save()


# Модульный синглтон
numbering_service = NumberingService()
