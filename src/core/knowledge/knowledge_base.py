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

import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.db.models import DomainTrap

logger = logging.getLogger(__name__)

# Lazy DB access — defers sqlalchemy + model imports to first use
_db = None


def _lazy_db():
    global _db
    if _db is None:
        from sqlalchemy import text as _sql_text
        from src.db.init_db import SessionLocal as _SessionLocal
        from src.db.models import DomainTrap as _DomainTrap
        _db = (_sql_text, _SessionLocal, _DomainTrap)
    return _db


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

    @staticmethod
    def _get_session():
        """Create a new database session. SessionLocal handles connection pooling internally."""
        _, SessionLocal, _ = _lazy_db()
        return SessionLocal()

    @property
    def vector_available(self) -> bool:
        """Check if pgvector extension is installed."""
        if self._vector_available is None:
            try:
                text, _, _ = _lazy_db()
                with self._get_session() as db:
                    db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
                self._vector_available = True
            except (ImportError, OSError, RuntimeError) as e:
                logger.debug("pgvector unavailable: %s", e)
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
        embedding = self._generate_embedding(query)
        text, _, _ = _lazy_db()

        with self._get_session() as db:
            try:
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

    def _keyword_search(
        self, query: str, domain: Optional[str], top_k: int, min_weight: int,
    ) -> List[Dict[str, Any]]:
        """Keyword search fallback using ILIKE."""
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

        text, _, _ = _lazy_db()
        with self._get_session() as db:
            try:
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
        _, _, DomainTrap = _lazy_db()

        with self._get_session() as db:
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

    # Cache for embeddings to avoid re-computing identical texts
    _embedding_cache: Dict[str, List[float]] = {}
    _embedding_cache_max_size = 1000

    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate bge-m3 embedding (1024 dim).

        Tries in order:
          1. Ollama embeddings API (bge-m3) — primary for dev_linux
          2. sentence-transformers (bge-m3) — primary for mac_studio / ASD_BGE_MODEL=1
          3. Deterministic hash fallback — only when nothing else works
        """
        # Truncate and normalize for embedding
        text_for_embed = text[:8192].strip()
        if not text_for_embed:
            text_for_embed = " "

        # Check cache
        cache_key = text_for_embed
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        embedding = None

        # Tier 1: Ollama embeddings API (Linux, dev_linux profile)
        embedding = self._ollama_embed(text_for_embed)

        # Tier 2: sentence-transformers (Mac Studio, or explicit opt-in)
        if embedding is None and os.environ.get("ASD_BGE_MODEL") == "1":
            embedding = self._sentence_transformers_embed(text_for_embed)

        # Tier 3: Deterministic hash fallback (last resort)
        if embedding is None:
            embedding = self._hash_embedding(text_for_embed)

        # Cache
        if len(self._embedding_cache) < self._embedding_cache_max_size:
            self._embedding_cache[cache_key] = embedding

        return embedding

    @staticmethod
    def _ollama_embed(text: str) -> Optional[List[float]]:
        """Generate embedding via Ollama API (bge-m3)."""
        try:
            import json
            import urllib.request

            body = json.dumps({"model": "bge-m3", "prompt": text}).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/embeddings",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                embedding = data.get("embedding")
                if embedding and len(embedding) == 1024:
                    return embedding
                logger.debug("Ollama embedding returned dim=%d, expected 1024",
                           len(embedding) if embedding else 0)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.debug("Ollama embedding failed: %s", e)  # fall through to next tier
        return None

    @staticmethod
    def _sentence_transformers_embed(text: str) -> Optional[List[float]]:
        """Generate embedding via sentence-transformers (bge-m3)."""
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("BAAI/bge-m3")
            embedding = model.encode(text, normalize_embeddings=True)
            return embedding.tolist()
        except ImportError:
            logger.debug("sentence-transformers not installed")
        except Exception as e:
            logger.warning("sentence-transformers embedding failed: %s", e)
        return None

    @staticmethod
    def _hash_embedding(text: str) -> List[float]:
        """
        Fallback: deterministic pseudo-random embedding from text hash.

        Uses SHA-256 to seed a simple PRNG that generates 1024 independent floats.
        NOT semantically meaningful — use bge-m3 for real embeddings.
        """
        import hashlib
        import struct

        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Use the hash as a 32-byte seed for a simple xorshift PRNG
        seed = int.from_bytes(h[:8], "big")
        state = seed & 0xFFFFFFFFFFFFFFFF
        if state == 0:
            state = 0xDEADBEEFCAFEBABE

        floats = []
        for _ in range(1024):
            # xorshift64*
            state ^= (state >> 12) & 0xFFFFFFFFFFFFFFFF
            state ^= (state << 25) & 0xFFFFFFFFFFFFFFFF
            state ^= (state >> 27) & 0xFFFFFFFFFFFFFFFF
            # Extract high 32 bits as a random uint32, normalize to [-1, 1]
            rnd = ((state * 0x2545F4914F6CDD1D) >> 32) & 0xFFFFFFFF
            val = rnd / 0xFFFFFFFF
            floats.append(val * 2 - 1)

        return floats

    # =========================================================================
    # Stats
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics."""
        _, _, DomainTrap = _lazy_db()
        with self._get_session() as db:
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
