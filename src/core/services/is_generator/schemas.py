"""
Pydantic-схемы для модуля ISGenerator (Исполнительные Схемы).
Определяют структуры данных, проходящие через весь пайплайн генерации ИС.

v12.0 — расширение: два пути генерации (DXF-First и PDF-Overlay),
фактические отметки/размеры, штамп ГОСТ 21.101-2020, индекс РД.
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


class RDFormat(str, Enum):
    """Формат исходного рабочего чертежа."""
    DWG = "dwg"       # AutoCAD DWG (конвертируется в DXF через ODA)
    DXF = "dxf"       # AutoCAD DXF (готов к обработке ezdxf)
    PDF = "pdf"        # PDF от проектировщика (растровая подложка + векторные аннотации)
    SCAN = "scan"      # Скан/фото бумажного чертежа (только VLM + ручная верификация)


class ISPipeline(str, Enum):
    """Выбор пайплайна генерации ИС."""
    DXF_FIRST = "dxf_first"       # Путь 1: векторный (DWG/DXF → clip → annotate → PDF)
    PDF_OVERLAY = "pdf_overlay"   # Путь 2: PDF-подложка + векторные аннотации


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


# ─── Фактическая отметка (из актов/АОСР) ──────────────────────────────────────

class FactMark(BaseModel):
    """Фактическая отметка для нанесения на ИС.

    Источник: акт освидетельствования, АОСР, журнал работ.
    Примеры: "Факт. отм. +3.247", "Уровень чистого пола +0.000".
    """
    label: str              # Описание: "Отм. низа балки", "Уровень пола"
    design_value: str       # Проектное значение: "+3.250"
    fact_value: str         # Фактическое значение: "+3.247"
    unit: str = "м"         # Единица измерения
    position_x: float = 0.0  # X координата на чертеже (DXF или PDF)
    position_y: float = 0.0  # Y координата на чертеже
    source: str = ""        # Источник: "АОСР-012", "Акт от 15.03.2026"
    deviation_mm: float = 0.0  # Разница факт-проект в мм


class FactDimension(BaseModel):
    """Фактический размер (линейный) для нанесения на ИС.

    Источник: замеры на захватке, геодезическая съёмка.
    Примеры: "Факт. пролёт 6010 мм", "Толщина стены 410 мм".
    """
    label: str              # Описание: "Пролёт А-Б", "Толщина стены"
    design_value_mm: float  # Проектный размер: 6000.0
    fact_value_mm: float    # Фактический размер: 6010.0
    tolerance_mm: float = 0.0  # Допуск по СП/ГОСТ
    position_x: float = 0.0  # X центра размерной линии
    position_y: float = 0.0  # Y центра размерной линии
    source: str = ""        # Источник: "Замер 12.03.2026"

    @property
    def deviation_mm(self) -> float:
        """Отклонение факт от проекта в мм."""
        return self.fact_value_mm - self.design_value_mm

    @property
    def is_within_tolerance(self) -> bool:
        """В допуске?"""
        if self.tolerance_mm <= 0:
            return True  # допуск не задан — не проверяем
        return abs(self.deviation_mm) <= self.tolerance_mm


# ─── Данные штампа ГОСТ 21.101-2020 ──────────────────────────────────────────

class ISStampData(BaseModel):
    """Данные для заполнения основной надписи (штампа) по ГОСТ 21.101-2020.

    Структура штампа:
    ┌──────────────────────────────────────────────────────────────┐
    │ Наим. объекта          │ Стадия │ Лист │ Листов              │
    ├─────────────────────────┼────────┼──────┼─────────────────────┤
    │ Наим. схемы (ИС)       │   И    │  1   │  1                  │
    ├─────────────────────────┴────────┴──────┴─────────────────────┤
    │ Разраб. │ Иванов │ 15.03 │ Масштаб │                         │
    │ Провер. │ Петров │ 16.03 │  1:100  │                         │
    │ Т.контр │        │       │         │                         │
    │ Н.контр │        │       │         │                         │
    │ Утв.    │        │       │         │                         │
    └─────────┴────────┴───────┴─────────┘─────────────────────────┘
    """
    # Верхняя часть
    object_name: str = ""         # Наименование объекта: "Жилой дом №3, корп. А"
    scheme_name: str = ""         # Наименование схемы: "Исполнительная схема фундаментов"
    stage: str = "И"              # Стадия: И = Исполнительная
    sheet_number: int = 1         # Номер листа
    total_sheets: int = 1         # Всего листов
    scale: str = ""               # Масштаб: "1:100", "1:200"

    # Нижняя часть — подписи
    developer: str = ""           # Разработал (ФИО)
    developer_date: str = ""      # Дата разработки
    checker: str = ""             # Проверил (ФИО)
    checker_date: str = ""        # Дата проверки
    tech_control: str = ""        # Т.контр.
    tech_control_date: str = ""   # Дата
    norm_control: str = ""        # Н.контр.
    norm_control_date: str = ""   # Дата
    approver: str = ""            # Утвердил (ФИО)
    approver_date: str = ""       # Дата утверждения

    # Дополнительные данные для ИС
    aosr_id: str = ""             # Номер АОСР, к которому относится ИС
    work_type: str = ""           # Вид работ: "бетонные", "монтажные"
    project_code: str = ""        # Шифр проекта
    organization: str = ""        # Организация-исполнитель


# ─── Информация о листе РД ────────────────────────────────────────────────────

class RDSheetInfo(BaseModel):
    """Один лист рабочей документации — элемент индекса РД.

    Заполняется Делопроизводителем при регистрации РД.
    Используется ПТО-агентом для поиска нужного листа под захватку.
    """
    project_code: str          # Шифр проекта: "ПГС-2024-012"
    sheet_number: str          # Номер листа: "Лист 3", "КМ-12"
    sheet_name: str            # Наименование: "План фундаментов на отм. -2.100"
    work_type: str             # Вид работ: "бетонные", "монтажные"
    section: str = ""          # Раздел/захватка: "Захватка 1", "Ось А-В"
    format: RDFormat           # Формат файла
    file_path: str             # Путь к файлу на диске
    page_number: int = 0       # Номер страницы (для PDF — страница в документе)
    bbox: Optional[list[float]] = None  # [x_min, y_min, x_max, y_max] — область захватки
    registered_at: str = ""    # Дата регистрации
    registered_by: str = ""    # Кто зарегистрировал

    class Config:
        # Разрешаем использовать RDFormat как строку
        use_enum_values = True


# ─── Результат генерации ИС ───────────────────────────────────────────────────

class ISResult(BaseModel):
    """Итоговый результат генерации Исполнительной Схемы."""
    project_id: str
    aosr_id: str

    pipeline: ISPipeline = ISPipeline.DXF_FIRST  # Какой пайплайн использовался

    output_dxf_path: str = ""    # Путь к аннотированному DXF (Путь 1)
    output_pdf_path: str = ""    # Путь к финальному PDF

    rd_sheet: Optional[RDSheetInfo] = None  # Лист РД, послуживший основой

    total_axes: int = 0
    matched_axes: int = 0
    critical_deviations: int = 0
    warning_deviations: int = 0
    ok_deviations: int = 0

    deviations: list[Deviation] = []
    fact_marks: list[FactMark] = []
    fact_dimensions: list[FactDimension] = []

    unmatched_axes: list[str] = []
    unmatched_survey_points: list[str] = []

    coordinate_transform_applied: bool = False

    stamp_data: Optional[ISStampData] = None  # Данные штампа

    output_verified: bool = False  # Пост-генерационная верификация выходных файлов

    def to_dict(self) -> dict:
        return self.model_dump()

    @property
    def is_acceptable(self) -> bool:
        """ИС можно подписывать? Нет критических отклонений и все факт. размеры в допуске."""
        has_critical_dev = self.critical_deviations > 0
        has_dim_violation = any(
            not d.is_within_tolerance for d in self.fact_dimensions
            if d.tolerance_mm > 0
        )
        return not has_critical_dev and not has_dim_violation


# ─── Bounding Box ─────────────────────────────────────────────────────────────

@dataclass
class BBox:
    """Прямоугольная область для вырезания фрагмента из РД."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    @property
    def center(self) -> tuple[float, float]:
        return (self.x_min + self.x_max) / 2, (self.y_min + self.y_max) / 2

    def contains(self, x: float, y: float, margin: float = 0.0) -> bool:
        """Точка внутри bbox (с опциональным отступом)?"""
        return (
            self.x_min - margin <= x <= self.x_max + margin
            and self.y_min - margin <= y <= self.y_max + margin
        )


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
