"""
MCP Tools for Journal Reconstructor v2.

3 tools: reconstruct, export, verify.
Uses JournalReconstructor singleton + Evidence Graph.
"""

import json
import logging
from datetime import date as date_type
from typing import Any, Dict, List, Optional

from src.core.evidence_graph import evidence_graph
from src.core.journal_reconstructor import journal_reconstructor

logger = logging.getLogger(__name__)


async def asd_journal_reconstruct(
    project_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    section: str = "all",
) -> Dict[str, Any]:
    """Реконструировать Общий Журнал Работ (ОЖР) из Evidence Graph.

    Пять этапов: Extract → Fill → Infer → Detect → Generate.
    Цветовая разметка: 🟢 подтверждено, 🟡 высокая, 🔴 низкая, ⬜ лакуны.

    Args:
        project_id: ID проекта
        date_from: Начальная дата периода (ISO, YYYY-MM-DD)
        date_to: Конечная дата периода (ISO)
        section: Раздел ОЖР (по умолчанию "all")

    Returns:
        {"status": "ok", "journal": {...}, "entries_count": N, ...}
    """
    journal = journal_reconstructor.reconstruct(evidence_graph, project_id=project_id)

    # Filter by date range
    entries = journal.entries
    if date_from or date_to:
        entries = [
            e for e in entries
            if (not date_from or e.date >= date_from)
            and (not date_to or e.date <= date_to)
        ]

    entries_json = []
    for e in entries:
        entries_json.append({
            "date": e.date,
            "work_type": e.work_type,
            "color": e.color,
            "confidence_label": e.confidence_label,
            "description": e.description,
            "volume": e.volume,
            "unit": e.unit,
            "confidence": e.confidence,
            "source": e.source.value,
            "operators": e.operators,
            "materials": e.materials,
        })

    colors = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
    for e in entries:
        colors[e.color] = colors.get(e.color, 0) + 1

    return {
        "status": "ok",
        "project_id": project_id,
        "period": {
            "from": journal.start_date,
            "to": journal.end_date,
        },
        "total_entries": len(entries),
        "color_distribution": {
            "green (подтверждено)": colors["green"],
            "yellow (высокая)": colors["yellow"],
            "red (низкая)": colors["red"],
            "gray (лакуны)": colors["gray"],
        },
        "coverage_pct": round(journal.coverage * 100, 1),
        "reconstruction_confidence": round(
            sum(e.confidence for e in entries) / max(len(entries), 1), 3
        ),
        "summary": journal.summary(),
        "entries": entries_json,
    }


async def asd_journal_export(
    project_id: str,
    format: str = "json",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Экспортировать реконструированный ОЖР в JSON или табличный формат.

    Args:
        project_id: ID проекта
        format: "json" или "table" (список списков для XLSX)
        date_from: Начальная дата (ISO)
        date_to: Конечная дата (ISO)
        output_path: Путь для сохранения файла (опционально)

    Returns:
        {"status": "ok", "format": "...", "entries_exported": N, ...}
    """
    journal = journal_reconstructor.reconstruct(evidence_graph, project_id=project_id)

    entries = journal.entries
    if date_from or date_to:
        entries = [
            e for e in entries
            if (not date_from or e.date >= date_from)
            and (not date_to or e.date <= date_to)
        ]

    if format == "json":
        export_data = [
            {
                "date": e.date,
                "work_type": e.work_type,
                "description": e.description,
                "volume": e.volume,
                "unit": e.unit,
                "confidence": e.confidence,
                "color": e.color,
                "source": e.source.value,
                "operators": e.operators,
                "materials": e.materials,
            }
            for e in entries
        ]
        content = json.dumps(export_data, ensure_ascii=False, indent=2, default=str)
    elif format == "table":
        # Table format: list of rows with headers
        export_data = {
            "headers": [
                "Дата", "Вид работ", "Описание", "Объём", "Ед.", "Уверенность",
                "Цвет", "Источник", "Исполнители", "Материалы",
            ],
            "rows": [
                [
                    e.date, e.work_type, e.description, e.volume, e.unit,
                    e.confidence, e.color, e.source.value, e.operators, e.materials,
                ]
                for e in entries
            ],
        }
        content = json.dumps(export_data, ensure_ascii=False, indent=2, default=str)
    else:
        return {
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": f"Unsupported format: {format}. Use 'json' or 'table'.",
        }

    # Save to file if output_path specified
    if output_path:
        from pathlib import Path
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    return {
        "status": "ok",
        "format": format,
        "entries_exported": len(entries),
        "content": content if not output_path else None,
        "file_path": output_path,
        "message": f"ОЖР экспортирован. {len(entries)} записей."
        if output_path else None,
    }


async def asd_journal_verify(
    project_id: str,
    strict_mode: bool = False,
) -> Dict[str, Any]:
    """Верифицировать реконструированный ОЖР по известным фактам.

    Сверяет записи журнала с подтверждёнными документами в графе.
    Выявляет расхождения между журналом и актами/сертификатами.

    Args:
        project_id: ID проекта
        strict_mode: Строгий режим — флагует любые расхождения

    Returns:
        {"status": "ok", "total_entries": N, "verified": M, "discrepancies": [...]}
    """
    journal = journal_reconstructor.reconstruct(evidence_graph, project_id=project_id)
    from src.core.evidence_graph import WorkUnitStatus

    discrepancies = []
    verified_count = 0
    work_units = evidence_graph.get_work_units()

    # Build lookup: date → work units with AOSR
    confirmed_dates: Dict[str, List[str]] = {}
    for wu in work_units:
        if wu.get("status") in (WorkUnitStatus.COMPLETED.value,
                                 WorkUnitStatus.CONFIRMED.value):
            wu_date = wu.get("end_date") or wu.get("start_date")
            if wu_date:
                if wu_date not in confirmed_dates:
                    confirmed_dates[wu_date] = []
                confirmed_dates[wu_date].append(wu.get("work_type", ""))

    for entry in journal.entries:
        # Skip lacunae — they're expected gaps
        if entry.confidence < 0.4:
            continue

        # Check if journal entry corresponds to a confirmed WorkUnit
        if entry.date in confirmed_dates:
            entry_types = confirmed_dates[entry.date]
            if entry.work_type in entry_types:
                verified_count += 1
                continue

        # Look for nearby confirmed dates (±3 days)
        matched = False
        for wu in work_units:
            wu_date = wu.get("end_date") or wu.get("start_date")
            if not wu_date:
                continue
            try:
                delta = abs(
                    date_type.fromisoformat(entry.date)
                    - date_type.fromisoformat(wu_date)
                )
                if delta.days <= 3 and wu.get("work_type") == entry.work_type:
                    matched = True
                    break
            except (ValueError, TypeError):
                continue

        if not matched and entry.confidence >= 0.6:
            if strict_mode or entry.confidence >= 0.8:
                discrepancies.append({
                    "entry_date": entry.date,
                    "work_type": entry.work_type,
                    "description": entry.description,
                    "issue": (
                        "Запись ОЖР есть, но АОСР не найден"
                        if entry.confidence >= 0.8
                        else "Низкая уверенность, нет подтверждающего документа"
                    ),
                    "confidence": entry.confidence,
                })

    return {
        "status": "ok",
        "project_id": project_id,
        "total_entries": len(journal.entries),
        "verified_entries": verified_count,
        "discrepancies": discrepancies,
        "discrepancy_count": len(discrepancies),
        "verification_pct": round(
            verified_count / max(len(journal.entries), 1) * 100, 1
        ),
        "strict_mode": strict_mode,
    }
