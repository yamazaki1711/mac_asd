"""
PPR Generator v0.1 — Строительный генеральный план (СГП).

Generates a site plan drawing (А1) showing:
- Construction site boundaries and security fences
- Temporary roads and access routes
- Warehouse and storage zones
- Crane placement and danger zones
- Utility connection points (temporary power, water, sewage)
- Administrative and welfare buildings
"""

from __future__ import annotations

from typing import List

from ..schemas import GraphicResult, PPRInput, SectionResult, TTKResult


def generate_site_plan(
    input: PPRInput,
    ttks: List[TTKResult],
    sections: List[SectionResult],
) -> GraphicResult:
    """Generate Строительный генеральный план (СГП) — А1 format.

    Describes the overall site layout: zones, roads, warehouses,
    crane positions, temporary utilities, and admin buildings.
    v0.1 placeholder — returns metadata only, no actual SVG.
    """
    # Build description from input data
    constraint_zones = [c.description for c in input.site_constraints]
    zones_desc = "; ".join(constraint_zones) if constraint_zones else "стандартная площадка"

    description = (
        f"СГП объекта «{input.object_name}» (шифр {input.project_code}). "
        f"Формат А1. Масштаб 1:500. "
        f"Отображены: границы стройплощадки, временное ограждение, "
        f"временные дороги с покрытием ж/б плит, склады открытого и закрытого хранения, "
        f"зоны складирования материалов и конструкций, "
        f"стоянка строительной техники, монтажный кран (опасная зона). "
        f"Временные инженерные сети: электроснабжение (ДЭС), водоснабжение, "
        f"канализация (биотуалеты), освещение площадки. "
        f"Административно-бытовые помещения: прорабская, бытовки, пункт обогрева. "
        f"Ограничения площадки: {zones_desc}. "
        f"Количество ТТК в комплекте: {len(ttks)}."
    )

    return GraphicResult(
        graphic_id="sgp_001",
        title=f"Строительный генеральный план — {input.object_name}",
        format_size="А1",
        svg_path=None,
        dxf_path=None,
        page_count=1,
    )
