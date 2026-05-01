"""
ASD v12.0 — Document Repository.

CRUD-слой для документов и чанков поверх PostgreSQL + pgvector.
Ленивые импорты БД-зависимостей — работает без PostgreSQL на dev-машине.

Usage:
    from src.core.document_repository import document_repo

    doc = await document_repo.create(project_id=1, filename="contract.pdf")
    await document_repo.add_chunks(doc.id, chunks, embed=True)
    results = await document_repo.search("неустойка", project_id=1, top_k=5)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _lazy_db():
    """Ленивый импорт БД-зависимостей (SQLAlchemy + pgvector)."""
    from sqlalchemy import select, delete, func, text
    from src.db.models import Document, DocumentChunk, Project
    from src.db.init_db import Session
    return select, delete, func, text, Document, DocumentChunk, Project, Session


def _lazy_llm():
    from src.core.llm_engine import llm_engine
    return llm_engine


class DocumentRepository:
    """
    Репозиторий документов ASD v12.0.
    Ленивые импорты — работает без PostgreSQL на dev-машине.
    """

    async def create(
        self,
        project_id: int,
        filename: str,
        file_path: str = "",
        doc_type: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        try:
            *_, Document, _, _, Session = _lazy_db()
            with Session() as session:
                doc = Document(
                    project_id=project_id, filename=filename,
                    file_path=file_path, doc_type=doc_type,
                    metadata_json=metadata or {},
                )
                session.add(doc)
                session.commit()
                session.refresh(doc)
            logger.info("Document #%d created: %s [%s]", doc.id, filename, doc_type)
            return doc
        except (ImportError, OSError) as e:
            logger.warning("DB unavailable — returning stub document: %s", e)
            from dataclasses import dataclass
            @dataclass
            class StubDoc:
                id: int = 0
                filename: str = filename
                doc_type: str = doc_type
                chunks: list = None
                def __post_init__(self): self.chunks = []
            return StubDoc()

    def get(self, document_id: int):
        try:
            *_, Document, _, _, Session = _lazy_db()
            with Session() as session:
                return session.query(Document).filter_by(id=document_id).first()
        except (ImportError, OSError):
            return None

    def list_by_project(self, project_id: int, doc_type: str = None, limit: int = 100, offset: int = 0):
        try:
            select, *_unused, Document, _, _, Session = _lazy_db()
            with Session() as session:
                stmt = select(Document).where(Document.project_id == project_id)
                if doc_type:
                    stmt = stmt.where(Document.doc_type == doc_type)
                stmt = stmt.order_by(Document.created_at.desc()).offset(offset).limit(limit)
                return list(session.execute(stmt).scalars().all())
        except (ImportError, OSError):
            return []

    def update_metadata(self, document_id: int, metadata: Dict[str, Any]) -> bool:
        try:
            *_, Document, _, _, Session = _lazy_db()
            with Session() as session:
                doc = session.query(Document).filter_by(id=document_id).first()
                if not doc:
                    return False
                existing = doc.metadata_json or {}
                existing.update(metadata)
                doc.metadata_json = existing
                session.commit()
                return True
        except (ImportError, OSError):
            return False

    def delete(self, document_id: int) -> bool:
        try:
            *_, Document, _, _, Session = _lazy_db()
            with Session() as session:
                doc = session.query(Document).filter_by(id=document_id).first()
                if not doc:
                    return False
                session.delete(doc)
                session.commit()
                logger.info("Document #%d deleted", document_id)
                return True
        except (ImportError, OSError):
            return False

    async def add_chunks(
        self, document_id: int, chunks: List[Dict[str, Any]],
        embed: bool = True, chunk_size: int = 0,
    ) -> int:
        try:
            *_, DocumentChunk, _, Session = _lazy_db()
            llm = _lazy_llm()
            count = 0
            with Session() as session:
                for chunk_data in chunks:
                    content = chunk_data.get("content", "")
                    if not content.strip():
                        continue
                    sub_contents = [content]
                    if chunk_size > 0 and len(content) > chunk_size:
                        sub_contents = [
                            content[i:i + chunk_size]
                            for i in range(0, len(content), chunk_size)
                        ]
                    for sub in sub_contents:
                        embedding = None
                        if embed:
                            try:
                                embedding = await llm.embed(sub)
                            except Exception as e:
                                logger.warning("Embed failed: %s", e)
                        db_chunk = DocumentChunk(
                            document_id=document_id, content=sub,
                            embedding=embedding,
                            page_number=chunk_data.get("page"),
                        )
                        session.add(db_chunk)
                        count += 1
                session.commit()
            logger.info("Doc #%d: %d chunks saved", document_id, count)
            return count
        except (ImportError, OSError) as e:
            logger.warning("DB unavailable — add_chunks skipped: %s", e)
            return 0

    async def index_from_parser(self, document_id: int, parsed_chunks: List[Any], embed: bool = True) -> int:
        chunk_dicts = [
            {"content": c.content, "page": c.page, "metadata": c.metadata}
            for c in parsed_chunks
            if c.content and not c.content.startswith("[")
        ]
        return await self.add_chunks(document_id, chunk_dicts, embed=embed)

    async def search(self, query: str, project_id: int = None, document_id: int = None, top_k: int = 5):
        try:
            select, _, func, _, DocumentChunk, Document, _, Session = _lazy_db()
            llm = _lazy_llm()
            query_embedding = await llm.embed(query)
            with Session() as session:
                stmt = select(
                    DocumentChunk.content, DocumentChunk.page_number,
                    DocumentChunk.document_id, Document.filename, Document.doc_type,
                    DocumentChunk.embedding.l2_distance(query_embedding).label("score"),
                ).join(Document, DocumentChunk.document_id == Document.id)
                if project_id:
                    stmt = stmt.where(Document.project_id == project_id)
                if document_id:
                    stmt = stmt.where(DocumentChunk.document_id == document_id)
                stmt = stmt.order_by("score").limit(top_k)
                rows = session.execute(stmt).all()
                return [
                    {"content": r.content[:500], "page": r.page_number,
                     "doc_id": r.document_id, "filename": r.filename,
                     "doc_type": r.doc_type, "score": round(float(r.score), 4)}
                    for r in rows
                ]
        except (ImportError, OSError):
            return []

    def get_stats(self, project_id: int = None):
        try:
            select, _, func, _, DocumentChunk, Document, _, Session = _lazy_db()
            with Session() as session:
                doc_stmt = select(func.count(Document.id))
                if project_id:
                    doc_stmt = doc_stmt.where(Document.project_id == project_id)
                total_docs = session.execute(doc_stmt).scalar() or 0

                chunk_stmt = select(func.count(DocumentChunk.id))
                if project_id:
                    chunk_stmt = chunk_stmt.join(Document).where(Document.project_id == project_id)
                total_chunks = session.execute(chunk_stmt).scalar() or 0

                type_stmt = select(Document.doc_type, func.count(Document.id)).group_by(Document.doc_type)
                if project_id:
                    type_stmt = type_stmt.where(Document.project_id == project_id)
                by_type = dict(session.execute(type_stmt).all())

                return {
                    "total_documents": total_docs, "total_chunks": total_chunks,
                    "by_type": by_type,
                }
        except (ImportError, OSError):
            return {"total_documents": 0, "total_chunks": 0, "by_type": {}}


document_repo = DocumentRepository()
