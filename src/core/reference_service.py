"""
ASD v12.0 — ReferenceService: Unified domain reference data with caching.

Replaces scattered Python dicts (rate_lookup.py, work_spec.py, contract_risks.py)
with a single PostgreSQL-backed service with in-memory TTL cache.

Usage:
    from src.core.reference_service import reference_service

    # Lookup by domain + code
    item = await reference_service.get("smeta", "FER-01-02-003")

    # Semantic search
    results = await reference_service.search("pto", "арматура ø16")

    # List all codes for a domain
    codes = await reference_service.list_codes("legal")
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache TTL: 1 hour for reference data (updates are infrequent)
_CACHE_TTL = 3600
_CACHE_MAXSIZE = 1000


class ReferenceService:
    """
    Unified reference data service with TTL cache.

    Domains: legal, pto, smeta, logistics, procurement.
    Backed by domain_references table (PostgreSQL).
    Falls back to in-memory stubs when DB is unavailable.
    """

    def __init__(self):
        self._cache: Optional[Any] = None  # cachetools.TTLCache (lazy import)

    def _init_cache(self):
        if self._cache is None:
            try:
                from cachetools import TTLCache
                self._cache = TTLCache(maxsize=_CACHE_MAXSIZE, ttl=_CACHE_TTL)
            except ImportError:
                self._cache = {}  # Fallback: plain dict (no TTL)
        return self._cache

    def _cache_key(self, domain: str, code: str) -> str:
        return f"{domain}:{code}"

    # -------------------------------------------------------------------------
    # Single lookup
    # -------------------------------------------------------------------------

    async def get(
        self, domain: str, code: str, default: Any = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single reference entry by domain + code.

        Returns dict with keys: domain, code, description, data, valid_from, valid_to, source.
        """
        cache = self._init_cache()
        ck = self._cache_key(domain, code)
        if ck in cache:
            return cache[ck]

        try:
            from src.db.init_db import Session
            from src.db.models import ReferenceData
            from sqlalchemy import select

            with Session() as session:
                stmt = select(ReferenceData).where(
                    ReferenceData.domain == domain,
                    ReferenceData.code == code,
                )
                row = session.execute(stmt).scalar_one_or_none()
                if row:
                    result = self._row_to_dict(row)
                    cache[ck] = result
                    return result
        except Exception as e:
            logger.debug("ReferenceService.get(%s, %s) DB error: %s", domain, code, e)

        # Fallback to stubs for known domains
        stub = self._stub_lookup(domain, code)
        if stub:
            cache[ck] = stub
            return stub

        return default

    # -------------------------------------------------------------------------
    # Semantic search
    # -------------------------------------------------------------------------

    async def search(
        self, domain: str, query: str, top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search within a domain's reference data.
        Uses pgvector when available, falls back to text matching.
        """
        try:
            from src.db.init_db import Session
            from src.db.models import ReferenceData
            from src.core.llm_engine import llm_engine

            query_embedding = await llm_engine.embed(query)

            with Session() as session:
                from sqlalchemy import select
                stmt = (
                    select(ReferenceData)
                    .where(ReferenceData.domain == domain)
                    .order_by(ReferenceData.embedding.l2_distance(query_embedding))
                    .limit(top_k)
                )
                rows = session.execute(stmt).scalars().all()
                return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.debug("ReferenceService.search DB error: %s", e)

        # Fallback: text search over stubs
        return self._stub_search(domain, query, top_k)

    # -------------------------------------------------------------------------
    # List codes
    # -------------------------------------------------------------------------

    async def list_codes(self, domain: str) -> List[str]:
        """List all codes for a domain."""
        try:
            from src.db.init_db import Session
            from src.db.models import ReferenceData
            from sqlalchemy import select

            with Session() as session:
                stmt = select(ReferenceData.code).where(ReferenceData.domain == domain)
                return session.execute(stmt).scalars().all()
        except Exception as e:
            logger.debug("ReferenceService.list_codes DB error: %s", e)

        return list(self._stub_data.get(domain, {}).keys())

    # -------------------------------------------------------------------------
    # Upsert (for migration and updates)
    # -------------------------------------------------------------------------

    async def upsert(
        self, domain: str, code: str, description: str = "",
        data: Optional[Dict[str, Any]] = None,
        valid_from: Optional[datetime] = None,
        valid_to: Optional[datetime] = None,
        source: str = "internal",
    ) -> bool:
        """Insert or update a reference entry."""
        try:
            from src.db.init_db import Session
            from src.db.models import ReferenceData
            from src.core.llm_engine import llm_engine
            from sqlalchemy import select

            embed_text = f"{code}: {description}"
            embedding = await llm_engine.embed(embed_text)

            with Session() as session:
                stmt = select(ReferenceData).where(
                    ReferenceData.domain == domain,
                    ReferenceData.code == code,
                )
                existing = session.execute(stmt).scalar_one_or_none()

                if existing:
                    existing.description = description
                    existing.data = data or {}
                    existing.valid_from = valid_from
                    existing.valid_to = valid_to
                    existing.source = source
                    existing.embedding = embedding
                    existing.updated_at = datetime.now()
                else:
                    row = ReferenceData(
                        domain=domain, code=code, description=description,
                        data=data or {}, valid_from=valid_from,
                        valid_to=valid_to, source=source,
                        embedding=embedding,
                    )
                    session.add(row)

                session.commit()

            # Invalidate cache
            cache = self._init_cache()
            ck = self._cache_key(domain, code)
            cache.pop(ck, None)

            return True
        except Exception as e:
            logger.error("ReferenceService.upsert error: %s", e)
            return False

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        return {
            "id": row.id,
            "domain": row.domain,
            "code": row.code,
            "description": row.description,
            "data": row.data,
            "valid_from": row.valid_from.isoformat() if row.valid_from else None,
            "valid_to": row.valid_to.isoformat() if row.valid_to else None,
            "source": row.source,
        }

    # -------------------------------------------------------------------------
    # Stub data (fallback when DB is unavailable)
    # -------------------------------------------------------------------------

    _stub_data: Dict[str, Dict[str, Dict[str, Any]]] = {
        "legal": {
            "BLS-001": {
                "domain": "legal", "code": "BLS-001",
                "description": "Неустойка за срыв сроков по вине заказчика",
                "data": {"category": "penalty"},
                "source": "internal",
            },
        },
        "smeta": {
            "FER-01-02-003": {
                "domain": "smeta", "code": "FER-01-02-003",
                "description": "Разработка грунта экскаватором (ФЕР 01-02-003)",
                "data": {"unit": "1000м3", "base_price_kop": 12000000},
                "source": "ФСНБ-2024",
            },
        },
        "pto": {
            "AOSR-HIDDEN-WORK": {
                "domain": "pto", "code": "AOSR-HIDDEN-WORK",
                "description": "Акт освидетельствования скрытых работ — типовая форма",
                "data": {"form": "АОСР", "norm": "РД-11-02-2006"},
                "source": "Ростехнадзор",
            },
        },
    }

    def _stub_lookup(self, domain: str, code: str) -> Optional[Dict[str, Any]]:
        domain_data = self._stub_data.get(domain, {})
        return domain_data.get(code)

    def _stub_search(self, domain: str, query: str, top_k: int) -> List[Dict[str, Any]]:
        domain_data = self._stub_data.get(domain, {})
        results = list(domain_data.values())

        # Simple text match
        query_lower = query.lower()
        scored = []
        for item in results:
            score = 0
            desc = item.get("description", "").lower()
            code = item.get("code", "").lower()
            for word in query_lower.split():
                if word in code:
                    score += 3
                if word in desc:
                    score += 1
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]


# =============================================================================
# Singleton
# =============================================================================

reference_service = ReferenceService()
