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
import time
from datetime import datetime
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
        self.default_chunk_size = 6000
        self.default_chunk_overlap = 300
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

        # Step 3: Add metadata
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
    # Text Chunking
    # =========================================================================

    @staticmethod
    def _chunk_text(
        text: str,
        chunk_size: int = 6000,
        chunk_overlap: int = 300,
    ) -> List[str]:
        """
        Разбивает текст на чанки с перекрытием.

        Старается резать по границам абзацев (двойной перенос строки),
        чтобы не разрывать предложения.
        """
        if len(text) <= chunk_size:
            return [text] if text.strip() else []

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            # Try to cut at paragraph boundary
            if end < len(text):
                # Look for double newline near the end
                boundary = text.rfind("\n\n", start + chunk_size // 2, end)
                if boundary > start:
                    end = boundary + 2  # Include the newlines
                else:
                    # Fall back to single newline
                    boundary = text.rfind("\n", start + chunk_size // 2, end)
                    if boundary > start:
                        end = boundary + 1

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Move forward with overlap
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


# Singleton
legal_service = LegalService()
