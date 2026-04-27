"""
RDIndex — индекс листов рабочей документации.

Заполняется Делопроизводителем при регистрации РД.
Используется ПТО-агентом для поиска нужного листа под захватку/вид работ.

Хранение: PostgreSQL (таблица rd_sheets) + in-memory кэш для быстрых запросов.

v12.0 — поддержка DWG, DXF, PDF, сканов.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

from src.core.services.is_generator.schemas import RDFormat, RDSheetInfo


# ─── In-memory индекс ─────────────────────────────────────────────────────────

class RDIndex:
    """
    Индекс листов рабочей документации.

    Предоставляет поиск по:
      - шифру проекта
      - виду работ
      - захватке/разделу
      - наименованию листа (fuzzy)
      - формату файла

    Использование:
        index = RDIndex()
        index.add(RDSheetInfo(project_code="ПГС-2024-012", ...))
        sheets = index.lookup(work_type="бетонные", section="Захватка 1")
    """

    def __init__(self) -> None:
        self._sheets: list[RDSheetInfo] = []

    # ─── CRUD ──────────────────────────────────────────────────────────────────

    def add(self, sheet: RDSheetInfo) -> None:
        """Добавляет лист в индекс."""
        # Проверяем дубликат по (project_code, sheet_number)
        existing = self.find(
            project_code=sheet.project_code,
            sheet_number=sheet.sheet_number,
        )
        if existing:
            logger.warning(
                f"Лист {sheet.sheet_number} проекта {sheet.project_code} "
                f"уже в индексе — обновляем"
            )
            self._sheets.remove(existing)
        self._sheets.append(sheet)

    def remove(self, project_code: str, sheet_number: str) -> bool:
        """Удаляет лист из индекса. Возвращает True если найден и удалён."""
        sheet = self.find(project_code=project_code, sheet_number=sheet_number)
        if sheet:
            self._sheets.remove(sheet)
            return True
        return False

    def clear(self) -> None:
        """Очищает весь индекс."""
        self._sheets.clear()

    @property
    def size(self) -> int:
        return len(self._sheets)

    # ─── Поиск ─────────────────────────────────────────────────────────────────

    def find(
        self,
        project_code: str,
        sheet_number: str,
    ) -> Optional[RDSheetInfo]:
        """Точный поиск по шифру проекта и номеру листа."""
        for s in self._sheets:
            if s.project_code == project_code and s.sheet_number == sheet_number:
                return s
        return None

    def lookup(
        self,
        project_code: Optional[str] = None,
        work_type: Optional[str] = None,
        section: Optional[str] = None,
        format: Optional[RDFormat | str] = None,
        sheet_name_contains: Optional[str] = None,
    ) -> list[RDSheetInfo]:
        """
        Поиск листов по критериям (все параметры — опциональные фильтры).

        Args:
            project_code: Шифр проекта (точное совпадение).
            work_type: Вид работ (точное совпадение).
            section: Захватка/раздел (точное совпадение).
            format: Формат файла (DWG, DXF, PDF).
            sheet_name_contains: Подстрока в наименовании листа (case-insensitive).

        Returns:
            Список подходящих листов РД.
        """
        results: list[RDSheetInfo] = []

        fmt_value = format.value if isinstance(format, RDFormat) else format

        for s in self._sheets:
            if project_code and s.project_code != project_code:
                continue
            if work_type and s.work_type != work_type:
                continue
            if section and s.section != section:
                continue
            if fmt_value and s.format != fmt_value:
                continue
            if sheet_name_contains:
                if sheet_name_contains.lower() not in s.sheet_name.lower():
                    continue
            results.append(s)

        return results

    def lookup_best_for_is(
        self,
        work_type: str,
        section: str = "",
        project_code: str = "",
    ) -> Optional[RDSheetInfo]:
        """
        Наилучший лист РД для генерации ИС.

        Приоритет: DXF > DWG > PDF > SCAN.
        Если несколько листов — сначала точное совпадение по section,
        затем по work_type.
        """
        candidates = self.lookup(
            project_code=project_code or None,
            work_type=work_type,
        )
        if not candidates:
            # Ослабляем фильтр — ищем только по проекту
            candidates = self.lookup(project_code=project_code or None)

        if not candidates:
            return None

        # Фильтруем по захватке (если задана)
        section_matches = [s for s in candidates if s.section == section] if section else []
        pool = section_matches if section_matches else candidates

        # Приоритет по формату: DXF > DWG > PDF > SCAN
        format_priority = {"dxf": 0, "dwg": 1, "pdf": 2, "scan": 3}
        pool.sort(key=lambda s: format_priority.get(s.format, 99))

        return pool[0]

    # ─── Сериализация ──────────────────────────────────────────────────────────

    def to_json(self, path: str | Path) -> None:
        """Сохраняет индекс в JSON-файл."""
        data = [s.model_dump() for s in self._sheets]
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"RDIndex: сохранено {len(data)} листов в {path}")

    @classmethod
    def from_json(cls, path: str | Path) -> RDIndex:
        """Загружает индекс из JSON-файла."""
        index = cls()
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        for item in raw:
            index.add(RDSheetInfo(**item))
        logger.info(f"RDIndex: загружено {index.size} листов из {path}")
        return index

    # ─── Статистика ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Статистика индекса."""
        by_format: dict[str, int] = {}
        by_work_type: dict[str, int] = {}
        for s in self._sheets:
            by_format[s.format] = by_format.get(s.format, 0) + 1
            by_work_type[s.work_type] = by_work_type.get(s.work_type, 0) + 1
        return {
            "total_sheets": len(self._sheets),
            "by_format": by_format,
            "by_work_type": by_work_type,
        }

    def __repr__(self) -> str:
        return f"RDIndex(sheets={self.size})"
