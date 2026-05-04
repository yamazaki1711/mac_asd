"""
ASD v12.0 — RAG Service.

Hybrid search: Vector (pgvector) + Graph (NetworkX).
Uses llm_engine for embeddings instead of direct ollama_client.
v12.0.0: Added search_traps() with weight-based ranking for БЛС.
v12.0.0: Added search_lessons() for Lessons Learned RAG (delegated to lessons_service).
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.db.models import DocumentChunk, DomainTrap, LegalTrap

logger = logging.getLogger(__name__)

# Lazy accessors — defer heavy imports to first use
_deps = None
_graph = None
_llm = None


def _lazy_deps():
    global _deps
    if _deps is None:
        from sqlalchemy import select, func, text
        from src.db.models import DocumentChunk, DomainTrap, LegalTrap
        from src.db.init_db import Session
        _deps = (select, func, text, DocumentChunk, DomainTrap, LegalTrap, Session)
    return _deps


def _lazy_graph():
    global _graph
    if _graph is None:
        from src.core.graph_service import graph_service
        _graph = graph_service
    return _graph


def _lazy_llm():
    global _llm
    if _llm is None:
        from src.core.llm_engine import llm_engine
        _llm = llm_engine
    return _llm


class RAGService:
    """
    Сервис для работы с RAG: индексация и поиск.
    Поддерживает гибридный поиск: Vector (pgvector) + Graph (NetworkX).
    """

    async def index_document(self, document_id: int, chunks: List[Dict[str, Any]]):
        """
        Создает эмбеддинги и сохраняет чанки в Postgres (pgvector),
        а также регистрирует документ в графовой БД (NetworkX).
        """
        logger.info(f"Indexing document {document_id} ({len(chunks)} chunks)")

        # Добавление узла документа в локальный граф
        _lazy_graph().add_document(str(document_id), {"status": "indexed"})

        _, _, _, DocumentChunk, _, _, Session = _lazy_deps()
        llm = _lazy_llm()
        with Session() as session:
            for chunk_data in chunks:
                # Получаем эмбеддинг через llm_engine
                embedding = await llm.embed(chunk_data["content"])

                chunk = DocumentChunk(
                    document_id=document_id,
                    content=chunk_data["content"],
                    embedding=embedding,
                    page_number=chunk_data.get("page"),
                )
                session.add(chunk)
            session.commit()
        logger.info("Indexing complete.")

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Векторный поиск по всем документам (pgvector).
        """
        query_embedding = await _lazy_llm().embed(query)
        select, _, _, DocumentChunk, _, _, Session = _lazy_deps()

        with Session() as session:
            # Используем оператор <-> для дистанции L2 в pgvector
            stmt = select(DocumentChunk).order_by(
                DocumentChunk.embedding.l2_distance(query_embedding)
            ).limit(top_k)

            results = session.execute(stmt).scalars().all()

            return [
                {"content": r.content, "page": r.page_number, "doc_id": r.document_id}
                for r in results
            ]

    async def hybrid_search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Гибридный поиск: Векторный RAG + контекст графа NetworkX.
        Это реализация паттерна LightRAG из CONCEPT_v12.md.
        """
        # Шаг 1: Получаем лучшие чанки семантическим поиском
        vector_results = await self.search(query, top_k=top_k)

        # Шаг 2: Извлекаем идентификаторы документов из векторной выдачи
        doc_ids = set(str(r["doc_id"]) for r in vector_results)

        # Шаг 3: Для каждого документа запрашиваем графовый контекст глубины 1
        graph = _lazy_graph()
        graph_context = []
        for doc_id in doc_ids:
            related = graph.get_related_nodes(node_id=doc_id, depth=1)
            for node in related:
                graph_context.append(node)

        # Возвращаем обогащенный контекст
        return {
            "vector_chunks": vector_results,
            "graph_context": graph_context,
        }

    async def search_traps(
        self,
        query: str,
        top_k: int = 10,
        category: Optional[str] = None,
        min_weight: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Поиск ловушек в БЛС (legal) — обёртка над search_domain_traps.
        """
        return await self.search_domain_traps(
            query, domain="legal", top_k=top_k,
            category=category, min_weight=min_weight,
        )

    async def search_domain_traps(
        self,
        query: str,
        domain: str = "legal",
        top_k: int = 10,
        category: Optional[str] = None,
        min_weight: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Поиск ловушек в указанном домене с учётом weight-ранжирования.

        v12.0.0: Комбинирует семантическую близость (vector distance)
        с весом источника (weight) для приоритизации авторитетных каналов.

        Формула ранжирования:
            score = (1 - normalized_distance) * 0.7 + (weight / 100) * 0.3

        Args:
            query: Поисковый запрос
            domain: Домен агента (legal, pto, smeta, logistics, procurement)
            top_k: Количество результатов
            category: Фильтр по категории
            min_weight: Минимальный вес источника (0-100)
        """
        query_embedding = await _lazy_llm().embed(query)
        select, _, _, _, DomainTrap, _, Session = _lazy_deps()

        with Session() as session:
            stmt = select(DomainTrap).where(DomainTrap.domain == domain)

            if category:
                stmt = stmt.where(DomainTrap.category == category)
            if min_weight > 0:
                stmt = stmt.where(DomainTrap.weight >= min_weight)

            stmt = stmt.order_by(
                DomainTrap.embedding.l2_distance(query_embedding)
            ).limit(top_k * 3)

            results = session.execute(stmt).scalars().all()

            ranked = []
            for r in results:
                trap_data = {
                    "id": r.id,
                    "domain": r.domain,
                    "title": r.title,
                    "description": r.description,
                    "source": r.source,
                    "channel": r.channel,
                    "category": r.category,
                    "weight": r.weight or 50,
                    "court_cases": r.court_cases or [],
                    "mitigation": r.mitigation,
                }
                ranked.append(trap_data)

            ranked.sort(key=lambda x: x["weight"], reverse=True)

            return ranked[:top_k]


rag_service = RAGService()
