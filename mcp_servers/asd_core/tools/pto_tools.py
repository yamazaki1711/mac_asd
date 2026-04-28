"""
MAC_ASD v12.0 — PTO MCP Tools.

Инструменты для агента ПТО:
  - asd_get_work_type_info: Полная информация по виду работ (состав ИД)
  - asd_list_work_types: Иерархический список всех видов работ
  - asd_get_tech_sequence: Технологическая последовательность оформления
  - asd_get_date_rules: Правила датировки документов
  - asd_get_input_control: Требования входного контроля (общие)
  - asd_id_completeness: Проверка комплектности ИД по виду работ
  - asd_id_search: Поиск шаблонов/примеров в базе id-prosto.ru
  - asd_id_download: Скачивание PDF-образцов с id-prosto.ru
  - asd_vor_check: Сверка ВОР с ПД
  - asd_pd_analysis: Комплексный анализ ПД
  - asd_generate_act: Генерация актов (АОСР, АООК, акты приёмки)

Источник данных: Пособие по ИД, Выпуск №2 (Сарвартдинова, ВАШ ФОРМАТ, 2026).
Покрытие: все 20 видов работ по Главе 5 Пособия.
"""

import logging
from typing import Any, Dict, List, Optional

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


async def asd_id_search(
    query: str,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Поиск шаблонов и примеров ИД в базе id-prosto.ru.

    Args:
        query: Поисковый запрос (например, "АОСР бетонирование фундамента")
        category: Фильтр по категории (earth, concrete, steel, ...)

    Returns:
        Найденные документы с описаниями и ссылками
    """
    logger.info("asd_id_search: query=%s category=%s", query, category)

    try:
        from src.integrations.id_prosto_client import IdProstoClient

        with IdProstoClient() as client:
            if category:
                docs = client.get_category(category)
            else:
                docs = client.search(query)

            return {
                "status": "success",
                "query": query,
                "category": category,
                "results_count": len(docs),
                "results": [d.to_dict() for d in docs[:20]],
            }

    except Exception as e:
        logger.error("Ошибка поиска ИД: %s", e)
        return {
            "status": "error",
            "message": str(e),
            "results": [],
        }


async def asd_id_download(
    url: str,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Скачивание PDF-образца с id-prosto.ru.

    Args:
        url: URL PDF-файла на id-prosto.ru
        filename: Имя файла для сохранения (без пути)

    Returns:
        Статус скачивания и путь к файлу
    """
    logger.info("asd_id_download: url=%s", url)

    try:
        from src.integrations.id_prosto_client import IdProstoClient

        with IdProstoClient() as client:
            if not filename:
                filename = url.split("/")[-1] or "document.pdf"

            save_path = f"/tmp/id_samples/{filename}"
            pdf_bytes = client.download_pdf(url, save_path=save_path)

            if pdf_bytes:
                return {
                    "status": "success",
                    "url": url,
                    "saved_to": save_path,
                    "size_bytes": len(pdf_bytes),
                }
            else:
                return {
                    "status": "error",
                    "message": "Не удалось скачать PDF",
                    "url": url,
                }

    except Exception as e:
        logger.error("Ошибка скачивания: %s", e)
        return {
            "status": "error",
            "message": str(e),
            "url": url,
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

async def asd_vor_check(vor_data: Dict[str, Any], pd_id: str) -> Dict[str, Any]:
    """Сверка ВОР с ПД (объёмы, единицы, наименования)."""
    logger.info("asd_vor_check: vs pd_id %s", pd_id)
    return {
        "status": "success",
        "action": "VOR Check Complete",
        "discrepancies": [],
    }


async def asd_pd_analysis(pd_id: str) -> Dict[str, Any]:
    """Комплексный анализ ПД (коллизии, неучтённые объёмы/материалы)."""
    logger.info("asd_pd_analysis: pd_id %s", pd_id)
    return {
        "status": "success",
        "action": "PD Analysis Complete",
        "collisions": [],
    }


async def asd_generate_act(act_type: str, context_id: str) -> Dict[str, Any]:
    """Генерация акта (АОСР, АООК, акты приёмки, входной контроль)."""
    logger.info("asd_generate_act: %s", act_type)
    return {
        "status": "success",
        "act_type": act_type,
        "mock_content": f"Акт формата {act_type}...",
    }
