"""
PDFOverlayBuilder — Путь 2 генерации ИС: PDF-подложка + векторные аннотации.

Сценарий: проектировщик дал только PDF (конфликт, нет исходников).
  1. PDF-crop: обрезаем страницу по области захватки (PyMuPDF)
  2. Экспорт crop в PNG (300 dpi) — растровая подложка
  3. Создаём новый DXF, вставляем подложку как IMAGE entity
  4. Наносим векторные аннотации (факт. отметки, размеры, штамп)
  5. Экспорт: DXF → SVG → PDF (подложка растровая, аннотации векторные)

Результат: чертёж-подложка (из PDF проектировщика) + чёткие векторные
выноски, отметки, штамп. Стройконтроль принимает.

v12.0
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from src.core.services.is_generator.schemas import (
    BBox,
    Deviation,
    FactDimension,
    FactMark,
    ISStampData,
)

try:
    import ezdxf
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False


# ─── Слои аннотаций ──────────────────────────────────────────────────────────

LAYER_BACKGROUND = "_IS_BACKGROUND"
LAYER_FACT_MARKS = "_IS_FACT_MARKS"
LAYER_FACT_DIMS  = "_IS_FACT_DIMS"
LAYER_DEVIATIONS = "_IS_DEVIATIONS"
LAYER_STAMP      = "_IS_STAMP"


class PDFOverlayBuilder:
    """
    Генерирует ИС поверх PDF-подложки от проектировщика.

    Args:
        dpi: Разрешение подложки (PNG из PDF).
        text_height: Высота текста аннотаций (в единицах DXF = мм).
        arrow_scale: Масштаб стрелок отклонений.
    """

    def __init__(
        self,
        dpi: int = 300,
        text_height: float = 100.0,
        arrow_scale: float = 50.0,
    ) -> None:
        self.dpi = dpi
        self.text_height = text_height
        self.arrow_scale = arrow_scale

    # ─── Публичный метод ──────────────────────────────────────────────────────

    def build(
        self,
        pdf_path: str | Path,
        output_dxf_path: str | Path,
        page_number: int = 0,
        crop_bbox: Optional[BBox] = None,
        fact_marks: Optional[list[FactMark]] = None,
        fact_dimensions: Optional[list[FactDimension]] = None,
        deviations: Optional[list[Deviation]] = None,
        stamp_data: Optional[ISStampData] = None,
    ) -> Path:
        """
        Полный цикл: PDF → PNG подложка → DXF с аннотациями.

        Args:
            pdf_path: Исходный PDF от проектировщика.
            output_dxf_path: Путь к выходному DXF (с подложкой + аннотациями).
            page_number: Номер страницы PDF (0-based).
            crop_bbox: Область обрезки (в координатах PDF-точках).
                       None = вся страница.
            fact_marks: Фактические отметки для нанесения.
            fact_dimensions: Фактические размеры для нанесения.
            deviations: Отклонения (если есть геодезия).
            stamp_data: Данные штампа ГОСТ 21.101-2020.

        Returns:
            Путь к созданному DXF.
        """
        if not FITZ_AVAILABLE:
            raise ImportError("PyMuPDF не установлен: pip install pymupdf")
        if not EZDXF_AVAILABLE:
            raise ImportError("ezdxf не установлен: pip install ezdxf")

        pdf_path = Path(pdf_path)
        out_dxf = Path(output_dxf_path)
        out_dxf.parent.mkdir(parents=True, exist_ok=True)

        # Шаг 1: Извлекаем PNG-подложку из PDF
        bg_png, bg_width_mm, bg_height_mm = self._pdf_to_png(
            pdf_path, page_number, crop_bbox
        )

        # Шаг 2: Создаём DXF с подложкой
        doc = ezdxf.new(dxfversion="R2013")
        msp = doc.modelspace()
        self._ensure_layers(doc)

        # Вставляем подложку как IMAGE
        self._insert_background(msp, bg_png, bg_width_mm, bg_height_mm)

        # Шаг 3: Наносим аннотации
        if fact_marks:
            self._draw_fact_marks(msp, fact_marks)

        if fact_dimensions:
            self._draw_fact_dimensions(msp, fact_dimensions)

        if deviations:
            self._draw_deviations(msp, deviations)

        if stamp_data:
            self._draw_stamp(msp, stamp_data, bg_width_mm, bg_height_mm)

        # Шаг 4: Сохраняем DXF
        doc.saveas(str(out_dxf))
        logger.info(
            f"PDFOverlayBuilder: {pdf_path.name} → {out_dxf.name} "
            f"(подложка {bg_width_mm:.0f}x{bg_height_mm:.0f} мм)"
        )
        return out_dxf

    # ─── PDF → PNG ────────────────────────────────────────────────────────────

    def _pdf_to_png(
        self,
        pdf_path: Path,
        page_number: int,
        crop_bbox: Optional[BBox],
    ) -> tuple[Path, float, float]:
        """
        Конвертирует страницу PDF в PNG.

        Returns:
            (png_path, width_mm, height_mm)
        """
        doc = fitz.open(str(pdf_path))
        page = doc[page_number]

        if crop_bbox:
            # PyMuPDF использует (x0, y0, x1, y1) в пунктах (1/72 дюйма)
            rect = fitz.Rect(
                crop_bbox.x_min, crop_bbox.y_min,
                crop_bbox.x_max, crop_bbox.y_max,
            )
            page.set_cropbox(rect)

        # Рендерим в PNG
        mat = fitz.Matrix(self.dpi / 72.0, self.dpi / 72.0)
        pix = page.get_pixmap(matrix=mat)

        png_path = pdf_path.with_suffix(f".page{page_number}.png")
        pix.save(str(png_path))

        # Размеры в мм
        page_rect = page.rect
        width_mm = page_rect.width * 25.4 / 72.0
        height_mm = page_rect.height * 25.4 / 72.0

        doc.close()
        logger.info(f"PDF → PNG: {png_path.name} ({width_mm:.0f}x{height_mm:.0f} мм)")
        return png_path, width_mm, height_mm

    # ─── Вставка подложки в DXF ───────────────────────────────────────────────

    def _insert_background(
        self,
        msp,
        png_path: Path,
        width_mm: float,
        height_mm: float,
    ) -> None:
        """Вставляет PNG как IMAGE entity в DXF."""
        try:
            # ezdxf поддерживает вставку изображений
            from ezdxf.addons import RasterInstaller
            # Простая вставка: изображение привязывается к (0,0)
            # с размерами width_mm × height_mm
            msp.add_image(
                image_path=str(png_path),
                size=(width_mm, height_mm),
                insert=(0, 0),
                dxfattribs={"layer": LAYER_BACKGROUND},
            )
        except (ImportError, AttributeError):
            # Fallback: если add_image недоступен, добавляем прямоугольник-рамку
            logger.warning(
                "ezdxf.add_image недоступен — подложка не вставлена. "
                "Аннотации будут на пустом листе."
            )
            msp.add_line((0, 0), (width_mm, 0), dxfattribs={"layer": LAYER_BACKGROUND})
            msp.add_line((width_mm, 0), (width_mm, height_mm), dxfattribs={"layer": LAYER_BACKGROUND})
            msp.add_line((width_mm, height_mm), (0, height_mm), dxfattribs={"layer": LAYER_BACKGROUND})
            msp.add_line((0, height_mm), (0, 0), dxfattribs={"layer": LAYER_BACKGROUND})

    # ─── Фактические отметки ──────────────────────────────────────────────────

    def _draw_fact_marks(self, msp, marks: list[FactMark]) -> None:
        """Наносит фактические отметки на DXF."""
        for mark in marks:
            x, y = mark.position_x, mark.position_y

            # Маркер (крестик)
            cs = self.arrow_scale * 0.3
            msp.add_line((x - cs, y), (x + cs, y), dxfattribs={"layer": LAYER_FACT_MARKS, "color": 5})
            msp.add_line((x, y - cs), (x, y + cs), dxfattribs={"layer": LAYER_FACT_MARKS, "color": 5})

            # Текст: "Отм. низа балки: пр.+3.250 / факт.+3.247"
            label = f"{mark.label}: пр.{mark.design_value} / факт.{mark.fact_value}"
            if mark.deviation_mm != 0:
                sign = "+" if mark.deviation_mm > 0 else ""
                label += f" ({sign}{mark.deviation_mm:.0f}мм)"

            # Цвет по отклонению
            color = 3  # зелёный — OK
            if abs(mark.deviation_mm) > 10:
                color = 1  # красный — CRITICAL
            elif abs(mark.deviation_mm) > 5:
                color = 2  # жёлтый — WARNING

            text = msp.add_text(
                label,
                dxfattribs={
                    "layer": LAYER_FACT_MARKS,
                    "color": color,
                    "height": self.text_height * 0.6,
                },
            )
            text.dxf.insert = (x + cs * 2, y + self.text_height * 0.3)

            # Выноска (линия от крестика к тексту)
            msp.add_line(
                (x + cs, y),
                (x + cs * 2, y + self.text_height * 0.15),
                dxfattribs={"layer": LAYER_FACT_MARKS, "color": color},
            )

    # ─── Фактические размеры ──────────────────────────────────────────────────

    def _draw_fact_dimensions(self, msp, dims: list[FactDimension]) -> None:
        """Наносит фактические размеры (линейные) на DXF."""
        for dim in dims:
            x, y = dim.position_x, dim.position_y

            # Цвет по допуску
            color = 3  # OK
            if not dim.is_within_tolerance and dim.tolerance_mm > 0:
                color = 1  # CRITICAL
            elif dim.tolerance_mm > 0 and abs(dim.deviation_mm) > dim.tolerance_mm * 0.8:
                color = 2  # WARNING

            # Текст: "6000/6010 (+10)"
            design_str = f"{dim.design_value_mm:.0f}"
            fact_str = f"{dim.fact_value_mm:.0f}"
            dev_str = f"{dim.deviation_mm:+.0f}" if dim.deviation_mm != 0 else ""
            label = f"{dim.label}: пр.{design_str} / факт.{fact_str}"
            if dev_str:
                label += f" ({dev_str}мм)"

            text = msp.add_text(
                label,
                dxfattribs={
                    "layer": LAYER_FACT_DIMS,
                    "color": color,
                    "height": self.text_height * 0.6,
                },
            )
            text.dxf.insert = (x, y + self.text_height * 0.3)

    # ─── Отклонения ────────────────────────────────────────────────────────────

    def _draw_deviations(self, msp, deviations: list[Deviation]) -> None:
        """Наносит аннотации отклонений (из geodata) на DXF.

        В PDF-пути координаты position_x/y берутся из FactMark,
        которые должны быть заданы вручную или через VLM.
        Если у Deviation нет привязанных FactMark с координатами,
        отклонения размещаются вертикальным списком в левой части листа.
        """
        if not deviations:
            return

        color_map = {"OK": 3, "WARNING": 2, "CRITICAL": 1}

        # Группируем по статусу для визуальной ясности
        y_offset = 0.0
        th = self.text_height * 0.5

        for i, dev in enumerate(deviations):
            color = color_map.get(dev.status.value, 7)

            # Текстовая аннотация с отклонением
            label = (
                f"[{dev.axis_label}] D={dev.distance_mm:.1f}мм "
                f"({dev.delta_x_mm:+.1f}, {dev.delta_y_mm:+.1f}) {dev.status.value}"
            )

            # Если у отклонения есть survey_point_id, пытаемся привязать
            # через координаты FactMark (если переданы)
            # Иначе — размещаем вертикальным списком в левой части
            text_x = 10.0
            text_y = y_offset

            txt = msp.add_text(
                label,
                dxfattribs={
                    "layer": LAYER_DEVIATIONS,
                    "color": color,
                    "height": th,
                },
            )
            txt.dxf.insert = (text_x, text_y)

            # Маркер слева от текста (квадратик)
            cs = th * 0.4
            marker_color = color
            msp.add_line(
                (text_x - cs * 2, text_y), (text_x - cs * 2 + cs, text_y),
                dxfattribs={"layer": LAYER_DEVIATIONS, "color": marker_color},
            )
            msp.add_line(
                (text_x - cs * 2, text_y - cs * 0.5),
                (text_x - cs * 2, text_y + cs * 0.5),
                dxfattribs={"layer": LAYER_DEVIATIONS, "color": marker_color},
            )

            y_offset -= th * 2.0

    # ─── Штамп ────────────────────────────────────────────────────────────────

    def _draw_stamp(
        self,
        msp,
        stamp_data: ISStampData,
        page_width_mm: float,
        page_height_mm: float,
    ) -> None:
        """Размещает штамп ГОСТ 21.101-2020 в правом нижнем углу."""
        from src.core.services.shared.gost_stamp import GOSTStampGenerator

        # Позиция: правый нижний угол (штамп 185мм шириной, ~130мм высотой)
        stamp_x = page_width_mm - 195.0  # 185 мм + 10 мм отступ
        stamp_y = 10.0  # 10 мм от нижнего края

        generator = GOSTStampGenerator(
            origin_x=stamp_x,
            origin_y=stamp_y,
        )
        generator.draw(msp, stamp_data)

    # ─── Вспомогательные ──────────────────────────────────────────────────────

    @staticmethod
    def _ensure_layers(doc) -> None:
        """Создаёт слои в документе."""
        layers_data = [
            (LAYER_BACKGROUND, 8),   # серый
            (LAYER_FACT_MARKS, 5),   # синий
            (LAYER_FACT_DIMS, 5),    # синий
            (LAYER_DEVIATIONS, 7),   # белый
            (LAYER_STAMP, 7),        # белый
        ]
        for name, color in layers_data:
            try:
                doc.layers.get(name)
            except Exception:
                try:
                    doc.layers.add(name, dxfattribs={"color": color})
                except Exception:
                    pass
