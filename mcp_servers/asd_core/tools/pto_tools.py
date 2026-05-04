"""
MAC_ASD v12.0 — PTO MCP Tools.

Инструменты для агента ПТО:
  - asd_get_work_type_info: Полная информация по виду работ (состав ИД)
  - asd_list_work_types: Иерархический список всех видов работ
  - asd_get_tech_sequence: Технологическая последовательность оформления
  - asd_get_date_rules: Правила датировки документов
  - asd_get_input_control: Требования входного контроля (общие)
  - asd_id_completeness: Проверка комплектности ИД по виду работ
  - asd_vor_check: Сверка ВОР с ПД
  - asd_pd_analysis: Комплексный анализ ПД
  - asd_generate_act: Генерация актов (АОСР, АООК, акты приёмки)

Источник данных: Пособие по ИД, Выпуск №2 (Сарвартдинова, ВАШ ФОРМАТ, 2026).
Покрытие: все 20 видов работ по Главе 5 Пособия.
"""

import logging
from typing import Any, Dict, List, Optional

from src.core.llm_engine import llm_engine

logger = logging.getLogger(__name__)


async def asd_get_work_type_info(work_type: str) -> Dict[str, Any]:
    """
    Полная информация по виду работ: состав ИД, журналы, акты, схемы,
    сертификаты, НТД, технологическая последовательность, правила датировки.

    Args:
        work_type: Вид работ (строка из WorkType, напр. 'фундаменты_монолитные')

    Returns:
        Полный состав исполнительной документации
    """
    from src.agents.skills.pto.work_spec import PTO_WorkSpec

    skill = PTO_WorkSpec()
    result = await skill._execute({
        "work_type": work_type,
        "include_regulations": True,
        "include_tech_sequence": True,
        "include_date_rules": True,
    })

    return {
        "status": "success" if result.status.value == "success" else "error",
        "work_type": work_type,
        "data": result.data,
        "errors": [e for e in (result.errors or [])],
    }


async def asd_list_work_types() -> Dict[str, Any]:
    """
    Иерархический список всех видов работ с категориями.

    Returns:
        Дерево категорий и полный перечень видов работ
    """
    from src.agents.skills.pto.work_spec import PTO_WorkSpec

    skill = PTO_WorkSpec()
    result = await skill.list_work_types()

    return {
        "status": "success",
        "data": result.data,
    }


async def asd_get_tech_sequence(work_type: str) -> Dict[str, Any]:
    """
    Технологическая последовательность оформления документов для вида работ.

    Args:
        work_type: Вид работ

    Returns:
        Последовательность шагов с указанием документов
    """
    from src.agents.skills.pto.work_spec import PTO_WorkSpec

    skill = PTO_WorkSpec()
    result = await skill.get_tech_sequence(work_type)

    return {
        "status": "success" if result.status.value == "success" else "error",
        "work_type": work_type,
        "data": result.data,
        "errors": [e for e in (result.errors or [])],
    }


async def asd_get_date_rules(work_type: str) -> Dict[str, Any]:
    """
    Правила датировки документов для вида работ.

    Args:
        work_type: Вид работ

    Returns:
        Правила датировки с примерами и ссылками на НТД
    """
    from src.agents.skills.pto.work_spec import PTO_WorkSpec

    skill = PTO_WorkSpec()
    result = await skill.get_date_rules(work_type)

    return {
        "status": "success" if result.status.value == "success" else "error",
        "work_type": work_type,
        "data": result.data,
        "errors": [e for e in (result.errors or [])],
    }


async def asd_get_input_control() -> Dict[str, Any]:
    """
    Требования входного контроля (общие для всех видов работ).

    Возвращает перечень документов входного контроля, правила,
    ссылки на нормативные источники.

    Returns:
        Требования входного контроля по СП 543.1325800.2024
    """
    from src.agents.skills.pto.work_spec import PTO_WorkSpec

    skill = PTO_WorkSpec()
    result = await skill.get_input_control()

    return {
        "status": "success",
        "data": result.data,
    }


async def asd_id_completeness(
    project_id: str,
    work_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Проверка комплектности ИД по видам работ.

    Сравнивает фактический комплект документов с перечнем,
    установленным для каждого вида работ на основе Пособия 2026.
    Покрывает все 20 видов работ.

    Args:
        project_id: Идентификатор проекта
        work_types: Список видов работ (из WorkType). Если None — проверяются все.

    Returns:
        Отчёт о комплектности с перечнем требуемых документов по видам работ.
        Каждый документ помечен: обязательный (mandatory=True),
        условный (conditional=...), необязательный (mandatory=False).
    """
    from src.agents.skills.pto.work_spec import PTO_WorkSpec, WorkType

    skill = PTO_WorkSpec()

    if work_types is None:
        work_types = [wt.value for wt in WorkType]

    completeness: Dict[str, Any] = {}
    total_required = 0

    for wt in work_types:
        result = await skill._execute({
            "work_type": wt,
            "include_regulations": False,
            "include_tech_sequence": False,
            "include_date_rules": False,
        })

        if result.status.value != "success":
            completeness[wt] = {"error": f"Неизвестный вид работ: {wt}"}
            continue

        data = result.data
        summary = data.get("summary", {})

        # Собираем все требуемые документы с пометками обязательности
        required_docs = []

        for j in data.get("journals", []):
            required_docs.append({
                "category": "journal",
                "name": j["name"],
                "mandatory": j.get("mandatory", True),
                "conditional": j.get("conditional"),
            })
            total_required += 1

        for a in data.get("hidden_works_acts", []):
            required_docs.append({
                "category": "act_hidden",
                "name": a["name"],
                "mandatory": a.get("mandatory", True),
                "conditional": a.get("conditional"),
            })
            total_required += 1

        for a in data.get("responsible_acts", []):
            required_docs.append({
                "category": "act_responsible",
                "name": a["name"],
                "mandatory": a.get("mandatory", True),
            })
            total_required += 1

        for a in data.get("acceptance_acts", []):
            required_docs.append({
                "category": "act_acceptance",
                "name": a["name"],
                "mandatory": a.get("mandatory", True),
            })
            total_required += 1

        for s in data.get("executive_schemes", []):
            required_docs.append({
                "category": "scheme",
                "name": s["name"],
                "mandatory": s.get("mandatory", True),
                "conditional": s.get("conditional"),
            })
            total_required += 1

        for c in data.get("certificates", []):
            required_docs.append({
                "category": "certificate",
                "name": c["name"],
                "mandatory": c.get("mandatory", True),
            })
            total_required += 1

        for d in data.get("additional_docs", []):
            required_docs.append({
                "category": "additional",
                "name": d["name"],
                "mandatory": d.get("mandatory", True),
            })
            total_required += 1

        # Подсчёт обязательных и условных
        mandatory_count = sum(1 for d in required_docs if d["mandatory"] and not d.get("conditional"))
        conditional_count = sum(1 for d in required_docs if d.get("conditional"))
        optional_count = sum(1 for d in required_docs if not d["mandatory"] and not d.get("conditional"))

        completeness[wt] = {
            "chapter": data.get("chapter", ""),
            "category": data.get("category", ""),
            "required_docs": required_docs,
            "summary": summary,
            "counts": {
                "mandatory": mandatory_count,
                "conditional": conditional_count,
                "optional": optional_count,
                "total": len(required_docs),
            },
        }

    # Общий подсчёт по проекту
    total_mandatory = sum(
        c["counts"]["mandatory"]
        for c in completeness.values()
        if isinstance(c, dict) and "counts" in c
    )
    total_conditional = sum(
        c["counts"]["conditional"]
        for c in completeness.values()
        if isinstance(c, dict) and "counts" in c
    )

    return {
        "status": "success",
        "project_id": project_id,
        "work_types_checked": work_types,
        "total_required_docs": total_required,
        "overview": {
            "total_mandatory": total_mandatory,
            "total_conditional": total_conditional,
            "work_types_count": len(work_types),
        },
        "completeness": completeness,
        "note": "Для автоматической проверки наличия документов требуется интеграция с БД проекта",
    }


# ─── Гео-контекст (адрес → координаты, погода, климат) ────

async def asd_enrich_geo_context(
    address: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Обогатить объект гео-контекстом: координаты, погода, климатический район.

    Использует Яндекс.Геокодер (бесплатно) и Open-Meteo (бесплатно).

    Args:
        address: Адрес объекта (например, «г. Новосибирск, ул. Станционная, 30а»)
        start_date: Дата начала строительства (ISO: «2026-05-01»)
        end_date: Дата окончания строительства (ISO: «2026-12-31»)

    Returns:
        Полный гео-контекст с:
        - Координатами (lat, lon)
        - Яндекс.Карты URL
        - Погодой за период (температура, осадки, ветер, дни для зимнего бетонирования)
        - Климатическим районом по СП 131.13330
        - Часовым поясом
        - Восход/заход (для ОЖР)
    """
    from datetime import date

    logger.info("asd_enrich_geo_context: address=%s", address)

    try:
        from src.core.services.geo_context import GeoContextService

        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None

        svc = GeoContextService()
        ctx = await svc.enrich(address, start, end)

        return {
            "status": "success",
            "address": address,
            "location": {
                "lat": ctx.location.lat,
                "lon": ctx.location.lon,
                "precision": ctx.location.precision,
                "region": ctx.location.region,
                "city": ctx.location.city,
                "street": ctx.location.street,
                "house": ctx.location.house,
            },
            "map_url": ctx.osm_map_url,
            "climate_zone": {
                "code": ctx.climate_zone_code,
                "description": ctx.climate_zone_desc,
            },
            "timezone": ctx.timezone,
            "sunrise_sunset": ctx.sunrise_sunset_note,
            "weather": {
                "summary": ctx.weather.summary_text if ctx.weather else "Даты не заданы",
                "days_total": ctx.weather.days_total if ctx.weather else 0,
                "temp_range_c": (
                    f"{ctx.weather.temp_min:.0f}..{ctx.weather.temp_max:.0f}"
                    if ctx.weather and ctx.weather.days_total > 0 else "N/A"
                ),
                "precipitation_total_mm": (
                    round(ctx.weather.total_precipitation_mm, 1)
                    if ctx.weather else 0
                ),
                "days_strong_wind": ctx.weather.days_strong_wind if ctx.weather else 0,
                "days_below_minus_5": ctx.weather.days_below_minus_5 if ctx.weather else 0,
                "days_above_25": ctx.weather.days_above_25 if ctx.weather else 0,
                "max_wind_ms": (
                    round(ctx.weather.max_wind_ms, 1) if ctx.weather else 0
                ),
                "daily": [
                    {
                        "date": str(d.date),
                        "t_min": d.temp_min_c,
                        "t_max": d.temp_max_c,
                        "precip_mm": d.precipitation_mm,
                        "wind_ms": d.wind_speed_max_ms,
                    }
                    for d in (ctx.weather.daily[:10] if ctx.weather else [])
                ],
            },
        }

    except Exception as e:
        logger.error("Geo context enrichment failed: %s", e)
        return {
            "status": "error",
            "message": str(e),
            "address": address,
        }


# ─── Заглушки (будущие инструменты) ────────────────────

_vor_check: Optional["PTO_VorCheck"] = None


async def asd_vor_check(
    vor_items: List[Dict[str, Any]],
    pd_items: List[Dict[str, Any]],
    pd_id: str = "",
    volume_tolerance_pct: float = 5.0,
) -> Dict[str, Any]:
    """
    Сверка ВОР с проектной документацией.

    Построчное сравнение позиций с fuzzy matching. Выявляет расхождения в объёмах,
    несовпадение единиц измерения, отсутствующие и лишние позиции.

    Args:
        vor_items: Список позиций ВОР [{"name": str, "quantity": float, "unit": str}, ...]
        pd_items: Список позиций ПД [{"name": str, "quantity": float, "unit": str}, ...]
        pd_id: Идентификатор проектной документации (опционально)
        volume_tolerance_pct: Допустимое расхождение объёмов в % (по умолчанию 5.0)

    Returns:
        {
            "status": "success" | "partial" | "error",
            "total_vor_items": int,
            "total_pd_items": int,
            "matches": [...],
            "missing_in_pd": [...],
            "extra_in_vor": [...],
            "discrepancies": [...],
            "summary": {...},
            "errors": [...]
        }
    """
    from src.agents.skills.pto.vor_check import PTO_VorCheck

    global _vor_check
    if _vor_check is None:
        _vor_check = PTO_VorCheck()

    logger.info("asd_vor_check: vor_items=%d, pd_items=%d, pd_id=%s",
                len(vor_items), len(pd_items), pd_id)

    result = await _vor_check.execute({
        "vor_items": vor_items,
        "pd_items": pd_items,
        "volume_tolerance_pct": volume_tolerance_pct,
    })

    return {
        "status": result.status.value,
        "total_vor_items": result.data.get("total_vor_items", 0),
        "total_pd_items": result.data.get("total_pd_items", 0),
        "matches": result.data.get("matches", []),
        "missing_in_pd": result.data.get("missing_in_pd", []),
        "extra_in_vor": result.data.get("extra_in_vor", []),
        "discrepancies": result.data.get("discrepancies", []),
        "summary": result.data.get("summary", {}),
        "errors": result.errors,
        "warnings": result.warnings,
    }


_pd_analysis: Optional["PTO_PDAnalysis"] = None


async def asd_pd_analysis(
    sections: List[Dict[str, Any]],
    pd_id: str = "",
    check_completeness: bool = True,
    check_collisions: bool = True,
    check_semantic: bool = False,
) -> Dict[str, Any]:
    """
    Комплексный анализ проектной документации.

    Выявляет коллизии между разделами (АР/КР/ИОС), проверяет комплектность
    разделов по ГОСТ Р 21.1101-2013, ищет неучтённые объёмы.

    Args:
        sections: Список разделов ПД [{"code": str, "name": str, "content": str, "key_positions": [...]}, ...]
        pd_id: Идентификатор ПД (опционально)
        check_completeness: Проверка комплектности разделов (по умолчанию true)
        check_collisions: Поиск пространственных коллизий (по умолчанию true)
        check_semantic: LLM-анализ текста на противоречия (по умолчанию false)

    Returns:
        {
            "status": "success" | "partial" | "error",
            "sections_analyzed": int,
            "collisions": [...],
            "completeness": {...},
            "llm_used": bool,
            "summary": {...},
            "errors": [...]
        }
    """
    from src.agents.skills.pto.pd_analysis import PTO_PDAnalysis

    global _pd_analysis
    if _pd_analysis is None:
        _pd_analysis = PTO_PDAnalysis(llm_engine=llm_engine)

    logger.info("asd_pd_analysis: sections=%d, pd_id=%s", len(sections), pd_id)

    result = await _pd_analysis.execute({
        "sections": sections,
        "check_completeness": check_completeness,
        "check_collisions": check_collisions,
        "check_semantic": check_semantic,
        "enable_llm": check_semantic,
    })

    return {
        "status": result.status.value,
        "sections_analyzed": result.data.get("sections_analyzed", 0),
        "collisions": result.data.get("collisions", []),
        "completeness": result.data.get("completeness", {}),
        "llm_used": result.data.get("llm_used", False),
        "summary": result.data.get("summary", {}),
        "errors": result.errors,
        "warnings": result.warnings,
    }


_act_generator: Optional["PTO_ActGenerator"] = None


async def asd_generate_act(
    act_type: str,
    context: Dict[str, Any],
    output_dir: str = "",
    template_path: str = "",
) -> Dict[str, Any]:
    """
    Генерация акта исполнительной документации в формате DOCX.

    Поддерживаемые типы: aosr, incoming_control, hidden_works, inspection.

    Args:
        act_type: Тип акта — "aosr" | "incoming_control" | "hidden_works" | "inspection"
        context: Данные для заполнения акта {
            "act_number": str, "act_date": str, "project_name": str,
            "object_name": str, "customer_name": str, "contractor_name": str,
            "work_description": str, "volume": float, "unit": str,
            "materials": [...], "commission_members": [...],
            "signatures": [...], "decision": str, ...
        }
        output_dir: Директория для сохранения (по умолчанию data/exports/acts)
        template_path: Путь к кастомному шаблону DOCX (опционально)

    Returns:
        {
            "status": "success" | "error",
            "act_type": str,
            "file_path": str,
            "filename": str,
            "template_used": str or None,
            "size_bytes": int,
            "errors": [...]
        }
    """
    from src.agents.skills.pto.act_generator import PTO_ActGenerator

    global _act_generator
    if _act_generator is None:
        _act_generator = PTO_ActGenerator()

    logger.info("asd_generate_act: type=%s", act_type)

    params: Dict[str, Any] = {
        "act_type": act_type,
        "context": context,
    }
    if output_dir:
        params["output_dir"] = output_dir
    if template_path:
        params["template_path"] = template_path

    result = await _act_generator.execute(params)

    return {
        "status": result.status.value,
        "act_type": result.data.get("act_type", act_type),
        "file_path": result.data.get("file_path", ""),
        "filename": result.data.get("filename", ""),
        "template_used": result.data.get("template_used"),
        "size_bytes": result.data.get("size_bytes", 0),
        "note": result.data.get("note", ""),
        "errors": result.errors,
        "warnings": result.warnings,
    }
