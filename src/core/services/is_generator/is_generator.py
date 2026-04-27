"""
ISGenerator — главный оркестратор пайплайна Исполнительных Схем.

Пайплайн:
  1. Парсинг геодезического отчёта → [SurveyPoint]
  2. Парсинг проектного DXF → [DesignAxis]
  3. Расчёт трансформации (если заданы опорные точки)
  4. Matching + расчёт отклонений → [Deviation]
  5. Аннотирование DXF + генерация PDF
  6. Формирование ISResult

Использование:
    from src.core.services.is_generator import ISGenerator, AnchorPoint

    gen = ISGenerator(
        output_dir="/data/projects/P001/IS",
        anchor_points=[
            AnchorPoint(dxf_x=100.0, dxf_y=200.0, geo_x=312540.12, geo_y=6789012.34),
            AnchorPoint(dxf_x=5000.0, dxf_y=200.0, geo_x=312545.00, geo_y=6789017.21),
        ],
    )
    result = gen.generate(
        project_id="P001",
        aosr_id="АОСР-001",
        survey_file="/data/survey_report.csv",
        design_dxf="/data/design.dxf",
    )
    print(result.is_acceptable, result.critical_deviations)
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

from src.core.services.is_generator.schemas import (
    AnchorPoint,
    CoordinateTransform,
    DesignAxis,
    ISResult,
    SurveyPoint,
    SurveyFormat,
)
from src.core.services.is_generator.geodata_parser import GeodataParser
from src.core.services.is_generator.dxf_parser      import DXFParser
from src.core.services.is_generator.deviation_calculator import DeviationCalculator
from src.core.services.is_generator.dxf_annotator   import DXFAnnotator


class ISGenerator:
    """
    Фасад для генерации Исполнительной Схемы.

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
        survey_file: str | Path,
        design_dxf: str | Path,
        survey_format: SurveyFormat | None = None,
        run_id: str | None = None,
    ) -> ISResult:
        """
        Запускает полный пайплайн генерации ИС.

        Args:
            project_id: Идентификатор проекта (для имён файлов).
            aosr_id:    Идентификатор АОСР.
            survey_file: Файл геодезического отчёта.
            design_dxf:  Проектный DXF.
            survey_format: Формат геодезии (None → автоопределение).
            run_id: Уникальный суффикс запуска (None → UUID4).

        Returns:
            ISResult — полный результат с метриками и путями к файлам.
        """
        run_id = run_id or uuid.uuid4().hex[:8]
        logger.info(f"[ISGenerator] Старт run_id={run_id}, project={project_id}, aosr={aosr_id}")

        # ── Шаг 1: геодезия ───────────────────────────────────────────────────
        survey_points: list[SurveyPoint] = self._geodata_parser.parse(
            survey_file, fmt=survey_format
        )
        logger.info(f"  → Точек геодезии: {len(survey_points)}")

        # ── Шаг 2: DXF ───────────────────────────────────────────────────────
        axes: list[DesignAxis] = self._dxf_parser.parse(design_dxf)
        logger.info(f"  → Осей в DXF: {len(axes)}")

        # ── Шаг 3: расчёт отклонений ─────────────────────────────────────────
        deviations, unmatched_axes, unmatched_points = self._calculator.calculate(
            axes, survey_points
        )

        # ── Шаг 4: статистика ────────────────────────────────────────────────
        ok_cnt   = sum(1 for d in deviations if d.status.value == "OK")
        warn_cnt = sum(1 for d in deviations if d.status.value == "WARNING")
        crit_cnt = sum(1 for d in deviations if d.status.value == "CRITICAL")

        # ── Шаг 5: выходные пути ─────────────────────────────────────────────
        out_dxf = self.output_dir / f"IS_{project_id}_{run_id}.dxf"
        out_pdf = self.output_dir / f"IS_{project_id}_{run_id}.pdf"

        # ── Шаг 6: предварительный ISResult (без файлов) ─────────────────────
        result = ISResult(
            project_id=project_id,
            aosr_id=aosr_id,
            output_dxf_path=str(out_dxf),
            output_pdf_path=str(out_pdf),
            total_axes=len(axes),
            matched_axes=len(deviations),
            critical_deviations=crit_cnt,
            warning_deviations=warn_cnt,
            ok_deviations=ok_cnt,
            deviations=deviations,
            unmatched_axes=unmatched_axes,
            unmatched_survey_points=unmatched_points,
            coordinate_transform_applied=self._calculator.transform is not None,
        )

        # ── Шаг 7: аннотирование ─────────────────────────────────────────────
        axis_geo_positions: dict[str, tuple[float, float]] = {}
        survey_pos_map: dict[str, tuple[float, float]] = {}

        if self._calculator.transform is not None:
            # Трансформация уже применена внутри calculator к design_x/y
            for ax in axes:
                ct = self._calculator.transform
                gx, gy = ct.apply(ax.design_x, ax.design_y)
                axis_geo_positions[ax.handle] = (gx, gy)
        else:
            for ax in axes:
                axis_geo_positions[ax.handle] = (ax.design_x, ax.design_y)

        for pt in survey_points:
            survey_pos_map[pt.point_id] = (pt.x, pt.y)

        try:
            self._annotator.annotate_with_positions(
                template_dxf_path=design_dxf,
                deviations=deviations,
                result=result,
                axis_geo_positions=axis_geo_positions,
                survey_positions=survey_pos_map,
                transform=self._calculator.transform,
                output_dxf_path=out_dxf,
                output_pdf_path=out_pdf,
            )
        except Exception as e:
            logger.error(f"Аннотирование не удалось: {e}. DXF/PDF могут быть неполными.")

        logger.info(
            f"[ISGenerator] Завершено. "
            f"OK={ok_cnt} WARN={warn_cnt} CRIT={crit_cnt} "
            f"Acceptable={result.is_acceptable}"
        )
        return result
