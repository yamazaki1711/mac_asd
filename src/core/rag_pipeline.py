"""
ASD v12.0 — RAG Pipeline.

Автоматический конвейер: парсинг → индексация → поиск → сборка контекста.
Ленивые импорты БД-зависимостей — работает без PostgreSQL на dev-машине.

Pipeline stages:
  1. ingest: file → parse → create document → index chunks with embeddings
  2. get_agent_context: query → vector search → graph enrichment → formatted context
  3. classify: auto-detect document type from filename + content (no DB needed)

Usage:
    from src.core.rag_pipeline import rag_pipeline

    doc = await rag_pipeline.ingest("contract.pdf", project_id=1)
    ctx = await rag_pipeline.get_agent_context("неустойка", agent="legal", project_id=1)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Маппинг agent_name → domain для поиска ловушек
AGENT_DOMAIN_MAP = {
    "legal": "legal",
    "pto": "pto",
    "smeta": "smeta",
    "procurement": "procurement",
    "logistics": "logistics",
}


def _lazy_rag_deps():
    """Ленивый импорт БД-зависимостей для RAG Pipeline."""
    from src.core.parser_engine import streaming_parser, ParseResult
    from src.core.document_repository import document_repo
    from src.core.rag_service import rag_service
    from src.core.graph_service import graph_service
    return streaming_parser, ParseResult, document_repo, rag_service, graph_service


class RAGPipeline:
    """RAG Pipeline ASD v12.0."""

    # -------------------------------------------------------------------------
    # Ingest
    # -------------------------------------------------------------------------

    async def ingest(
        self, file_path: str, project_id: int,
        doc_type: str = "unknown", embed: bool = True, auto_classify: bool = True,
    ):
        """Полный цикл ingestion одного файла."""
        import os
        streaming_parser, ParseResult, document_repo, rag_service, graph_service = _lazy_rag_deps()

        filename = os.path.basename(file_path)
        logger.info("RAG ingest: %s → project %d", filename, project_id)

        # 1. Parse
        try:
            parse_result = await streaming_parser.parse_file(file_path, project_id)
        except Exception as e:
            logger.error("RAG ingest parse error: %s — %s", filename, e)
            return None

        if not parse_result.chunks:
            try:
                return await document_repo.create(
                    project_id=project_id, filename=filename,
                    file_path=file_path, doc_type=doc_type,
                    metadata=parse_result.metadata,
                )
            except (ValueError, OSError, RuntimeError) as e:
                logger.warning("Document repo create failed for %s: %s", filename, e)
                return None

        # 2. Auto-classify
        if auto_classify and doc_type == "unknown":
            doc_type = self._classify_document(parse_result)

        # 3. Create document + index
        try:
            doc = await document_repo.create(
                project_id=project_id, filename=filename,
                file_path=file_path, doc_type=doc_type,
                metadata=parse_result.metadata,
            )
            await document_repo.index_from_parser(doc.id, parse_result.chunks, embed=embed)

            # 4. Graph registration
            graph_service.add_document(str(doc.id), {
                "filename": filename, "doc_type": doc_type,
                "total_chars": parse_result.total_chars,
                "total_pages": parse_result.total_pages,
                "status": "indexed",
            })
            graph_service.add_reference(
                source_id=f"project_{project_id}", target_id=str(doc.id),
                context=f"Document: {filename} [{doc_type}]",
            )

            logger.info("RAG ingest done: doc #%d — %d chunks, %s", 
                        doc.id, len(parse_result.chunks), doc_type)
            return doc
        except Exception as e:
            logger.warning("DB unavailable — ingest returns stub: %s", e)
            return None

    # -------------------------------------------------------------------------
    # Agent Context Assembly
    # -------------------------------------------------------------------------

    async def get_agent_context(
        self, query: str, agent: str,
        project_id: Optional[int] = None, top_k: int = 5,
        include_graph: bool = True, include_traps: bool = False,
    ) -> str:
        """Собрать RAG-контекст для инъекции в промпт агента."""
        logger.debug("RAG context for %s: '%s'", agent, query[:80])

        try:
            _, _, document_repo, rag_service, graph_service = _lazy_rag_deps()

            # 1. Vector search
            vector_results = await document_repo.search(query, project_id=project_id, top_k=top_k)

            # 2. Graph context
            graph_context = []
            if include_graph and vector_results:
                doc_ids = set(str(r["doc_id"]) for r in vector_results)
                for doc_id in doc_ids:
                    graph_context.extend(graph_service.get_related_nodes(node_id=doc_id, depth=1))

            # 3. Domain traps for all agents
            trap_context = ""
            if include_traps:
                agent_domain = AGENT_DOMAIN_MAP.get(agent, "legal")
                try:
                    traps = await rag_service.search_domain_traps(query, domain=agent_domain, top_k=3)
                    if traps:
                        lines = [f"\n⚠️ ЛОВУШКИ ({agent_domain.upper()}):"]
                        for t in traps:
                            lines.append(
                                f"  • {t['title']} [w={t.get('weight', 0)}]"
                            )
                            lines.append(f"    {t['description'][:200]}")
                        trap_context = "\n".join(lines)
                except Exception as e:
                    logger.warning("Domain trap search failed for %s: %s", agent_domain, e)

            return self._format_context(vector_results, graph_context, trap_context, agent, query)
        except Exception as e:
            logger.warning("RAG context unavailable: %s", e)
            return ""

    # -------------------------------------------------------------------------
    # Classification
    # -------------------------------------------------------------------------

    def _classify_document(self, result) -> str:
        """Автоклассификация документа по имени файла и содержимому."""
        text = (result.full_text or "").lower()
        filename = (result.metadata.get("filename", "") or "").lower()

        def _match_filename(keywords):
            """Ищет ключевые слова в имени файла.
            Для коротких слов (< 4 символов) — проверяет границы слова (начало/конец/разделители).
            """
            for kw in keywords:
                if len(kw) < 4:
                    # Check boundaries: start, end, or separator-bounded
                    idx = filename.find(kw)
                    while idx != -1:
                        before_ok = idx == 0 or not filename[idx-1].isalpha()
                        after_ok = idx + len(kw) == len(filename) or not filename[idx + len(kw)].isalpha()
                        if before_ok and after_ok:
                            return True
                        idx = filename.find(kw, idx + 1)
                elif kw in filename:
                    return True
            return False

        # By filename
        kw_map = {
            "KS2": ["кс-2", "кс2"],
            "KS3": ["кс-3", "кс3"],
            "AOSR": ["аоср"],
            "VOR": ["вор", "ведомость"],
            "Smeta": ["смет", "лср", "lsr"],
            "Contract": ["договор", "контракт", "contract"],
            "Certificate": ["сертификат", "паспорт", "декларац"],
            "OZHR": ["ожр"],
            "Drawing": ["чертёж", "чертеж", "dwg"],
            "PPR": ["ппр"],
            "Scheme": ["схема", "план", "генплан"],
        }
        for doc_type, keywords in kw_map.items():
            if _match_filename(keywords):
                return doc_type

        # By content
        if "акт о приёмке выполненных работ" in text or "форма кс-2" in text:
            return "KS2"
        if "акт освидетельствования скрытых работ" in text:
            return "AOSR"
        if "ведомость объёмов работ" in text:
            return "VOR"
        if "локальный сметный расчёт" in text or "сметная стоимость" in text:
            return "Smeta"
        if "договор подряда" in text:
            return "Contract"
        if "сертификат соответствия" in text or "декларация о соответствии" in text:
            return "Certificate"

        return "unknown"

    def _format_context(
        self, vector_results, graph_context, trap_context, agent, query
    ) -> str:
        """Форматировать контекст для промпта агента."""
        parts = []

        if vector_results:
            lines = [
                f"\n📚 РЕЛЕВАНТНЫЕ ДОКУМЕНТЫ (по запросу: «{query[:80]}»):",
                "=" * 60,
            ]
            for i, r in enumerate(vector_results[:5], 1):
                lines.append(
                    f"\n[{i}] {r['filename']} [{r['doc_type']}] "
                    f"— стр. {r['page']} (score: {r['score']:.3f})"
                )
                lines.append(f"    {r['content'][:300]}")
            lines.append("=" * 60)
            parts.append("\n".join(lines))

        if graph_context:
            lines = ["\n🔗 СВЯЗАННЫЕ ДОКУМЕНТЫ (граф знаний):"]
            for node in graph_context[:5]:
                data = node.get("data", {})
                lines.append(
                    f"  • {node['id']}: {data.get('filename', data.get('title', 'N/A'))}"
                )
            parts.append("\n".join(lines))

        if trap_context:
            parts.append(trap_context)

        return "\n\n".join(parts)


rag_pipeline = RAGPipeline()
