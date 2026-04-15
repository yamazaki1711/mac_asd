"""Smeta tools — rate lookup, index calculation, estimate queries."""

from typing import Optional
import json
import os


# Default paths (overridden by agent config at runtime)
_RATES_PATH = "./data/rates/fer_2024.json"
_INDICES_PATH = "./data/indices/minstroy_latest.json"


def smeta_query(
    query: str,
    category: Optional[str] = None,
    limit: int = 5,
) -> dict:
    """
    Поиск расценок в базе ФЕР/ГЭСН.

    Args:
        query: Текстовый запрос (описание работы).
        category: Категория расценки (строительные, монтаж, отделка...).
        limit: Максимум результатов.

    Returns:
        dict со списком подходящих расценок и метаданными.
    """
    # TODO: load rates from JSON/DB and perform fuzzy match
    return {
        "status": "not_implemented",
        "query": query,
        "category": category,
        "results": [],
        "metadata": {
            "note": "Rates DB pending initialization",
        },
    }


def smeta_rate_lookup(rate_code: str) -> dict:
    """
    Получить расценку по точному коду (например "ФЕРрр-01-001").

    Args:
        rate_code: Код расценки.

    Returns:
        dict с полями: unit_price, labor, materials, machinery, unit.
    """
    return {
        "status": "not_implemented",
        "rate_code": rate_code,
        "metadata": {
            "note": "Rate lookup pending rates DB",
        },
    }


def index_lookup(
    region: str = "federal",
    quarter: Optional[str] = None,
) -> dict:
    """
    Получить индекс Минстроя для пересчёта сметной стоимости.

    Args:
        region: Регион (по умолчанию federal).
        quarter: Квартал в формате "2024-Q2". Если None — последний доступный.

    Returns:
        dict с индексами по группам затрат.
    """
    # TODO: load from minstroy indices file
    return {
        "status": "not_implemented",
        "region": region,
        "quarter": quarter,
        "indices": {},
        "metadata": {
            "note": "Index DB pending initialization",
        },
    }
