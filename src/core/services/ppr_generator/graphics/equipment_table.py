"""
PPR Generator v0.1 — Таблица потребности в машинах и механизмах.

Generates an А1 drawing with a table listing all construction
machinery and equipment required for the project:
- Machine name, brand/model, quantity
- Technical characteristics (capacity, power, weight)
- Purpose and work types assigned
"""

from __future__ import annotations

from typing import List

from ..schemas import GraphicResult, PPRInput, SectionResult, TTKResult


def generate_equipment_table(
    input: PPRInput,
    ttks: List[TTKResult],
    sections: List[SectionResult],
) -> GraphicResult:
    """Generate таблица потребности в машинах и механизмах — А1 format.

    Lists all construction equipment needed with technical specs.
    v0.1 placeholder — returns metadata only, no actual SVG.
    """
    # Collect unique machines across all TTKs
    machines_set: set[str] = set()
    for t in ttks:
        for m in t.resources.machines:
            machines_set.add(m.name)
    machine_count = len(machines_set)

    page_count = max(1, (machine_count + 12) // 13)  # ~13 rows per А1

    machines_list = ", ".join(sorted(machines_set)) if machines_set else "по проекту"

    description = (
        f"Таблица потребности в машинах, механизмах и средствах малой механизации "
        f"по объекту «{input.object_name}» (шифр {input.project_code}). "
        f"Формат А1. {page_count} листов. "
        f"Всего позиций техники: {machine_count}. "
        f"Техника: {machines_list}. "
        f"Столбцы таблицы: № п/п, Наименование, Марка/модель, "
        f"Кол-во, Техническая характеристика (грузоподъёмность/мощность/"
        f"вместимость/масса), Назначение, Вид работ, Примечание."
    )

    return GraphicResult(
        graphic_id="equipment_table_001",
        title=f"Ведомость потребности в машинах и механизмах — {input.object_name}",
        format_size="А1",
        svg_path=None,
        dxf_path=None,
        page_count=page_count,
    )
