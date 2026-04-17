import logging
from typing import List, Dict, Any
from sqlalchemy import select
from src.core.ollama_client import ollama_client
from src.core.graph_service import graph_service
from src.db.models import DocumentChunk
from src.db.init_db import Session
from src.config import settings

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
                # Получаем эмбеддинг через Ollama
                embedding = await ollama_client.get_embedding(chunk_data["content"])
                
                chunk = DocumentChunk(
                    document_id=document_id,
                    content=chunk_data["content"],
                    embedding=embedding,
                    page_number=chunk_data.get("page")
                )
                session.add(chunk)
            session.commit()
        logger.info("Indexing complete.")

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Векторный поиск по всем документам (pgvector).
        """
        query_embedding = await ollama_client.get_embedding(query)
        
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
        doc_ids = set([str(r["doc_id"]) for r in vector_results])
        
        # Шаг 3: Для каждого документа запрашиваем графовый контекст глубины 1
        graph_context = []
        for doc_id in doc_ids:
            related = graph_service.get_related_nodes(node_id=doc_id, depth=1)
            for node in related:
                graph_context.append(node)
                
        # Возвращаем обогащенный контекст
        return {
            "vector_chunks": vector_results,
            "graph_context": graph_context
        }

rag_service = RAGService()
