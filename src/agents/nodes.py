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
from typing import Dict, Any, List, Optional
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
from src.core.rag_pipeline import rag_pipeline

# Setup DB session for Audit Logging
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)

# Module-level HermesRouter instance (weighted scoring + veto rules)
# v12.0: llm_engine передан для LLM-рассуждения в серой зоне (0.3–0.7)
_hermes_router = HermesRouter(llm_engine=llm_engine)


# =============================================================================
# LLM Fallback Tracking
# =============================================================================

async def _safe_agent_chat(
    agent: str,
    messages: List,
    fallback_response: str,
    state: Dict[str, Any],
    **kwargs,
) -> str:
    """
    Wrapper around llm_engine.safe_chat that records fallback events.
    
    If LLM is unavailable and fallback_response is used, this sets
    _llm_fallback_triggered=True in the state and logs the affected agent.
    """
    try:
        response = await llm_engine.chat(agent, messages, **kwargs)
        return response
    except Exception as e:
        logger.warning(
            "LLM fallback triggered for agent %s: %s. Using fallback response.", 
            agent, str(e)
        )
        state["_llm_fallback_triggered"] = True
        fallback_agents = state.setdefault("_llm_fallback_agents", [])
        if agent not in fallback_agents:
            fallback_agents.append(agent)
        return fallback_response


def _compute_agent_confidence(
    state: Dict[str, Any],
    agent: str,
    result_text: str,
    parsed_data: Optional[Dict] = None,
) -> float:
    """
    Compute agent confidence based on response quality.
    
    Factors:
    - 0.00: LLM fallback was triggered (result is dummy data)
    - 0.30: Response couldn't be parsed as JSON
    - 0.50: Parsed but very short / minimal
    - 0.70: Parsed with expected structure
    - 0.90: Parsed with rich structure and expected keys present
    
    Args:
        state: Agent pipeline state
        agent: Agent name
        result_text: Raw LLM response text
        parsed_data: Parsed JSON (or None if parsing failed)
    
    Returns:
        Confidence score 0.0-1.0
    """
    # Fallback → zero confidence
    if state.get("_llm_fallback_triggered") and agent in state.get("_llm_fallback_agents", []):
        return 0.0
    
    # No response at all
    if not result_text or len(result_text.strip()) < 10:
        return 0.1
    
    # Couldn't parse JSON
    if parsed_data is None:
        return 0.3
    
    # Parsed but minimal structure
    if isinstance(parsed_data, dict) and len(parsed_data) <= 1:
        return 0.5
    
    # Rich structure with multiple keys
    if isinstance(parsed_data, dict) and len(parsed_data) >= 3:
        return 0.85
    
    # Default: structured but sparse
    return 0.7


def _compute_legal_confidence(
    state: Dict[str, Any],
    result: Any,
) -> float:
    """
    Compute legal agent confidence from analysis quality.
    
    Factors:
    - 0.0: LLM fallback triggered
    - 0.2: No findings at all (empty analysis)
    - 0.5: Few findings, mostly low/medium severity
    - 0.8: Multiple findings with high/critical severity → high confidence
    - 0.95: Definitively dangerous/rejected verdict with critical findings
    
    The logic: finding traps takes expertise, so having detailed findings
    with high severity = high confidence in the analysis.
    """
    if state.get("_llm_fallback_triggered") and "legal" in state.get("_llm_fallback_agents", []):
        return 0.0
    
    findings_count = getattr(result, "findings_count", 0) or len(getattr(result, "findings", []))
    critical_count = getattr(result, "critical_count", 0)
    high_count = getattr(result, "high_count", 0)
    verdict_value = getattr(getattr(result, "verdict", None), "value", "")
    
    if findings_count == 0:
        return 0.2
    
    # Strong signals → high confidence
    if verdict_value in ("dangerous", "rejected"):
        if critical_count >= 2:
            return 0.95
        return 0.85
    
    if critical_count >= 1 or high_count >= 3:
        return 0.80
    
    if findings_count >= 5:
        return 0.70
    
    if findings_count >= 1:
        return 0.55
    
    return 0.3


# =============================================================================
# Уровень 2: RAG-инъекция уроков (Lessons Learned) в контекст агентов
# =============================================================================

async def _get_rag_context(
    agent_name: str,
    task_description: str,
    project_id: Optional[int] = None,
    include_traps: bool = False,
) -> str:
    """
    Получить RAG-контекст для агента: документы проекта + граф знаний + БЛС.

    Использует rag_pipeline для сборки полного контекста.
    Возвращает пустую строку если RAG недоступен или нет результатов.
    """
    try:
        context = await rag_pipeline.get_agent_context(
            query=task_description,
            agent=agent_name,
            project_id=project_id,
            top_k=5,
            include_graph=True,
            include_traps=include_traps,
        )
        if context:
            logger.info("RAG context injected for %s: %d chars", agent_name, len(context))
        return context
    except Exception as e:
        logger.warning("RAG context failed for %s: %s", agent_name, e)
        return ""


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
            logger.info(f"Lessons injected for {agent_name}: {len(context)} chars")
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
    logger.info("Hermes Orchestrator Router (v12.0)")
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
        
        # Check if any LLM fallbacks occurred during the pipeline
        if state.get("_llm_fallback_triggered"):
            fallback_agents = state.get("_llm_fallback_agents", [])
            logger.warning(
                "LLM fallback detected for agents: %s. Verdict may be unreliable.",
                ", ".join(fallback_agents),
            )
        
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
    logger.info("Archive Processing Starting")
    rules = load_wiki_page("Archive_Rules")
    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"Задача:\n{state['task_description']}\n\n"
        f"Зарегистрируйте входящий пакет документов."
    )

    messages = [{"role": "user", "content": prompt}]
    result_text = await _safe_agent_chat(
        "archive",
        messages,
        state,
        fallback_response='{"status": "registered", "doc_id": "REG-001"}',
    )

    try:
        archive_data = json.loads(result_text)
        confidence = _compute_agent_confidence(state, "archive", result_text, archive_data)
    except (json.JSONDecodeError, TypeError):
        archive_data = {"status": "unknown", "doc_id": "PARSE_ERROR"}
        confidence = _compute_agent_confidence(state, "archive", result_text, None)

    return {
        "archive_result": {
            "doc_id": archive_data.get("doc_id", "UNKNOWN"),
            "status": archive_data.get("status", "unknown"),
            "pages_registered": archive_data.get("pages", 0),
            "confidence_score": confidence,
        },
        "confidence_scores": {**state.get("confidence_scores", {}), "archive": confidence},
        "next_step": "archive",
    }


async def archive_ingest_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Узел инвентаризации: парсинг + индексация документа.
    Вызывается когда archive находит новый документ для обработки.

    Использует RAG Pipeline для полного цикла: file → parse → index.
    """
    logger.info("Archive Ingest: parsing and indexing documents")
    intermediate = state.get("intermediate_data", {})
    file_path = intermediate.get("file_path") or intermediate.get("contract_path")

    if not file_path or not os.path.exists(file_path):
        logger.warning("Archive Ingest: no file_path found in state")
        return {"next_step": "archive"}

    project_id = state["project_id"]

    # Полный цикл: парсинг + индексация через RAG Pipeline
    try:
        doc = await rag_pipeline.ingest(
            file_path=file_path,
            project_id=project_id,
            doc_type="unknown",
            embed=True,
            auto_classify=True,
        )
        if doc:
            logger.info(
                "Archive Ingest: doc #%d created (%s), %d chunks indexed",
                doc.id, doc.doc_type, len(doc.chunks),
            )
            return {
                "archive_result": {
                    "doc_id": str(doc.id),
                    "status": "indexed",
                    "pages_registered": len(doc.chunks),
                    "confidence_score": 0.9,
                },
                "intermediate_data": {
                    **intermediate,
                    "ingested_doc_id": doc.id,
                    "ingested_doc_type": doc.doc_type,
                },
                "next_step": "archive",
            }
    except Exception as e:
        logger.error("Archive Ingest failed: %s", e)

    return {"next_step": "archive"}


async def procurement_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Закупщика: Анализ тендера и НМЦК. (Gemma 4 31B)"""
    logger.info("Procurement Analysis Starting")
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
    result_text = await _safe_agent_chat(
        "procurement",
        messages,
        state,
        fallback_response='{"lot_id": "T-100", "nmck": 50000000, "decision": "bid"}',
    )

    try:
        proc_data = json.loads(result_text)
        confidence = _compute_agent_confidence(state, "procurement", result_text, proc_data)
    except (json.JSONDecodeError, TypeError):
        proc_data = {}
        confidence = _compute_agent_confidence(state, "procurement", result_text, None)

    return {
        "procurement_result": {
            "lot_id": proc_data.get("lot_id", ""),
            "nmck": proc_data.get("nmck", 0),
            "nmck_vs_market": proc_data.get("nmck_vs_market", 0),
            "competitor_count": proc_data.get("competitor_count", 0),
            "decision": proc_data.get("decision", "bid"),
            "confidence_score": confidence,
        },
        "confidence_scores": {**state.get("confidence_scores", {}), "procurement": confidence},
        "next_step": "procurement",
    }


async def pto_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел ПТО: Анализ объемов работ через LLM. (Gemma 4 31B VLM)"""
    logger.info("PTO Analysis Starting")
    rules = load_wiki_page("PTO_Rules")
    work_type = _extract_work_type(state)

    # v12.0: Извлечение текста из файла, если он передан в стейте
    intermediate = state.get("intermediate_data", {})
    file_path = intermediate.get("file_path")
    document_text = intermediate.get("document_text", "")

    if file_path and os.path.exists(file_path):
        logger.info("PTO reading file: %s", os.path.basename(file_path))
        if file_path.endswith(".docx"):
            doc = docx.Document(file_path)
            document_text = "\n".join([para.text for para in doc.paragraphs])
        elif file_path.endswith(".pdf"):
            with fitz.open(file_path) as doc:
                document_text = "\n".join([page.get_text() for page in doc])
    
    # v12.0: RAG-инъекция уроков (Lessons Learned)
    lessons = await _get_lessons_context("ПТО", state['task_description'], work_type)
    # v12.0: RAG-контекст из документов проекта
    project_id = state.get("project_id")
    rag_ctx = await _get_rag_context("pto", state['task_description'], project_id)
    
    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"{lessons}\n\n"
        f"{rag_ctx}\n\n"
        f"Задача:\n{state['task_description']}\n\n"
        f"Контекст документа:\n{document_text[:10000]}\n\n"
        f"Извлеките ВОР в формате JSON (укажите только JSON)."
    )

    messages = [{"role": "user", "content": prompt}]
    start_time = datetime.now()

    result_text = await _safe_agent_chat(
        "pto",
        messages,
        state,
        fallback_response='{"earthworks": 1500, "concrete": 200}',
    )

    duration = int((datetime.now() - start_time).total_seconds() * 1000)

    try:
        vor_data = json.loads(result_text)
        confidence = _compute_agent_confidence(state, "pto", result_text, vor_data)
    except (json.JSONDecodeError, TypeError):
        vor_data = {"raw_text": result_text}
        confidence = _compute_agent_confidence(state, "pto", result_text, None)

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
            "confidence_score": confidence,
            "total_positions": len(vor_data.get("volumes", [])),
            "drawing_refs": [vor_data.get("source_drawing", "")],
            "unit_mismatches": 0,
        },
        "confidence_scores": {**state.get("confidence_scores", {}), "pto": confidence},
        "next_step": "pto",
    }


async def logistics_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Логиста: Поиск поставщиков и цен. (Gemma 4 31B)"""
    logger.info("Logistics Sourcing Starting")
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
    result_text = await _safe_agent_chat(
        "logistics",
        messages,
        state,
        fallback_response='{"vendors": ["MetalInvest", "Severstal"], "best_price": 65000}',
    )

    try:
        log_data = json.loads(result_text)
        confidence = _compute_agent_confidence(state, "logistics", result_text, log_data)
    except (json.JSONDecodeError, TypeError):
        log_data = {}
        confidence = _compute_agent_confidence(state, "logistics", result_text, None)

    return {
        "logistics_result": {
            "vendors_found": len(log_data.get("vendors", [])),
            "best_price": log_data.get("best_price", 0),
            "delivery_available": log_data.get("delivery_available", True),
            "lead_time_days": log_data.get("lead_time_days", 14),
            "confidence_score": confidence,
        },
        "confidence_scores": {**state.get("confidence_scores", {}), "logistics": confidence},
        "next_step": "logistics",
    }


async def smeta_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Узел Сметчика: Расчет стоимостей через LLM. (Gemma 4 31B)"""
    logger.info("Smeta Calculation Starting")
    rules = load_wiki_page("Smeta_Rules")
    # Read VOR from typed state field (v2.0) or fall back to intermediate_data
    vor = state.get("vor_result") or state.get("intermediate_data", {}).get("vor", {})
    work_type = _extract_work_type(state)
    # v12.0: RAG-инъекция уроков (Lessons Learned)
    lessons = await _get_lessons_context("Сметчик", state['task_description'], work_type)
    # v12.0: RAG-контекст
    project_id = state.get("project_id")
    rag_ctx = await _get_rag_context("smeta", state['task_description'], project_id)

    prompt = (
        f"Инструкции:\n{rules}\n\n"
        f"{lessons}\n\n"
        f"{rag_ctx}\n\n"
        f"Доступные объемы:\n{json.dumps(vor, ensure_ascii=False)}\n\n"
        f"Оцените стоимость, верните валидный JSON."
    )
    messages = [{"role": "user", "content": prompt}]

    result_text = await _safe_agent_chat(
        "smeta",
        messages,
        state,
        fallback_response='{"earthworks_cost": 150000, "concrete_cost": 20000}',
    )

    try:
        smeta_data = json.loads(result_text)
        confidence = _compute_agent_confidence(state, "smeta", result_text, smeta_data)
    except (json.JSONDecodeError, TypeError):
        smeta_data = {"raw_costs": result_text}
        confidence = _compute_agent_confidence(state, "smeta", result_text, None)

    return {
        "smeta_result": {
            "total_cost": smeta_data.get("grand_totals", {}).get("total_with_vat", 0),
            "nmck": 0,
            "profit_margin_pct": 0,
            "fer_positions_used": len(smeta_data.get("grand_totals", {})),
            "confidence_score": confidence,
        },
        "confidence_scores": {**state.get("confidence_scores", {}), "smeta": confidence},
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
    logger.info("Legal Review Starting")

    from src.core.services.legal_service import legal_service
    from src.schemas.legal import LegalAnalysisRequest, ReviewType

    # Determine document source
    intermediate = state.get("intermediate_data", {})
    document_text = intermediate.get("document_text")
    file_path = intermediate.get("contract_path") or intermediate.get("file_path")
    document_id = intermediate.get("document_id")

    # v12.0: Извлечение текста из файла контракта (.docx/.pdf)
    if file_path and os.path.exists(file_path):
        logger.info("Legal reading file: %s", os.path.basename(file_path))
        if file_path.endswith(".docx"):
            doc = docx.Document(file_path)
            document_text = "\n".join([para.text for para in doc.paragraphs])
        elif file_path.endswith(".pdf"):
            with fitz.open(file_path) as doc:
                document_text = "\n".join([page.get_text() for page in doc])

    # v12.0: RAG-инъекция уроков (Lessons Learned)
    work_type = _extract_work_type(state)
    lessons = await _get_lessons_context("Юрист", state['task_description'], work_type)
    # v12.0: RAG-контекст (документы проекта + граф знаний + БЛС)
    project_id = state.get("project_id")
    rag_ctx = await _get_rag_context("legal", state['task_description'], project_id, include_traps=True)
    # Уроки + RAG добавляются в document_text для LegalService
    if lessons and document_text:
        document_text = f"{lessons}\n\n{document_text}"
    if rag_ctx and document_text:
        document_text = f"{rag_ctx}\n\n{document_text}"

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

        # Compute confidence from actual analysis quality
        legal_confidence = _compute_legal_confidence(state, result)

        return {
            "findings": findings_dicts,
            "legal_result": {
                "verdict": result.verdict.value,
                "findings_count": len(findings_dicts),
                "critical_count": result.critical_count,
                "high_count": result.high_count,
                "summary": result.summary,
                "protocol_items_count": 0,
                "confidence_score": legal_confidence,
                "blc_matches": [],
            },
            "confidence_scores": {**state.get("confidence_scores", {}), "legal": legal_confidence},
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
    logger.info("Self-Optimization Loop Starting")
    await run_reflection_cycle()
    return {"is_complete": True}
