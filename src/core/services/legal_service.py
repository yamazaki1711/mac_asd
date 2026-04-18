"""
ASD v11.0 — Legal Service.

Core service for contract analysis with Map-Reduce + БЛС + Regulatory Check.

Pipeline:
    1. Upload & Parse  → ParserEngine extracts text from PDF/DOCX
    2. Chunk           → Split document into ~6000-char chunks with overlap
    3. БЛС Lookup      → For each chunk, find similar known traps via RAG
    4. MAP Stage       → LLM analyzes each chunk independently
    5. REDUCE Stage    → LLM aggregates findings, deduplicates, forms verdict
    6. Result          → Structured LegalAnalysisResult

For short documents (< chunk_size), Quick Review is used instead of Map-Reduce.

Architecture: MLX-only (Mac Studio M4 Max 128GB).
No Ollama/Linux fallback.
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
    LEGAL_ID_CHECK_PROMPT,
    LEGAL_SYSTEM_PROMPT,
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

# Work type context mapping for specialized legal analysis
WORK_TYPE_CONTEXT = {
    "общестроительные": (
        "Широкий спектр работ: от нулевого цикла до кровли. "
        "Ключевые риски: размытый предмет договора, отсутствие чётких критериев "
        "приёмки, перекладывание ответственности за качество материалов на субподрядчика. "
        "Нормативка: СП 48.13330.2019 изм. №2, Приказ № 344/пр, Приказ № 1026/пр."
    ),
    "бетонные": (
        "Монолитные и сборные бетонные/ж/б конструкции. "
        "Ключевые риски: кто обеспечивает лабораторию, кто заказывает испытания "
        "кубиков, ответственность за трещины и дефекты. "
        "Нормативка: СП 70.13330.2012, ГОСТ 18105-2010, АОСР формы 1-6."
    ),
    "земляные": (
        "Разработка грунта, планировка, обратная засыпка. "
        "Ключевые риски: скрытые работы без геологии, пересечение с коммуникациями, "
        "обратная засыпка без уплотнения. "
        "Нормативка: СП 45.13330.2017, СП 22.13330.2016."
    ),
    "сварочные": (
        "Ручная дуговая, полуавтоматическая сварка. "
        "Ключевые риски: аттестация НАКС, контроль швов (ВИК, РК, УЗК), "
        "ответственность за дефектные швы. "
        "Нормативка: ВСН 012-88, СП 70.13330.2012, НАКС."
    ),
    "монтажные": (
        "Монтаж металлоконструкций и оборудования. "
        "Ключевые риски: кто обеспечивает такелаж, последовательность монтажа, "
        "испытания конструкций. "
        "Нормативка: СП 70.13330.2012, СП 16.13330.2017."
    ),
    "шпунтовые": (
        "Шпунтовые ограждения, крепление котлованов. "
        "Ключевые риски: кто проектирует ППР на шпунтовое крепление, "
        "ответственность за деформации, извлечение шпунта. "
        "Нормативка: ГОСТ Р 57365-2016, СП 45.13330.2017."
    ),
}

# Required ID documents per work type (for ID check review)
REQUIRED_ID_DOCS = {
    "общестроительные": (
        "1. АОСР (акты освидетельствования скрытых работ) — по каждому этапу\n"
        "2. Журнал работ (Приказ № 1026/пр, 7 разделов)\n"
        "3. Акты приёмки выполненных работ (КС-2)\n"
        "4. Справки о стоимости (КС-3)\n"
        "5. Исполнительные схемы и чертежи\n"
        "6. Акты испытаний материалов и конструкций\n"
        "7. Паспорта и сертификаты на материалы"
    ),
    "бетонные": (
        "1. АОСР на армирование, опалубку, подготовку основания\n"
        "2. Журнал бетонных работ\n"
        "3. Журнал работ (Приказ № 1026/пр)\n"
        "4. Акты испытания бетонных кубиков (ГОСТ 18105-2010)\n"
        "5. Паспорта на бетонную смесь\n"
        "6. Паспорта на арматуру и закладные детали\n"
        "7. Исполнительные схемы конструкций\n"
        "8. КС-2, КС-3"
    ),
    "земляные": (
        "1. АОСР на основание, обратную засыпку, уплотнение\n"
        "2. Журнал работ (Приказ № 1026/пр)\n"
        "3. Акты геодезической разбивки\n"
        "4. Исполнительные схемы земляных сооружений\n"
        "5. Протоколы испытаний грунта\n"
        "6. КС-2, КС-3"
    ),
    "сварочные": (
        "1. АОСР на сварные соединения (ВСН 012-88)\n"
        "2. Журнал сварочных работ\n"
        "3. Журнал работ (Приказ № 1026/пр)\n"
        "4. Удостоверения сварщиков (НАКС)\n"
        "5. Заключения по НК (ВИК, РК, УЗК)\n"
        "6. Паспорта на сварочные материалы\n"
        "7. КС-2, КС-3"
    ),
    "монтажные": (
        "1. АОСР на монтаж элементов (СП 70.13330.2012)\n"
        "2. Журнал монтажных работ\n"
        "3. Журнал работ (Приказ № 1026/пр)\n"
        "4. Акты испытаний конструкций\n"
        "5. Паспорта и сертификаты на конструкции\n"
        "6. Исполнительные схемы\n"
        "7. КС-2, КС-3"
    ),
    "шпунтовые": (
        "1. АОСР на погружение шпунта (ГОСТ Р 57365-2016)\n"
        "2. Журнал работ (Приказ № 1026/пр)\n"
        "3. Акты приёмки шпунтового ограждения\n"
        "4. Исполнительные схемы шпунтового ряда\n"
        "5. Паспорта на шпунт\n"
        "6. КС-2, КС-3"
    ),
}


class LegalService:
    """
    Сервис юридической экспертизы контрактов.

    Поддерживает три режима:
    - Quick Review: для коротких документов (< chunk_size символов)
    - Map-Reduce: для длинных контрактов (разбивка на чанки + агрегация)
    - ID Check: проверка состава исполнительной документации
    """

    def __init__(self):
        self.agent = "legal"
        self.default_chunk_size = 6000
        self.default_chunk_overlap = 300

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

        # Special handling for ID check
        if request.review_type == ReviewType.ID_CHECK:
            result = await self._id_check(request)
        else:
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
            chunk_size = request.chunk_size or self.default_chunk_size
            total_chars = len(document_text)

            if total_chars <= chunk_size:
                # Short document — Quick Review
                logger.info(f"Quick Review mode (document: {total_chars} chars)")
                result = await self._quick_review(
                    document_text, request.review_type, request.work_type
                )
            else:
                # Long document — Map-Reduce
                logger.info(
                    f"Map-Reduce mode (document: {total_chars} chars, "
                    f"chunk_size: {chunk_size})"
                )
                result = await self._map_reduce(
                    document_text,
                    request.chunk_size,
                    request.chunk_overlap,
                    request.review_type,
                    request.work_type,
                )

        # Step 3: Add metadata
        elapsed = time.time() - start_time
        model_config = settings.get_model_config(self.agent)
        result.analysis_metadata = {
            "duration_seconds": round(elapsed, 2),
            "model": model_config["model"],
            "engine": model_config["engine"],
            "document_chars": (
                len(document_text)
                if request.review_type != ReviewType.ID_CHECK
                else 0
            ),
            "review_type": request.review_type.value,
            "work_type": request.work_type,
            "timestamp": datetime.now().isoformat(),
        }

        logger.info(
            f"Legal analysis complete. Findings: {result.total_risks}, "
            f"Verdict: {result.verdict.value}, Duration: {elapsed:.1f}s"
        )

        return result

    # =========================================================================
    # ID Check — проверка состава ИД
    # =========================================================================

    async def _id_check(self, request: LegalAnalysisRequest) -> LegalAnalysisResult:
        """Проверка состава исполнительной документации."""

        work_type = request.work_type or "общестроительные"
        document_text = await self._resolve_document_text(request)
        required_docs = REQUIRED_ID_DOCS.get(work_type, REQUIRED_ID_DOCS["общестроительные"])

        prompt = LEGAL_ID_CHECK_PROMPT.format(
            system_context=LEGAL_SYSTEM_PROMPT,
            work_type=work_type,
            document_list=document_text or "Список документов не предоставлен",
            required_id_docs=required_docs,
        )

        response_text = await llm_engine.safe_chat(
            self.agent,
            [{"role": "user", "content": prompt}],
            fallback_response=self._empty_id_check_json(),
        )

        return self._parse_analysis_response(response_text, ReviewType.ID_CHECK)

    # =========================================================================
    # Quick Review (short documents)
    # =========================================================================

    async def _quick_review(
        self,
        document_text: str,
        review_type: ReviewType,
        work_type: Optional[str] = None,
    ) -> LegalAnalysisResult:
        """Быстрый обзор для коротких документов (без Map-Reduce)."""

        # БЛС lookup
        blc_context = await self._blc_lookup(document_text[:2000])

        # Work type context
        work_type_context = self._get_work_type_context(work_type)

        prompt = LEGAL_QUICK_REVIEW_PROMPT.format(
            system_context=LEGAL_SYSTEM_PROMPT,
            document_text=document_text,
            blc_context=blc_context,
            work_type_context=work_type_context,
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
        work_type: Optional[str] = None,
    ) -> LegalAnalysisResult:
        """
        Map-Reduce анализ для длинных контрактов.

        MAP:    Каждый чанк анализируется независимо
        REDUCE: Результаты агрегируются в итоговое заключение
        """
        # Step 1: Chunk the document
        chunks = self._chunk_text(document_text, chunk_size, chunk_overlap)
        logger.info(f"Document split into {len(chunks)} chunks")

        work_type_context = self._get_work_type_context(work_type)

        # Step 2: MAP — analyze each chunk
        map_results: List[Dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            logger.info(f"MAP stage: analyzing chunk {i + 1}/{len(chunks)}")

            # БЛС lookup for this chunk
            blc_context = await self._blc_lookup(chunk[:2000])

            prompt = LEGAL_MAP_PROMPT.format(
                system_context=LEGAL_SYSTEM_PROMPT,
                chunk_text=chunk,
                blc_context=blc_context,
                work_type_context=work_type_context,
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
        result = await self._reduce(map_results, review_type, work_type)

        return result

    async def _reduce(
        self,
        map_results: List[Dict[str, Any]],
        review_type: ReviewType,
        work_type: Optional[str] = None,
    ) -> LegalAnalysisResult:
        """REDUCE stage: агрегация результатов MAP."""

        work_type_context = self._get_work_type_context(work_type)

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
            system_context=LEGAL_SYSTEM_PROMPT,
            map_results=map_results_text,
            contradictions_text=contradictions_text,
            work_type_context=work_type_context,
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

        Args:
            text: Текст для поиска (первые ~2000 символов чанка)

        Returns:
            Строка с описаниями найденных ловушек или "Ловушки не найдены"
        """
        try:
            from src.core.rag_service import rag_service
            results = await rag_service.search(text, top_k=3)
            if not results:
                return "Ловушки из БЛС не найдены для данного фрагмента."

            blc_entries = []
            for i, r in enumerate(results, 1):
                content = r.get("content", "")
                blc_entries.append(f"{i}. {content[:300]}")

            return "\n".join(blc_entries)

        except Exception as e:
            logger.warning(f"БЛС lookup failed (DB may be unavailable): {e}")
            return "БЛС временно недоступна. Анализ без учёта известных ловушек."

    # =========================================================================
    # Work Type Context
    # =========================================================================

    @staticmethod
    def _get_work_type_context(work_type: Optional[str]) -> str:
        """Получить контекстную информацию для вида работ."""
        if not work_type:
            return (
                "Вид работ не указан. Анализ проводится в общем контексте "
                "общестроительных работ."
            )
        return WORK_TYPE_CONTEXT.get(
            work_type,
            f"Вид работ: {work_type}. Анализ проводится с учётом данной специфики.",
        )

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

    @staticmethod
    def _empty_id_check_json() -> str:
        """JSON для пустого результата ID Check."""
        return json.dumps({
            "findings": [],
            "missing_documents": [],
            "extra_documents": [],
            "outdated_refs": [],
            "compliance_pct": 0,
            "verdict": "approved",
            "summary": "LLM недоступна. Проверка ИД не выполнена.",
        })


# Singleton
legal_service = LegalService()
