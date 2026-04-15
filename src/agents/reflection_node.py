import logging
import os
import json
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import select, update
from src.db.models import AuditLog
from src.db.init_db import Session
from src.core.ollama_client import ollama_client
from src.config import settings

logger = logging.getLogger(__name__)

async def run_reflection_cycle():
    """
    Автономный цикл обучения: 
    Анализ логов -> Выводы -> Обновление Wiki.
    """
    logger.info("Starting Reflection Cycle...")
    
    with Session() as session:
        # 1. Извлекаем неизученные логи
        stmt = select(AuditLog).where(AuditLog.is_learned == False).limit(50)
        logs = session.execute(stmt).scalars().all()
        
        if not logs:
            logger.info("No new logs to learn from.")
            return

        # 2. Формируем контекст для LLM
        log_summary = "\n".join([
            f"Agent: {l.agent_name}, Action: {l.action}, Output: {json.dumps(l.output_data)[:200]}"
            for l in logs
        ])
        
        prompt = f"""
        Вы - Система Оптимизации ASD. Проанализируйте следующие логи работы агентов:
        {log_summary}
        
        Ваша задача:
        1. Определить ошибки или узкие места.
        2. Предложить ОДНУ конкретную поправку в правила для Obsidian Wiki, чтобы повысить точность системы.
        
        Ответ дайте в формате:
        PAGE: [название страницы, например Hermes_Core]
        CHANGE: [текст поправки]
        """
        
        response = await ollama_client.chat([{"role": "user", "content": prompt}])
        advice = response["message"]["content"]
        
        # 3. Применяем изменения в Wiki (Obsidian)
        try:
            # Парсим ответ (упрощенно)
            if "PAGE:" in advice and "CHANGE:" in advice:
                parts = advice.split("CHANGE:")
                page = parts[0].split("PAGE:")[1].strip()
                change = parts[1].strip()
                
                wiki_file = os.path.join(settings.WIKI_PATH, f"{page}.md")
                if os.path.exists(wiki_file):
                    with open(wiki_file, "a", encoding="utf-8") as f:
                        f.write(f"\n\n## Оптимизация от {datetime.now().date()}\n{change}\n")
                    logger.info(f"Wiki page {page} optimized successfully.")
                
            # Помечаем логи как изученные
            for l in logs:
                l.is_learned = True
            session.commit()
            
        except Exception as e:
            logger.error(f"Error during Wiki optimization: {e}")

# Интегрируем в существующий reflection_node из nodes.py
# (В nodes.py мы оставили заглушку, теперь мы можем вызвать run_reflection_cycle)
