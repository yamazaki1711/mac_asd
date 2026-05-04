"""
ASD v12.0 — Quality Cascade Metrics.

Инструментация конвейера обработки документов для измерения потерь качества
на каждом этапе. Вдохновлено анализом АФИДЫ (Газпром ЦПС): только 13% потерь
качества приходится на LLM, остальные 87% — на OCR, чанкинг, эмбеддинг,
retrieval, ранжирование и пользовательский промт.

Этапы конвейера ASD и источники потерь:
  1. OCR (text extraction quality)
  2. Classification (keyword + VLM fallback accuracy)
  3. Entity Extraction (recall of key fields)
  4. Graph Ingestion (node/link completeness)
  5. RAG Retrieval (chunk relevance)
  6. LLM Response (answer quality)

Использование:
    from src.core.quality_metrics import quality_cascade

    # Инструментировать пайплайн
    metrics = quality_cascade.instrument_pipeline(pipeline)

    # После обработки — получить отчёт
    report = quality_cascade.get_cascade_report()
    print(quality_cascade.format_cascade_table())
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.ingestion import DocumentType, ExtractedDocument

logger = logging.getLogger(__name__)


@dataclass
class StageMetrics:
    """Метрики одного этапа конвейера."""
    stage_name: str
    total_attempts: int = 0
    successes: int = 0
    failures: int = 0
    total_time_ms: float = 0.0
    confidence_scores: List[float] = field(default_factory=list)
    error_details: List[str] = field(default_factory=list)

    # Для entity extraction: recall по ключевым полям
    field_recall: Dict[str, float] = field(default_factory=dict)

    # Для классификации: confusion matrix (type → count)
    type_confusion: Dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_attempts == 0:
            return 1.0
        return self.successes / self.total_attempts

    @property
    def avg_confidence(self) -> float:
        if not self.confidence_scores:
            return 0.0
        return sum(self.confidence_scores) / len(self.confidence_scores)

    @property
    def avg_time_ms(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.total_time_ms / self.total_attempts

    @property
    def loss_contribution(self) -> float:
        """Доля потерь качества, приходящаяся на этот этап (0.0–1.0)."""
        return 1.0 - self.success_rate


@dataclass
class CascadeReport:
    """Полный отчёт каскада качества."""
    stages: Dict[str, StageMetrics] = field(default_factory=dict)
    total_documents: int = 0
    total_time_ms: float = 0.0
    pipeline_version: str = "v13.0"

    @property
    def total_loss(self) -> float:
        """Суммарная потеря качества (композиция потерь всех этапов).

        Использует формулу каскада: loss = 1 - ∏(1 - stage_loss)
        """
        surviving_quality = 1.0
        for stage in self.stages.values():
            surviving_quality *= (1.0 - stage.loss_contribution)
        return 1.0 - surviving_quality

    def get_loss_distribution(self) -> Dict[str, float]:
        """Распределение потерь по этапам в процентах от общей потери."""
        total = self.total_loss
        if total == 0:
            return {name: 0.0 for name in self.stages}
        return {
            name: (stage.loss_contribution / sum(
                s.loss_contribution for s in self.stages.values()
            )) * 100
            for name, stage in self.stages.items()
        }


class QualityCascade:
    """Измеритель каскада качества конвейера ASD.

    Подключается к IngestionPipeline и собирает метрики на каждом этапе.
    Анализирует, где теряется качество — как в АФИДЕ: только ~13% на LLM,
    остальное на pre-processing этапах.
    """

    # Этапы конвейера ASD в порядке выполнения
    STAGES = [
        "1_ocr",
        "2_classification",
        "3_vlm_fallback",
        "4_entity_extraction",
        "5_graph_ingestion",
    ]

    def __init__(self):
        self.stages: Dict[str, StageMetrics] = {
            name: StageMetrics(stage_name=name)
            for name in self.STAGES
        }
        self._doc_counter = 0

    def record_ocr(
        self,
        text: str,
        time_ms: float,
        error: Optional[str] = None,
    ):
        """Записать метрики OCR-этапа."""
        stage = self.stages["1_ocr"]
        stage.total_attempts += 1
        stage.total_time_ms += time_ms

        if error:
            stage.failures += 1
            stage.error_details.append(error)
        elif text and len(text.strip()) > 100:
            stage.successes += 1
            # Качество OCR: доля читаемых символов (русские буквы + цифры)
            readable = sum(1 for c in text if c.isalpha() or c.isdigit() or c in ' .,;:-()')
            quality = readable / max(len(text), 1)
            stage.confidence_scores.append(quality)
        elif text and len(text.strip()) > 0:
            # Текст есть, но очень короткий — частичный успех
            stage.successes += 1
            stage.confidence_scores.append(0.3)
        else:
            stage.failures += 1
            stage.error_details.append("empty_text")

    def record_classification(
        self,
        doc_type: DocumentType,
        confidence: float,
        time_ms: float,
        is_unknown: bool = False,
    ):
        """Записать метрики классификации."""
        stage = self.stages["2_classification"]
        stage.total_attempts += 1
        stage.total_time_ms += time_ms
        stage.confidence_scores.append(confidence)

        if is_unknown or doc_type == DocumentType.UNKNOWN:
            stage.failures += 1
            stage.error_details.append(f"unknown_type")
        else:
            stage.successes += 1

    def record_vlm_fallback(
        self,
        used: bool,
        vlm_type: str,
        confidence: float,
        time_ms: float,
        embedded_refs: int,
    ):
        """Записать метрики VLM-фолбэка."""
        stage = self.stages["3_vlm_fallback"]
        if not used:
            return

        stage.total_attempts += 1
        stage.total_time_ms += time_ms
        stage.confidence_scores.append(confidence)

        if vlm_type and vlm_type != "Неизвестно":
            stage.successes += 1
            stage.type_confusion[vlm_type] = stage.type_confusion.get(vlm_type, 0) + 1
        else:
            stage.failures += 1
            stage.error_details.append("vlm_unknown")

    def record_entity_extraction(
        self,
        entities: Dict[str, Any],
        time_ms: float,
        expected_fields: Optional[List[str]] = None,
    ):
        """Записать метрики извлечения сущностей.

        Если указаны expected_fields — вычисляет recall по полям.
        """
        stage = self.stages["4_entity_extraction"]
        stage.total_attempts += 1
        stage.total_time_ms += time_ms

        # Подсчёт извлечённых полей
        extracted_count = sum(
            1 for v in entities.values()
            if v and (isinstance(v, (list, str)) and len(str(v)) > 0)
        )
        if extracted_count > 0:
            stage.successes += 1

        # Recall по ожидаемым полям
        if expected_fields:
            for field in expected_fields:
                if field not in stage.field_recall:
                    stage.field_recall[field] = 0.0
                value = entities.get(field, "")
                if value and (isinstance(value, (list, str)) and len(str(value)) > 0):
                    stage.field_recall[field] += 1

    def record_graph_ingestion(
        self,
        nodes_added: int,
        time_ms: float,
        errors: int = 0,
    ):
        """Записать метрики добавления в граф."""
        stage = self.stages["5_graph_ingestion"]
        stage.total_attempts += 1
        stage.total_time_ms += time_ms

        if nodes_added > 0:
            stage.successes += 1
        if errors > 0:
            stage.failures += 1
            stage.error_details.append(f"graph_errors={errors}")

    def finalize_entity_field_recall(self):
        """Нормализовать recall по полям (разделить на количество документов)."""
        stage = self.stages["4_entity_extraction"]
        for field in stage.field_recall:
            if stage.total_attempts > 0:
                stage.field_recall[field] /= stage.total_attempts

    def get_cascade_report(self) -> CascadeReport:
        """Сформировать отчёт каскада качества."""
        self.finalize_entity_field_recall()

        total_time = sum(s.total_time_ms for s in self.stages.values())

        report = CascadeReport(
            stages=self.stages,
            total_documents=self._doc_counter,
            total_time_ms=total_time,
        )
        return report

    def format_cascade_table(self) -> str:
        """Форматировать таблицу каскада качества для вывода в терминал."""
        report = self.get_cascade_report()
        loss_dist = report.get_loss_distribution()

        lines = []
        lines.append("")
        lines.append("╔══════════════════════════════════════════════════════════════╗")
        lines.append("║         КАСКАД КАЧЕСТВА ASD v12.0 (Quality Cascade)          ║")
        lines.append("╠══════════════════════════╤══════╤═══════╤══════╤════════════╣")
        lines.append("║ Этап                     │ Поп. │ Успех │ Потеря│ Доля потерь║")
        lines.append("╟──────────────────────────┼──────┼───────┼──────┼────────────╢")

        stage_labels = {
            "1_ocr": "1. OCR (Tesseract)",
            "2_classification": "2. Классификация",
            "3_vlm_fallback": "3. VLM-фолбэк",
            "4_entity_extraction": "4. Извлечение сущностей",
            "5_graph_ingestion": "5. Заполнение графа",
        }

        for stage_name in self.STAGES:
            stage = self.stages[stage_name]
            label = stage_labels.get(stage_name, stage_name)
            rate = f"{stage.success_rate:.0%}"
            loss = f"{stage.loss_contribution:.0%}"
            dist = f"{loss_dist.get(stage_name, 0):.0f}%"

            lines.append(
                f"║ {label:<24} │ {stage.total_attempts:>4} │ {rate:>5} │ {loss:>4} │ {dist:>10} ║"
            )

        lines.append("╟──────────────────────────┴──────┴───────┴──────┴────────────╢")
        lines.append(
            f"║ СУММАРНАЯ ПОТЕРЯ КАЧЕСТВА: {report.total_loss:.0%}                             ║"
        )
        lines.append(
            f"║ (Выжившее качество: {(1 - report.total_loss):.0%})                               ║"
        )
        lines.append("╚══════════════════════════════════════════════════════════════╝")

        # Детализация по этапам
        for stage_name in self.STAGES:
            stage = self.stages[stage_name]
            if stage.total_attempts == 0:
                continue
            label = stage_labels.get(stage_name, stage_name)
            lines.append(f"\n{label}:")
            lines.append(f"  Попыток: {stage.total_attempts}")
            lines.append(f"  Успешно: {stage.successes} / Неудач: {stage.failures}")
            lines.append(f"  Средняя уверенность: {stage.avg_confidence:.2f}")
            lines.append(f"  Среднее время: {stage.avg_time_ms:.0f} мс")
            if stage.error_details:
                unique_errors = set(stage.error_details)
                lines.append(f"  Ошибки: {', '.join(list(unique_errors)[:5])}")

        return "\n".join(lines)

    def get_loss_waterfall(self) -> str:
        """Водопад потерь — как в оригинальном анализе АФИДЫ.

        Показывает, как качество падает этап за этапом:
        Исходное 100% → этап1 → этап2 → ... → финальное качество.
        """
        report = self.get_cascade_report()

        lines = []
        lines.append("\nВОДОПАД КАЧЕСТВА (Quality Waterfall):")
        lines.append(f"  Исходное качество:          100.0%")

        quality = 100.0
        for stage_name in self.STAGES:
            stage = self.stages[stage_name]
            if stage.total_attempts == 0:
                continue

            loss = stage.loss_contribution * 100
            quality_before = quality
            quality *= (1.0 - stage.loss_contribution)

            stage_labels = {
                "1_ocr": "  после OCR:                 ",
                "2_classification": "  после Классификации:       ",
                "3_vlm_fallback": "  после VLM:                 ",
                "4_entity_extraction": "  после Извлечения сущностей: ",
                "5_graph_ingestion": "  после Заполнения графа:    ",
            }
            label = stage_labels.get(stage_name, f"  после {stage_name}:")
            lines.append(
                f"{label}{quality:.1f}%  (потеряно {loss:.1f}% на этом этапе)"
            )

        lines.append(f"\n  Итоговое качество конвейера:   {quality:.1f}%")
        lines.append(f"  Общая потеря:                  {report.total_loss * 100:.1f}%")

        # Интерпретация
        lines.append(f"\n  Доля потерь на pre-LLM этапах:  {quality:.0f}%")
        lines.append(f"  (Сравните: у АФИДЫ только ~13% потерь на LLM)")

        return "\n".join(lines)


# =============================================================================
# Инструментирование IngestionPipeline
# =============================================================================


class InstrumentedPipeline:
    """Обёртка над IngestionPipeline с автоматическим сбором метрик."""

    def __init__(self, pipeline, quality_cascade: QualityCascade):
        self._pipeline = pipeline
        self._qc = quality_cascade
        self._original_process_single = pipeline.process_single

    def __getattr__(self, name):
        """Проксирование всех атрибутов на оригинальный pipeline."""
        return getattr(self._pipeline, name)

    def process_single(self, file_path):
        """Инструментированная версия process_single с замером метрик."""
        from pathlib import Path
        file_path = Path(file_path)

        # Этап 1: OCR
        t0 = time.monotonic()
        try:
            text, page_count = self._pipeline.ocr.extract_text(file_path)
            ocr_time = (time.monotonic() - t0) * 1000
            self._qc.record_ocr(text, ocr_time)
        except Exception as e:
            ocr_time = (time.monotonic() - t0) * 1000
            self._qc.record_ocr("", ocr_time, error=str(e))

        # Вызов оригинального метода
        result = self._original_process_single(file_path)

        # Этап 2: Классификация
        self._qc.record_classification(
            doc_type=result.doc_type,
            confidence=result.classification_confidence,
            time_ms=0,  # время уже учтено в оригинальном методе
            is_unknown=(result.doc_type == DocumentType.UNKNOWN),
        )

        # Этап 3: VLM-фолбэк
        if result.vlm_classified:
            # VLM успешен если тип не UNKNOWN после фолбэка
            vlm_success = result.doc_type != DocumentType.UNKNOWN
            vlm_type = result.doc_type.value
            embedded_count = len(result.embedded_refs)
            self._qc.record_vlm_fallback(
                used=True,
                vlm_type=vlm_type if vlm_success else "Неизвестно",
                confidence=result.classification_confidence,
                time_ms=0,
                embedded_refs=embedded_count,
            )

        # Этап 4: Извлечение сущностей
        if result.entities:
            self._qc.record_entity_extraction(
                entities=result.entities,
                time_ms=0,
                expected_fields=[
                    "work_type", "date", "material_name", "batch_number",
                    "batch_size", "supplier_name", "gost", "document_number",
                ],
            )

        self._qc._doc_counter += 1
        return result

    def ingest_to_graph(self, project_id: str = "") -> int:
        """Инструментированная версия ingest_to_graph."""
        t0 = time.monotonic()
        try:
            nodes = self._pipeline.ingest_to_graph(project_id)
            graph_time = (time.monotonic() - t0) * 1000
            self._qc.record_graph_ingestion(nodes, graph_time)
            return nodes
        except Exception:
            graph_time = (time.monotonic() - t0) * 1000
            self._qc.record_graph_ingestion(0, graph_time, errors=1)
            return 0

    def process_files(self, files):
        """Инструментированная версия process_files — вызывает инструментированный process_single."""
        self._pipeline.documents = []
        type_counts: Dict[str, int] = {}
        errors_total = 0

        for file_path in files:
            try:
                doc = self.process_single(file_path)  # ← инструментированный
                self._pipeline.documents.append(doc)
                type_counts[doc.doc_type.value] = type_counts.get(doc.doc_type.value, 0) + 1
                errors_total += len(doc.errors)
            except Exception as e:
                logger.error("Failed to process %s: %s", file_path.name, e)
                self._pipeline.documents.append(ExtractedDocument(
                    file_path=file_path,
                    doc_type=DocumentType.UNKNOWN,
                    classification_confidence=0.0,
                    errors=[str(e)],
                ))

        self._pipeline.stats = {
            "total_files": len(files),
            "processed": len(self._pipeline.documents),
            "type_counts": type_counts,
            "total_errors": errors_total,
            "completed_at": datetime.now().isoformat(),
        }
        return self._pipeline.documents

    def scan_folder(
        self,
        folder: Path,
        recursive: bool = True,
        file_types: Optional[List[str]] = None,
    ):
        """Инструментированная версия scan_folder."""
        if file_types is None:
            file_types = ['pdf', 'jpg', 'jpeg', 'png', 'tiff', 'tif', 'bmp', 'docx', 'xlsx', 'txt']

        folder = Path(folder)
        if not folder.exists():
            logger.error("Folder not found: %s", folder)
            return []

        files = []
        glob_pattern = "**/*" if recursive else "*"
        for file_path in sorted(folder.glob(glob_pattern)):
            if file_path.is_file() and file_path.suffix.lower().lstrip('.') in file_types:
                files.append(file_path)

        logger.info("Ingestion: found %d files in %s", len(files), folder)
        return self.process_files(files)  # ← инструментированный


# =============================================================================
# Singleton
# =============================================================================

quality_cascade = QualityCascade()


def instrument_pipeline(pipeline) -> InstrumentedPipeline:
    """Инструментировать IngestionPipeline для сбора метрик каскада качества."""
    wrapped = InstrumentedPipeline(pipeline, quality_cascade)
    return wrapped
