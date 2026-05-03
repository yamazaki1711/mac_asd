"""
ASD v12.0 — Legal MCP Tools.

Legal research: federal law lookup, RAG search, normative compliance.
Delegates to legal_service for LLM-powered analysis.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Inline FZ-44 / FZ-223 article database (key articles) ──

_FZ44_ARTICLES = {
    "34": {
        "title": "Статья 34. Контракт",
        "summary": "Контракт заключается на условиях, предусмотренных извещением об осуществлении закупки. Цена контракта является твёрдой. При заключении и исполнении контракта изменение его существенных условий не допускается.",
        "key_points": [
            "Цена контракта — твёрдая (ч.2)",
            "В контракт включается условие об ответственности заказчика и поставщика (ч.4-8)",
            "Штрафы: для поставщика — по ПП РФ №1042, для заказчика — по ПП РФ №1042",
            "Изменение существенных условий — только в случаях, прямо предусмотренных статьёй 95",
        ],
    },
    "95": {
        "title": "Статья 95. Изменение, расторжение контракта",
        "summary": "Изменение существенных условий контракта при его исполнении не допускается, за исключением случаев, предусмотренных настоящей статьёй.",
        "key_points": [
            "Снижение цены без изменения объёма — допускается (п.1)",
            "Увеличение/уменьшение объёма до 10% — допускается (пп.б п.1)",
            "Расторжение по соглашению сторон, по решению суда, односторонний отказ (ч.8-9)",
            "Срок приёмки — не более 20 рабочих дней (ч.13 ст.94)",
        ],
    },
    "94": {
        "title": "Статья 94. Особенности исполнения контракта",
        "summary": "Исполнение контракта включает приёмку, оплату, взаимодействие заказчика и поставщика.",
        "key_points": [
            "Приёмка — экспертиза своими силами или с привлечением экспертов (ч.3)",
            "Срок приёмки — не более 20 рабочих дней (ч.13)",
            "Мотивированный отказ от подписания документа о приёмке (ч.13)",
        ],
    },
}

_FZ223_ARTICLES = {
    "3": {
        "title": "Статья 3. Принципы и основные положения закупки",
        "summary": "Закупки проводятся на основе Положения о закупке заказчика. Принципы: информационная открытость, равноправие, целевое расходование средств.",
    },
    "4": {
        "title": "Статья 4. Информационное обеспечение закупки",
        "summary": "Положение о закупке, изменения, извещения, документация, протоколы размещаются в ЕИС в течение 15 дней.",
    },
}


async def legal_search(
    query: str,
    law_code: Optional[str] = None,
    article: Optional[str] = None,
) -> dict:
    """
    Поиск нормы закона по тексту или ссылке.

    Args:
        query: Текстовый запрос или ключевые слова.
        law_code: Код закона (fz44, fz223, gk, grk).
        article: Номер статьи (например "34").

    Returns:
        dict с текстом нормы и ссылками.
    """
    results = []

    # Direct article lookup
    if article:
        article = article.replace("ст.", "").replace(" ", "").strip()
        if law_code == "fz44" or not law_code:
            art = _FZ44_ARTICLES.get(article)
            if art:
                results.append({"law": "ФЗ-44", "article": article, **art})
        if law_code == "fz223" or not law_code:
            art = _FZ223_ARTICLES.get(article)
            if art:
                results.append({"law": "ФЗ-223", "article": article, **art})

    # Text search (simple keyword match)
    query_lower = query.lower()
    if not results:
        for code, db in [("ФЗ-44", _FZ44_ARTICLES), ("ФЗ-223", _FZ223_ARTICLES)]:
            if law_code and not code.lower().endswith(law_code.lower()):
                continue
            for art_num, art_data in db.items():
                if query_lower in art_data.get("summary", "").lower():
                    results.append({"law": code, "article": art_num, **art_data})

    return {
        "status": "ok",
        "query": query,
        "law_code": law_code,
        "article": article,
        "results_count": len(results),
        "results": results,
    }


async def fz_lookup(
    law: str,
    article: Optional[str] = None,
    part: Optional[str] = None,
    clause: Optional[str] = None,
) -> dict:
    """
    Получить точную статью федерального закона.

    Args:
        law: "fz44" | "fz223".
        article: Номер статьи.
        part: Часть статьи.
        clause: Пункт.

    Returns:
        dict с полным текстом нормы.
    """
    db = _FZ44_ARTICLES if law == "fz44" else _FZ223_ARTICLES
    law_name = "ФЗ-44" if law == "fz44" else "ФЗ-223"

    if article:
        article = article.replace("ст.", "").replace(" ", "").strip()
        art = db.get(article)
        if art:
            return {
                "status": "ok",
                "law": law_name,
                "article": article,
                "part": part,
                "clause": clause,
                "title": art["title"],
                "summary": art["summary"],
                "key_points": art.get("key_points", []),
            }

    return {
        "status": "not_found",
        "law": law_name,
        "article": article,
        "message": f"Статья {article} {law_name} не найдена в локальной базе",
    }


async def rag_query(
    query: str,
    index: str = "legal",
    top_k: int = 5,
) -> dict:
    """
    RAG-поиск по базе юридических документов.

    Использует LightRAG (Graph + Vector) через legal_service.

    Args:
        query: Текстовый запрос.
        index: Имя векторного индекса (legal / normative).
        top_k: Количество результатов.

    Returns:
        dict с релевантными фрагментами документов.
    """
    try:
        from src.core.services.legal_service import legal_service
        result = await legal_service.normative_search(query, top_k=top_k)
        return {"status": "ok", "query": query, "index": index, **result}
    except ImportError:
        logger.warning("legal_service not available for RAG query")
        return {
            "status": "unavailable",
            "query": query,
            "index": index,
            "top_k": top_k,
            "results": [],
            "message": "LightRAG engine pending initialization",
        }
