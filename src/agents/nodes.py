"""
ASD v12.0 — Agent Nodes for LangGraph Workflow.

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
from src.agents.hermes_router import HermesRouter
from src.schemas.verdict import TenderVerdict
import docx
import fitz  # PyMuPDF
import os

logger = logging.getLogger(__name__)
from src.db.models import AuditLog
from src.db.init_db import create_engine
from sqlalchemy.orm import sessionmaker
from src.config import settings
from src.utils.wiki_loader import load_wiki_page
from src.core.lessons_service import lessons_service

# Setup DB session for Audit Logging
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)

# Module-level HermesRouter instance (weighted scoring + veto rules)
# v12.0: llm_engine передан для LLM-рассуждения в серой зоне (0.3–0.7)
_hermes_router = HermesRouter(llm_engine=llm_engine)


# =============================================================================
# Уровень 2: RAG-инъекция уроков (Lessons Learned) в контекст агентов
# =============================================================================

async def _get_lessons_context(
    agent_name: str, 
    task_description: str, 
    work_type: str = "*"
) -> str:
    """
    Получить контекст из Lessons Learned для инъекции в промпт агента.
    
    Автоматически ищет релевантные уроки через RAG и формирует
    текстовый блок для добавления в промпт.
    
    Args:
        agent_name: Имя агента (ПТО, Юрист, Сметчик...)
        task_description: Описание задачи (для семантического поиска)
        work_type: Вид работ из WorkTypeRegistry
        
    Returns:
        Строка с уроками или пустая строка
    """
    try:
        context = await lessons_service.get_lessons_context(
            work_type=work_type,
            agent_name=agent_name,
            task_description=task_description,
            top_k=5,
        )
        if context:
            print(f"  📚 {agent_name}: injected lessons context ({len(context)} chars)")
        return context
    except Exception as e:
        logger.warning(f"Failed to inject lessons context for {agent_name}: {e}")
        return ""


def _extract_work_type(state: Dict[str, Any]) -> str:
    """Извлечь вид работ из стейта для RAG-поиска уроков."""
    intermediate = state.get("intermediate_data", {})
    # Извлекаем из intermediate_data или из описания задачи
    return intermediate.get("work_type", "*")


# =============================================================================
# Hermes — Orchestrator Router (v12.0: HermesRouter integration)
# =============================================================================

async def hermes_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hermes orchestrator node — routes pipeline and computes verdict.

    v12.0: Uses HermesRouter with hybrid 3-stage decision model:
      1. Weighted scoring (agent weights: Legal 0.35, Smeta 0.25, PTO 0.20, Procurement 0.12, Logistics 0.08)
      2. LLM reasoning for grey zone (0.3–0.7)
      3. Veto rules (legal DANGEROUS, margin<10%, critical_traps≥3, НМЦК<70%)

    Pipeline flow:
      start → archive → procurement → pto → smeta → legal → logistics → verdict
    """
    print("--- Hermes Orchestrator Router (v12.0) ---")
    next_step = state.get("next_step", "start")

    # Simple routing map for pipeline flow
    routing_map = {
        "start": "archive",
        "archive": "procurement",
        "procurement": "pto",
        "pto": "smeta",
        "smeta": "legal",
        "legal": "logistics",
    }

    if next_step in routing_map:
        # Normal pipeline flow
        return {
            "next_step": routing_map[next_step],
            "current_step": next_step,
        }
    elif next_step == "logistics":
        # All agents done → compute verdict via HermesRouter
        try:
            decision = await _hermes_router.decide(state)
            return {
                "next_step": "complete",
                "current_step": "verdict",
                "hermes_decision": decision,
            }
        except Exception as e:
            logger.error(f"HermesRouter.decide() failed: {e}")
            # Fallback: if HermesRouter fails, continue without verdict
            return {
                "next_step": "complete",
                "current_step": "verdict_fallback",
            }
    else:
        # Unknown step → complete
        return {"next_step": "complete", "is_complete": True}


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
        "archive_result": {
            "documents_registered": 0,
            "versions_tracked": 0,
        },
        "next_step": "archive",
    }


async def procurement_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Закупщика: Анализ тендера и НМЦК. (Gemma 4 31B)"""
    print("--- Procurement Analysis Starting ---")
    rules = load_wiki_page("Procurement_Rules")
    work_type = _extract_work_type(state)
    lessons = await _get_lessons_context("Закупщик", state['task_description'], work_type)
    
    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"{lessons}\n\n"
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
        "procurement_result": {
            "lot_id": "",
            "nmck_vs_market": 0,
            "competitor_count": 0,
            "decision": "bid",
        },
        "next_step": "procurement",
    }


async def pto_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел ПТО: Анализ объемов работ через LLM. (Gemma 4 31B VLM)"""
    print("--- PTO Analysis Starting ---")
    rules = load_wiki_page("PTO_Rules")
    work_type = _extract_work_type(state)

    # v12.0: Извлечение текста из файла, если он передан в стейте
    intermediate = state.get("intermediate_data", {})
    file_path = intermediate.get("file_path")
    document_text = intermediate.get("document_text", "")

    if file_path and os.path.exists(file_path):
        print(f"--- PTO Reading File: {os.path.basename(file_path)} ---")
        if file_path.endswith(".docx"):
            doc = docx.Document(file_path)
            document_text = "\n".join([para.text for para in doc.paragraphs])
        elif file_path.endswith(".pdf"):
            with fitz.open(file_path) as doc:
                document_text = "\n".join([page.get_text() for page in doc])
    
    # v12.0: RAG-инъекция уроков (Lessons Learned)
    lessons = await _get_lessons_context("ПТО", state['task_description'], work_type)
    
    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"{lessons}\n\n"
        f"Задача:\n{state['task_description']}\n\n"
        f"Контекст документа:\n{document_text[:10000]}\n\n"
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
        "vor_result": {
            "positions": vor_data.get("volumes", []),
            "confidence": vor_data.get("confidence", 0.5),
            "drawing_refs": [vor_data.get("source_drawing", "")],
            "unit_mismatches": 0,
        },
        "next_step": "pto",
    }


async def logistics_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Логиста: Поиск поставщиков и цен. (Gemma 4 31B)"""
    print("--- Logistics Sourcing Starting ---")
    rules = load_wiki_page("Logistics_Rules")
    # Read VOR from typed state field (v2.0) or fall back to intermediate_data
    vor = state.get("vor_result") or state.get("intermediate_data", {}).get("vor", {})
    work_type = _extract_work_type(state)
    # v12.0: RAG-инъекция уроков (Lessons Learned)
    lessons = await _get_lessons_context("Логист", state['task_description'], work_type)

    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"{lessons}\n\n"
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
        "logistics_result": {
            "vendors_found": 0,
            "best_price": 0,
            "delivery_available": True,
            "lead_time_days": 14,
        },
        "next_step": "logistics",
    }


async def smeta_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Сметчика: Расчет стоимостей через LLM. (Gemma 4 31B)"""
    print("--- Smeta Calculation Starting ---")
    rules = load_wiki_page("Smeta_Rules")
    # Read VOR from typed state field (v2.0) or fall back to intermediate_data
    vor = state.get("vor_result") or state.get("intermediate_data", {}).get("vor", {})
    work_type = _extract_work_type(state)
    # v12.0: RAG-инъекция уроков (Lessons Learned)
    lessons = await _get_lessons_context("Сметчик", state['task_description'], work_type)

    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"{lessons}\n\n"
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
        smeta_data = json.loads(result_text)
    except (json.JSONDecodeError, TypeError):
        smeta_data = {"raw_costs": result_text}

    return {
        "smeta_result": {
            "total_cost": smeta_data.get("grand_totals", {}).get("total_with_vat", 0),
            "nmck": 0,
            "profit_margin_pct": 0,
            "fer_positions": len(smeta_data.get("grand_totals", {})),
            "confidence": 0.8,
        },
        "next_step": "smeta",
    }


async def legal_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Узел Юриста: Полный юридический анализ через LegalService. (Gemma 4 31B, 128K контекст)

    Поддерживает два режима:
    - Если в intermediate_data есть document_text/file_path — полный анализ (до 300K символов в 128K контексте)
    - Иначе — быстрый обзор по task_description (Quick Review)

    v12.0: RAG-инъекция уроков (Lessons Learned) для учёта предыдущего опыта.
    БЛС: 58 ловушек в 10 категориях.
    """
    print("--- Legal Review Starting ---")

    from src.core.services.legal_service import legal_service
    from src.schemas.legal import LegalAnalysisRequest, ReviewType

    # Determine document source
    intermediate = state.get("intermediate_data", {})
    document_text = intermediate.get("document_text")
    file_path = intermediate.get("contract_path") or intermediate.get("file_path")
    document_id = intermediate.get("document_id")

    # v12.0: Извлечение текста из файла контракта (.docx/.pdf)
    if file_path and os.path.exists(file_path):
        print(f"--- Legal Reading File: {os.path.basename(file_path)} ---")
        if file_path.endswith(".docx"):
            doc = docx.Document(file_path)
            document_text = "\n".join([para.text for para in doc.paragraphs])
        elif file_path.endswith(".pdf"):
            with fitz.open(file_path) as doc:
                document_text = "\n".join([page.get_text() for page in doc])

    # v12.0: RAG-инъекция уроков (Lessons Learned)
    work_type = _extract_work_type(state)
    lessons = await _get_lessons_context("Юрист", state['task_description'], work_type)
    # Уроки добавляются в intermediate_data для использования LegalService
    if lessons and document_text:
        document_text = f"{lessons}\n\n{document_text}"

    try:
        request = LegalAnalysisRequest(
            document_id=document_id,
            document_text=document_text,
            file_path=None, # Передаем извлеченный текст вместо пути
            review_type=ReviewType.CONTRACT,
        )

        result = await legal_service.analyze(request)

        # Convert Pydantic model to dict for LangGraph state
        findings_dicts = [f.model_dump() for f in result.findings]

        return {
            "findings": findings_dicts,
            "legal_result": {
                "verdict": result.verdict.value,
                "findings_count": len(findings_dicts),
                "critical_count": result.critical_count,
                "high_count": result.high_count,
                "summary": result.summary,
                "protocol_items_count": 0,
                "confidence_score": 0.8,
                "blc_matches": [],
            },
            "intermediate_data": {
                **intermediate,
                "legal_verdict": result.verdict.value,
                "legal_summary": result.summary,
                "legal_critical_count": result.critical_count,
                "legal_high_count": result.high_count,
            },
            "is_complete": True,
            "next_step": "legal",
        }

    except Exception as e:
        logger.error(f"Legal analysis failed: {e}")
        return {
            "findings": [{"trap": "Analysis Error", "risk": "High", "details": str(e)}],
            "is_complete": True,
            "next_step": "legal",
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
