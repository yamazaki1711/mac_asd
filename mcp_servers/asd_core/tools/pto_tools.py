"""
MAC_ASD v11.3 — PTO MCP Tools.

Инструменты для агента ПТО:
  - asd_vor_check: Сверка ВОР с ПД
  - asd_pd_analysis: Комплексный анализ ПД
  - asd_generate_act: Генерация актов (АОСР, АООК, АОИС, входной контроль)
  - asd_id_completeness: Проверка комплектности ИД по Регламенту
  - asd_id_search: Поиск шаблонов/примеров в базе id-prosto.ru
  - asd_id_download: Скачивание PDF-образцов с id-prosto.ru
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Заглушки (изначальные) ────────────────────

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
    """Генерация акта (АОСР, АООК, АОИС, входной контроль)."""
    logger.info("asd_generate_act: %s", act_type)
    return {
        "status": "success",
        "act_type": act_type,
        "mock_content": f"Акт формата {act_type}...",
    }


# ─── Новые инструменты (id-prosto.ru) ──────────

async def asd_id_completeness(
    project_id: str,
    work_sections: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Проверка комплектности ИД по Регламенту ТЗ с П.

    Сравнивает фактический комплект документов с перечнем,
    установленным Регламентом для каждого раздела проекта.

    Args:
        project_id: Идентификатор проекта
        work_sections: Список разделов ПД (КЖ, АР, ОВиК, ВК, ЭОМ, СС, АУПТ, ТХ)

    Returns:
        Отчёт о комплектности с перечнем недостающих документов
    """
    logger.info("asd_id_completeness: project=%s sections=%s", project_id, work_sections)

    # Требования к ИД по разделам (из Регламента)
    required_docs = {
        "КЖ": {
            "acts": ["АОСР (арматура, бетонирование, опалубка)", "АООК (ответственные конструкции)"],
            "schemes": ["Исполнительные геодезические схемы"],
            "quality": ["Паспорта на бетон", "Сертификаты на арматуру", "Протоколы испытания бетона"],
            "journals": ["Журнал бетонных работ", "Журнал сварочных работ"],
        },
        "АР": {
            "acts": ["АОСР (перегородки, проёмы, отделка)", "Акт готовности под отделку"],
            "schemes": ["Исполнительные чертежи"],
            "quality": ["Паспорта/сертификаты на материалы", "Санитарно-эпидемиологические заключения", "Сертификаты пожарной безопасности"],
            "journals": ["Общий журнал работ"],
        },
        "ОВиК": {
            "acts": ["АОСР (воздуховоды, трубопроводы, изоляция)", "АОИС", "Акты гидростатических испытаний", "Акты промывки"],
            "schemes": ["Исполнительные чертежи"],
            "quality": ["Паспорта на оборудование", "Результаты наладки", "Паспорта систем вентиляции"],
            "journals": ["Специальный журнал работ"],
        },
        "ВК": {
            "acts": ["АОСР (трубопроводы, изоляция, проходы)", "АОИС", "Акты гидростатических испытаний", "Акты промывки", "Акт испытания на пролив"],
            "schemes": ["Исполнительные чертежи"],
            "quality": ["Паспорта на оборудование", "Документы поверки приборов"],
            "journals": ["Специальный журнал работ"],
        },
        "ЭОМ": {
            "acts": ["АОСР (кабельные трассы, лотки, уравнивание потенциалов)", "АОИС", "Акты проверки осветительной сети", "Акт технической готовности"],
            "schemes": ["Исполнительные чертежи"],
            "quality": ["Протоколы электроизмерительной лаборатории (сопротивление, фазировка, УЗО)", "Паспорта на оборудование"],
            "journals": ["Журнал электромонтажных работ"],
        },
        "СС": {
            "acts": ["АОСР (лотки, кабельные трассы)", "Акт об окончании монтажных работ", "Акт об окончании ПНР", "Акты индивидуальных/комплексных испытаний"],
            "schemes": ["Исполнительные чертежи"],
            "quality": ["Протоколы электроизмерительной лаборатории", "Программа испытаний"],
            "journals": ["Специальный журнал работ"],
        },
        "АУПТ": {
            "acts": ["АОСР (трубопроводы, крепления, спринклеры)", "Акты гидростатических испытаний", "Акт об окончании ПНР", "Акты индивидуальных/комплексных испытаний"],
            "schemes": ["Исполнительные чертежи"],
            "quality": ["Паспорта на оборудование", "Лицензия МЧС"],
            "journals": ["Специальный журнал работ"],
        },
        "ТХ": {
            "acts": ["Акты приёмки в эксплуатацию"],
            "schemes": ["Исполнительные чертежи"],
            "quality": ["Паспорта на оборудование", "Инструкции по эксплуатации и монтажу"],
            "journals": [],
        },
    }

    sections = work_sections or list(required_docs.keys())
    missing: Dict[str, List[str]] = {}
    total_required = 0

    for section in sections:
        reqs = required_docs.get(section, {})
        section_missing = []
        for category, docs in reqs.items():
            total_required += len(docs)
            # Заглушка: в реальной системе проверяем наличие каждого документа
            # Сейчас помечаем всё как "требует проверки"
            section_missing.extend([f"[{category}] {d}" for d in docs])
        if section_missing:
            missing[section] = section_missing

    return {
        "status": "success",
        "project_id": project_id,
        "sections_checked": sections,
        "total_required_docs": total_required,
        "missing": missing,
        "note": "Требуется интеграция с реальной БД проекта для автоматической проверки",
    }


async def asd_id_search(
    query: str,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Поиск шаблонов и примеров ИД в базе id-prosto.ru.

    Ищет в локальной базе знаний (артефакты), при необходимости
    обращается онлайн к id-prosto.ru.

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
