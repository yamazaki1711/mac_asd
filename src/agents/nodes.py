import json
from datetime import datetime
from typing import Dict, Any
from src.core.ollama_client import ollama_client
from src.db.models import AuditLog
from src.db.init_db import create_engine
from sqlalchemy.orm import sessionmaker
from src.config import settings
from src.utils.wiki_loader import load_wiki_page

# Setup DB session for Audit Logging
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)

async def hermes_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Узел Оркестратора. Решает, что делать дальше.
    """
    rules = load_wiki_page("Hermes_Core")
    messages = state["messages"]
    
    # Формируем промпт для Hermes
    sys_prompt = f"Вы - Hermes, PM системы ASD. Ваши правила:\n{rules}\nТекущая фаза: {state.get('next_step', 'start')}"
    
    # В реальности тут будет вызов LLM для принятия решения
    # Пока что реализуем базовую логику конвейера
    if state["next_step"] == "start":
        next_val = "pto"
    elif state["next_step"] == "pto_done":
        next_val = "smeta"
    elif state["next_step"] == "smeta_done":
        next_val = "legal"
    elif state["next_step"] == "legal_done":
        next_val = "complete"
    else:
        next_val = "complete"
        
    return {"next_step": next_val}

async def pto_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел ПТО: Анализ объемов работ."""
    print("--- PTO Analysis Starting ---")
    rules = load_wiki_page("PTO_Rules") # Предварительно создать
    
    # Имитация работы: извлечение ВОР
    vor_data = {"earthworks": 1500, "concrete": 200}
    
    # Логируем действие
    with Session() as session:
        log = AuditLog(
            agent_name="PTO",
            action="extract_vor",
            input_data={"task": state["task_description"]},
            output_data=vor_data,
            duration_ms=1200
        )
        session.add(log)
        session.commit()
        
    return {
        "intermediate_data": {"vor": vor_data},
        "next_step": "pto_done"
    }

async def smeta_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Сметчика: Расчет стоимостей."""
    print("--- Smeta Calculation Starting ---")
    vor = state["intermediate_data"].get("vor", {})
    
    # Имитация: применение расценок (ФЕР)
    costs = {k: v * 100 for k, v in vor.items()}
    
    return {
        "intermediate_data": {**state["intermediate_data"], "costs": costs},
        "next_step": "smeta_done"
    }

async def legal_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Юриста: Поиск ловушек в контракте."""
    print("--- Legal Review Starting ---")
    
    # Имитация: поиск по базе БЛС
    findings = [{"trap": "Indemnity Clause", "risk": "High"}]
    
    return {
        "findings": findings,
        "is_complete": True,
        "next_step": "legal_done"
    }

from src.agents.reflection_node import run_reflection_cycle

async def reflection_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Узел Рефлексии (Обучения). Срабатывает в конце.
    """
    print("--- Self-Optimization Loop Starting ---")
    await run_reflection_cycle()
    return {"is_complete": True}
