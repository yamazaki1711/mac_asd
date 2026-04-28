"""
api — FastAPI endpoints для модуля ISGenerator.

Предоставляет REST API для вызова генерации ИС из других модулей
(ПТО-агент, Делопроизводитель) и для мониторинга процесса.

Эндпоинты:
  POST /is/generate         — запуск генерации одной ИС
  POST /is/batch            — запуск batch-генерации комплекта
  GET  /is/result/{run_id}  — результат генерации
  GET  /is/events           — event stream (для n8n/dashboard)
  GET  /is/tolerances       — справочник допусков СП 126
  GET  /is/health           — проверка доступности модуля

v12.0
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from src.core.services.is_generator.schemas import (
    FactDimension,
    FactMark,
    ISPipeline,
    ISResult,
    ISStampData,
    RDFormat,
    RDSheetInfo,
    SurveyFormat,
)
from src.core.services.is_generator.is_generator import ISGenerator
from src.core.services.is_generator.batch_generator import (
    ISBatchGenerator,
    ISBatchResult,
    ISBatchTask,
)
from src.core.services.is_generator.events import (
    EventType,
    ISEventEmitter,
    get_event_emitter,
)
from src.core.services.is_generator.tolerance_profiles import list_profiles, build_tolerance_map
from src.core.services.is_generator.completeness_gate import (
    CompletenessGate,
    GateStatus,
)

# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/is", tags=["IS Generator"])


# ─── Request/Response Models ──────────────────────────────────────────────────

class RDSheetRequest(BaseModel):
    """Лист РД в запросе."""
    project_code: str
    sheet_number: str
    sheet_name: str
    work_type: str
    format: str = "dxf"  # dxf, dwg, pdf, scan
    file_path: str
    page_number: int = 0
    bbox: Optional[list[float]] = None
    section: str = ""


class FactMarkRequest(BaseModel):
    """Фактическая отметка в запросе."""
    label: str
    design_value: str
    fact_value: str
    unit: str = "м"
    position_x: float = 0.0
    position_y: float = 0.0
    source: str = ""
    deviation_mm: float = 0.0


class FactDimensionRequest(BaseModel):
    """Фактический размер в запросе."""
    label: str
    design_value_mm: float
    fact_value_mm: float
    tolerance_mm: float = 0.0
    position_x: float = 0.0
    position_y: float = 0.0
    source: str = ""


class StampDataRequest(BaseModel):
    """Данные штампа в запросе."""
    object_name: str = ""
    scheme_name: str = ""
    stage: str = "И"
    sheet_number: int = 1
    total_sheets: int = 1
    scale: str = ""
    developer: str = ""
    developer_date: str = ""
    checker: str = ""
    checker_date: str = ""
    tech_control: str = ""
    tech_control_date: str = ""
    norm_control: str = ""
    norm_control_date: str = ""
    approver: str = ""
    approver_date: str = ""
    aosr_id: str = ""
    work_type: str = ""
    project_code: str = ""
    organization: str = ""


class GenerateRequest(BaseModel):
    """Запрос на генерацию одной ИС."""
    project_id: str
    aosr_id: str
    output_dir: str = "/tmp/is_output"
    rd_sheet: Optional[RDSheetRequest] = None
    design_dxf: Optional[str] = None
    survey_file: Optional[str] = None
    survey_format: Optional[str] = None
    fact_marks: list[FactMarkRequest] = Field(default_factory=list)
    fact_dimensions: list[FactDimensionRequest] = Field(default_factory=list)
    stamp_data: Optional[StampDataRequest] = None
    run_id: Optional[str] = None


class BatchTaskRequest(BaseModel):
    """Одна задача batch-генерации."""
    aosr_id: str
    rd_sheet: Optional[RDSheetRequest] = None
    design_dxf: Optional[str] = None
    survey_file: Optional[str] = None
    survey_format: Optional[str] = None
    fact_marks: list[FactMarkRequest] = Field(default_factory=list)
    fact_dimensions: list[FactDimensionRequest] = Field(default_factory=list)
    stamp_data: Optional[StampDataRequest] = None


class BatchGenerateRequest(BaseModel):
    """Запрос на batch-генерацию комплекта ИС."""
    project_id: str
    output_dir: str = "/tmp/is_output"
    tasks: list[BatchTaskRequest]
    max_workers: int = 1
    batch_id: Optional[str] = None


class GenerateResponse(BaseModel):
    """Ответ генерации ИС."""
    success: bool
    project_id: str
    aosr_id: str
    pipeline: str = ""
    is_acceptable: bool = False
    output_verified: bool = False
    output_dxf_path: str = ""
    output_pdf_path: str = ""
    total_axes: int = 0
    matched_axes: int = 0
    ok_deviations: int = 0
    warning_deviations: int = 0
    critical_deviations: int = 0
    run_id: str = ""
    error: str = ""


class BatchGenerateResponse(BaseModel):
    """Ответ batch-генерации."""
    success: bool
    batch_id: str
    project_id: str
    total_tasks: int = 0
    completed: int = 0
    failed: int = 0
    success_rate: float = 0.0
    all_acceptable: bool = False
    total_ok: int = 0
    total_warning: int = 0
    total_critical: int = 0
    duration_sec: float = 0.0
    errors: list[dict] = Field(default_factory=list)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _rd_sheet_from_request(req: RDSheetRequest) -> RDSheetInfo:
    """Конвертирует request model в RDSheetInfo."""
    return RDSheetInfo(
        project_code=req.project_code,
        sheet_number=req.sheet_number,
        sheet_name=req.sheet_name,
        work_type=req.work_type,
        format=req.format,
        file_path=req.file_path,
        page_number=req.page_number,
        bbox=req.bbox,
        section=req.section,
    )


def _fact_marks_from_request(marks: list[FactMarkRequest]) -> list[FactMark]:
    return [FactMark(**m.model_dump()) for m in marks]


def _fact_dims_from_request(dims: list[FactDimensionRequest]) -> list[FactDimension]:
    return [FactDimension(**d.model_dump()) for d in dims]


def _stamp_from_request(stamp: StampDataRequest | None) -> ISStampData | None:
    if stamp is None:
        return None
    return ISStampData(**stamp.model_dump())


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
async def generate_is(req: GenerateRequest) -> GenerateResponse:
    """
    Запускает генерацию одной Исполнительной Схемы.

    Автоматически выбирает пайплайн (DXF-First или PDF-Overlay)
    по формату исходного файла РД.
    """
    try:
        gen = ISGenerator(output_dir=req.output_dir)

        rd_sheet = _rd_sheet_from_request(req.rd_sheet) if req.rd_sheet else None
        fact_marks = _fact_marks_from_request(req.fact_marks)
        fact_dims = _fact_dims_from_request(req.fact_dimensions)
        stamp_data = _stamp_from_request(req.stamp_data)

        result = gen.generate(
            project_id=req.project_id,
            aosr_id=req.aosr_id,
            rd_sheet=rd_sheet,
            design_dxf=req.design_dxf,
            survey_file=req.survey_file,
            survey_format=SurveyFormat(req.survey_format) if req.survey_format else None,
            fact_marks=fact_marks,
            fact_dimensions=fact_dims,
            stamp_data=stamp_data,
            run_id=req.run_id,
        )

        return GenerateResponse(
            success=True,
            project_id=result.project_id,
            aosr_id=result.aosr_id,
            pipeline=result.pipeline.value,
            is_acceptable=result.is_acceptable,
            output_verified=result.output_verified,
            output_dxf_path=result.output_dxf_path,
            output_pdf_path=result.output_pdf_path,
            total_axes=result.total_axes,
            matched_axes=result.matched_axes,
            ok_deviations=result.ok_deviations,
            warning_deviations=result.warning_deviations,
            critical_deviations=result.critical_deviations,
        )

    except Exception as e:
        logger.error(f"IS generation failed: {e}")
        return GenerateResponse(
            success=False,
            project_id=req.project_id,
            aosr_id=req.aosr_id,
            error=str(e),
        )


@router.post("/batch", response_model=BatchGenerateResponse)
async def generate_batch(req: BatchGenerateRequest) -> BatchGenerateResponse:
    """
    Запускает batch-генерацию комплекта ИС для проекта.

    Поддерживает параллельную обработку (max_workers > 1).
    """
    try:
        batch_gen = ISBatchGenerator(
            output_dir=req.output_dir,
            max_workers=req.max_workers,
        )

        tasks = []
        for t in req.tasks:
            tasks.append(ISBatchTask(
                aosr_id=t.aosr_id,
                rd_sheet=_rd_sheet_from_request(t.rd_sheet) if t.rd_sheet else None,
                design_dxf=t.design_dxf,
                survey_file=t.survey_file,
                survey_format=SurveyFormat(t.survey_format) if t.survey_format else None,
                fact_marks=_fact_marks_from_request(t.fact_marks),
                fact_dimensions=_fact_dims_from_request(t.fact_dimensions),
                stamp_data=_stamp_from_request(t.stamp_data),
            ))

        result = batch_gen.generate_for_project(
            project_id=req.project_id,
            tasks=tasks,
            batch_id=req.batch_id,
        )

        return BatchGenerateResponse(
            success=result.failed == 0,
            batch_id=result.batch_id,
            project_id=result.project_id,
            total_tasks=result.total_tasks,
            completed=result.completed,
            failed=result.failed,
            success_rate=result.success_rate,
            all_acceptable=result.all_acceptable,
            total_ok=result.total_ok,
            total_warning=result.total_warning,
            total_critical=result.total_critical,
            duration_sec=result.duration_sec,
            errors=result.errors,
        )

    except Exception as e:
        logger.error(f"Batch generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events")
async def get_events(
    run_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """
    Возвращает event stream (для n8n/dashboard визуализации).

    Фильтрация по run_id, project_id, event_type.
    """
    emitter = get_event_emitter()

    et = None
    if event_type:
        try:
            et = EventType(event_type)
        except ValueError:
            pass  # Игнорируем невалидный тип

    events = emitter.get_events(
        run_id=run_id,
        project_id=project_id,
        event_type=et,
        limit=limit,
    )
    return {"events": events, "count": len(events)}


@router.get("/tolerances")
async def get_tolerances():
    """
    Возвращает справочник допусков из СП 126.13330.2017.

    Используется ПТО-агентом для назначения допусков по видам конструкций.
    """
    return {
        "profiles": list_profiles(),
        "tolerance_map": build_tolerance_map(),
    }


@router.get("/health")
async def health_check():
    """Проверка доступности модуля IS Generator."""
    # Проверяем ключевые зависимости
    deps = {}
    try:
        import ezdxf
        deps["ezdxf"] = True
    except ImportError:
        deps["ezdxf"] = False

    try:
        import cairosvg
        deps["cairosvg"] = True
    except ImportError:
        deps["cairosvg"] = False

    try:
        import fitz
        deps["pymupdf"] = True
    except ImportError:
        deps["pymupdf"] = False

    try:
        import structlog
        deps["structlog"] = True
    except ImportError:
        deps["structlog"] = False

    all_ok = all(deps.values())
    return {
        "status": "OK" if all_ok else "DEGRADED",
        "module": "is_generator",
        "version": "12.0",
        "dependencies": deps,
    }
