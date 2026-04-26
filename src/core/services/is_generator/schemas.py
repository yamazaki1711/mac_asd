"""
Pydantic-схемы для модуля ISGenerator (Исполнительные Схемы).
Определяют структуры данных, проходящие через весь пайплайн генерации ИС.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pydantic import BaseModel


# ─── Перечисления ──────────────────────────────────────────────────────────────

class DeviationStatus(str, Enum):
    OK = "OK"               # Отклонение в пределах допуска
    WARNING = "WARNING"     # Отклонение близко к допуску (80–100%)
    CRITICAL = "CRITICAL"   # Отклонение превышает допуск


class SurveyFormat(str, Enum):
    CSV_STANDARD = "csv_standard"   # ID, X, Y, Z, DESC
    LEICA_GSI    = "leica_gsi"      # Формат Leica GSI-8/GSI-16
    CREDO_TXT    = "credo_txt"      # Экспорт из CREDO DAT
    XLSX         = "xlsx"           # Таблица Excel


# ─── Точка геодезии ────────────────────────────────────────────────────────────

class SurveyPoint(BaseModel):
    """Фактически измеренная точка из геодезического отчёта."""
    point_id: str
    x: float          # Северо-восток (Easting) в метрах
    y: float          # Северо-запад (Northing) в метрах
    z: float = 0.0    # Высота (Elevation) в метрах
    description: str  # Метка: "Ось А/1 факт", "Угол ростверка", и т.д.
    raw_line: Optional[str] = None   # Исходная строка для отладки


# ─── Проектная ось из DXF ──────────────────────────────────────────────────────

class DesignAxis(BaseModel):
    """Проектная ось или конструктивный элемент, извлечённый из DXF."""
    handle: str         # ezdxf entity handle (уникальный ID объекта в DXF)
    layer: str          # Слой DXF ("ОСИ", "КМ", "ШПУНТ", и т.д.)
    label: str          # Метка оси: "А", "1", "Ось Б/3"
    start_x: float      # Начало линии (в координатах DXF)
    start_y: float
    end_x: float        # Конец линии
    end_y: float
    design_x: float     # Проектная координата середины (x)
    design_y: float     # Проектная координата середины (y)
    entity_type: str    # "LINE", "LWPOLYLINE", "ARC"


# ─── Отклонение ────────────────────────────────────────────────────────────────

class Deviation(BaseModel):
    """Результат сравнения проектной оси с фактическими замерами."""
    axis_id: str            # handle из DesignAxis
    axis_label: str         # Человекочитаемая метка оси
    survey_point_id: str    # ID точки из геодезического отчёта
    match_score: float      # Уверенность совпадения меток (0.0–1.0)

    delta_x_mm: float       # Отклонение ΔX в мм (факт − проект)
    delta_y_mm: float       # Отклонение ΔY в мм (факт − проект)
    delta_z_mm: float = 0.0 # Отклонение ΔZ по высоте в мм
    distance_mm: float      # |вектор отклонения| в мм

    status: DeviationStatus
    tolerance_mm: float     # Применённый допуск


# ─── Результат генерации ИС ───────────────────────────────────────────────────

class ISResult(BaseModel):
    """Итоговый результат генерации Исполнительной Схемы."""
    project_id: str
    aosr_id: str

    output_dxf_path: str    # Путь к аннотированному DXF
    output_pdf_path: str    # Путь к финальному PDF

    total_axes: int
    matched_axes: int
    critical_deviations: int
    warning_deviations: int
    ok_deviations: int

    deviations: list[Deviation]
    unmatched_axes: list[str]        # Оси без геодезических замеров
    unmatched_survey_points: list[str]  # Замеры без осей в чертеже

    coordinate_transform_applied: bool  # Применено ли преобразование CRS

    def to_dict(self) -> dict:
        return self.model_dump()

    @property
    def is_acceptable(self) -> bool:
        """ИС можно подписывать? Нет критических отклонений."""
        return self.critical_deviations == 0


# ─── Параметры трансформации координат ────────────────────────────────────────

@dataclass
class AnchorPoint:
    """Контрольная точка для привязки DXF к геодезической системе координат."""
    dxf_x: float    # X в системе координат DXF-чертежа
    dxf_y: float    # Y в системе координат DXF-чертежа
    geo_x: float    # Реальная геодезическая координата (Easting)
    geo_y: float    # Реальная геодезическая координата (Northing)
    label: str = ""  # Опциональная метка (например, "Марка МЦ1")


@dataclass
class CoordinateTransform:
    """Матрица аффинного преобразования из DXF-координат в геодезические."""
    scale: float = 1.0
    rotation_rad: float = 0.0
    translate_x: float = 0.0
    translate_y: float = 0.0
    anchor_points: list[AnchorPoint] = field(default_factory=list)
    residual_mm: float = 0.0  # Ошибка привязки на контрольных точках

    def apply(self, dxf_x: float, dxf_y: float) -> tuple[float, float]:
        """Преобразует DXF-координаты в геодезические."""
        import math
        cos_r = math.cos(self.rotation_rad)
        sin_r = math.sin(self.rotation_rad)
        geo_x = self.scale * (dxf_x * cos_r - dxf_y * sin_r) + self.translate_x
        geo_y = self.scale * (dxf_x * sin_r + dxf_y * cos_r) + self.translate_y
        return geo_x, geo_y

    def inverse(self, geo_x: float, geo_y: float) -> tuple[float, float]:
        """Обратное преобразование: из геодезических координат в DXF."""
        import math
        # Аффинное обратное преобразование
        dx = (geo_x - self.translate_x) / self.scale
        dy = (geo_y - self.translate_y) / self.scale
        cos_r = math.cos(-self.rotation_rad)
        sin_r = math.sin(-self.rotation_rad)
        dxf_x = dx * cos_r - dy * sin_r
        dxf_y = dx * sin_r + dy * cos_r
        return dxf_x, dxf_y
