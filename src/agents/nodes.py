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
    Узел Оркестратора. Решает, что делать дальше, опираясь на правила из Obsidian.
    """
    print("--- Hermes Orchestrator Router ---")
    rules = load_wiki_page("Hermes_Core")
    messages = state["messages"]
    
    # В v11.0 Hermes сам использует Gemma 4 для роутинга, но для простоты State Graph 
    # пока оставим базовый пайплайн маршрутизации, если LLM недоступна.
    if state.get("next_step") == "start":
        next_val = "archive"
    elif state.get("next_step") == "archive_done":
        next_val = "procurement"
    elif state.get("next_step") == "procurement_done":
        next_val = "pto"
    elif state.get("next_step") == "pto_done":
        next_val = "logistics"
    elif state.get("next_step") == "logistics_done":
        next_val = "smeta"
    elif state.get("next_step") == "smeta_done":
        next_val = "legal"
    elif state.get("next_step") == "legal_done":
        next_val = "complete"
    else:
        next_val = "complete"
        
    return {"next_step": next_val}

async def _safe_ollama_chat(messages, agent_name):
    """Обертка для вызова Ollama, возвращающая мок при ошибке (для Linux dev окружения)"""
    try:
        response = await ollama_client.chat(messages=messages)
        return response['message']['content']
    except Exception as e:
        print(f"[{agent_name}] Warning: Ollama not reachable: {e}. Using fallback mock.")
        if agent_name == "PTO":
            return '{"earthworks": 1500, "concrete": 200}'
        elif agent_name == "Smeta":
            return '{"earthworks_cost": 150000, "concrete_cost": 20000}'
        elif agent_name == "Archive":
            return '{"status": "registered", "doc_id": "TRANS-001"}'
        elif agent_name == "Procurement":
            return '{"lot_id": "T-100", "nmck": 50000000, "decision": "bid"}'
        elif agent_name == "Logistics":
            return '{"vendors": ["MetalInvest", "Severstal"], "best_price": 65000}'
        else:
            return '[{"trap": "Indemnity Clause", "risk": "High"}]'

async def archive_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Делопроизводителя: Регистрация и структурирование."""
    print("--- Archive Processing Starting ---")
    rules = load_wiki_page("Archive_Rules")
    prompt = f"Инструкции:\n{rules}\n\nЗадача:\n{state['task_description']}\n\nЗарегистрируйте входящий пакет документов."
    
    messages = [{"role": "user", "content": prompt}]
    result_text = await _safe_ollama_chat(messages, "Archive")
    
    return {
        "intermediate_data": {**state.get("intermediate_data", {}), "archive": result_text},
        "next_step": "archive_done"
    }

async def procurement_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Закупщика: Анализ тендера и НМЦК."""
    print("--- Procurement Analysis Starting ---")
    rules = load_wiki_page("Procurement_Rules")
    prompt = f"Инструкции:\n{rules}\n\nЗадача:\n{state['task_description']}\n\nОцените лот и его рентабельность."
    
    messages = [{"role": "user", "content": prompt}]
    result_text = await _safe_ollama_chat(messages, "Procurement")
    
    return {
        "intermediate_data": {**state.get("intermediate_data", {}), "procurement": result_text},
        "next_step": "procurement_done"
    }

async def pto_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел ПТО: Анализ объемов работ через LLM."""
    print("--- PTO Analysis Starting ---")
    rules = load_wiki_page("PTO_Rules")
    
    prompt = f"Инструкции:\n{rules}\n\nЗадача:\n{state['task_description']}\n\nИзвлеките ВОР в формате JSON (укажите только JSON)."
    
    messages = [{"role": "user", "content": prompt}]
    start_time = datetime.now()
    
    # Real LLM Call
    result_text = await _safe_ollama_chat(messages, "PTO")
    
    duration = int((datetime.now() - start_time).total_seconds() * 1000)

    try:
        vor_data = json.loads(result_text)
    except:
        vor_data = {"raw_text": result_text}
    
    with Session() as session:
        log = AuditLog(
            agent_name="PTO",
            action="extract_vor",
            input_data={"task": state["task_description"]},
            output_data=vor_data,
            duration_ms=duration
        )
        session.add(log)
        session.commit()
        
    return {
        "intermediate_data": {**state.get("intermediate_data", {}), "vor": vor_data},
        "next_step": "pto_done"
    }

async def logistics_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Логиста: Поиск поставщиков и цен."""
    print("--- Logistics Sourcing Starting ---")
    rules = load_wiki_page("Logistics_Rules")
    vor = state.get("intermediate_data", {}).get("vor", {})
    
    prompt = f"Инструкции:\n{rules}\n\nВОР:\n{json.dumps(vor)}\n\nНайдите поставщиков для этих работ."
    
    messages = [{"role": "user", "content": prompt}]
    result_text = await _safe_ollama_chat(messages, "Logistics")
    
    return {
        "intermediate_data": {**state.get("intermediate_data", {}), "logistics": result_text},
        "next_step": "logistics_done"
    }

async def smeta_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Сметчика: Расчет стоимостей через LLM."""
    print("--- Smeta Calculation Starting ---")
    rules = load_wiki_page("Smeta_Rules")
    vor = state.get("intermediate_data", {}).get("vor", {})
    
    prompt = f"Инструкции:\n{rules}\n\nДоступные объемы:\n{json.dumps(vor)}\n\nОцените стоимость, верните валидный JSON."
    messages = [{"role": "user", "content": prompt}]
    
    result_text = await _safe_ollama_chat(messages, "Smeta")
    
    try:
        costs = json.loads(result_text)
    except:
        costs = {"raw_costs": result_text}
    
    return {
        "intermediate_data": {**state.get("intermediate_data", {}), "costs": costs},
        "next_step": "smeta_done"
    }

async def legal_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Юриста: Поиск ловушек в контракте через LLM."""
    print("--- Legal Review Starting ---")
    rules = load_wiki_page("Jurist_Rules")
    
    prompt = f"Инструкции:\n{rules}\n\nПроанализируй риск. Выведи массив JSON с объектами {{trap, risk}}."
    messages = [{"role": "user", "content": prompt}]
    
    result_text = await _safe_ollama_chat(messages, "Jurist")
    
    try:
        findings = json.loads(result_text)
        if not isinstance(findings, list):
            findings = [findings]
    except:
        findings = [{"trap": "Unparsed Risk", "details": result_text}]
    
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
