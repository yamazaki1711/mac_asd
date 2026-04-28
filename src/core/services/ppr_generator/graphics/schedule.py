"""
PPR Generator v0.1 — Календарный график производства работ (диаграмма Ганта).

Generates an А1 drawing with a Gantt chart table showing:
- Work stages and operations as rows
- Timeline bars with start/end dates
- Duration, labor intensity, crew size per row
"""

from __future__ import annotations

from typing import List

from ..schemas import GraphicResult, PPRInput, SectionResult, TTKResult


def generate_schedule(
    input: PPRInput,
    ttks: List[TTKResult],
    sections: List[SectionResult],
) -> GraphicResult:
    """Generate календарный график (диаграмма Ганта) — А1 format.

    Table-based Gantt chart showing construction schedule:
    stages, operations, dates, durations, resources.
    v0.1 placeholder — returns metadata only, no actual SVG.
    """
    schedule = input.construction_schedule
    stages_count = len(schedule.stages)
    ttks_count = len(ttks)

    # Rough row count: stages + TTK operations + title rows
    total_ops = sum(len(t.technology.main_operations) for t in ttks)
    total_rows = stages_count + total_ops
    page_count = max(1, (total_rows + 20) // 21)  # ~21 rows per А1

    description = (
        f"Календарный график производства работ (диаграмма Ганта) "
        f"по объекту «{input.object_name}» (шифр {input.project_code}). "
        f"Формат А1. {page_count} листов. "
        f"Период строительства: {schedule.construction_start} — "
        f"{schedule.construction_end} "
        f"({schedule.total_duration_days} дн.). "
        f"Этапов: {stages_count}, ТТК: {ttks_count}, "
        f"всего операций: {total_rows}. "
        f"Столбцы: № п/п, Наименование работ, Ед. изм., Объём, "
        f"Трудоёмкость (чел.-ч), Состав бригады (чел.), "
        f"Продолжительность (дн.), "
        f"График (календарная линейка по месяцам/неделям)."
    )

    return GraphicResult(
        graphic_id="schedule_001",
        title=f"Календарный график производства работ — {input.object_name}",
        format_size="А1",
        svg_path=None,
        dxf_path=None,
        page_count=page_count,
    )
