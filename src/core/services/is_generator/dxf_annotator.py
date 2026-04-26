"""
Аннотатор DXF для модуля ISGenerator.

Наносит на копию проектного чертежа:
  - Стрелки от проектной точки к фактической
  - Текстовые подписи: Delta=XX мм / Статус
  - Цветовую заливку по статусу: OK=зелёный, WARNING=жёлтый, CRITICAL=красный
  - Сводный штамп (таблица итогов) в угол листа
"""
from __future__ import annotations

import logging
import math
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

from src.core.services.is_generator.schemas import (
    Deviation,
    DeviationStatus,
    ISResult,
    CoordinateTransform,
)

try:
    import ezdxf
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False


# --- Цветовая палитра (ACI-коды AutoCAD) ------------------------------------
# ACI 3 = Зелёный, ACI 2 = Жёлтый, ACI 1 = Красный

STATUS_COLOR: dict[DeviationStatus, int] = {
    DeviationStatus.OK:       3,    # green
    DeviationStatus.WARNING:  2,    # yellow
    DeviationStatus.CRITICAL: 1,    # red
}

ANNOTATION_LAYER = "_IS_ANNOTATIONS"
STAMP_LAYER      = "_IS_STAMP"


# --- Основной аннотатор ------------------------------------------------------

class DXFAnnotator:
    """
    Открывает DXF-шаблон, вносит аннотации по отклонениям,
    сохраняет аннотированный DXF и генерирует PDF (через matplotlib/ezdxf).

    Args:
        arrow_scale: Масштаб стрелки относительно единиц чертежа.
        text_height: Высота текста аннотации (в единицах чертежа).
        stamp_position: (x, y) — позиция сводного штампа в модельном пространстве.
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

    # -------------------------------------------------------------------------

    def annotate_with_positions(
        self,
        template_dxf_path: str | Path,
        deviations: list[Deviation],
        result: ISResult,
        axis_geo_positions: dict[str, tuple[float, float]],   # axis_id -> (geo_x, geo_y)
        survey_positions: dict[str, tuple[float, float]],      # point_id -> (x, y)
        transform: CoordinateTransform | None,
        output_dxf_path: str | Path,
        output_pdf_path: str | Path,
    ) -> None:
        """
        Полный цикл аннотирования с явными координатами точек.

        Это основной публичный метод, вызываемый из ISGenerator.
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

        for dev in deviations:
            color = STATUS_COLOR[dev.status]

            # Проектная позиция (в координатах DXF)
            if dev.axis_id not in axis_geo_positions:
                continue   # нет позиции — пропускаем

            gx, gy = axis_geo_positions[dev.axis_id]
            if transform:
                design_dxf_x, design_dxf_y = transform.inverse(gx, gy)
            else:
                design_dxf_x, design_dxf_y = gx, gy

            # Фактическая позиция -> DXF
            if dev.survey_point_id in survey_positions:
                sx, sy = survey_positions[dev.survey_point_id]
                if transform:
                    fact_dxf_x, fact_dxf_y = transform.inverse(sx, sy)
                else:
                    fact_dxf_x, fact_dxf_y = sx, sy
            else:
                fact_dxf_x, fact_dxf_y = design_dxf_x, design_dxf_y

            # --- Крест в проектной точке ------------------------------------
            cs = self.arrow_scale * 0.5
            msp.add_line(
                (design_dxf_x - cs, design_dxf_y),
                (design_dxf_x + cs, design_dxf_y),
                dxfattribs={"layer": ANNOTATION_LAYER, "color": 8},   # grey
            )
            msp.add_line(
                (design_dxf_x, design_dxf_y - cs),
                (design_dxf_x, design_dxf_y + cs),
                dxfattribs={"layer": ANNOTATION_LAYER, "color": 8},
            )

            # --- Точка факт -------------------------------------------------
            msp.add_circle(
                center=(fact_dxf_x, fact_dxf_y),
                radius=self.arrow_scale * 0.3,
                dxfattribs={"layer": ANNOTATION_LAYER, "color": color},
            )

            # --- Стрелка проект -> факт ------------------------------------
            dist = math.hypot(fact_dxf_x - design_dxf_x, fact_dxf_y - design_dxf_y)
            if dist > self.arrow_scale * 0.1:
                msp.add_line(
                    (design_dxf_x, design_dxf_y),
                    (fact_dxf_x, fact_dxf_y),
                    dxfattribs={"layer": ANNOTATION_LAYER, "color": color, "lineweight": 35},
                )

            # --- Текстовая подпись -----------------------------------------
            sign_x = (design_dxf_x + fact_dxf_x) / 2 + self.text_height * 0.5
            sign_y = (design_dxf_y + fact_dxf_y) / 2 + self.text_height * 0.5

            label_text = (
                f"D={dev.distance_mm:.1f}mm  {dev.status.value}  [{dev.axis_label}]"
            )
            # ezdxf >= 1.x: insert устанавливается через dxf namespace
            text = msp.add_text(
                label_text,
                dxfattribs={
                    "layer":  ANNOTATION_LAYER,
                    "color":  color,
                    "height": self.text_height,
                },
            )
            text.dxf.insert = (sign_x, sign_y)

        # Сводный штамп
        self._draw_stamp(msp, result)

        doc.saveas(str(out_dxf))
        logger.info(f"Аннотированный DXF сохранён: {out_dxf}")

        self._export_pdf(doc, out_pdf)

    # --- Вспомогательные методы -----------------------------------------------

    def _ensure_layers(self, doc) -> None:
        """Создаёт аннотационные слои в документе (idempotent)."""
        layer_table = doc.layers
        for name, color in ((ANNOTATION_LAYER, 7), (STAMP_LAYER, 5)):
            if layer_table.get(name) is None:
                layer_table.add(name, dxfattribs={"color": color})

    def _draw_stamp(self, msp, result: ISResult) -> None:
        """Рисует сводную таблицу-штамп в нижнем левом углу чертежа."""
        x0, y0 = self.stamp_position
        th = self.text_height
        lh = th * 2.0   # межстрочный интервал

        status_label = "ДОПУСТИМО" if result.is_acceptable else "КРИТИЧЕСКОЕ ОТКЛОНЕНИЕ"
        lines = [
            f"ИСПОЛНИТЕЛЬНАЯ СХЕМА  -  IS-{result.project_id}",
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
        text_colors  = [5, 7, 7, 7, status_color]   # title=blue, rows=white, status=colored

        for i, (line, text_color) in enumerate(zip(lines, text_colors)):
            text = msp.add_text(
                line,
                dxfattribs={
                    "layer":  STAMP_LAYER,
                    "color":  text_color,
                    "height": th * (1.4 if i == 0 else 1.0),
                },
            )
            text.dxf.insert = (x0, y0 - i * lh)

    def _export_pdf(self, doc, output_pdf: Path) -> None:
        """Экспортирует DXF -> PDF через ezdxf matplotlib backend."""
        try:
            from ezdxf.addons.drawing import RenderContext, Frontend
            from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
            import matplotlib.pyplot as plt

            fig = plt.figure(figsize=(16.54, 11.69))   # A3 landscape
            ax  = fig.add_axes([0, 0, 1, 1])
            ctx = RenderContext(doc)
            out = MatplotlibBackend(ax)
            Frontend(ctx, out).draw_layout(doc.modelspace(), finalize=True)
            fig.savefig(str(output_pdf), dpi=200, bbox_inches="tight")
            plt.close(fig)
            logger.info(f"PDF сохранён: {output_pdf}")

        except ImportError:
            logger.warning("matplotlib/ezdxf.addons.drawing не установлен — PDF пропущен")
        except Exception as e:
            logger.error(f"Ошибка генерации PDF: {e}")
