"""
ASD v12.0 — Legal Service.

Core service for contract analysis with Quick Review + БЛС + Map-Reduce fallback.

v12.0 Pipeline (Gemma 4 31B, 128K context):
    1. Upload & Parse  → ParserEngine extracts text from PDF/DOCX
    2. БЛС Lookup      → Find similar known traps via RAG
    3. Quick Review     → LLM analyzes FULL document in one call (128K context)
    4. Map-Reduce       → Fallback only for documents > 128K tokens (~300K chars)

With Gemma 4 31B (128K context), Map-Reduce is RARELY needed:
- 128K tokens ≈ 300K Cyrillic characters ≈ 150 pages of contract text
- Most construction contracts fit entirely within a single LLM call
- This dramatically improves accuracy (no lost context between chunks)
  and speed (1 LLM call instead of 5-8 for Map-Reduce)
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.config import settings
from src.core.llm_engine import llm_engine
from src.core.prompts.legal_prompts import (
    LEGAL_MAP_PROMPT,
    LEGAL_REDUCE_PROMPT,
    LEGAL_QUICK_REVIEW_PROMPT,
)
from src.schemas.legal import (
    LegalAnalysisRequest,
    LegalAnalysisResult,
    LegalFinding,
    LegalSeverity,
    LegalFindingCategory,
    LegalVerdict,
    ReviewType,
    ContractUploadResult,
)

logger = logging.getLogger(__name__)


class LegalService:
    """
    Сервис юридической экспертизы контрактов.

    v12.0: С Gemma 4 31B (128K контекст) стратегия выбора режима изменилась:
    - Quick Review: документы до ~280K символов (128K токенов, ~150 страниц)
      Это покрывает подавляющее большинство строительных контрактов.
    - Map-Reduce: только для документов > 280K символов (редкость)

    Преимущества Quick Review перед Map-Reduce:
    - Целостный контекст (нет потери связей между разделами договора)
    - 1 вызов LLM вместо 5-8 (быстрее, дешевле по токенам)
    - Более точный verdict (модель видит весь договор целиком)
    """

    def __init__(self):
        self.agent = "legal"
        self.default_chunk_size = 12000
        self.default_chunk_overlap = 2400
        # Gemma 4 31B: 128K контекст ≈ 280K Cyrillic символов (1 токен ≈ 2.2 символа)
        # Порог с запасом: оставляем ~20K токенов на промпт + ответ
        self.quick_review_max_chars = 280_000

    # =========================================================================
    # Public API
    # =========================================================================

    async def upload_and_parse(self, file_path: str) -> ContractUploadResult:
        """
        Загрузка и парсинг документа.

        Args:
            file_path: Путь к файлу (PDF, DOCX)

        Returns:
            ContractUploadResult с количеством извлечённых чанков
        """
        logger.info(f"Uploading and parsing: {file_path}")

        from src.core.parser_engine import parser_engine

        if file_path.lower().endswith(".pdf"):
            chunks = await parser_engine.parse_pdf(file_path)
        elif file_path.lower().endswith((".xlsx", ".xls")):
            chunks = parser_engine.parse_xlsx(file_path)
        else:
            # Попытка прочитать как текст
            try:
                from pathlib import Path
                text = Path(file_path).read_text(encoding="utf-8")
                chunks = [{"content": text, "page": 1, "method": "text_read"}]
            except Exception as e:
                logger.error(f"Unsupported file format: {file_path}. Error: {e}")
                chunks = []

        total_chars = sum(len(c.get("content", "")) for c in chunks)

        return ContractUploadResult(
            file_path=file_path,
            chunks_extracted=len(chunks),
            total_chars=total_chars,
        )

    async def analyze(self, request: LegalAnalysisRequest) -> LegalAnalysisResult:
        """
        Полный цикл юридической экспертизы.

        Args:
            request: LegalAnalysisRequest с текстом/файлом/ID документа

        Returns:
            LegalAnalysisResult с findings, verdict, summary
        """
        start_time = time.time()
        logger.info(f"Starting legal analysis. Review type: {request.review_type}")

        # Step 1: Get document text
        document_text = await self._resolve_document_text(request)
        if not document_text:
            return LegalAnalysisResult(
                review_type=request.review_type,
                findings=[],
                verdict=LegalVerdict.APPROVED,
                summary="Документ пуст или не найден. Анализ невозможен.",
                analysis_metadata={"error": "empty_document"},
            )

        # Step 2: Choose analysis strategy
        # v12.0: Gemma 4 31B supports 128K context (~280K chars)
        # Quick Review handles the vast majority of construction contracts
        total_chars = len(document_text)

        if total_chars <= self.quick_review_max_chars:
            # Full document fits in 128K context — Quick Review
            logger.info(
                f"Quick Review mode (document: {total_chars} chars, "
                f"limit: {self.quick_review_max_chars})"
            )
            result = await self._quick_review(document_text, request.review_type)
        else:
            # Document exceeds 128K — fallback to Map-Reduce (rare)
            chunk_size = request.chunk_size or self.default_chunk_size
            logger.warning(
                f"Map-Reduce FALLBACK mode (document: {total_chars} chars > "
                f"{self.quick_review_max_chars}). Consider splitting the document."
            )
            result = await self._map_reduce(
                document_text,
                chunk_size,
                request.chunk_overlap,
                request.review_type,
            )

        # Step 3: Check normative refs validity via InvalidationEngine
        if result.normative_refs:
            validity_warnings = self._check_norms_validity(result.normative_refs)
            if validity_warnings:
                result.normative_validity_warnings = validity_warnings
                # Add as a finding if any norms are stale
                for vw in validity_warnings:
                    if vw.get("status") in ("stale", "replaced"):
                        result.findings.append(LegalFinding(
                            category=LegalFindingCategory.RISK,
                            severity=LegalSeverity.HIGH,
                            clause_ref=vw.get("norm_ref", ""),
                            legal_basis="InvalidationEngine",
                            issue=f"Нормативный документ устарел: {vw.get('warning', '')}",
                            recommendation=f"Проверить актуальность: {vw.get('norm_ref', '')}",
                            auto_fixable=False,
                        ))

        # Step 4: Add metadata
        elapsed = time.time() - start_time
        model_config = settings.get_model_config(self.agent)
        result.analysis_metadata = {
            "duration_seconds": round(elapsed, 2),
            "model": model_config["model"],
            "engine": model_config["engine"],
            "document_chars": total_chars,
            "review_type": request.review_type.value,
            "timestamp": datetime.now().isoformat(),
        }

        logger.info(
            f"Legal analysis complete. Findings: {result.total_risks}, "
            f"Verdict: {result.verdict.value}, Duration: {elapsed:.1f}s"
        )

        # ── NormativeGuard: валидация нормативных ссылок ──
        validation = normative_guard.validate_response(result.summary)
        if validation["warning"]:
            logger.warning(validation["warning"])
            result.normative_validity_warnings.append({
                "type": "unverified_references",
                "message": validation["warning"],
                "unverified": validation["unverified"],
                "verification_ratio": validation["verification_ratio"],
            })

        return result

    # =========================================================================
    # Quick Review (short documents)
    # =========================================================================

    async def _quick_review(
        self,
        document_text: str,
        review_type: ReviewType,
    ) -> LegalAnalysisResult:
        """Быстрый обзор для коротких документов (без Map-Reduce)."""

        # БЛС lookup
        blc_context = await self._blc_lookup(document_text[:2000])

        prompt = LEGAL_QUICK_REVIEW_PROMPT.format(
            document_text=document_text,
            blc_context=blc_context,
        )

        response_text = await llm_engine.safe_chat(
            self.agent,
            [{"role": "user", "content": prompt}],
            fallback_response=self._empty_result_json(review_type),
        )

        return self._parse_analysis_response(response_text, review_type)

    # =========================================================================
    # Map-Reduce (long documents)
    # =========================================================================

    async def _map_reduce(
        self,
        document_text: str,
        chunk_size: int,
        chunk_overlap: int,
        review_type: ReviewType,
    ) -> LegalAnalysisResult:
        """
        Map-Reduce анализ для длинных контрактов.

        MAP:    Каждый чанк анализируется независимо
        REDUCE: Результаты агрегируются в итоговое заключение
        """
        # Step 1: Chunk the document
        chunks = self._chunk_text(document_text, chunk_size, chunk_overlap)
        logger.info(f"Document split into {len(chunks)} chunks")

        # Step 2: MAP — analyze each chunk
        map_results: List[Dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            logger.info(f"MAP stage: analyzing chunk {i + 1}/{len(chunks)}")

            # БЛС lookup for this chunk
            blc_context = await self._blc_lookup(chunk[:2000])

            prompt = LEGAL_MAP_PROMPT.format(
                chunk_text=chunk,
                blc_context=blc_context,
            )

            chunk_response = await llm_engine.safe_chat(
                self.agent,
                [{"role": "user", "content": prompt}],
                fallback_response="[]",
            )

            map_results.append({
                "chunk_index": i + 1,
                "chunk_preview": chunk[:200] + "...",
                "findings_raw": chunk_response,
            })

        # Step 3: REDUCE — aggregate all MAP results
        logger.info("REDUCE stage: aggregating findings")
        result = await self._reduce(map_results, review_type)

        return result

    async def _reduce(
        self,
        map_results: List[Dict[str, Any]],
        review_type: ReviewType,
    ) -> LegalAnalysisResult:
        """REDUCE stage: агрегация результатов MAP."""

        # Format MAP results for the REDUCE prompt
        formatted_maps = []
        for mr in map_results:
            formatted_maps.append(
                f"### Фрагмент {mr['chunk_index']}\n"
                f"Фрагмент: {mr['chunk_preview']}\n"
                f"Найденные риски:\n{mr['findings_raw']}\n"
            )

        map_results_text = "\n---\n".join(formatted_maps)
        contradictions_text = "Не проверялись на данном этапе."

        prompt = LEGAL_REDUCE_PROMPT.format(
            map_results=map_results_text,
            contradictions_text=contradictions_text,
        )

        response_text = await llm_engine.safe_chat(
            self.agent,
            [{"role": "user", "content": prompt}],
            fallback_response=self._empty_result_json(review_type),
        )

        return self._parse_analysis_response(response_text, review_type)

    # =========================================================================
    # БЛС (База Ловушек Субподрядчика) Lookup
    # =========================================================================

    async def _blc_lookup(self, text: str) -> str:
        """
        Поиск похожих ловушек в БЛС через RAG.

        v12.0.0: Использует search_traps() с weight-ранжированием,
        чтобы ловушки из авторитетных каналов (legal_practice)
        имели приоритет над новостными (legal_news).

        Args:
            text: Текст для поиска (первые ~2000 символов чанка)

        Returns:
            Строка с описаниями найденных ловушек или "Ловушки не найдены"
        """
        try:
            from src.core.rag_service import rag_service
            results = await rag_service.search_domain_traps(text, domain="legal", top_k=5, min_weight=40)
            if not results:
                return "Ловушки из БЛС не найдены для данного фрагмента."

            blc_entries = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "Без названия")
                description = r.get("description", "")[:300]
                domain = r.get("domain", "legal")
                channel = r.get("channel", "")
                weight = r.get("weight", 50)
                category = r.get("category", "")
                mitigation = r.get("mitigation", "")

                entry = f"{i}. [{domain}|{category}|w={weight}] {title}"
                if channel:
                    entry += f" (источник: @{channel})"
                entry += f"\n   Описание: {description}"
                if mitigation:
                    entry += f"\n   Защита: {mitigation[:200]}"
                blc_entries.append(entry)

            return "\n\n".join(blc_entries)

        except Exception as e:
            logger.warning(f"БЛС lookup failed (DB may be unavailable): {e}")
            return "БЛС временно недоступна. Анализ без учёта известных ловушек."

    # =========================================================================
    # Text Chunking (структурный — не разрывает таблицы и разделы)
    # =========================================================================

    # Regex: нумерованный заголовок раздела верхнего уровня
    # "5. Ответственность", "10. Порядок", но НЕ "5.1.", "10.2.1."
    _SECTION_HEADER = re.compile(
        r'(?:^|\n)(\d+)\.\s+[А-ЯA-Z]',
        re.MULTILINE,
    )

    # Regex: строка таблицы (содержит | как разделитель колонок)
    # Детектит markdown-таблицы и pipe-разделители
    _TABLE_LINE = re.compile(r'\|.+\|')

    @staticmethod
    def _chunk_text(
        text: str,
        chunk_size: int = 12000,
        chunk_overlap: int = 2400,
    ) -> List[str]:
        """
        Разбивает текст на чанки со структурными границами.

        Приоритет: разделы > таблицы > абзацы > предложения.
        Не разрывает таблицы и разделы контракта.
        """
        if len(text) <= chunk_size:
            return [text.strip()] if text.strip() else []

        # Stage 1: split into top-level sections
        sections = LegalService._split_by_sections(text)

        # Stage 2: split oversized sections by tables, then paragraphs
        chunks = []
        for section in sections:
            if len(section) <= chunk_size:
                if section.strip():
                    chunks.append(section.strip())
            else:
                chunks.extend(
                    LegalService._split_by_tables(
                        section, chunk_size, chunk_overlap,
                    )
                )

        return chunks

    @staticmethod
    def _split_by_sections(text: str) -> List[str]:
        """Нарезать текст по границам нумерованных разделов."""
        header = LegalService._SECTION_HEADER

        # Find all section boundaries
        boundaries = [0]
        for m in header.finditer(text):
            boundaries.append(m.start())

        if len(boundaries) == 1:
            return [text]

        # Build sections
        sections = []
        for i, start in enumerate(boundaries):
            end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
            section = text[start:end]
            if section.strip():
                sections.append(section)

        return sections

    @staticmethod
    def _split_by_tables(
        text: str, chunk_size: int, chunk_overlap: int,
    ) -> List[str]:
        """
        Нарезать секцию по границам таблиц, затем по абзацам.

        Таблица детектится: 2+ строки подряд с разделителями (| / табуляция).
        Таблицы не разрываются — уходят в отдельный чанк.
        """
        table_line = LegalService._TABLE_LINE
        lines = text.split('\n')

        # Group consecutive table lines into blocks
        blocks: List[str] = []      # content blocks
        block_starts: List[int] = [] # start line index
        in_table = False
        buf: List[str] = []

        for i, line in enumerate(lines):
            is_table_row = bool(table_line.search(line))

            if is_table_row and not in_table:
                # Table starting — flush paragraph buf
                if buf:
                    blocks.append('\n'.join(buf))
                    block_starts.append(i - len(buf))
                    buf = []
                in_table = True
                buf.append(line)
            elif is_table_row and in_table:
                buf.append(line)
            elif not is_table_row and in_table:
                # Table ended — flush table block
                blocks.append('\n'.join(buf))
                block_starts.append(i - len(buf))
                buf = [line]
                in_table = False
            else:
                buf.append(line)

        if buf:
            blocks.append('\n'.join(buf))

        # Merge blocks respecting chunk_size
        return LegalService._merge_blocks(
            blocks, chunk_size, chunk_overlap,
        )

    @staticmethod
    def _merge_blocks(
        blocks: List[str], chunk_size: int, chunk_overlap: int,
    ) -> List[str]:
        """Слить блоки в чанки нужного размера без разрыва таблиц."""
        chunks: List[str] = []
        current: List[str] = []
        current_len = 0

        for block in blocks:
            block_len = len(block)

            if current_len + block_len <= chunk_size:
                current.append(block)
                current_len += block_len
            else:
                # Flush current chunk (if any)
                if current:
                    chunks.append('\n'.join(current))

                # If a single block exceeds chunk_size (huge table),
                # split it with overlap (paragraph fallback)
                if block_len > chunk_size:
                    subs = LegalService._chunk_by_paragraphs(
                        block, chunk_size, chunk_overlap,
                    )
                    chunks.extend(subs)
                    current = []
                    current_len = 0
                else:
                    # Start new chunk with overlap from previous
                    current = [block]
                    current_len = block_len

        if current:
            chunks.append('\n'.join(current))

        return chunks

    @staticmethod
    def _chunk_by_paragraphs(
        text: str, chunk_size: int, chunk_overlap: int,
    ) -> List[str]:
        """
        Fallback: нарезка по абзацам (для одиночных блоков > chunk_size).

        Старается резать по двойному переносу строки, не разрывая предложения.
        """
        if len(text) <= chunk_size:
            return [text.strip()] if text.strip() else []

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            if end < len(text):
                # Priority: double newline
                boundary = text.rfind('\n\n', start + chunk_size // 2, end)
                if boundary > start:
                    end = boundary + 2
                else:
                    # Single newline
                    boundary = text.rfind('\n', start + chunk_size // 2, end)
                    if boundary > start:
                        end = boundary + 1

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - chunk_overlap if end < len(text) else end

        return chunks

    # =========================================================================
    # Document Text Resolution
    # =========================================================================

    async def _resolve_document_text(self, request: LegalAnalysisRequest) -> str:
        """Получить текст документа из запроса (из файла, текста или БД)."""

        # Direct text provided
        if request.document_text:
            return request.document_text

        # File path provided
        if request.file_path:
            upload_result = await self.upload_and_parse(request.file_path)
            if upload_result.chunks_extracted > 0:
                # Re-parse to get full text
                from src.core.parser_engine import parser_engine

                if request.file_path.lower().endswith(".pdf"):
                    chunks = await parser_engine.parse_pdf(request.file_path)
                elif request.file_path.lower().endswith((".xlsx", ".xls")):
                    chunks = parser_engine.parse_xlsx(request.file_path)
                else:
                    from pathlib import Path
                    text = Path(request.file_path).read_text(encoding="utf-8")
                    return text

                return "\n\n".join(c.get("content", "") for c in chunks)

        # Document ID provided — query from DB
        if request.document_id:
            try:
                from src.db.init_db import Session
                from src.db.models import DocumentChunk
                from sqlalchemy import select

                with Session() as session:
                    stmt = select(DocumentChunk).where(
                        DocumentChunk.document_id == request.document_id
                    ).order_by(DocumentChunk.page_number)
                    chunks = session.execute(stmt).scalars().all()
                    if chunks:
                        return "\n\n".join(c.content for c in chunks)
            except Exception as e:
                logger.error(f"Failed to load document from DB: {e}")

        return ""

    # =========================================================================
    # Normative Validity Check (Knowledge Invalidation)
    # =========================================================================

    def _check_norms_validity(self, norm_refs: List[str]) -> List[Dict[str, Any]]:
        """
        Check normative references against the InvalidationEngine.

        Returns list of warnings for stale/replaced norms.
        """
        try:
            from src.core.knowledge.invalidation_engine import invalidation_engine
            results = invalidation_engine.check_validity_batch(norm_refs)
        except Exception:
            return []

        warnings = []
        for ref, status in results.items():
            if not status.get("valid", True) or status.get("warning"):
                warnings.append({
                    "norm_ref": ref,
                    "status": status.get("status", "unknown"),
                    "replaced_by": status.get("replaced_by"),
                    "warning": status.get("warning", ""),
                })
        return warnings

    # =========================================================================
    # Response Parsing
    # =========================================================================

    def _parse_analysis_response(
        self,
        response_text: str,
        review_type: ReviewType,
    ) -> LegalAnalysisResult:
        """
        Парсинг JSON-ответа от LLM в LegalAnalysisResult.
        Устойчив к невалидному JSON — извлекает что может.
        """
        try:
            # Try to extract JSON from markdown code block
            json_text = response_text
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0]
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0]

            data = json.loads(json_text.strip())

            # Parse findings
            findings = []
            for f_data in data.get("findings", []):
                try:
                    finding = LegalFinding(
                        category=self._safe_enum(
                            f_data.get("category", "risk"), LegalFindingCategory
                        ),
                        severity=self._safe_enum(
                            f_data.get("severity", "medium"), LegalSeverity
                        ),
                        clause_ref=f_data.get("clause_ref", "не указан"),
                        legal_basis=f_data.get("legal_basis", "не указана"),
                        issue=f_data.get("issue", ""),
                        recommendation=f_data.get("recommendation", ""),
                        auto_fixable=f_data.get("auto_fixable", False),
                    )
                    findings.append(finding)
                except Exception as e:
                    logger.warning(f"Failed to parse finding: {e}. Data: {f_data}")

            # Parse verdict
            verdict = self._safe_enum(
                data.get("verdict", "approved_with_comments"), LegalVerdict
            )

            return LegalAnalysisResult(
                review_type=review_type,
                findings=findings,
                normative_refs=data.get("normative_refs", []),
                contradictions=data.get("contradictions", []),
                verdict=verdict,
                summary=data.get("summary", "Анализ завершён."),
            )

        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Raw response: {response_text[:500]}")

            return LegalAnalysisResult(
                review_type=review_type,
                findings=[LegalFinding(
                    category=LegalFindingCategory.RISK,
                    severity=LegalSeverity.MEDIUM,
                    clause_ref="N/A",
                    legal_basis="N/A",
                    issue="Не удалось распарсить ответ LLM",
                    recommendation=f"Повторить анализ. Ошибка: {str(e)[:100]}",
                    auto_fixable=False,
                )],
                verdict=LegalVerdict.APPROVED_WITH_COMMENTS,
                summary="Анализ завершён с ошибками парсинга. Требуется повторная проверка.",
            )

    @staticmethod
    def _safe_enum(value: str, enum_class) -> Any:
        """Безопасное преобразование строки в Enum."""
        try:
            return enum_class(value)
        except ValueError:
            return list(enum_class)[0]  # Default to first value

    @staticmethod
    def _empty_result_json(review_type: ReviewType) -> str:
        """JSON для пустого результата (fallback при ошибке LLM)."""
        return json.dumps({
            "findings": [],
            "normative_refs": [],
            "contradictions": [],
            "verdict": "approved",
            "summary": "LLM недоступна. Анализ не выполнен.",
        })


    # =========================================================================
    # Knowledge Base RAG
    # =========================================================================

    def ask_kb(
        self, query: str, top_k: int = 5, min_weight: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search legal domain knowledge base for relevant traps, cases, insights.

        Uses pgvector + bge-m3 embeddings with keyword fallback.

        Args:
            query: Search query in Russian (e.g. "сроки оплаты субподрядчику")
            top_k: Number of results
            min_weight: Minimum importance weight (0-100)

        Returns:
            List of {id, title, description, source, mitigation, similarity, ...}
        """
        from src.core.knowledge.knowledge_base import knowledge_base

        results = knowledge_base.search(
            query=query, domain="legal", top_k=top_k, min_weight=min_weight,
        )

        logger.info("ask_kb: '%s' → %d results", query[:60], len(results))
        return results

    def enrich_prompt_with_kb(
        self, prompt: str, query: str, max_chars: int = 2000
    ) -> str:
        """
        Enrich an LLM prompt with relevant knowledge base entries.

        Args:
            prompt: Original LLM prompt
            query: What to search for
            max_chars: Max characters of KB context to inject

        Returns:
            Prompt with injected KB context
        """
        results = self.ask_kb(query, top_k=3, min_weight=30)
        if not results:
            return prompt

        kb_block = "\n\n[ЗНАНИЯ ИЗ БАЗЫ ДОМЕННЫХ ЛОВУШЕК]\n"
        chars_used = 0
        for i, r in enumerate(results[:3], 1):
            entry = (
                f"{i}. {r['title']}\n"
                f"   {r['description'][:300]}\n"
            )
            if r.get("mitigation"):
                entry += f"   Защита: {r['mitigation'][:200]}\n"
            if r.get("court_cases"):
                entry += f"   Дела: {', '.join(r['court_cases'][:3])}\n"
            if chars_used + len(entry) > max_chars:
                break
            kb_block += entry
            chars_used += len(entry)

        # Inject after first sentence of prompt (before main content)
        parts = prompt.split("\n", 2)
        if len(parts) >= 2:
            return f"{parts[0]}\n{kb_block}\n{parts[1]}\n" + ("\n".join(parts[2:]) if len(parts) > 2 else "")
        return prompt + kb_block


# Singleton
legal_service = LegalService()


# =============================================================================
# NormativeGuard — SSOT валидатор нормативных ссылок
# =============================================================================

class NormativeGuard:
    """
    Валидатор нормативных ссылок из ответов LLM.

    Принцип: LLM не имеет права ссылаться на нормы, отсутствующие в library/normative/.
    Перед выдачей результата пользователю все ГОСТ/СП/СНиП/ФЗ из ответа LLM
    проверяются на наличие в индексе normative_index.json.

    Если ссылка не найдена — она помечается как UNVERIFIED и требует проверки экспертом.
    """

    def __init__(self):
        self._index: Dict[str, Any] = {}
        self._loaded = False

    def _load_index(self) -> Dict[str, Any]:
        """Загрузить индекс нормативных документов."""
        if self._loaded:
            return self._index

        index_paths = [
            Path("library/normative/normative_index.json"),
            Path(__file__).parent.parent.parent.parent / "library" / "normative" / "normative_index.json",
        ]
        for path in index_paths:
            if path.exists():
                try:
                    self._index = json.loads(path.read_text(encoding="utf-8"))
                    self._loaded = True
                    logger.info("NormativeGuard: loaded %d documents from %s",
                                self._index.get("metadata", {}).get("total", 0), path)
                    return self._index
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("NormativeGuard: failed to load index %s: %s", path, e)

        logger.warning("NormativeGuard: normative_index.json not found — all references will be UNVERIFIED")
        self._index = {"documents": {}, "aliases": {}}
        self._loaded = True
        return self._index

    def extract_references(self, text: str) -> List[str]:
        """
        Извлечь нормативные ссылки из текста (ответ LLM).

        Ищет паттерны: ГОСТ Р XXXX-XXXX, ГОСТ XXXXX-XXXX, СП XX.XXXXX.XXXX,
        СНиП XX-XX-XXXX, ФЗ-XX, Приказ XXX/пр, ГК РФ, ГрК РФ.
        """
        refs = set()
        patterns = [
            r"ГОСТ\s*(?:Р\s*)?\d+[\s]*[-–][\s]*\d{2,4}",
            r"СП\s*\d+\.\d+[\s]*[-–][\s]*\d{4}",
            r"СНиП\s*[\d\s\-–]+",
            r"ФЗ[\s]*[-–][\s]*\d+",
            r"Приказ\s*\d+[\s]*/[\s]*пр",
            r"ГК\s*РФ",
            r"ГрК\s*РФ",
            r"ПП\s*РФ\s*№\s*\d+",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                ref = match.group(0).strip()
                # Normalize spacing
                ref = re.sub(r"\s+", " ", ref)
                refs.add(ref)

        return sorted(refs)

    def lookup(self, reference: str) -> Optional[Dict[str, Any]]:
        """
        Проверить нормативную ссылку по индексу.

        Args:
            reference: Строка ссылки, например "ГОСТ Р 51872-2024"

        Returns:
            Информация о документе или None если не найден.
        """
        index = self._load_index()
        documents = index.get("documents", {})
        aliases = index.get("aliases", {})

        # 1. Direct alias match
        alias_key = reference.strip()
        if alias_key in aliases:
            doc_id = aliases[alias_key]
            return documents.get(doc_id)

        # 2. Direct document ID match
        if alias_key in documents:
            return documents[alias_key]

        # 3. Normalized match: strip spaces, dashes, unify
        normalized = re.sub(r"\s+", " ", alias_key.lower())
        normalized = normalized.replace("–", "-").replace("—", "-")
        normalized = normalized.replace("№", "")

        for doc_id, info in documents.items():
            doc_norm = re.sub(r"\s+", " ", doc_id.lower())
            doc_norm = doc_norm.replace("–", "-").replace("—", "-")
            if normalized in doc_norm or doc_norm in normalized:
                return info

        # 4. Partial match: e.g. "ГОСТ Р 51872" matches "ГОСТ Р 51872-2024"
        for doc_id, info in documents.items():
            if doc_id.lower().startswith(normalized) or normalized.startswith(doc_id.lower()):
                return info

        return None

    def validate_response(self, response_text: str) -> Dict[str, Any]:
        """
        Валидировать все нормативные ссылки в ответе LLM.

        Args:
            response_text: Полный текст ответа (JSON или plain text)

        Returns:
            {
                "total_refs": int,
                "verified": [{"ref": str, "doc": dict}],
                "unverified": [str],
                "verification_ratio": float (0.0-1.0),
                "warning": str or None
            }
        """
        refs = self.extract_references(response_text)
        verified = []
        unverified = []

        for ref in refs:
            match = self.lookup(ref)
            if match:
                verified.append({"ref": ref, "doc": match})
            else:
                unverified.append(ref)

        total = len(refs)
        ratio = len(verified) / max(total, 1)

        warning = None
        if unverified:
            warning = (
                f"⚠️ {len(unverified)} нормативных ссылок не найдены в library/normative/ "
                f"и не могут быть верифицированы: {', '.join(unverified)}. "
                f"LLM могла сослаться на несуществующий документ — требуется проверка экспертом."
            )

        return {
            "total_refs": total,
            "verified": verified,
            "unverified": unverified,
            "verification_ratio": round(ratio, 2),
            "warning": warning,
        }


# Singleton
normative_guard = NormativeGuard()
