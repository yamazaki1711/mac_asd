"""
ISGenerator — главный оркестратор пайплайна Исполнительных Схем.

v12.0 — два равноправных пути генерации:

  Путь 1 (DXF-First): DWG/DXF от проектировщика → clip → annotate → PDF
    Полный векторный пайплайн. Проектный чертёж — подложка.
    Аннотации: отклонения (геодезия) + факт. отметки + факт. размеры + штамп ГОСТ.

  Путь 2 (PDF-Overlay): PDF от проектировщика → PNG-подложка → векторные аннотации → PDF
    Когда исходники DWG/DXF недоступны (конфликт с проектировщиком).
    Подложка растровая, аннотации векторные — стройконтроль принимает.

  Общий рабочий процесс (реальный):
    1. RDIndex.lookup() — найти нужный лист РД по виду работ / захватке
    2. Выбрать путь по формату файла (DWG/DXF → Путь 1, PDF → Путь 2)
    3. Вырезать фрагмент РД под захватку (clip)
    4. Нанести факт. данные (из АОСР, актов, геодезии)
    5. Заполнить штамп ГОСТ 21.101-2020
    6. Экспорт → векторный PDF

Использование:
    from src.core.services.is_generator import ISGenerator

    gen = ISGenerator(output_dir="/data/projects/P001/IS")
    result = gen.generate(
        project_id="P001",
        aosr_id="АОСР-001",
        rd_sheet=RDSheetInfo(
            format="dxf",
            file_path="/data/RD/КЖ-03.dxf",
            bbox=BBox(x_min=10000, y_min=5000, x_max=30000, y_max=20000),
        ),
        survey_file="/data/survey_report.csv",
        fact_marks=[FactMark(...)],
        stamp_data=ISStampData(object_name="Жилой дом №3", ...),
    )
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from src.core.services.is_generator.schemas import (
    AnchorPoint,
    BBox,
    CoordinateTransform,
    FactDimension,
    FactMark,
    ISPipeline,
    ISResult,
    ISStampData,
    RDSheetInfo,
    RDFormat,
    SurveyFormat,
    SurveyPoint,
)
from src.core.services.is_generator.geodata_parser import GeodataParser
from src.core.services.is_generator.dxf_parser import DXFParser
from src.core.services.is_generator.deviation_calculator import DeviationCalculator
from src.core.services.is_generator.dxf_annotator import DXFAnnotator


class ISGenerator:
    """
    Фасад для генерации Исполнительной Схемы.

    Поддерживает два пайплайна:
      - DXF-First (Путь 1): для DWG/DXF исходников
      - PDF-Overlay (Путь 2): для PDF исходников

    Args:
        output_dir: Базовый каталог для выходных файлов.
        anchor_points: Опорные точки для CRS-привязки DXF.
        axis_layers: Слои с проектными осями (см. DXFParser).
        tolerance_map: Переопределение допусков (слой → мм).
        label_match_threshold: Порог fuzzy-matching (0..1).
        spatial_search_radius_m: Радиус пространственного поиска (м).
        text_height: Высота аннотационного текста в единицах DXF.
    """

    def __init__(
        self,
        output_dir: str | Path = "/tmp/is_output",
        anchor_points: list[AnchorPoint] | None = None,
        axis_layers: list[str] | None = None,
        tolerance_map: dict[str, float] | None = None,
        label_match_threshold: float = 0.55,
        spatial_search_radius_m: float = 5.0,
        text_height: float = 150.0,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._anchor_points = anchor_points or []

        self._geodata_parser = GeodataParser()
        self._dxf_parser     = DXFParser(axis_layers=axis_layers)
        self._calculator     = DeviationCalculator(
            anchor_points=anchor_points,
            tolerance_map=tolerance_map,
            label_match_threshold=label_match_threshold,
            spatial_search_radius_m=spatial_search_radius_m,
        )
        self._annotator = DXFAnnotator(text_height=text_height)

    # ──────────────────────────────────────────────────────────────────────────

    def generate(
        self,
        project_id: str,
        aosr_id: str,
        rd_sheet: Optional[RDSheetInfo] = None,
        survey_file: Optional[str | Path] = None,
        design_dxf: Optional[str | Path] = None,
        survey_format: SurveyFormat | None = None,
        fact_marks: Optional[list[FactMark]] = None,
        fact_dimensions: Optional[list[FactDimension]] = None,
        stamp_data: Optional[ISStampData] = None,
        run_id: str | None = None,
    ) -> ISResult:
        """
        Запускает полный пайплайн генерации ИС.

        Автоматически выбирает путь:
          - Если rd_sheet.format in (DWG, DXF) или design_dxf задан → Путь 1
          - Если rd_sheet.format == PDF → Путь 2

        Args:
            project_id: Идентификатор проекта.
            aosr_id: Идентификатор АОСР.
            rd_sheet: Информация о листе РД (из RDIndex).
            survey_file: Файл геодезического отчёта (опционально).
            design_dxf: Проектный DXF напрямую (опционально, приоритет над rd_sheet).
            survey_format: Формат геодезии (None → автоопределение).
            fact_marks: Фактические отметки для нанесения.
            fact_dimensions: Фактические размеры для нанесения.
            stamp_data: Данные штампа ГОСТ 21.101-2020.
            run_id: Уникальный суффикс запуска (None → UUID4).

        Returns:
            ISResult — полный результат с метриками и путями к файлам.
        """
        run_id = run_id or uuid.uuid4().hex[:8]

        # Определяем пайплайн
        pipeline, dxf_source, pdf_source = self._resolve_pipeline(rd_sheet, design_dxf)

        logger.info(
            f"[ISGenerator] Старт run_id={run_id}, project={project_id}, "
            f"aosr={aosr_id}, pipeline={pipeline.value}"
        )

        # ── Геодезия (если есть) ──────────────────────────────────────────
        survey_points: list[SurveyPoint] = []
        if survey_file:
            survey_points = self._geodata_parser.parse(survey_file, fmt=survey_format)
            logger.info(f"  → Точек геодезии: {len(survey_points)}")

        if pipeline == ISPipeline.DXF_FIRST:
            result = self._run_dxf_first(
                project_id=project_id,
                aosr_id=aosr_id,
                run_id=run_id,
                dxf_source=dxf_source,
                rd_sheet=rd_sheet,
                survey_points=survey_points,
                fact_marks=fact_marks or [],
                fact_dimensions=fact_dimensions or [],
                stamp_data=stamp_data,
            )
        else:
            result = self._run_pdf_overlay(
                project_id=project_id,
                aosr_id=aosr_id,
                run_id=run_id,
                pdf_source=pdf_source,
                rd_sheet=rd_sheet,
                survey_points=survey_points,
                fact_marks=fact_marks or [],
                fact_dimensions=fact_dimensions or [],
                stamp_data=stamp_data,
            )

        result.pipeline = pipeline
        result.rd_sheet = rd_sheet

        logger.info(
            f"[ISGenerator] Завершено. pipeline={pipeline.value} "
            f"Acceptable={result.is_acceptable}"
        )
        return result

    # ─── Определение пайплайна ────────────────────────────────────────────────

    def _resolve_pipeline(
        self,
        rd_sheet: Optional[RDSheetInfo],
        design_dxf: Optional[str | Path],
    ) -> tuple[ISPipeline, Optional[Path], Optional[Path]]:
        """
        Определяет пайплайн и источники файлов.

        Returns:
            (pipeline, dxf_source, pdf_source)
        """
        # Приоритет: явно заданный DXF
        if design_dxf:
            return ISPipeline.DXF_FIRST, Path(design_dxf), None

        # По rd_sheet
        if rd_sheet:
            fmt = rd_sheet.format if isinstance(rd_sheet.format, str) else rd_sheet.format
            if fmt in ("dxf", "dwg"):
                return ISPipeline.DXF_FIRST, Path(rd_sheet.file_path), None
            elif fmt == "pdf":
                return ISPipeline.PDF_OVERLAY, None, Path(rd_sheet.file_path)
            elif fmt == "scan":
                # Скан — fallback на PDF-путь с предупреждением
                logger.warning(
                    "Формат исходника: скан. Качество подложки может быть низким. "
                    "Рекомендуется верификация VLM."
                )
                return ISPipeline.PDF_OVERLAY, None, Path(rd_sheet.file_path)

        # Нет данных — ошибочная ситуация
        raise ValueError(
            "Не указан источник РД: передайте rd_sheet или design_dxf. "
            "Используйте RDIndex.lookup() для поиска листа РД."
        )

    # ─── Путь 1: DXF-First ────────────────────────────────────────────────────

    def _run_dxf_first(
        self,
        project_id: str,
        aosr_id: str,
        run_id: str,
        dxf_source: Path,
        rd_sheet: Optional[RDSheetInfo],
        survey_points: list[SurveyPoint],
        fact_marks: list[FactMark],
        fact_dimensions: list[FactDimension],
        stamp_data: Optional[ISStampData],
    ) -> ISResult:
        """Путь 1: DWG/DXF → clip → parse axes → deviations → annotate → PDF."""
        from src.core.services.is_generator.svg_exporter import SVGExporter

        # Шаг 1: Вырезать фрагмент РД (если задан bbox)
        if rd_sheet and rd_sheet.bbox:
            bbox = BBox(*rd_sheet.bbox)
            clipped_dxf = self.output_dir / f"IS_{project_id}_{run_id}_clip.dxf"
            self._dxf_parser.clip_by_bbox(dxf_source, bbox, clipped_dxf)
            work_dxf = clipped_dxf
        else:
            work_dxf = dxf_source

        # Шаг 2: Парсинг осей из DXF
        axes = self._dxf_parser.parse(work_dxf)
        logger.info(f"  → Осей в DXF: {len(axes)}")

        # Шаг 3: Расчёт отклонений
        deviations, unmatched_axes, unmatched_points = self._calculator.calculate(
            axes, survey_points
        )

        # Шаг 4: Статистика
        ok_cnt   = sum(1 for d in deviations if d.status.value == "OK")
        warn_cnt = sum(1 for d in deviations if d.status.value == "WARNING")
        crit_cnt = sum(1 for d in deviations if d.status.value == "CRITICAL")

        # Шаг 5: Пути вывода
        out_dxf = self.output_dir / f"IS_{project_id}_{run_id}.dxf"
        out_pdf = self.output_dir / f"IS_{project_id}_{run_id}.pdf"

        # Шаг 6: ISResult
        result = ISResult(
            project_id=project_id,
            aosr_id=aosr_id,
            pipeline=ISPipeline.DXF_FIRST,
            output_dxf_path=str(out_dxf),
            output_pdf_path=str(out_pdf),
            total_axes=len(axes),
            matched_axes=len(deviations),
            critical_deviations=crit_cnt,
            warning_deviations=warn_cnt,
            ok_deviations=ok_cnt,
            deviations=deviations,
            fact_marks=fact_marks,
            fact_dimensions=fact_dimensions,
            unmatched_axes=unmatched_axes,
            unmatched_survey_points=unmatched_points,
            coordinate_transform_applied=self._calculator.transform is not None,
            stamp_data=stamp_data,
        )

        # Шаг 7: Координаты для аннотирования
        axis_geo_positions: dict[str, tuple[float, float]] = {}
        survey_pos_map: dict[str, tuple[float, float]] = {}

        if self._calculator.transform is not None:
            for ax in axes:
                ct = self._calculator.transform
                gx, gy = ct.apply(ax.design_x, ax.design_y)
                axis_geo_positions[ax.handle] = (gx, gy)
        else:
            for ax in axes:
                axis_geo_positions[ax.handle] = (ax.design_x, ax.design_y)

        for pt in survey_points:
            survey_pos_map[pt.point_id] = (pt.x, pt.y)

        # Шаг 8: Аннотирование
        try:
            self._annotator.annotate_with_positions(
                template_dxf_path=work_dxf,
                deviations=deviations,
                result=result,
                axis_geo_positions=axis_geo_positions,
                survey_positions=survey_pos_map,
                transform=self._calculator.transform,
                output_dxf_path=out_dxf,
                output_pdf_path=out_pdf,
                stamp_data=stamp_data,
            )
        except Exception as e:
            logger.error(f"Аннотирование не удалось: {e}")

        return result

    # ─── Путь 2: PDF-Overlay ──────────────────────────────────────────────────

    def _run_pdf_overlay(
        self,
        project_id: str,
        aosr_id: str,
        run_id: str,
        pdf_source: Optional[Path],
        rd_sheet: Optional[RDSheetInfo],
        survey_points: list[SurveyPoint],
        fact_marks: list[FactMark],
        fact_dimensions: list[FactDimension],
        stamp_data: Optional[ISStampData],
    ) -> ISResult:
        """Путь 2: PDF → PNG подложка → векторные аннотации → PDF."""
        from src.core.services.is_generator.pdf_overlay_builder import PDFOverlayBuilder
        from src.core.services.is_generator.svg_exporter import SVGExporter

        if not pdf_source:
            raise ValueError("PDF-путь требует pdf_source (файл PDF от проектировщика)")

        # Определяем bbox (если задан в rd_sheet)
        crop_bbox = None
        page_number = 0
        if rd_sheet:
            page_number = rd_sheet.page_number
            if rd_sheet.bbox:
                crop_bbox = BBox(*rd_sheet.bbox)

        # Пути вывода
        out_dxf = self.output_dir / f"IS_{project_id}_{run_id}_overlay.dxf"
        out_pdf = self.output_dir / f"IS_{project_id}_{run_id}_overlay.pdf"

        # Строим DXF с подложкой + аннотациями
        builder = PDFOverlayBuilder()
        builder.build(
            pdf_path=pdf_source,
            output_dxf_path=out_dxf,
            page_number=page_number,
            crop_bbox=crop_bbox,
            fact_marks=fact_marks,
            fact_dimensions=fact_dimensions,
            stamp_data=stamp_data,
        )

        # Конвертируем DXF → PDF
        try:
            exporter = SVGExporter(page_size="A3")
            exporter.export_pdf(out_dxf, out_pdf)
        except Exception as e:
            logger.error(f"SVG-экспорт overlay DXF не удался: {e}")

        # Отклонения для PDF-пути (без автоматического matching)
        deviations = self._compute_pdf_deviations(survey_points)

        result = ISResult(
            project_id=project_id,
            aosr_id=aosr_id,
            pipeline=ISPipeline.PDF_OVERLAY,
            output_dxf_path=str(out_dxf),
            output_pdf_path=str(out_pdf),
            total_axes=0,  # В PDF-пути оси не извлекаются
            matched_axes=0,
            critical_deviations=sum(1 for d in deviations if d.status.value == "CRITICAL"),
            warning_deviations=sum(1 for d in deviations if d.status.value == "WARNING"),
            ok_deviations=sum(1 for d in deviations if d.status.value == "OK"),
            deviations=deviations,
            fact_marks=fact_marks,
            fact_dimensions=fact_dimensions,
            unmatched_axes=[],
            unmatched_survey_points=[],
            coordinate_transform_applied=False,
            stamp_data=stamp_data,
        )

        return result

    @staticmethod
    def _compute_pdf_deviations(survey_points: list[SurveyPoint]) -> list:
        """Для PDF-пути: отклонения не рассчитываются автоматически (нет проектных осей)."""
        return []  # В PDF-пути нужны FactMark/FactDimension с ручными координатами
