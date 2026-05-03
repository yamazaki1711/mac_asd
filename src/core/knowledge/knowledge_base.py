"""
ASD v12.0 — Knowledge Base (RAG over DomainTraps).

Provides semantic search over stored domain knowledge (legal traps, PTO patterns,
procurement insights) using pgvector + bge-m3 embeddings.

DomainTrap entries are ingested from Telegram channels, internal experience,
and court case analysis.

Usage:
    from src.core.knowledge.knowledge_base import knowledge_base

    # Search for relevant knowledge
    results = knowledge_base.search("сроки выполнения работ", domain="legal", top_k=5)

    # Index a new trap
    knowledge_base.index_trap(domain="legal", title="...", description="...", source="@channel")
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.db.init_db import SessionLocal
from src.db.models import DomainTrap

logger = logging.getLogger(__name__)


# =============================================================================
# Knowledge Base — pgvector RAG
# =============================================================================

class KnowledgeBase:
    """
    Semantic search over domain knowledge using pgvector + bge-m3.

    Domains: legal, pto, smeta, logistics, procurement

    Two-tier architecture:
      Tier 1 — Vector search (pgvector): primary, when PostgreSQL available
      Tier 2 — Keyword search (PostgreSQL ILIKE): fallback when pgvector unavailable
    """

    EMBEDDING_DIM = 1024  # bge-m3

    def __init__(self):
        self._vector_available = None

    @property
    def vector_available(self) -> bool:
        """Check if pgvector extension is installed."""
        if self._vector_available is None:
            try:
                db: Session = SessionLocal()
                db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
                db.close()
                self._vector_available = True
            except Exception:
                self._vector_available = False
        return self._vector_available

    # =========================================================================
    # Search
    # =========================================================================

    def search(
        self,
        query: str,
        domain: Optional[str] = None,
        top_k: int = 5,
        min_weight: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over stored knowledge.

        Args:
            query: Search query in Russian
            domain: Filter by domain (legal/pto/smeta/logistics/procurement) or None for all
            top_k: Number of results to return
            min_weight: Minimum weight threshold (0-100)

        Returns:
            List of {id, domain, title, description, source, channel, mitigation, score, ...}
        """
        if self.vector_available:
            return self._vector_search(query, domain, top_k, min_weight)
        else:
            logger.info("pgvector unavailable — falling back to keyword search")
            return self._keyword_search(query, domain, top_k, min_weight)

    def _vector_search(
        self, query: str, domain: Optional[str], top_k: int, min_weight: int,
    ) -> List[Dict[str, Any]]:
        """pgvector similarity search."""
        # Generate embedding via bge-m3 (fallback: pseudo-embedding from keywords)
        embedding = self._generate_embedding(query)

        db: Session = SessionLocal()
        try:
            # pgvector cosine similarity search
            params = {
                "embedding": embedding,
                "top_k": top_k,
                "min_weight": min_weight,
            }
            domain_filter = ""
            if domain:
                domain_filter = "AND domain = :domain"
                params["domain"] = domain

            sql = text(f"""
                SELECT id, domain, title, description, source, channel,
                       category, weight, court_cases, mitigation,
                       1 - (embedding <=> :embedding) AS similarity
                FROM domain_traps
                WHERE weight >= :min_weight
                  {domain_filter}
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> :embedding
                LIMIT :top_k
            """)

            result = db.execute(sql, params)
            rows = result.fetchall()
            return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            logger.warning("Vector search failed: %s — falling back to keyword", e)
            return self._keyword_search(query, domain, top_k, min_weight)
        finally:
            db.close()

    def _keyword_search(
        self, query: str, domain: Optional[str], top_k: int, min_weight: int,
    ) -> List[Dict[str, Any]]:
        """Keyword search fallback using ILIKE."""
        db: Session = SessionLocal()
        try:
            # Build ILIKE patterns from query words
            words = [w for w in re.split(r'\s+', query.strip()) if len(w) >= 3]
            if not words:
                words = [query]

            conditions = []
            params: Dict[str, Any] = {"top_k": top_k, "min_weight": min_weight}
            for i, word in enumerate(words):
                param_name = f"word_{i}"
                conditions.append(
                    f"(title ILIKE '%' || :{param_name} || '%' OR "
                    f"description ILIKE '%' || :{param_name} || '%')"
                )
                params[param_name] = word

            domain_filter = ""
            if domain:
                domain_filter = "AND domain = :domain"
                params["domain"] = domain

            sql = text(f"""
                SELECT id, domain, title, description, source, channel,
                       category, weight, court_cases, mitigation,
                       0.5 AS similarity
                FROM domain_traps
                WHERE weight >= :min_weight
                  {domain_filter}
                  AND ({" OR ".join(conditions)})
                ORDER BY weight DESC
                LIMIT :top_k
            """)

            result = db.execute(sql, params)
            rows = result.fetchall()
            return [self._row_to_dict(row) for row in rows]

        except Exception as e:
            logger.error("Keyword search failed: %s", e)
            return []
        finally:
            db.close()

    # =========================================================================
    # Indexing
    # =========================================================================

    def index_trap(
        self,
        domain: str,
        title: str,
        description: str,
        source: str = "",
        channel: str = "",
        category: str = "",
        weight: int = 100,
        court_cases: Optional[List[str]] = None,
        mitigation: str = "",
    ) -> Optional[int]:
        """
        Index a new domain trap in the knowledge base.

        Args:
            domain: legal | pto | smeta | logistics | procurement
            title: Short descriptive title
            description: Full trap description
            source: Source identifier (e.g. "@advokatgrikevich")
            channel: Channel username
            category: Domain-specific category
            weight: Importance weight (0-100)
            court_cases: List of related court case numbers
            mitigation: Recommended mitigation strategy

        Returns:
            trap_id if successful, None if duplicate
        """
        # Deduplicate: check if similar trap already exists
        existing = self.search(title, domain=domain, top_k=1, min_weight=0)
        if existing and existing[0].get("similarity", 0) > 0.85:
            logger.info("Duplicate trap detected: %s", title[:80])
            return None

        # Generate embedding
        embedding = self._generate_embedding(f"{title}\n\n{description}")

        db: Session = SessionLocal()
        try:
            trap = DomainTrap(
                domain=domain,
                title=title,
                description=description,
                source=source or "manual",
                channel=channel or "",
                category=category or "",
                weight=weight,
                court_cases=court_cases or [],
                mitigation=mitigation or "",
                embedding=embedding,
            )
            db.add(trap)
            db.commit()
            db.refresh(trap)
            logger.info("Indexed trap #%d: %s [%s]", trap.id, title[:60], domain)
            return trap.id

        except Exception as e:
            db.rollback()
            logger.error("Failed to index trap: %s", e)
            return None
        finally:
            db.close()

    def index_batch(
        self, traps: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Batch-index multiple traps.

        Returns:
            (indexed_count, skipped_count)
        """
        indexed, skipped = 0, 0
        for trap in traps:
            trap_id = self.index_trap(
                domain=trap.get("domain", "legal"),
                title=trap.get("title", ""),
                description=trap.get("description", ""),
                source=trap.get("source", ""),
                channel=trap.get("channel", ""),
                category=trap.get("category", ""),
                weight=trap.get("weight", 100),
                court_cases=trap.get("court_cases", []),
                mitigation=trap.get("mitigation", ""),
            )
            if trap_id:
                indexed += 1
            else:
                skipped += 1

        logger.info("Batch indexed: %d new, %d skipped", indexed, skipped)
        return indexed, skipped

    # =========================================================================
    # Embedding generation
    # =========================================================================

    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate bge-m3 embedding (1024 dim).

        Uses sentence-transformers if model is cached. Falls back to
        deterministic hash embedding on first run (model download is 2.2 GB).

        Set ASD_BGE_MODEL=1 to force model download.
        """
        import os
        if os.environ.get("ASD_BGE_MODEL") == "1":
            try:
                from sentence_transformers import SentenceTransformer
                model = SentenceTransformer("BAAI/bge-m3")
                embedding = model.encode(text[:8192], normalize_embeddings=True)
                return embedding.tolist()
            except ImportError:
                logger.debug("sentence-transformers not installed")
            except Exception as e:
                logger.warning("bge-m3 embedding failed: %s", e)

        # Deterministic hash fallback
        return self._hash_embedding(text)

    @staticmethod
    def _hash_embedding(text: str) -> List[float]:
        """
        Fallback: deterministic embedding from text hash.

        NOT semantically meaningful, but allows pgvector to function.
        Real bge-m3 embeddings will be loaded when sentence-transformers
        is installed on the production machine (Mac Studio).
        """
        import hashlib

        # Generate 1024 deterministic floats from text hash
        h = hashlib.sha256(text.encode("utf-8")).digest()
        floats = []
        for i in range(0, min(len(h), 128), 4):
            val = int.from_bytes(h[i:i + 4], "big") / (2 ** 32)
            floats.append(val * 2 - 1)  # Normalize to [-1, 1]

        # Pad to 1024 dimensions
        while len(floats) < 1024:
            floats.append(floats[len(floats) % len(floats)] * 0.5)

        return floats[:1024]

    # =========================================================================
    # Stats
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics."""
        db: Session = SessionLocal()
        try:
            total = db.query(DomainTrap).count()
            by_domain = {}
            for domain in ["legal", "pto", "smeta", "logistics", "procurement"]:
                count = db.query(DomainTrap).filter(DomainTrap.domain == domain).count()
                if count:
                    by_domain[domain] = count

            embedded = db.query(DomainTrap).filter(
                DomainTrap.embedding.isnot(None)
            ).count()

            return {
                "total_traps": total,
                "by_domain": by_domain,
                "embedded": embedded,
                "vector_available": self.vector_available,
                "timestamp": datetime.now().isoformat(),
            }
        finally:
            db.close()

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        """Convert SQLAlchemy row to dict."""
        return {
            "id": row[0],
            "domain": row[1],
            "title": row[2],
            "description": row[3][:500] if row[3] else "",
            "source": row[4],
            "channel": row[5],
            "category": row[6],
            "weight": row[7],
            "court_cases": row[8] if row[8] else [],
            "mitigation": row[9] or "",
            "similarity": round(float(row[10]), 3) if len(row) > 10 else 0.5,
        }


# Singleton
knowledge_base = KnowledgeBase()
