"""
PPR Generator v0.1 — Технологические схемы (per TTK).

Generates one А1 drawing per TTK showing:
- Work zone boundary and dimensions
- Sequence of operations (numbered)
- Equipment and machinery placement
- Temporary structures (scaffolding, formwork, etc.)
- Loading/unloading zones
"""

from __future__ import annotations

from typing import List

from ..schemas import GraphicResult, PPRInput, SectionResult, TTKResult


def generate_tech_schemes(
    input: PPRInput,
    ttks: List[TTKResult],
    sections: List[SectionResult],
) -> GraphicResult:
    """Generate технологические схемы for each TTK — А1 format.

    One drawing per TTK type describing the work technology visually:
    operation sequence, equipment layout, temporary structures.
    v0.1 placeholder — returns metadata only, no actual SVG.
    """
    page_count = max(len(ttks), 1)  # at least 1 page, 1 per TTK
    ttk_names = [t.work_type for t in ttks]
    names_list = ", ".join(ttk_names) if ttk_names else "общие работы"

    description = (
        f"Комплект технологических схем по объекту «{input.object_name}» "
        f"(шифр {input.project_code}). "
        f"Формат А1. {page_count} листов (по одному на каждую ТТК). "
        f"Виды работ: {names_list}. "
        f"Каждая схема содержит: границы рабочей зоны, расстановку техники "
        f"и механизмов, последовательность операций (1-2-3...), "
        f"схемы временных сооружений (леса, опалубка), "
        f"зоны погрузки/разгрузки, направления движения техники и рабочих. "
        f"Масштаб 1:100 (фрагменты 1:50)."
    )

    return GraphicResult(
        graphic_id="tech_schemes_001",
        title=f"Технологические схемы производства работ — {input.object_name}",
        format_size="А1",
        svg_path=None,
        dxf_path=None,
        page_count=page_count,
    )
