"""
ASD v11.0 — Agent Nodes for LangGraph Workflow.

Each node represents an agent in the ASD pipeline.
All LLM calls go through llm_engine (unified interface).
"""

import json
from datetime import datetime
from typing import Dict, Any
from src.core.llm_engine import llm_engine
from src.db.models import AuditLog
from src.db.init_db import create_engine
from sqlalchemy.orm import sessionmaker
from src.config import settings
from src.utils.wiki_loader import load_wiki_page

# Setup DB session for Audit Logging
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)


# =============================================================================
# Hermes — Orchestrator Router
# =============================================================================

async def hermes_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Узел Оркестратора. Решает, что делать дальше, опираясь на правила из Obsidian.

    В текущей реализации — линейный пайплайн (if/elif).
    TODO: Заменить на LLM-роутинг, когда Hermes будет использовать Llama 70B.
    """
    print("--- Hermes Orchestrator Router ---")
    rules = load_wiki_page("Hermes_Core")

    # Линейный пайплайн (будет заменён на AI-роутинг)
    routing_map = {
        "start": "archive",
        "archive_done": "procurement",
        "procurement_done": "pto",
        "pto_done": "logistics",
        "logistics_done": "smeta",
        "smeta_done": "legal",
        "legal_done": "complete",
    }

    next_val = routing_map.get(state.get("next_step"), "complete")
    return {"next_step": next_val}


# =============================================================================
# Worker Nodes — специализированные агенты
# =============================================================================

async def archive_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Делопроизводителя: Регистрация и структурирование."""
    print("--- Archive Processing Starting ---")
    rules = load_wiki_page("Archive_Rules")
    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"Задача:\n{state['task_description']}\n\n"
        f"Зарегистрируйте входящий пакет документов."
    )

    messages = [{"role": "user", "content": prompt}]
    result_text = await llm_engine.safe_chat(
        "archive",
        messages,
        fallback_response='{"status": "registered", "doc_id": "REG-001"}',
    )

    return {
        "intermediate_data": {**state.get("intermediate_data", {}), "archive": result_text},
        "next_step": "archive_done",
    }


async def procurement_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Закупщика: Анализ тендера и НМЦК."""
    print("--- Procurement Analysis Starting ---")
    rules = load_wiki_page("Procurement_Rules")
    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"Задача:\n{state['task_description']}\n\n"
        f"Оцените лот и его рентабельность."
    )

    messages = [{"role": "user", "content": prompt}]
    result_text = await llm_engine.safe_chat(
        "procurement",
        messages,
        fallback_response='{"lot_id": "T-100", "nmck": 50000000, "decision": "bid"}',
    )

    return {
        "intermediate_data": {**state.get("intermediate_data", {}), "procurement": result_text},
        "next_step": "procurement_done",
    }


async def pto_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел ПТО: Анализ объемов работ через LLM."""
    print("--- PTO Analysis Starting ---")
    rules = load_wiki_page("PTO_Rules")

    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"Задача:\n{state['task_description']}\n\n"
        f"Извлеките ВОР в формате JSON (укажите только JSON)."
    )

    messages = [{"role": "user", "content": prompt}]
    start_time = datetime.now()

    result_text = await llm_engine.safe_chat(
        "pto",
        messages,
        fallback_response='{"earthworks": 1500, "concrete": 200}',
    )

    duration = int((datetime.now() - start_time).total_seconds() * 1000)

    try:
        vor_data = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        vor_data = {"raw_text": result_text}

    with Session() as session:
        log = AuditLog(
            agent_name="PTO",
            action="extract_vor",
            input_data={"task": state["task_description"]},
            output_data=vor_data,
            duration_ms=duration,
        )
        session.add(log)
        session.commit()

    return {
        "intermediate_data": {**state.get("intermediate_data", {}), "vor": vor_data},
        "next_step": "pto_done",
    }


async def logistics_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Логиста: Поиск поставщиков и цен."""
    print("--- Logistics Sourcing Starting ---")
    rules = load_wiki_page("Logistics_Rules")
    vor = state.get("intermediate_data", {}).get("vor", {})

    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"ВОР:\n{json.dumps(vor, ensure_ascii=False)}\n\n"
        f"Найдите поставщиков для этих работ."
    )

    messages = [{"role": "user", "content": prompt}]
    result_text = await llm_engine.safe_chat(
        "logistics",
        messages,
        fallback_response='{"vendors": ["MetalInvest", "Severstal"], "best_price": 65000}',
    )

    return {
        "intermediate_data": {**state.get("intermediate_data", {}), "logistics": result_text},
        "next_step": "logistics_done",
    }


async def smeta_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Сметчика: Расчет стоимостей через LLM."""
    print("--- Smeta Calculation Starting ---")
    rules = load_wiki_page("Smeta_Rules")
    vor = state.get("intermediate_data", {}).get("vor", {})

    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"Доступные объемы:\n{json.dumps(vor, ensure_ascii=False)}\n\n"
        f"Оцените стоимость, верните валидный JSON."
    )
    messages = [{"role": "user", "content": prompt}]

    result_text = await llm_engine.safe_chat(
        "smeta",
        messages,
        fallback_response='{"earthworks_cost": 150000, "concrete_cost": 20000}',
    )

    try:
        costs = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        costs = {"raw_costs": result_text}

    return {
        "intermediate_data": {**state.get("intermediate_data", {}), "costs": costs},
        "next_step": "smeta_done",
    }


async def legal_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Юриста: Поиск ловушек в контракте через LLM."""
    print("--- Legal Review Starting ---")
    rules = load_wiki_page("Jurist_Rules")

    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"Проанализируй риск. Выведи массив JSON с объектами {{trap, risk}}."
    )
    messages = [{"role": "user", "content": prompt}]

    result_text = await llm_engine.safe_chat(
        "legal",
        messages,
        fallback_response='[{"trap": "Indemnity Clause", "risk": "High"}]',
    )

    try:
        findings = json.loads(result_text)
        if not isinstance(findings, list):
            findings = [findings]
    except (json.JSONDecodeError, TypeError):
        findings = [{"trap": "Unparsed Risk", "details": result_text}]

    return {
        "findings": findings,
        "is_complete": True,
        "next_step": "legal_done",
    }


# =============================================================================
# Reflection Node
# =============================================================================

from src.agents.reflection_node import run_reflection_cycle


async def reflection_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Рефлексии (Обучения). Срабатывает в конце конвейера."""
    print("--- Self-Optimization Loop Starting ---")
    await run_reflection_cycle()
    return {"is_complete": True}
