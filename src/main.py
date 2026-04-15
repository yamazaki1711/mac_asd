import asyncio
import logging
from src.agents.workflow import asd_app
from src.db.init_db import Session
from src.db.models import Project
from src.utils.wiki_loader import get_all_rules

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ASD_MAIN")

async def run_demo():
    logger.info("--- ЗАПУСК ДЕМОНСТРАЦИИ ASD v11.0 ---")
    
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
        "is_complete": False
    }

    # 3. Запуск конвейера LangGraph
    logger.info("Запуск графа агентов...")
    final_output = await asd_app.ainvoke(initial_state)
    
    logger.info("--- КОНВЕЙЕР ЗАВЕРШЕН ---")
    logger.info(f"Найдено ловушек: {len(final_output.get('findings', []))}")
    
    # 4. Проверка обучения
    logger.info("Проверка обновлений в Wiki (Самообучение)...")
    with open("/home/oleg/MAC_ASD/data/wiki/Hermes_Core.md", "r") as f:
        content = f.read()
        if "Оптимизация" in content:
            logger.info("УСПЕХ: Hermes успешно обновил правила в Obsidian Wiki!")
        else:
            logger.info("Внимание: Изменений в Wiki пока нет (возможно, первая итерация прошла идеально).")

if __name__ == "__main__":
    asyncio.run(run_demo())
