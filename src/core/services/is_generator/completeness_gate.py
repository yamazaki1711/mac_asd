"""
CompletenessGate — «Матрица Полноты» для устранения Риска 1 MAC_ASD.

Проверяет полноту пакета документов перед началом пайплайна ИС.
Блокирует генерацию, если критические документы отсутствуют или устарели.

Концепция:
    Каждый документ (DXF, геодезия, АОСР, проектная документация)
    имеет свой «уровень критичности» (MANDATORY / RECOMMENDED / OPTIONAL).
    CompletenessGate возвращает структурированный отчёт:
      - Список отсутствующих обязательных документов
      - Список предупреждений по рекомендуемым
      - Итоговый статус: PASS / WARN / BLOCK
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

logger = logging.getLogger(__name__)


# ─── Типы документов ──────────────────────────────────────────────────────────

class DocLevel(str, Enum):
    MANDATORY    = "MANDATORY"     # Без него пайплайн не запускается
    RECOMMENDED  = "RECOMMENDED"   # Предупреждение, но запуск разрешён
    OPTIONAL     = "OPTIONAL"      # Логируется, не влияет на статус


class GateStatus(str, Enum):
    PASS  = "PASS"    # Все обязательные документы в порядке
    WARN  = "WARN"    # Есть предупреждения (рекомендуемые отсутствуют)
    BLOCK = "BLOCK"   # Отсутствуют обязательные документы


# ─── Один элемент требования ──────────────────────────────────────────────────

@dataclass
class DocRequirement:
    """Описание одного требуемого документа."""
    key: str                      # Логический ключ (например, "design_dxf")
    label: str                    # Человекочитаемое название
    level: DocLevel               # Уровень критичности
    validator: Callable[[Path], bool] = field(default=lambda p: p.exists(), repr=False)
    hint: str = ""                # Подсказка, если документ не найден


@dataclass
class DocCheckResult:
    """Результат проверки одного документа."""
    requirement: DocRequirement
    path: Path | None
    passed: bool
    message: str


@dataclass
class GateReport:
    """Итоговый отчёт CompletenessGate."""
    status: GateStatus
    checks: list[DocCheckResult] = field(default_factory=list)

    @property
    def blocking_issues(self) -> list[DocCheckResult]:
        return [c for c in self.checks if not c.passed and c.requirement.level == DocLevel.MANDATORY]

    @property
    def warnings(self) -> list[DocCheckResult]:
        return [c for c in self.checks if not c.passed and c.requirement.level == DocLevel.RECOMMENDED]

    def summary(self) -> str:
        lines = [f"CompletenessGate: {self.status.value}"]
        for c in self.checks:
            icon = "✓" if c.passed else ("✗" if c.requirement.level == DocLevel.MANDATORY else "⚠")
            lines.append(f"  {icon} [{c.requirement.level.value}] {c.requirement.label}: {c.message}")
        return "\n".join(lines)

    def raise_if_blocked(self) -> None:
        """Вызывает исключение, если статус BLOCK."""
        if self.status == GateStatus.BLOCK:
            issues = "; ".join(c.requirement.label for c in self.blocking_issues)
            raise DocumentationIncompleteError(
                f"Пайплайн заблокирован. Отсутствуют обязательные документы: {issues}"
            )


class DocumentationIncompleteError(RuntimeError):
    """Вызывается CompletenessGate при отсутствии обязательных документов."""


# ─── Стандартные требования ИС ────────────────────────────────────────────────

def _is_non_empty_file(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0

def _is_dxf_or_dwg(path: Path) -> bool:
    return path.exists() and path.suffix.lower() in (".dxf", ".dwg") and path.stat().st_size > 0

def _is_survey_file(path: Path) -> bool:
    return path.exists() and path.suffix.lower() in (".csv", ".txt", ".xlsx", ".xls", ".gsi") and path.stat().st_size > 0


IS_DEFAULT_REQUIREMENTS: list[DocRequirement] = [
    DocRequirement(
        key="design_dxf",
        label="Проектный DXF/DWG",
        level=DocLevel.MANDATORY,
        validator=_is_dxf_or_dwg,
        hint="Необходим файл рабочих чертежей (КМ, КЖ и т.д.) в формате DXF или DWG.",
    ),
    DocRequirement(
        key="survey_report",
        label="Геодезический отчёт",
        level=DocLevel.MANDATORY,
        validator=_is_survey_file,
        hint="Файл замеров тахеометра (CSV, GSI, CREDO TXT, XLSX).",
    ),
    DocRequirement(
        key="aosr_template",
        label="Шаблон АОСР",
        level=DocLevel.RECOMMENDED,
        validator=_is_non_empty_file,
        hint="Шаблон АОСР (.docx) для автоподстановки данных.",
    ),
    DocRequirement(
        key="project_metadata",
        label="Метаданные проекта (JSON/YAML)",
        level=DocLevel.RECOMMENDED,
        validator=_is_non_empty_file,
        hint="Файл с реквизитами: заказчик, подрядчик, шифр проекта.",
    ),
    DocRequirement(
        key="sp_tolerances",
        label="Конфигурация допусков (YAML)",
        level=DocLevel.OPTIONAL,
        validator=_is_non_empty_file,
        hint="Файл переопределения допусков по СП 126.13330.2017.",
    ),
]


# ─── Главный класс ────────────────────────────────────────────────────────────

class CompletenessGate:
    """
    Проверяет полноту пакета документов для генерации ИС.

    Args:
        requirements: Список DocRequirement. None → IS_DEFAULT_REQUIREMENTS.
        extra_requirements: Дополнительные требования, добавляются к базовым.
    """

    def __init__(
        self,
        requirements: list[DocRequirement] | None = None,
        extra_requirements: list[DocRequirement] | None = None,
    ) -> None:
        self._requirements = list(requirements or IS_DEFAULT_REQUIREMENTS)
        if extra_requirements:
            self._requirements.extend(extra_requirements)

    # ──────────────────────────────────────────────────────────────────────────

    def check(self, doc_paths: dict[str, str | Path | None]) -> GateReport:
        """
        Выполняет проверку всех документов.

        Args:
            doc_paths: Словарь {key → путь}. Ключи должны совпадать
                       с DocRequirement.key. Отсутствующие ключи → None.

        Returns:
            GateReport
        """
        checks: list[DocCheckResult] = []
        has_block = False
        has_warn  = False

        for req in self._requirements:
            raw_path = doc_paths.get(req.key)
            path = Path(raw_path) if raw_path else None

            if path is None:
                passed  = False
                message = f"Не передан путь. {req.hint}"
            else:
                try:
                    passed = req.validator(path)
                    message = "OK" if passed else f"Файл не найден или пуст: {path}. {req.hint}"
                except Exception as e:
                    passed  = False
                    message = f"Ошибка проверки: {e}"

            checks.append(DocCheckResult(
                requirement=req,
                path=path,
                passed=passed,
                message=message,
            ))

            if not passed:
                if req.level == DocLevel.MANDATORY:
                    has_block = True
                elif req.level == DocLevel.RECOMMENDED:
                    has_warn = True

        status = GateStatus.BLOCK if has_block else (GateStatus.WARN if has_warn else GateStatus.PASS)
        report = GateReport(status=status, checks=checks)

        log_fn = logger.error if status == GateStatus.BLOCK else (logger.warning if status == GateStatus.WARN else logger.info)
        log_fn(report.summary())

        return report

    def check_and_raise(self, doc_paths: dict[str, str | Path | None]) -> GateReport:
        """check() + raise_if_blocked()."""
        report = self.check(doc_paths)
        report.raise_if_blocked()
        return report
