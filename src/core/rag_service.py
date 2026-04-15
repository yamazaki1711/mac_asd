import logging
from typing import List, Dict, Any
from sqlalchemy import select
from src.core.ollama_client import ollama_client
from src.db.models import DocumentChunk
from src.db.init_db import Session
from src.config import settings

logger = logging.getLogger(__name__)

class RAGService:
    """
    Сервис для работы с RAG: индексация и поиск.
    """
    
    async def index_document(self, document_id: int, chunks: List[Dict[str, Any]]):
        """
        Создает эмбеддинги и сохраняет чанки в Postgres (pgvector).
        """
        logger.info(f"Indexing document {document_id} ({len(chunks)} chunks)")
        
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
        Векторный поиск по всем документам.
        """
        query_embedding = await ollama_client.get_embedding(query)
        
        with Session() as session:
            # Используем оператор <-> для дистанции L2 или <=> для косинуса в pgvector
            # По умолчанию pgvector в sqlalchemy-моделях поддерживает эти операторы
            stmt = select(DocumentChunk).order_by(
                DocumentChunk.embedding.l2_distance(query_embedding)
            ).limit(top_k)
            
            results = session.execute(stmt).scalars().all()
            
            return [
                {"content": r.content, "page": r.page_number, "doc_id": r.document_id}
                for r in results
            ]

rag_service = RAGService()
