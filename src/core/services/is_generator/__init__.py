"""
is_generator — модуль генерации Исполнительных Схем для MAC_ASD.

Публичный API:
    from src.core.services.is_generator import (
        ISGenerator,
        CompletenessGate,
        GateReport,
        GateStatus,
        DocumentationIncompleteError,
        AnchorPoint,
        CoordinateTransform,
        SurveyPoint,
        DesignAxis,
        Deviation,
        DeviationStatus,
        ISResult,
        SurveyFormat,
        GeodataParser,
        DXFParser,
        DeviationCalculator,
        DXFAnnotator,
    )
"""
from src.core.services.is_generator.schemas import (
    AnchorPoint,
    CoordinateTransform,
    DesignAxis,
    Deviation,
    DeviationStatus,
    ISResult,
    SurveyFormat,
    SurveyPoint,
)
from src.core.services.is_generator.geodata_parser import GeodataParser, detect_format
from src.core.services.is_generator.dxf_parser      import DXFParser
from src.core.services.is_generator.deviation_calculator import DeviationCalculator
from src.core.services.is_generator.dxf_annotator   import DXFAnnotator
from src.core.services.is_generator.is_generator     import ISGenerator
from src.core.services.is_generator.completeness_gate import (
    CompletenessGate,
    DocRequirement,
    DocLevel,
    GateReport,
    GateStatus,
    DocumentationIncompleteError,
)

__all__ = [
    # Главный фасад
    "ISGenerator",
    # Матрица полноты
    "CompletenessGate",
    "DocRequirement",
    "DocLevel",
    "GateReport",
    "GateStatus",
    "DocumentationIncompleteError",
    # Схемы данных
    "AnchorPoint",
    "CoordinateTransform",
    "DesignAxis",
    "Deviation",
    "DeviationStatus",
    "ISResult",
    "SurveyFormat",
    "SurveyPoint",
    # Компоненты пайплайна (для прямого использования)
    "GeodataParser",
    "detect_format",
    "DXFParser",
    "DeviationCalculator",
    "DXFAnnotator",
]
