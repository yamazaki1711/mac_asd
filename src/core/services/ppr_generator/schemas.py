"""
PPR Generator v0.1 — Pydantic schemas.

Data models for Project of Works Production (ППР) generation.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Organization Info
# =============================================================================

class OrganizationInfo(BaseModel):
    name: str = Field(description="Наименование организации")
    inn: str = Field(default="", description="ИНН")
    address: str = Field(default="", description="Юридический адрес")
    phone: str = Field(default="")
    email: str = Field(default="")


class DeveloperInfo(BaseModel):
    organization: str = Field(description="Организация-разработчик ППР")
    chief_engineer: str = Field(default="", description="Главный инженер проекта")
    developer: str = Field(default="", description="Разработчик ППР")
    position: str = Field(default="Инженер ПТО")


# =============================================================================
# Schedule & Constraints
# =============================================================================

class Stage(BaseModel):
    name: str = Field(description="Название этапа")
    start_date: date
    end_date: date
    duration_days: int = 0

class ScheduleData(BaseModel):
    construction_start: date
    construction_end: date
    stages: List[Stage] = Field(default_factory=list, description="Этапы строительства")
    total_duration_days: int = 0


class Constraint(BaseModel):
    constraint_type: str = Field(description="Тип: охранная_зона, коммуникации, стеснённость")
    description: str
    zone_bounds: Optional[str] = None


class ResourceNeeds(BaseModel):
    workers_total: int = Field(default=0, description="Общая потребность в рабочих (из ПОС)")
    machines: List[str] = Field(default_factory=list)
    materials_summary: str = Field(default="")


# =============================================================================
# Work Types & Materials
# =============================================================================

class WorkTypeItem(BaseModel):
    code: str = Field(description="Код вида работ (из WorkTypeRegistry)")
    name: str = Field(description="Наименование вида работ")
    volume: str = Field(default="", description="Объём (например, '245 м³')")
    quantity: float = Field(default=0.0)
    unit: str = Field(default="")
    section: str = Field(default="", description="Раздел ПД/РД")


class MaterialSpec(BaseModel):
    name: str = Field(description="Наименование материала")
    code: str = Field(default="")
    quantity: float = 0.0
    unit: str = ""
    gost: str = Field(default="", description="ГОСТ/ТУ")
    supplier: str = Field(default="")


class StructRef(BaseModel):
    drawing_code: str = Field(description="Шифр чертежа")
    description: str = Field(default="")
    format_size: str = Field(default="А1")


class QualityReq(BaseModel):
    parameter: str = Field(description="Контролируемый параметр")
    tolerance: str = Field(default="", description="Допуск")
    control_method: str = Field(default="", description="Метод контроля")
    gost_ref: str = Field(default="")


# =============================================================================
# PPR Input
# =============================================================================

class PPRInput(BaseModel):
    """Входные данные для генерации ППР."""
    # Реквизиты
    object_name: str = Field(description="Наименование объекта")
    project_code: str = Field(description="Шифр проекта (например, '2023/02-05')")
    customer: OrganizationInfo
    contractor: OrganizationInfo
    developer: DeveloperInfo

    # Данные из ПОС
    construction_schedule: ScheduleData
    site_constraints: List[Constraint] = Field(default_factory=list)
    pos_resource_needs: ResourceNeeds = Field(default_factory=ResourceNeeds)

    # Данные из ПД/РД
    work_types: List[WorkTypeItem] = Field(description="Виды работ с объёмами")
    material_specs: List[MaterialSpec] = Field(default_factory=list)
    structural_solutions: List[StructRef] = Field(default_factory=list)
    quality_requirements: List[QualityReq] = Field(default_factory=list)

    # Параметры генерации
    include_graphics: bool = Field(default=True, description="Генерировать графическую часть")
    output_format: Literal["pdf", "docx", "both"] = "both"


# =============================================================================
# TTK Types
# =============================================================================

class TTKScope(BaseModel):
    """Область применения ТТК."""
    work_type: str
    description: str = Field(description="Где и когда применяется")
    applicable_objects: List[str] = Field(default_factory=list)
    climate_zone: str = Field(default="")
    work_conditions: str = Field(default="")


class TTKOperation(BaseModel):
    """Одна технологическая операция."""
    seq_number: int
    name: str
    description: str
    equipment: List[str] = Field(default_factory=list)
    workers: List[str] = Field(default_factory=list)
    duration_hours: float = 0.0
    quality_checkpoint: bool = False


class TTKTechnology(BaseModel):
    """Технология выполнения работ."""
    preparatory_work: List[str] = Field(default_factory=list)
    main_operations: List[TTKOperation] = Field(default_factory=list)
    final_operations: List[str] = Field(default_factory=list)
    process_diagram: str = Field(default="", description="Ссылка на технологическую схему")


class TTKQualityCheck(BaseModel):
    """Одна проверка качества."""
    parameter: str
    tolerance: str
    method: str
    instrument: str = ""
    frequency: str = Field(default="", description="Периодичность контроля")
    gost_ref: str = ""


class TTKQuality(BaseModel):
    """Требования к качеству."""
    incoming_control: List[str] = Field(default_factory=list)
    operational_control: List[TTKQualityCheck] = Field(default_factory=list)
    acceptance_control: List[str] = Field(default_factory=list)
    hidden_works_certification: List[str] = Field(default_factory=list, description="Оформление скрытых работ")


class TTKResource(BaseModel):
    """Один ресурс (рабочий, машина, материал)."""
    name: str
    quantity: float
    unit: str
    category: Literal["worker", "machine", "material", "tool"] = "material"


class TTKResources(BaseModel):
    """Потребность в ресурсах."""
    workers: List[TTKResource] = Field(default_factory=list)
    machines: List[TTKResource] = Field(default_factory=list)
    materials: List[TTKResource] = Field(default_factory=list)
    tools: List[TTKResource] = Field(default_factory=list)


class TTKResult(BaseModel):
    """Результат генерации одной ТТК."""
    work_type: str
    scope: TTKScope
    technology: TTKTechnology
    quality: TTKQuality
    resources: TTKResources
    total_labor_intensity_person_hours: float = 0.0
    total_machine_hours: float = 0.0


# =============================================================================
# Section Results
# =============================================================================

class SectionResult(BaseModel):
    """Результат генерации одного раздела ПЗ."""
    section_id: str
    title: str
    content: str = Field(description="Текстовое содержание раздела (markdown/html)")
    page_count: int = 0
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Graphics Results
# =============================================================================

class GraphicResult(BaseModel):
    graphic_id: str
    title: str
    format_size: str = "А1"
    svg_path: Optional[str] = None
    dxf_path: Optional[str] = None
    page_count: int = 1


# =============================================================================
# PPR Generation Stats
# =============================================================================

class PPRStats(BaseModel):
    sections_generated: int = 0
    ttks_generated: int = 0
    graphics_generated: int = 0
    total_pages: int = 0
    generation_time_seconds: float = 0.0
    warnings: List[str] = Field(default_factory=list)


# =============================================================================
# PPR Result
# =============================================================================

class PPRResult(BaseModel):
    """Результат генерации полного комплекта ППР."""
    project_code: str
    sections: List[SectionResult] = Field(default_factory=list)
    ttks: List[TTKResult] = Field(default_factory=list)
    graphics: List[GraphicResult] = Field(default_factory=list)
    pdf_path: Optional[str] = None
    docx_path: Optional[str] = None
    stats: PPRStats = Field(default_factory=PPRStats)
