"""
ASD v11.0 — Jurist MCP Tools.

Updated for MLX-only architecture + LegalService integration.
No Ollama/Linux dependencies.
"""

import logging
from typing import Dict, Any, List, Optional

from src.schemas.legal import (
    LegalAnalysisRequest,
    ReviewType,
    BLCEntry,
    BLCTrapExtraction,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Document Upload & Parsing
# =============================================================================

async def asd_upload_document(file_path: str) -> Dict[str, Any]:
    """Загрузка + парсинг документа (PDF/DOCX/TXT)."""
    logger.info(f"asd_upload_document: {file_path}")

    from src.core.services.legal_service import legal_service

    result = await legal_service.upload_and_parse(file_path)
    return result.model_dump()


# =============================================================================
# Contract Analysis (Map-Reduce + БЛС)
# =============================================================================

async def asd_analyze_contract(
    document_text: Optional[str] = None,
    file_path: Optional[str] = None,
    document_id: Optional[int] = None,
    review_type: str = "contract",
    work_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Юридическая экспертиза контракта.

    Поддерживаемые review_type:
    - contract: экспертиза договора/контракта
    - tender: экспертиза тендерной документации
    - compliance: проверка соответствия нормативке
    - id_check: проверка состава ИД

    Поддерживаемые work_type:
    - общестроительные, бетонные, земляные, сварочные, монтажные, шпунтовые
    """
    logger.info(f"asd_analyze_contract: type={review_type}, work={work_type}")

    from src.core.services.legal_service import legal_service

    # Map string review_type to enum
    review_type_map = {
        "contract": ReviewType.CONTRACT,
        "tender": ReviewType.TENDER,
        "compliance": ReviewType.COMPLIANCE,
        "id_check": ReviewType.ID_CHECK,
    }
    rt = review_type_map.get(review_type, ReviewType.CONTRACT)

    request = LegalAnalysisRequest(
        document_text=document_text,
        file_path=file_path,
        document_id=document_id,
        review_type=rt,
        work_type=work_type,
    )

    result = await legal_service.analyze(request)
    return result.model_dump()


# =============================================================================
# Normative Search
# =============================================================================

async def asd_normative_search(query: str) -> Dict[str, Any]:
    """Поиск по нормативной базе (Graph+Vector/RAG)."""
    logger.info(f"asd_normative_search: {query}")

    from src.core.rag_service import rag_service

    results = await rag_service.hybrid_search(query)
    return {
        "status": "success",
        "query": query,
        "results": results,
    }


# =============================================================================
# Document Generation (stubs → future DOCX generation)
# =============================================================================

async def asd_generate_protocol(document_id: str) -> Dict[str, Any]:
    """Протокол разногласий (DOCX)."""
    logger.info(f"asd_generate_protocol: {document_id}")
    return {
        "status": "success",
        "document_id": document_id,
        "mock_content": "Протокол разногласий к договору №...",
        "action": "DOCX generation stubbed — will be implemented with docx skill",
    }


async def asd_generate_claim(document_id: str) -> Dict[str, Any]:
    """Претензия при неоплате СМР (DOCX)."""
    logger.info(f"asd_generate_claim: {document_id}")
    return {
        "status": "success",
        "document_id": document_id,
        "mock_content": "Претензия о нарушении сроков оплаты...",
        "action": "DOCX generation stubbed — will be implemented with docx skill",
    }


async def asd_generate_lawsuit(document_id: str) -> Dict[str, Any]:
    """Исковое заявление в арбитраж (DOCX)."""
    logger.info(f"asd_generate_lawsuit: {document_id}")
    return {
        "status": "success",
        "document_id": document_id,
        "mock_content": "Исковое заявление в Арбитражный суд...",
        "action": "DOCX generation stubbed — will be implemented with docx skill",
    }


# =============================================================================
# БЛС (База Ловушек Субподрядчика) Management
# =============================================================================

async def asd_add_trap(
    title: str,
    description: str,
    source: str,
    mitigation: str,
    work_types: Optional[List[str]] = None,
    legal_basis: str = "",
    severity: str = "high",
) -> Dict[str, Any]:
    """
    Добавление «Ловушки субподрядчика» в БЛС.

    Args:
        title: Краткое название ловушки
        description: Полное описание
        source: Источник (ФЗ, судебная практика, опыт)
        mitigation: Рекомендация по защите
        work_types: Список видов работ (бетонные, земляные и т.д.)
        legal_basis: Нормативная база
        severity: critical/high/medium/low
    """
    logger.info(f"asd_add_trap: {title}")

    try:
        from src.core.rag_service import rag_service

        # Index the trap in RAG for future similarity search
        entry_text = f"Ловушка: {title}. {description}. Источник: {source}. Защита: {mitigation}"
        if work_types:
            entry_text += f". Виды работ: {', '.join(work_types)}"
        if legal_basis:
            entry_text += f". Нормативка: {legal_basis}"

        await rag_service.index_document(
            text=entry_text,
            metadata={
                "type": "blc_trap",
                "title": title,
                "severity": severity,
                "work_types": work_types or [],
            },
        )

        return {
            "status": "success",
            "message": f"Trap '{title}' added to BLC and indexed in RAG.",
            "work_types": work_types or [],
        }

    except Exception as e:
        logger.error(f"Failed to add trap: {e}")
        return {
            "status": "error",
            "message": str(e),
        }


async def asd_search_traps(
    query: str,
    work_type: Optional[str] = None,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Поиск ловушек в БЛС по запросу.

    Args:
        query: Поисковый запрос
        work_type: Фильтр по виду работ
        top_k: Количество результатов
    """
    logger.info(f"asd_search_traps: query={query}, work_type={work_type}")

    try:
        from src.core.rag_service import rag_service

        search_query = query
        if work_type:
            search_query = f"{query} {work_type}"

        results = await rag_service.search(
            search_query,
            top_k=top_k,
            filter_metadata={"type": "blc_trap"},
        )

        return {
            "status": "success",
            "query": query,
            "work_type_filter": work_type,
            "traps_found": len(results),
            "results": results,
        }

    except Exception as e:
        logger.error(f"Trap search failed: {e}")
        return {
            "status": "error",
            "message": str(e),
        }


# =============================================================================
# ID Check (Проверка состава ИД)
# =============================================================================

async def asd_check_id_composition(
    work_type: str,
    document_list: str,
) -> Dict[str, Any]:
    """
    Проверка состава исполнительной документации.

    Args:
        work_type: Вид работ (бетонные, земляные, сварочные, монтажные, шпунтовые, общестроительные)
        document_list: Список имеющихся документов (текст)
    """
    logger.info(f"asd_check_id_composition: work_type={work_type}")

    return await asd_analyze_contract(
        document_text=document_list,
        review_type="id_check",
        work_type=work_type,
    )
