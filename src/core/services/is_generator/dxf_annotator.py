"""
DXFAnnotator — аннотатор DXF для модуля ISGenerator.

Наносит на копию проектного чертежа:
  - Фактические отметки (из актов/АОСР)
  - Фактические размеры (из замеров)
  - Стрелки отклонений (из геодезии): проектная точка → фактическая
  - Цветовую индикацию: OK=зелёный, WARNING=жёлтый, CRITICAL=красный
  - Штамп ГОСТ 21.101-2020 (через GOSTStampGenerator)

v12.0 — полная переработка: факт. данные + ГОСТ штамп + SVG→PDF через SVGExporter.
"""
from __future__ import annotations

import logging
import math
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from src.core.services.is_generator.schemas import (
    CoordinateTransform,
    Deviation,
    DeviationStatus,
    FactDimension,
    FactMark,
    ISResult,
    ISStampData,
)

try:
    import ezdxf
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False


# --- Цветовая палитра (ACI-коды AutoCAD) ------------------------------------

STATUS_COLOR: dict[DeviationStatus, int] = {
    DeviationStatus.OK:       3,    # green
    DeviationStatus.WARNING:  2,    # yellow
    DeviationStatus.CRITICAL: 1,    # red
}

# Слои аннотаций
LAYER_ANNOTATIONS  = "_IS_ANNOTATIONS"
LAYER_FACT_MARKS   = "_IS_FACT_MARKS"
LAYER_FACT_DIMS    = "_IS_FACT_DIMS"
LAYER_STAMP        = "_IS_STAMP"
LAYER_STAMP_TEXT   = "_IS_STAMP_TEXT"


class DXFAnnotator:
    """
    Открывает DXF-шаблон (фрагмент РД), вносит аннотации,
    сохраняет аннотированный DXF и генерирует PDF (через SVGExporter).

    Args:
        arrow_scale: Масштаб стрелки относительно единиц чертежа.
        text_height: Высота текста аннотации (в единицах чертежа).
        stamp_position: (x, y) — позиция штампа в модельном пространстве.
    """

    def __init__(
        self,
        arrow_scale: float = 50.0,
        text_height: float = 100.0,
        stamp_position: tuple[float, float] = (0.0, -2000.0),
    ) -> None:
        self.arrow_scale    = arrow_scale
        self.text_height    = text_height
        self.stamp_position = stamp_position

    # ──────────────────────────────────────────────────────────────────────────

    def annotate_with_positions(
        self,
        template_dxf_path: str | Path,
        deviations: list[Deviation],
        result: ISResult,
        axis_geo_positions: dict[str, tuple[float, float]],
        survey_positions: dict[str, tuple[float, float]],
        transform: CoordinateTransform | None,
        output_dxf_path: str | Path,
        output_pdf_path: str | Path,
        stamp_data: Optional[ISStampData] = None,
    ) -> None:
        """
        Полный цикл аннотирования с явными координатами точек.

        Расширен в v12.0: добавлены факт. отметки, факт. размеры, штамп ГОСТ.
        """
        if not EZDXF_AVAILABLE:
            raise ImportError("ezdxf не установлен: pip install ezdxf")

        template = Path(template_dxf_path)
        out_dxf  = Path(output_dxf_path)
        out_pdf  = Path(output_pdf_path)
        out_dxf.parent.mkdir(parents=True, exist_ok=True)
        out_pdf.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(template, out_dxf)
        doc = ezdxf.readfile(str(out_dxf))
        msp = doc.modelspace()
        self._ensure_layers(doc)

        # ── Отклонения (геодезия) ─────────────────────────────────────────
        self._draw_deviations(msp, deviations, axis_geo_positions, survey_positions, transform)

        # ── Фактические отметки ────────────────────────────────────────────
        if result.fact_marks:
            self._draw_fact_marks(msp, result.fact_marks)

        # ── Фактические размеры ───────────────────────────────────────────
        if result.fact_dimensions:
            self._draw_fact_dimensions(msp, result.fact_dimensions)

        # ── Штамп ГОСТ 21.101-2020 ───────────────────────────────────────
        if stamp_data:
            self._draw_gost_stamp(msp, stamp_data)

        # ── Сводный штамп (упрощённый, для обратной совместимости) ────────
        if not stamp_data:
            self._draw_summary_stamp(msp, result)

        doc.saveas(str(out_dxf))
        logger.info(f"Аннотированный DXF сохранён: {out_dxf}")

        # ── Векторный PDF через SVGExporter ───────────────────────────────
        self._export_pdf(doc, out_dxf, out_pdf)

    # ─── Отклонения ───────────────────────────────────────────────────────────

    def _draw_deviations(
        self,
        msp,
        deviations: list[Deviation],
        axis_geo_positions: dict[str, tuple[float, float]],
        survey_positions: dict[str, tuple[float, float]],
        transform: CoordinateTransform | None,
    ) -> None:
        """Наносит стрелки отклонений на DXF."""
        for dev in deviations:
            color = STATUS_COLOR[dev.status]

            # Проектная позиция (в координатах DXF)
            if dev.axis_id not in axis_geo_positions:
                continue

            gx, gy = axis_geo_positions[dev.axis_id]
            if transform:
                design_dxf_x, design_dxf_y = transform.inverse(gx, gy)
            else:
                design_dxf_x, design_dxf_y = gx, gy

            # Фактическая позиция → DXF
            if dev.survey_point_id in survey_positions:
                sx, sy = survey_positions[dev.survey_point_id]
                if transform:
                    fact_dxf_x, fact_dxf_y = transform.inverse(sx, sy)
                else:
                    fact_dxf_x, fact_dxf_y = sx, sy
            else:
                fact_dxf_x, fact_dxf_y = design_dxf_x, design_dxf_y

            # Крест в проектной точке
            cs = self.arrow_scale * 0.5
            msp.add_line(
                (design_dxf_x - cs, design_dxf_y),
                (design_dxf_x + cs, design_dxf_y),
                dxfattribs={"layer": LAYER_ANNOTATIONS, "color": 8},
            )
            msp.add_line(
                (design_dxf_x, design_dxf_y - cs),
                (design_dxf_x, design_dxf_y + cs),
                dxfattribs={"layer": LAYER_ANNOTATIONS, "color": 8},
            )

            # Точка факт
            msp.add_circle(
                center=(fact_dxf_x, fact_dxf_y),
                radius=self.arrow_scale * 0.3,
                dxfattribs={"layer": LAYER_ANNOTATIONS, "color": color},
            )

            # Стрелка проект → факт
            dist = math.hypot(fact_dxf_x - design_dxf_x, fact_dxf_y - design_dxf_y)
            if dist > self.arrow_scale * 0.1:
                msp.add_line(
                    (design_dxf_x, design_dxf_y),
                    (fact_dxf_x, fact_dxf_y),
                    dxfattribs={"layer": LAYER_ANNOTATIONS, "color": color, "lineweight": 35},
                )

            # Текстовая подпись
            sign_x = (design_dxf_x + fact_dxf_x) / 2 + self.text_height * 0.5
            sign_y = (design_dxf_y + fact_dxf_y) / 2 + self.text_height * 0.5

            label_text = (
                f"D={dev.distance_mm:.1f}mm  {dev.status.value}  [{dev.axis_label}]"
            )
            text = msp.add_text(
                label_text,
                dxfattribs={
                    "layer": LAYER_ANNOTATIONS,
                    "color": color,
                    "height": self.text_height,
                },
            )
            text.dxf.insert = (sign_x, sign_y)

    # ─── Фактические отметки ──────────────────────────────────────────────────

    def _draw_fact_marks(self, msp, marks: list[FactMark]) -> None:
        """Наносит фактические отметки на DXF."""
        for mark in marks:
            x, y = mark.position_x, mark.position_y
            if x == 0.0 and y == 0.0:
                continue  # Нет координат — пропускаем

            # Цвет по отклонению
            color = 3  # OK
            if abs(mark.deviation_mm) > 10:
                color = 1  # CRITICAL
            elif abs(mark.deviation_mm) > 5:
                color = 2  # WARNING

            # Маркер (треугольник)
            cs = self.arrow_scale * 0.3
            msp.add_line(
                (x, y + cs), (x - cs * 0.6, y - cs * 0.3),
                dxfattribs={"layer": LAYER_FACT_MARKS, "color": color},
            )
            msp.add_line(
                (x - cs * 0.6, y - cs * 0.3), (x + cs * 0.6, y - cs * 0.3),
                dxfattribs={"layer": LAYER_FACT_MARKS, "color": color},
            )
            msp.add_line(
                (x + cs * 0.6, y - cs * 0.3), (x, y + cs),
                dxfattribs={"layer": LAYER_FACT_MARKS, "color": color},
            )

            # Текст отметки
            label = f"{mark.label}: пр.{mark.design_value} факт.{mark.fact_value}"
            if mark.deviation_mm != 0:
                sign = "+" if mark.deviation_mm > 0 else ""
                label += f" ({sign}{mark.deviation_mm:.0f}мм)"
            if mark.source:
                label += f" [{mark.source}]"

            text = msp.add_text(
                label,
                dxfattribs={
                    "layer": LAYER_FACT_MARKS,
                    "color": color,
                    "height": self.text_height * 0.5,
                },
            )
            text.dxf.insert = (x + cs * 2, y)

            # Выноска
            msp.add_line(
                (x + cs, y),
                (x + cs * 2, y),
                dxfattribs={"layer": LAYER_FACT_MARKS, "color": color},
            )

    # ─── Фактические размеры ──────────────────────────────────────────────────

    def _draw_fact_dimensions(self, msp, dims: list[FactDimension]) -> None:
        """Наносит фактические размеры на DXF."""
        for dim in dims:
            x, y = dim.position_x, dim.position_y
            if x == 0.0 and y == 0.0:
                continue

            # Цвет по допуску
            color = 3  # OK
            if not dim.is_within_tolerance and dim.tolerance_mm > 0:
                color = 1  # CRITICAL
            elif dim.tolerance_mm > 0 and abs(dim.deviation_mm) > dim.tolerance_mm * 0.8:
                color = 2  # WARNING

            # Текст размера
            label = (
                f"{dim.label}: пр.{dim.design_value_mm:.0f} "
                f"факт.{dim.fact_value_mm:.0f}"
            )
            if dim.deviation_mm != 0:
                label += f" ({dim.deviation_mm:+.0f}мм)"

            text = msp.add_text(
                label,
                dxfattribs={
                    "layer": LAYER_FACT_DIMS,
                    "color": color,
                    "height": self.text_height * 0.5,
                },
            )
            text.dxf.insert = (x, y)

    # ─── Штамп ГОСТ 21.101-2020 ──────────────────────────────────────────────

    def _draw_gost_stamp(self, msp, stamp_data: ISStampData) -> None:
        """Рисует штамп ГОСТ 21.101-2020 через GOSTStampGenerator."""
        from src.core.services.is_generator.gost_stamp import GOSTStampGenerator

        generator = GOSTStampGenerator(
            origin_x=self.stamp_position[0],
            origin_y=self.stamp_position[1],
        )
        generator.draw(msp, stamp_data)

    # ─── Упрощённый штамп (обратная совместимость) ───────────────────────────

    def _draw_summary_stamp(self, msp, result: ISResult) -> None:
        """Упрощённый штамп — сводка результатов (для обратной совместимости)."""
        x0, y0 = self.stamp_position
        th = self.text_height
        lh = th * 2.0

        status_label = "ДОПУСТИМО" if result.is_acceptable else "КРИТИЧЕСКОЕ ОТКЛОНЕНИЕ"
        lines = [
            f"ИСПОЛНИТЕЛЬНАЯ СХЕМА - IS-{result.project_id}",
            f"АОСР: {result.aosr_id}",
            f"Всего осей: {result.total_axes}  |  Сопоставлено: {result.matched_axes}",
            (
                f"OK: {result.ok_deviations}  |  "
                f"WARNING: {result.warning_deviations}  |  "
                f"CRITICAL: {result.critical_deviations}"
            ),
            f"Статус: {status_label}",
        ]

        status_color = 3 if result.is_acceptable else 1
        text_colors = [5, 7, 7, 7, status_color]

        for i, (line, text_color) in enumerate(zip(lines, text_colors)):
            text = msp.add_text(
                line,
                dxfattribs={
                    "layer": LAYER_STAMP,
                    "color": text_color,
                    "height": th * (1.4 if i == 0 else 1.0),
                },
            )
            text.dxf.insert = (x0, y0 - i * lh)

    # ─── PDF-экспорт ──────────────────────────────────────────────────────────

    def _export_pdf(self, doc, out_dxf: Path, output_pdf: Path) -> None:
        """Экспортирует DXF → PDF через SVGExporter (векторный)."""
        try:
            from src.core.services.is_generator.svg_exporter import SVGExporter

            exporter = SVGExporter(page_size="A3")
            exporter.export_pdf(out_dxf, output_pdf)
        except ImportError:
            logger.warning("SVGExporter недоступен — fallback на matplotlib")
            self._export_pdf_matplotlib(doc, output_pdf)
        except Exception as e:
            logger.error(f"SVG-экспорт не удался: {e}. Fallback на matplotlib")
            self._export_pdf_matplotlib(doc, output_pdf)

    @staticmethod
    def _export_pdf_matplotlib(doc, output_pdf: Path) -> None:
        """Fallback: экспорт DXF → PDF через matplotlib (растровый)."""
        try:
            from ezdxf.addons.drawing import RenderContext, Frontend
            from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
            import matplotlib.pyplot as plt

            fig = plt.figure(figsize=(16.54, 11.69))
            ax = fig.add_axes([0, 0, 1, 1])
            ctx = RenderContext(doc)
            out = MatplotlibBackend(ax)
            Frontend(ctx, out).draw_layout(doc.modelspace(), finalize=True)
            fig.savefig(str(output_pdf), dpi=200, bbox_inches="tight")
            plt.close(fig)
            logger.info(f"PDF (matplotlib) сохранён: {output_pdf}")
        except ImportError:
            logger.warning("matplotlib/ezdxf.addons.drawing не установлен — PDF пропущен")
        except Exception as e:
            logger.error(f"Ошибка генерации PDF: {e}")

    # ─── Вспомогательные ──────────────────────────────────────────────────────

    @staticmethod
    def _ensure_layers(doc) -> None:
        """Создаёт аннотационные слои в документе."""
        layer_data = [
            (LAYER_ANNOTATIONS, 7),
            (LAYER_FACT_MARKS, 5),
            (LAYER_FACT_DIMS, 5),
            (LAYER_STAMP, 5),
            (LAYER_STAMP_TEXT, 7),
        ]
        for name, color in layer_data:
            if doc.layers.get(name) is None:
                doc.layers.add(name, dxfattribs={"color": color})
