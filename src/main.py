"""
ASD v11.0 — Main Entry Point.

Runs the demonstration pipeline:
  Archive → Procurement → PTO → Logistics → Smeta → Legal → Reflection
"""

import asyncio
import logging
from src.agents.workflow import asd_app
from src.db.init_db import Session
from src.db.models import Project
from src.utils.wiki_loader import get_all_rules
from src.config import settings

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ASD_MAIN")


async def run_demo():
    logger.info(f"--- ЗАПУСК ДЕМОНСТРАЦИИ ASD v11.0 (profile: {settings.ASD_PROFILE}) ---")
    logger.info(f"Project root: {settings.BASE_DIR}")
    logger.info(f"Wiki path: {settings.wiki_path}")
    logger.info(f"Artifacts path: {settings.artifacts_path}")

    # 1. Создание тестового проекта в базе
    with Session() as session:
        project = Project(name="Тендер: Строительство моста в Новосибирске")
        session.add(project)
        session.commit()
        project_id = project.id
        logger.info(f"Создан проект ID: {project_id}")

    # 2. Подготовка начального состояния
    task = "Проверить ВОР и Смету на соответствие чертежам. Выявить юридические риски."
    initial_state = {
        "messages": [{"role": "user", "content": task}],
        "project_id": project_id,
        "task_description": task,
        "intermediate_data": {},
        "findings": [],
        "next_step": "start",
        "is_complete": False,
    }

    # 3. Запуск конвейера LangGraph
    logger.info("Запуск графа агентов...")
    final_output = await asd_app.ainvoke(initial_state)

    logger.info("--- КОНВЕЙЕР ЗАВЕРШЕН ---")
    logger.info(f"Найдено ловушек: {len(final_output.get('findings', []))}")

    # 4. Проверка обучения
    logger.info("Проверка обновлений в Wiki (Самообучение)...")
    hermes_wiki = settings.wiki_path / "Hermes_Core.md"
    if hermes_wiki.exists():
        content = hermes_wiki.read_text(encoding="utf-8")
        if "Оптимизация" in content:
            logger.info("УСПЕХ: Hermes успешно обновил правила в Obsidian Wiki!")
        else:
            logger.info(
                "Внимание: Изменений в Wiki пока нет "
                "(возможно, первая итерация прошла идеально)."
            )
    else:
        logger.info(f"Wiki-файл не найден: {hermes_wiki}")


if __name__ == "__main__":
    asyncio.run(run_demo())
