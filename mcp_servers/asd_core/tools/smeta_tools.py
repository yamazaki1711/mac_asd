"""
ASD Core — Сметчик MCP Tools.

Инструменты для расчёта и проверки смет, обёрнутые вокруг Skills:
  - SmetaCalc: расчёт локальной сметы (ПЗ + НР + СП + НДС)
  - SmetaRateLookup: поиск расценок ФЕР/ГЭСН
  - SmetaVorCompare: сверка ВОР со сметой
"""

from fastmcp import tool
from typing import Dict, Any, List
import asyncio

from src.agents.skills.smeta.calc import SmetaCalc
from src.agents.skills.smeta.rate_lookup import SmetaRateLookup
from src.agents.skills.smeta.vor_compare import SmetaVorCompare

# Skill instances (stateless, no LLM needed)
_calc = SmetaCalc()
_rate_lookup = SmetaRateLookup()
_vor_compare = SmetaVorCompare()


@tool()
async def asd_estimate_compare(
    vor_items: List[Dict[str, Any]],
    estimate_items: List[Dict[str, Any]],
    volume_tolerance_pct: float = 5.0,
) -> Dict[str, Any]:
    """Сверка ведомости объёмов работ (ВОР) со сметным расчётом. Выявляет расхождения по объёмам, единицам и стоимости."""
    result = await _vor_compare.execute({
        "action": "compare",
        "vor_items": vor_items,
        "estimate_items": estimate_items,
        "volume_tolerance_pct": volume_tolerance_pct,
    })
    return result.to_dict()


@tool()
async def asd_create_lsr(
    sections: List[Dict[str, Any]],
    project_id: str = "unknown",
    vat_pct: float = 20.0,
) -> Dict[str, Any]:
    """Создание локальной сметы (ЛСР) из списка позиций с расчётом ПЗ, НР, СП, НДС."""
    result = await _calc.execute({
        "action": "calculate",
        "sections": sections,
        "project_id": project_id,
        "vat_pct": vat_pct,
    })
    return result.to_dict()


@tool()
async def asd_supplement_estimate(
    section_totals: List[Dict[str, Any]],
    additional_costs: List[Dict[str, Any]] = None,
    vat_pct: float = 20.0,
) -> Dict[str, Any]:
    """Дополнение сметы: подведение итогов с дополнительными затратами (временные здания, зимнее удорожание и т.п.)."""
    result = await _calc.execute({
        "action": "totals",
        "section_totals": section_totals,
        "additional_costs": additional_costs or [],
        "vat_pct": vat_pct,
    })
    return result.to_dict()


@tool()
async def asd_rate_lookup(code: str = "", query: str = "", work_type: str = "") -> Dict[str, Any]:
    """Поиск расценки ФЕР/ГЭСН по коду, описанию или виду работ."""
    if code:
        result = await _rate_lookup.execute({"action": "lookup", "code": code})
    elif query:
        result = await _rate_lookup.execute({"action": "search", "query": query, "work_type": work_type or None})
    elif work_type:
        result = await _rate_lookup.execute({"action": "list_by_work", "work_type": work_type})
    else:
        return {"status": "error", "errors": ["Укажите code, query или work_type"]}
    return result.to_dict()


@tool()
async def asd_get_minstroy_index(work_type: str = "") -> Dict[str, Any]:
    """Получить актуальный индекс изменения сметной стоимости Минстроя по виду работ."""
    result = await _rate_lookup.execute({
        "action": "get_index",
        "work_type": work_type or None,
    })
    return result.to_dict()
