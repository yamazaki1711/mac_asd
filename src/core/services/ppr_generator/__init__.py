"""
PPR Generator v0.1 — Проект производства работ.

Публичный API модуля:
    from src.core.services.ppr_generator import PPRGenerator, PPRInput

    generator = PPRGenerator()
    result = generator.generate(ppr_input)
    # result.pdf_path → путь к PDF
    # result.docx_path → путь к DOCX
    # result.sections → список разделов ПЗ
    # result.ttks → список технологических карт
    # result.graphics → список графических листов
"""
from .ppr_generator import PPRGenerator
from .schemas import (
    PPRInput, PPRResult, PPRStats,
    OrganizationInfo, DeveloperInfo,
    ScheduleData, Stage, Constraint,
    WorkTypeItem, MaterialSpec, StructRef, QualityReq,
    TTKScope, TTKTechnology, TTKQuality, TTKResources,
    TTKOperation, TTKQualityCheck, TTKResource, TTKResult,
    SectionResult, GraphicResult,
)
from .event_bus import PPRBus, PPRStage, PPREvent

__all__ = [
    "PPRGenerator",
    "PPRInput", "PPRResult", "PPRStats",
    "OrganizationInfo", "DeveloperInfo",
    "ScheduleData", "Stage", "Constraint",
    "WorkTypeItem", "MaterialSpec", "StructRef", "QualityReq",
    "TTKScope", "TTKTechnology", "TTKQuality", "TTKResources",
    "TTKOperation", "TTKQualityCheck", "TTKResource", "TTKResult",
    "SectionResult", "GraphicResult",
    "PPRBus", "PPRStage", "PPREvent",
]
