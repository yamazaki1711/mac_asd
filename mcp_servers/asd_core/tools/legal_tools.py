"""Legal tools — federal law lookup, RAG-based compliance search."""

from typing import Optional


def legal_search(
    query: str,
    law_code: Optional[str] = None,
    article: Optional[str] = None,
) -> dict:
    """
    Поиск нормы закона по тексту или ссылке.

    Args:
        query: Текстовый запрос или ключевые слова.
        law_code: Код закона (ФЗ-44, ФЗ-223, ГК РФ...).
        article: Номер статьи (например "34", "ст. 34").

    Returns:
        dict с текстом нормы и ссылками.
    """
    return {
        "status": "not_implemented",
        "query": query,
        "law_code": law_code,
        "article": article,
        "results": [],
        "metadata": {
            "note": "Legal DB pending initialization",
        },
    }


def fz_lookup(
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
    return {
        "status": "not_implemented",
        "law": law,
        "article": article,
        "part": part,
        "clause": clause,
        "text": "",
        "metadata": {
            "note": "FZ text DB pending initialization",
        },
    }


def rag_query(
    query: str,
    index: str = "legal_rag",
    top_k: int = 5,
) -> dict:
    """
    RAG-поиск по базе юридических документов.

    Args:
        query: Текстовый запрос.
        index: Имя векторного индекса.
        top_k: Количество результатов.

    Returns:
        dict с релевантными фрагментами документов.
    """
    return {
        "status": "not_implemented",
        "query": query,
        "index": index,
        "top_k": top_k,
        "results": [],
        "metadata": {
            "note": "LightRAG index pending initialization",
        },
    }
