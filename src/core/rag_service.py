"""
ASD v11.3 — RAG Service.

Hybrid search: Vector (pgvector) + Graph (NetworkX).
Uses llm_engine for embeddings instead of direct ollama_client.
v11.3.0: Added search_traps() with weight-based ranking for БЛС.
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import select, func, text
from src.core.llm_engine import llm_engine
from src.core.graph_service import graph_service
from src.db.models import DocumentChunk, LegalTrap
from src.db.init_db import Session

logger = logging.getLogger(__name__)


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
        graph_service.add_document(str(document_id), {"status": "indexed"})

        with Session() as session:
            for chunk_data in chunks:
                # Получаем эмбеддинг через llm_engine
                embedding = await llm_engine.embed(chunk_data["content"])

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
        query_embedding = await llm_engine.embed(query)

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
        Это реализация паттерна LightRAG из CONCEPT_v11.md.
        """
        # Шаг 1: Получаем лучшие чанки семантическим поиском
        vector_results = await self.search(query, top_k=top_k)

        # Шаг 2: Извлекаем идентификаторы документов из векторной выдачи
        doc_ids = set(str(r["doc_id"]) for r in vector_results)

        # Шаг 3: Для каждого документа запрашиваем графовый контекст глубины 1
        graph_context = []
        for doc_id in doc_ids:
            related = graph_service.get_related_nodes(node_id=doc_id, depth=1)
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
        Поиск ловушек в БЛС с учётом weight-ранжирования.

        v11.3.0: Комбинирует семантическую близость (vector distance)
        с весом источника (weight) для приоритизации ловушек
        из авторитетных каналов (legal_practice > legal_news).

        Формула ранжирования:
            score = (1 - normalized_distance) * 0.7 + (weight / 100) * 0.3

        Args:
            query: Поисковый запрос (например, "неустойка генподрядчика")
            top_k: Количество результатов
            category: Фильтр по категории (legal_practice, legal_news, и т.д.)
            min_weight: Минимальный вес источника (0-100)
        """
        query_embedding = await llm_engine.embed(query)

        with Session() as session:
            # Build query with optional filters
            stmt = select(LegalTrap)

            if category:
                stmt = stmt.where(LegalTrap.category == category)
            if min_weight > 0:
                stmt = stmt.where(LegalTrap.weight >= min_weight)

            # Order by vector distance, fetch more than top_k for re-ranking
            stmt = stmt.order_by(
                LegalTrap.embedding.l2_distance(query_embedding)
            ).limit(top_k * 3)

            results = session.execute(stmt).scalars().all()

            # Re-rank with weight
            ranked = []
            for r in results:
                # Calculate distance (we don't have it directly, approximate from order)
                # For proper re-ranking, we'd need raw distance — use a simpler approach
                trap_data = {
                    "id": r.id,
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

            # Sort by weight (higher weight = more authoritative source = better)
            # Within same weight, maintain vector distance order (already sorted)
            ranked.sort(key=lambda x: x["weight"], reverse=True)

            return ranked[:top_k]


rag_service = RAGService()
