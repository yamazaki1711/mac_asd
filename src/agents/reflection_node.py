"""
ASD v11.3 — Reflection Node (Self-Learning Loop).

Analyzes audit logs → draws conclusions → updates Obsidian Wiki.
Uses llm_engine for LLM calls instead of direct ollama_client.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List

from sqlalchemy import select
from src.db.models import AuditLog
from src.db.init_db import Session
from src.core.llm_engine import llm_engine
from src.config import settings

logger = logging.getLogger(__name__)


async def run_reflection_cycle():
    """
    Автономный цикл обучения:
    Анализ логов → Выводы → Обновление Wiki.
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
            f"Agent: {l.agent_name}, Action: {l.action}, "
            f"Output: {str(l.output_data)[:200]}"
            for l in logs
        ])

        prompt = f"""
        Вы - Система Оптимизации ASD. Проанализируйте следующие логи работы агентов:
        {log_summary}

        Ваша задача:
        1. Определить ошибки или узкие места.
        2. Предложить ОДНУ конкретную поправку в правила для Obsidian Wiki,
           чтобы повысить точность системы.

        Ответ дайте в формате:
        PAGE: [название страницы, например Hermes_Core]
        CHANGE: [текст поправки]
        """

        # 3. LLM-анализ через llm_engine
        try:
            advice = await llm_engine.safe_chat(
                "pm",
                [{"role": "user", "content": prompt}],
                fallback_response="",
            )

            if not advice:
                logger.warning("Reflection: LLM returned empty response. Skipping.")
                return

        except Exception as e:
            logger.error(f"Reflection: LLM call failed: {e}")
            return

        # 4. Применяем изменения в Wiki (Obsidian)
        try:
            if "PAGE:" in advice and "CHANGE:" in advice:
                parts = advice.split("CHANGE:")
                page = parts[0].split("PAGE:")[1].strip()
                change = parts[1].strip()

                wiki_file = settings.wiki_path / f"{page}.md"
                if wiki_file.exists():
                    with open(wiki_file, "a", encoding="utf-8") as f:
                        f.write(
                            f"\n\n## Оптимизация от {datetime.now().date()}\n{change}\n"
                        )
                    logger.info(f"Wiki page '{page}' optimized successfully.")
                else:
                    logger.warning(f"Wiki page '{page}' not found at {wiki_file}")

            # Помечаем логи как изученные
            for l in logs:
                l.is_learned = True
            session.commit()

        except Exception as e:
            logger.error(f"Error during Wiki optimization: {e}")
