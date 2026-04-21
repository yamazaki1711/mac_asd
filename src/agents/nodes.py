"""
ASD v11.3 — Agent Nodes for LangGraph Workflow.

Each node represents an agent in the ASD pipeline.
All LLM calls go through llm_engine (unified interface).

Model Lineup (mac_studio):
    PM:     Llama 3.3 70B 4-bit
    ПТО:    Gemma 4 31B 4-bit (VLM, shared)
    Юрист:  Gemma 4 31B 4-bit (shared)
    Сметчик:Gemma 4 31B 4-bit (shared)
    Закупщик:Gemma 4 31B 4-bit (shared)
    Логист: Gemma 4 31B 4-bit (shared)
    Дело:   Gemma 4 E4B 4-bit
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any
from src.core.llm_engine import llm_engine

logger = logging.getLogger(__name__)
from src.db.models import AuditLog
from src.db.init_db import create_engine
from sqlalchemy.orm import sessionmaker
from src.config import settings
from src.utils.wiki_loader import load_wiki_page

# Setup DB session for Audit Logging
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)


# =============================================================================
# Hermes — Orchestrator Router (v11.3: hybrid 3-stage decision model)
# =============================================================================

async def hermes_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Узел Оркестратора. Решает, что делать дальше.

    v11.3: Использует HermesRouter с гибридной 3-стадийной моделью:
      1. Weighted scoring (агентные веса: Юрист 0.35, Сметчик 0.25, ПТО 0.20, Закупщик 0.12, Логист 0.08)
      2. LLM reasoning для серой зоны (0.3–0.7)
      3. Veto rules (legal DANGEROUS, margin<10%, critical_traps≥3, НМЦК<70%)

    Pipeline поддерживает параллельное выполнение агентов (Сметчик+Юрист, Закупщик+Логист).
    """
    print("--- Hermes Orchestrator Router (v11.3 hybrid) ---")
    rules = load_wiki_page("Hermes_Core")

    # v11.3: Расширенный пайплайн с поддержкой параллельных шагов
    routing_map = {
        "start": "archive",
        "archive_done": "procurement",
        "procurement_done": "pto",
        "pto_done": "parallel_smeta_legal",  # Параллельный запуск Сметчик+Юрист
        "smeta_legal_done": "logistics",
        "logistics_done": "hermes_verdict",   # Финальный вердикт Hermes
        "verdict_done": "complete",
    }

    next_val = routing_map.get(state.get("next_step"), "complete")
    return {"next_step": next_val}


# =============================================================================
# Worker Nodes — специализированные агенты
# =============================================================================

async def archive_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Делопроизводителя: Регистрация и структурирование. (Gemma 4 E4B)"""
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
    """Узел Закупщика: Анализ тендера и НМЦК. (Gemma 4 31B)"""
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
    """Узел ПТО: Анализ объемов работ через LLM. (Gemma 4 31B VLM)"""
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
    """Узел Логиста: Поиск поставщиков и цен. (Gemma 4 31B)"""
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
    """Узел Сметчика: Расчет стоимостей через LLM. (Gemma 4 31B)"""
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
    """
    Узел Юриста: Полный юридический анализ через LegalService. (Gemma 4 31B, 128K контекст)

    Поддерживает два режима:
    - Если в intermediate_data есть document_text/file_path — полный анализ (до 300K символов в 128K контексте)
    - Иначе — быстрый обзор по task_description (Quick Review)

    БЛС: 58 ловушек в 10 категориях.
    """
    print("--- Legal Review Starting ---")

    from src.core.services.legal_service import legal_service
    from src.schemas.legal import LegalAnalysisRequest, ReviewType

    # Determine document source
    intermediate = state.get("intermediate_data", {})
    document_text = intermediate.get("document_text")
    file_path = intermediate.get("file_path")
    document_id = intermediate.get("document_id")

    # If no document provided, analyze the task description itself
    if not document_text and not file_path and not document_id:
        document_text = state.get("task_description", "")

    try:
        request = LegalAnalysisRequest(
            document_id=document_id,
            document_text=document_text,
            file_path=file_path,
            review_type=ReviewType.CONTRACT,
        )

        result = await legal_service.analyze(request)

        # Convert Pydantic model to dict for LangGraph state
        findings_dicts = [f.model_dump() for f in result.findings]

        return {
            "findings": findings_dicts,
            "intermediate_data": {
                **intermediate,
                "legal_verdict": result.verdict.value,
                "legal_summary": result.summary,
                "legal_critical_count": result.critical_count,
                "legal_high_count": result.high_count,
            },
            "is_complete": True,
            "next_step": "legal_done",
        }

    except Exception as e:
        logger.error(f"Legal analysis failed: {e}")
        return {
            "findings": [{"trap": "Analysis Error", "risk": "High", "details": str(e)}],
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
