"""
ASD v12.0 — Dry Test: Project "Demontazh"
=========================================
Запуск полной цепочки агентов на реальных данных из /home/oleg/демонтаж/
"""

import asyncio
import logging
import os
from src.agents.workflow import asd_app
from src.db.init_db import Session
from src.db.models import Project
from src.config import settings

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DRY_TEST")

DEMO_DIR = "/home/oleg/демонтаж"

async def run_dry_test():
    logger.info("--- ЗАПУСК СУХОГО ТЕСТА: ПРОЕКТ ДЕМОНТАЖ ---")
    
    if not os.path.exists(DEMO_DIR):
        logger.error(f"Папка {DEMO_DIR} не найдена!")
        return

    # 1. Поиск ключевых файлов
    files = os.listdir(DEMO_DIR)
    sow_file = next((f for f in files if "Описание_объекта_закупки" in f), None)
    contract_file = next((f for f in files if "Проект_контракта" in f), None)
    
    logger.info(f"Найдено файлов в папке: {len(files)}")
    logger.info(f"ТЗ (SOW): {sow_file}")
    logger.info(f"Контракт: {contract_file}")

    # 2. Создание проекта в БД
    with Session() as session:
        project = Project(name="Сухой тест: Демонтаж (v12.0)")
        session.add(project)
        session.commit()
        project_id = project.id
        logger.info(f"Создан проект ID: {project_id}")

    # 3. Подготовка состояния (AgentState)
    task = "Провести комплексный анализ тендера по демонтажу. Извлечь ВОР и выявить критические риски в контракте."
    
    # Мы передаем путь к ТЗ как основной файл для ПТО
    file_path = os.path.join(DEMO_DIR, sow_file) if sow_file else None
    contract_path = os.path.join(DEMO_DIR, contract_file) if contract_file else None

    initial_state = {
        "messages": [{"role": "user", "content": task}],
        "project_id": project_id,
        "task_description": task,
        "intermediate_data": {
            "file_path": file_path,        # Для ПТО
            "contract_path": contract_path, # Для Юриста
            "demo_dir": DEMO_DIR
        },
        "findings": [],
        "next_step": "start",
        "is_complete": False,
        "schema_version": "2.0",
        "workflow_mode": "tender_pipeline",
        "audit_trail": [],
    }

    # 4. Запуск графа агентов
    logger.info("Агенты приступают к работе (Руководитель проекта координирует)...")
    try:
        final_output = await asd_app.ainvoke(initial_state)
        
        logger.info("--- ТЕСТ ЗАВЕРШЕН УСПЕШНО ---")
        
        # Вывод результатов
        intermediate = final_output.get('intermediate_data', {})
        vor = intermediate.get('vor', {})
        logger.info(f"ПТО извлек ВОР: {list(vor.keys()) if isinstance(vor, dict) else 'Ошибка формата'}")
        
        legal_verdict = intermediate.get('legal_verdict', 'N/A')
        logger.info(f"Юридический вердикт: {legal_verdict}")
        
        logger.info(f"Всего найдено замечаний/рисков: {len(final_output.get('findings', []))}")
        
    except Exception as e:
        logger.error(f"Ошибка в ходе выполнения теста: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(run_dry_test())
