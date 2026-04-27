"""
is_generator — модуль генерации Исполнительных Схем для MAC_ASD v12.0.

Два равноправных пайплайна:
  Путь 1 (DXF-First): DWG/DXF → clip → annotate → векторный PDF
  Путь 2 (PDF-Overlay): PDF → PNG-подложка + векторные аннотации → PDF

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
        ISStampData,
        FactMark,
        FactDimension,
        RDSheetInfo,
        RDFormat,
        ISPipeline,
        BBox,
        SurveyFormat,
        GeodataParser,
        DXFParser,
        DeviationCalculator,
        DXFAnnotator,
        SVGExporter,
        GOSTStampGenerator,
        PDFOverlayBuilder,
        RDIndex,
    )
"""
from src.core.services.is_generator.schemas import (
    AnchorPoint,
    BBox,
    CoordinateTransform,
    DesignAxis,
    Deviation,
    DeviationStatus,
    FactDimension,
    FactMark,
    ISPipeline,
    ISResult,
    ISStampData,
    RDFormat,
    RDSheetInfo,
    SurveyFormat,
    SurveyPoint,
)
from src.core.services.is_generator.geodata_parser import GeodataParser, detect_format
from src.core.services.is_generator.dxf_parser      import DXFParser
from src.core.services.is_generator.deviation_calculator import DeviationCalculator
from src.core.services.is_generator.dxf_annotator   import DXFAnnotator
from src.core.services.is_generator.is_generator     import ISGenerator
from src.core.services.is_generator.svg_exporter     import SVGExporter
from src.core.services.is_generator.gost_stamp       import GOSTStampGenerator
from src.core.services.is_generator.pdf_overlay_builder import PDFOverlayBuilder
from src.core.services.is_generator.rd_index         import RDIndex
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
    "BBox",
    "CoordinateTransform",
    "DesignAxis",
    "Deviation",
    "DeviationStatus",
    "FactDimension",
    "FactMark",
    "ISPipeline",
    "ISResult",
    "ISStampData",
    "RDFormat",
    "RDSheetInfo",
    "SurveyFormat",
    "SurveyPoint",
    # Компоненты пайплайна
    "GeodataParser",
    "detect_format",
    "DXFParser",
    "DeviationCalculator",
    "DXFAnnotator",
    "SVGExporter",
    "GOSTStampGenerator",
    "PDFOverlayBuilder",
    "RDIndex",
]
