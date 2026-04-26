"""
Парсер геодезических отчётов для модуля ISGenerator.

Поддерживает форматы:
  - CSV стандартный (ID, X, Y, Z, DESC)
  - Leica GSI-8 / GSI-16 (формат тахеометра)
  - Экспорт из CREDO DAT (текстовый)
  - Excel (XLSX) с произвольными заголовками
"""
from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Импорт схем без цикличной зависимости
from src.core.services.is_generator.schemas import SurveyPoint, SurveyFormat


# ─── Детектор формата ─────────────────────────────────────────────────────────

def detect_format(file_path: str | Path) -> SurveyFormat:
    """Автоопределение формата геодезического отчёта по содержимому."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".xlsx", ".xls"):
        return SurveyFormat.XLSX

    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            first_lines = [f.readline() for _ in range(5)]
    except OSError as e:
        raise ValueError(f"Не удаётся открыть файл геодезии: {e}") from e

    content = "".join(first_lines)

    # Leica GSI: строки начинаются с блоков фиксированной длины "*110001..."
    if re.search(r"\*\d{6}[\+\-]", content):
        return SurveyFormat.LEICA_GSI

    # CREDO DAT: заголовок содержит "CREDO" или "ВНС"
    if "CREDO" in content.upper() or "ВНС" in content.upper():
        return SurveyFormat.CREDO_TXT

    # По умолчанию — CSV
    return SurveyFormat.CSV_STANDARD


# ─── Основной парсер ──────────────────────────────────────────────────────────

class GeodataParser:
    """
    Единая точка входа для разбора геодезических отчётов.
    Возвращает унифицированный список SurveyPoint.
    """

    def parse(
        self,
        file_path: str | Path,
        fmt: SurveyFormat | None = None,
    ) -> list[SurveyPoint]:
        """
        Парсит файл геодезического отчёта.

        Args:
            file_path: Путь к файлу.
            fmt: Формат файла. Если None — определяется автоматически.

        Returns:
            Список SurveyPoint.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Файл геодезии не найден: {path}")

        if fmt is None:
            fmt = detect_format(path)
            logger.info(f"Определён формат геодезического отчёта: {fmt}")

        parsers: dict[SurveyFormat, Callable] = {
            SurveyFormat.CSV_STANDARD: self._parse_csv,
            SurveyFormat.LEICA_GSI:    self._parse_leica_gsi,
            SurveyFormat.CREDO_TXT:    self._parse_credo_txt,
            SurveyFormat.XLSX:         self._parse_xlsx,
        }

        parser_fn = parsers.get(fmt)
        if parser_fn is None:
            raise ValueError(f"Неизвестный формат: {fmt}")

        points = parser_fn(path)
        logger.info(f"Распознано {len(points)} геодезических точек из {path.name}")
        return points

    # ─── CSV ──────────────────────────────────────────────────────────────────

    def _parse_csv(self, path: Path) -> list[SurveyPoint]:
        """
        Стандартный CSV: ID, X, Y, Z, DESCRIPTION
        Заголовок опционален. Разделители: запятая или точка с запятой.
        """
        points: list[SurveyPoint] = []
        with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
            sample = f.read(1024)
            f.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            reader = csv.reader(f, dialect)

            for line_num, row in enumerate(reader, start=1):
                # Пропускаем заголовок и пустые строки
                if not row or row[0].strip().upper() in (
                    "ID", "POINT", "POINT_ID", "ТОЧКА", "N", "№"
                ):
                    continue

                try:
                    point_id = str(row[0]).strip()
                    x = float(row[1].replace(",", "."))
                    y = float(row[2].replace(",", "."))
                    z = float(row[3].replace(",", ".")) if len(row) > 3 else 0.0
                    description = str(row[4]).strip() if len(row) > 4 else point_id
                    points.append(SurveyPoint(
                        point_id=point_id,
                        x=x, y=y, z=z,
                        description=description,
                        raw_line=",".join(row),
                    ))
                except (ValueError, IndexError) as e:
                    logger.warning(f"Строка {line_num}: пропущена ({e}): {row}")

        return points

    # ─── Leica GSI ────────────────────────────────────────────────────────────

    def _parse_leica_gsi(self, path: Path) -> list[SurveyPoint]:
        """
        Формат Leica GSI-8 и GSI-16.
        Каждая строка содержит блоки: *WI+значение
        WI 11 = Point ID, WI 81 = Easting, WI 82 = Northing, WI 83 = Elevation
        """
        points: list[SurveyPoint] = []
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                # Извлекаем блоки WI+данные
                blocks = re.findall(r"\*?(\d{2,3})\d*[\+\-](\S+)", line)
                if not blocks:
                    continue

                data: dict[str, str] = {wi: val for wi, val in blocks}

                try:
                    point_id = data.get("11", f"PT{line_num}").strip()
                    # Leica хранит координаты с масштабным фактором (обычно /1000)
                    x = float(data["81"]) / 1000.0
                    y = float(data["82"]) / 1000.0
                    z = float(data.get("83", "0")) / 1000.0
                    description = data.get("71", point_id).strip()
                    points.append(SurveyPoint(
                        point_id=point_id,
                        x=x, y=y, z=z,
                        description=description or point_id,
                        raw_line=line,
                    ))
                except (KeyError, ValueError) as e:
                    logger.warning(f"GSI строка {line_num}: пропущена ({e})")

        return points

    # ─── CREDO DAT ────────────────────────────────────────────────────────────

    def _parse_credo_txt(self, path: Path) -> list[SurveyPoint]:
        """
        Экспорт из CREDO DAT в текстовый формат.
        Пример строки: А/1    12345.234   54321.876   15.234
        """
        points: list[SurveyPoint] = []
        # Паттерн: метка + 3 числа (X, Y, Z)
        pattern = re.compile(
            r"^([А-Яа-яA-Za-z0-9/_\-\.]+)\s+"
            r"([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)"
        )

        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            for line_num, line in enumerate(f, start=1):
                m = pattern.match(line.strip())
                if m:
                    label, x_str, y_str, z_str = m.groups()
                    try:
                        points.append(SurveyPoint(
                            point_id=label,
                            x=float(x_str),
                            y=float(y_str),
                            z=float(z_str),
                            description=label,
                            raw_line=line.strip(),
                        ))
                    except ValueError as e:
                        logger.warning(f"CREDO строка {line_num}: {e}")

        return points

    # ─── XLSX ─────────────────────────────────────────────────────────────────

    def _parse_xlsx(self, path: Path) -> list[SurveyPoint]:
        """
        Excel-файл с гибкими заголовками.
        Ищет колонки по ключевым словам: ID/Точка, X/N/Восток, Y/E/Север, Z/H/Высота.
        """
        try:
            import openpyxl
        except ImportError:
            raise ImportError("Для парсинга XLSX нужен openpyxl: pip install openpyxl")

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))

        if not rows:
            return []

        # Определяем колонки по заголовку
        col_map = _detect_xlsx_columns(rows[0])
        if col_map is None:
            logger.warning("Не удалось определить колонки XLSX — используем позиции 0,1,2,3,4")
            col_map = {"id": 0, "x": 1, "y": 2, "z": 3, "desc": 4}

        points: list[SurveyPoint] = []
        for row_num, row in enumerate(rows[1:], start=2):
            try:
                val = lambda k: row[col_map[k]] if k in col_map and col_map[k] < len(row) else None
                pid = str(val("id") or f"PT{row_num}").strip()
                x = float(val("x") or 0)
                y = float(val("y") or 0)
                z = float(val("z") or 0)
                desc = str(val("desc") or pid).strip()
                points.append(SurveyPoint(
                    point_id=pid, x=x, y=y, z=z,
                    description=desc, raw_line=str(row),
                ))
            except (TypeError, ValueError) as e:
                logger.debug(f"XLSX строка {row_num}: пропущена ({e})")

        wb.close()
        return points


def _detect_xlsx_columns(header_row: tuple) -> dict[str, int] | None:
    """Определяет индексы колонок по заголовку (нечувствительно к регистру)."""
    if not header_row:
        return None

    KEY_ALIASES = {
        "id":   ["id", "точка", "name", "n", "no", "номер", "№", "point"],
        "x":    ["x", "easting", "восток", "е"],
        "y":    ["y", "northing", "север", "n"],
        "z":    ["z", "h", "elevation", "высота", "отметка"],
        "desc": ["desc", "description", "name", "метка", "label", "описание"],
    }

    col_map: dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        if cell is None:
            continue
        cell_lower = str(cell).lower().strip()
        for key, aliases in KEY_ALIASES.items():
            if key not in col_map and cell_lower in aliases:
                col_map[key] = idx
                break

    # Обязательные колонки
    if not all(k in col_map for k in ("id", "x", "y")):
        return None

    return col_map
