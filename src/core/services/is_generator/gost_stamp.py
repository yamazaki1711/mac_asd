"""
GOSTStamp — генератор основной надписи (штампа) по ГОСТ 21.101-2020.

Создаёт табличную структуру штампа в DXF через ezdxf:
  - Верхняя часть: наименование объекта, стадия, лист, масштаб
  - Нижняя часть: разработал / проверил / т.контр / н.контр / утвердил

Размеры по ГОСТ 21.101-2020 (основная надпись для листов А4-А1):
  - Общая ширина: 185 мм
  - Верхняя часть: 55 мм высоты
  - Нижняя часть: 15 мм × 5 строк = 75 мм

v12.0
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from src.core.services.is_generator.schemas import ISStampData

try:
    import ezdxf
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False

if TYPE_CHECKING:
    from ezdxf.document import Drawing
    from ezdxf.layouts import Modelspace


# ─── Размеры штампа ГОСТ 21.101-2020 (в единицах DXF = мм) ──────────────────

STAMP_WIDTH = 185.0      # Общая ширина штампа
STAMP_TOP_HEIGHT = 55.0  # Высота верхней части
STAMP_BOTTOM_ROW_H = 15.0  # Высота одной строки нижней части
STAMP_BOTTOM_ROWS = 5     # Число строк: разраб, провер, т.контр, н.контр, утв
STAMP_TOTAL_HEIGHT = STAMP_TOP_HEIGHT + STAMP_BOTTOM_ROW_H * STAMP_BOTTOM_ROWS

# Ширина колонок нижней части
COL_ROLE_W = 15.0    # Ширина колонки "Роль" (Разраб., Провер.)
COL_NAME_W = 55.0    # Ширина колонки "ФИО"
COL_DATE_W = 20.0    # Ширина колонки "Дата"
COL_EXTRA_W = STAMP_WIDTH - COL_ROLE_W - COL_NAME_W - COL_DATE_W  # Масштаб и пр.

# Ширины колонок верхней части
TOP_OBJECT_W = 115.0  # Наименование объекта
TOP_STAGE_W = 20.0    # Стадия
TOP_SHEET_W = 25.0    # Лист / Листов
TOP_NAME_W = 135.0    # Наименование схемы
TOP_STAGE2_W = 20.0   # Стадия (повтор)
TOP_SHEET2_W = 15.0   # Лист
TOP_SHEETS_W = 15.0   # Листов

# Слои
STAMP_LAYER = "_IS_STAMP"
STAMP_TEXT_LAYER = "_IS_STAMP_TEXT"

# Толщина линий
STAMP_LINEWEIGHT = 25  # 0.25 мм


class GOSTStampGenerator:
    """
    Генерирует основную надпись (штамп) по ГОСТ 21.101-2020 в DXF-документе.

    Штамп размещается в правом нижнем углу (типичная позиция).
    Координаты — в единицах DXF (мм).

    Args:
        origin_x: X-координата левого края штампа.
        origin_y: Y-координата нижнего края штампа.
        text_height_small: Высота мелкого текста (ячейки).
        text_height_title: Высота текста наименования.
    """

    def __init__(
        self,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
        text_height_small: float = 2.5,
        text_height_title: float = 5.0,
    ) -> None:
        self.ox = origin_x
        self.oy = origin_y
        self.th_small = text_height_small
        self.th_title = text_height_title

    # ─── Публичный метод ──────────────────────────────────────────────────────

    def draw(self, msp: "Modelspace", data: ISStampData) -> None:
        """
        Рисует штамп в modelspace DXF-документа.

        Args:
            msp: ezdxf Modelspace.
            data: Данные для заполнения ячеек штампа.
        """
        if not EZDXF_AVAILABLE:
            raise ImportError("ezdxf не установлен: pip install ezdxf")

        self._draw_top_part(msp, data)
        self._draw_bottom_part(msp, data)
        self._draw_outer_frame(msp)

        logger.info(
            f"GOSTStamp: нарисован в ({self.ox}, {self.oy}), "
            f"объект='{data.object_name}', лист {data.sheet_number}/{data.total_sheets}"
        )

    def draw_in_doc(self, doc: "Drawing", data: ISStampData) -> None:
        """Удобный метод: рисует штамп в modelspace документа."""
        msp = doc.modelspace()
        self._ensure_layers(doc)
        self.draw(msp, data)

    # ─── Верхняя часть штампа ─────────────────────────────────────────────────

    def _draw_top_part(self, msp: "Modelspace", data: ISStampData) -> None:
        """
        Верхняя часть: наименование объекта + наименование схемы + стадия/лист.

        Макет (снизу вверх, origin = левый нижний угол):
        ┌────────────────────┬─────────┬──────────┬───────────┐
        │ Наим. объекта      │ Стадия  │   Лист   │  Листов   │  y = oy + top_h
        ├────────────────────┴─────────┴──────────┴───────────┤
        │ Наименование схемы (ИС)         │ Стад. │Лист│Лстов │  y = oy + 25
        └─────────────────────────────────┴───────┴────┴──────┘  y = oy
        """
        x0 = self.ox
        y0 = self.oy
        top_h = STAMP_TOP_HEIGHT

        # ── Горизонтальные линии верхней части ───────────────────────────
        # Нижняя граница
        self._hline(msp, x0, y0, STAMP_WIDTH)
        # Разделитель строк (2 строки в верхней части)
        mid_y = y0 + 25.0
        self._hline(msp, x0, mid_y, STAMP_WIDTH)
        # Верхняя граница
        self._hline(msp, x0, y0 + top_h, STAMP_WIDTH)

        # ── Вертикальные линии (нижняя строка: наим. объекта) ───────────
        # Нижняя строка: наим. объекта | стадия | лист | листов
        col2_x = x0 + TOP_OBJECT_W
        col3_x = col2_x + TOP_STAGE_W
        col4_x = col3_x + TOP_SHEET_W
        self._vline(msp, col2_x, y0, mid_y)
        self._vline(msp, col3_x, y0, mid_y)
        self._vline(msp, col4_x, y0, mid_y)

        # ── Вертикальные линии (верхняя строка: наим. схемы) ───────────
        s2_x = x0 + TOP_NAME_W
        s3_x = s2_x + TOP_STAGE2_W
        s4_x = s3_x + TOP_SHEET2_W
        self._vline(msp, s2_x, mid_y, y0 + top_h)
        self._vline(msp, s3_x, mid_y, y0 + top_h)
        self._vline(msp, s4_x, mid_y, y0 + top_h)

        # ── Текст: наименование объекта ─────────────────────────────────
        self._cell_text(
            msp, data.object_name,
            x0 + 2, y0 + 2,
            width=TOP_OBJECT_W - 4,
            height=25.0 - 4,
            text_height=self.th_title,
        )

        # ── Текст: стадия (нижняя строка) ───────────────────────────────
        self._cell_text_centered(
            msp, data.stage,
            col2_x, y0 + 2,
            width=TOP_STAGE_W,
            height=25.0 - 4,
            text_height=self.th_small,
        )

        # ── Текст: лист / листов ────────────────────────────────────────
        self._cell_text_centered(
            msp, str(data.sheet_number),
            col3_x, y0 + 2,
            width=TOP_SHEET_W,
            height=25.0 - 4,
            text_height=self.th_small,
        )
        self._cell_text_centered(
            msp, str(data.total_sheets),
            col4_x, y0 + 2,
            width=STAMP_WIDTH - col4_x + x0,
            height=25.0 - 4,
            text_height=self.th_small,
        )

        # ── Текст: наименование схемы (верхняя строка) ──────────────────
        scheme_name = data.scheme_name or "Исполнительная схема"
        if data.work_type:
            scheme_name += f" ({data.work_type})"
        self._cell_text(
            msp, scheme_name,
            x0 + 2, mid_y + 2,
            width=TOP_NAME_W - 4,
            height=top_h - 25.0 - 4,
            text_height=self.th_title,
        )

        # Стадия (верх)
        self._cell_text_centered(
            msp, data.stage,
            s2_x, mid_y + 2,
            width=TOP_STAGE2_W,
            height=top_h - 25.0 - 4,
            text_height=self.th_small,
        )
        # Лист
        self._cell_text_centered(
            msp, str(data.sheet_number),
            s3_x, mid_y + 2,
            width=TOP_SHEET2_W,
            height=top_h - 25.0 - 4,
            text_height=self.th_small,
        )
        # Листов
        self._cell_text_centered(
            msp, str(data.total_sheets),
            s4_x, mid_y + 2,
            width=STAMP_WIDTH - s4_x + x0,
            height=top_h - 25.0 - 4,
            text_height=self.th_small,
        )

    # ─── Нижняя часть штампа ──────────────────────────────────────────────────

    def _draw_bottom_part(self, msp: "Modelspace", data: ISStampData) -> None:
        """
        Нижняя часть: 5 строк с ролями и подписями.

        ┌──────────┬─────────────────────┬──────────┬───────────────┐
        │ Разраб.   │ ФИО                │ Дата     │ Масштаб       │
        ├──────────┼─────────────────────┼──────────┤               │
        │ Провер.   │ ФИО                │ Дата     │               │
        ├──────────┼─────────────────────┼──────────┤               │
        │ Т.контр.  │ ФИО                │ Дата     │               │
        ├──────────┼─────────────────────┼──────────┤               │
        │ Н.контр.  │ ФИО                │ Дата     │               │
        ├──────────┼─────────────────────┼──────────┤               │
        │ Утв.      │ ФИО                │ Дата     │               │
        └──────────┴─────────────────────┴──────────┴───────────────┘
        """
        x0 = self.ox
        y0 = self.oy + STAMP_TOP_HEIGHT  # Нижняя часть начинается после верхней

        roles = [
            ("Разраб.", data.developer, data.developer_date),
            ("Провер.", data.checker, data.checker_date),
            ("Т.контр.", data.tech_control, data.tech_control_date),
            ("Н.контр.", data.norm_control, data.norm_control_date),
            ("Утв.", data.approver, data.approver_date),
        ]

        for i, (role, name, date_str) in enumerate(roles):
            row_y = y0 + i * STAMP_BOTTOM_ROW_H

            # Горизонтальные линии строк
            self._hline(msp, x0, row_y, STAMP_WIDTH)

            # Вертикальные разделители
            col_name_x = x0 + COL_ROLE_W
            col_date_x = col_name_x + COL_NAME_W
            col_extra_x = col_date_x + COL_DATE_W

            self._vline(msp, col_name_x, row_y, row_y + STAMP_BOTTOM_ROW_H)
            self._vline(msp, col_date_x, row_y, row_y + STAMP_BOTTOM_ROW_H)

            # Объединённая ячейка "Масштаб" — вертикальная линия только в первой и последней строке
            if i == 0:
                self._vline(msp, col_extra_x, row_y, row_y + STAMP_BOTTOM_ROW_H * len(roles))

            # Текст: роль
            self._cell_text_centered(
                msp, role,
                x0, row_y + 1,
                width=COL_ROLE_W,
                height=STAMP_BOTTOM_ROW_H - 2,
                text_height=self.th_small * 0.85,
            )

            # Текст: ФИО
            self._cell_text(
                msp, name or "",
                col_name_x + 2, row_y + 1,
                width=COL_NAME_W - 4,
                height=STAMP_BOTTOM_ROW_H - 2,
                text_height=self.th_small,
            )

            # Текст: дата
            self._cell_text_centered(
                msp, date_str or "",
                col_date_x, row_y + 1,
                width=COL_DATE_W,
                height=STAMP_BOTTOM_ROW_H - 2,
                text_height=self.th_small * 0.85,
            )

        # Масштаб (в объединённой ячейке) — только в первой строке
        col_extra_x = x0 + COL_ROLE_W + COL_NAME_W + COL_DATE_W
        if data.scale:
            self._cell_text_centered(
                msp, f"М {data.scale}",
                col_extra_x, y0 + 1,
                width=STAMP_WIDTH - (COL_ROLE_W + COL_NAME_W + COL_DATE_W),
                height=STAMP_BOTTOM_ROW_H * len(roles) - 2,
                text_height=self.th_title,
            )

        # Последняя горизонтальная линия
        last_y = y0 + STAMP_BOTTOM_ROW_H * len(roles)
        self._hline(msp, x0, last_y, STAMP_WIDTH)

    # ─── Рамка штампа ─────────────────────────────────────────────────────────

    def _draw_outer_frame(self, msp: "Modelspace") -> None:
        """Рисует внешнюю рамку штампа (жирная линия)."""
        x0, y0 = self.ox, self.oy
        h = STAMP_TOTAL_HEIGHT
        w = STAMP_WIDTH

        msp.add_line(
            (x0, y0), (x0 + w, y0),
            dxfattribs={"layer": STAMP_LAYER, "lineweight": 50},
        )
        msp.add_line(
            (x0 + w, y0), (x0 + w, y0 + h),
            dxfattribs={"layer": STAMP_LAYER, "lineweight": 50},
        )
        msp.add_line(
            (x0 + w, y0 + h), (x0, y0 + h),
            dxfattribs={"layer": STAMP_LAYER, "lineweight": 50},
        )
        msp.add_line(
            (x0, y0 + h), (x0, y0),
            dxfattribs={"layer": STAMP_LAYER, "lineweight": 50},
        )

    # ─── Примитивы рисования ──────────────────────────────────────────────────

    def _hline(self, msp: "Modelspace", x: float, y: float, width: float) -> None:
        """Горизонтальная линия."""
        msp.add_line(
            (x, y), (x + width, y),
            dxfattribs={"layer": STAMP_LAYER, "lineweight": STAMP_LINEWEIGHT},
        )

    def _vline(self, msp: "Modelspace", x: float, y1: float, y2: float) -> None:
        """Вертикальная линия."""
        msp.add_line(
            (x, y1), (x, y2),
            dxfattribs={"layer": STAMP_LAYER, "lineweight": STAMP_LINEWEIGHT},
        )

    def _cell_text(
        self,
        msp: "Modelspace",
        text: str,
        x: float,
        y: float,
        width: float,
        height: float,
        text_height: float = 2.5,
    ) -> None:
        """Текст в ячейке (левый нижний угол, с переносом если не влезает)."""
        if not text:
            return
        txt = msp.add_text(
            text,
            dxfattribs={
                "layer": STAMP_TEXT_LAYER,
                "height": text_height,
                "color": 7,  # белый
            },
        )
        txt.dxf.insert = (x, y + (height - text_height) / 2)

    def _cell_text_centered(
        self,
        msp: "Modelspace",
        text: str,
        x: float,
        y: float,
        width: float,
        height: float,
        text_height: float = 2.5,
    ) -> None:
        """Центрированный текст в ячейке."""
        if not text:
            return
        # Для центрирования используем выравнивание MIDDLE_CENTER через MTEXT
        mtxt = msp.add_mtext(
            text,
            dxfattribs={
                "layer": STAMP_TEXT_LAYER,
                "char_height": text_height,
                "color": 7,
            },
        )
        # Позиция через insert + attachment point
        mtxt.dxf.insert = (x + width / 2, y + height / 2)
        mtxt.dxf.attachment_point = 5  # MIDDLE_CENTER

    # ─── Вспомогательные ──────────────────────────────────────────────────────

    @staticmethod
    def _ensure_layers(doc: "Drawing") -> None:
        """Создаёт слои штампа в документе."""
        for name in (STAMP_LAYER, STAMP_TEXT_LAYER):
            try:
                doc.layers.get(name)
            except Exception:
                try:
                    doc.layers.add(name, dxfattribs={"color": 7})
                except Exception:
                    pass
