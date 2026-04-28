"""
batch_generator — генерация комплекта Исполнительных Схем для проекта.

Оборачивает ISGenerator для массовой генерации ИС:
  - Все захватки проекта за один вызов
  - Все АОСР проекта за один вызов
  - Конфигурируемый параллелизм
  - Единый отчёт по комплекту

Использование:
    from src.core.services.is_generator.batch_generator import ISBatchGenerator

    batch = ISBatchGenerator(output_dir="/data/projects/P001/IS")
    results = batch.generate_for_project(
        project_id="P001",
        tasks=[
            ISBatchTask(aosr_id="АОСР-001", rd_sheet=..., ...),
            ISBatchTask(aosr_id="АОСР-002", rd_sheet=..., ...),
        ],
    )
    print(results.summary())
"""
from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from src.core.services.is_generator.schemas import (
    FactDimension,
    FactMark,
    ISPipeline,
    ISResult,
    ISStampData,
    RDSheetInfo,
    SurveyFormat,
)
from src.core.services.is_generator.is_generator import ISGenerator
from src.core.services.is_generator.events import (
    EventType,
    ISEvent,
    EventSeverity,
    get_event_emitter,
)


# ─── Одна задача генерации ────────────────────────────────────────────────────

@dataclass
class ISBatchTask:
    """Один элемент задачника для batch-генерации."""
    aosr_id: str                             # АОСР для этой ИС
    rd_sheet: Optional[RDSheetInfo] = None   # Лист РД
    design_dxf: Optional[str] = None         # DXF напрямую
    survey_file: Optional[str] = None        # Геодезия
    survey_format: Optional[SurveyFormat] = None
    fact_marks: list[FactMark] = field(default_factory=list)
    fact_dimensions: list[FactDimension] = field(default_factory=list)
    stamp_data: Optional[ISStampData] = None


# ─── Результат batch-генерации ────────────────────────────────────────────────

@dataclass
class ISBatchResult:
    """Итоговый результат batch-генерации комплекта ИС."""
    batch_id: str = ""
    project_id: str = ""
    total_tasks: int = 0
    completed: int = 0
    failed: int = 0
    results: list[ISResult] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    # Временные метрики
    started_at: float = 0.0
    completed_at: float = 0.0

    @property
    def duration_sec(self) -> float:
        if self.completed_at > 0:
            return self.completed_at - self.started_at
        return 0.0

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.completed / self.total_tasks

    @property
    def total_critical(self) -> int:
        return sum(r.critical_deviations for r in self.results)

    @property
    def total_warning(self) -> int:
        return sum(r.warning_deviations for r in self.results)

    @property
    def total_ok(self) -> int:
        return sum(r.ok_deviations for r in self.results)

    @property
    def all_acceptable(self) -> bool:
        """Все ИС в комплекте допустимы для подписания?"""
        return all(r.is_acceptable for r in self.results) and self.failed == 0

    def summary(self) -> str:
        """Текстовый отчёт по комплекту."""
        lines = [
            f"Batch IS Generation Report: batch={self.batch_id}",
            f"  Project: {self.project_id}",
            f"  Tasks: {self.total_tasks} (completed={self.completed}, failed={self.failed})",
            f"  Duration: {self.duration_sec:.1f}s",
            f"  Success rate: {self.success_rate:.0%}",
            f"  Deviations: OK={self.total_ok} WARNING={self.total_warning} CRITICAL={self.total_critical}",
            f"  All acceptable: {self.all_acceptable}",
        ]
        if self.errors:
            lines.append("  Errors:")
            for err in self.errors:
                lines.append(f"    - АОСР={err.get('aosr_id', '?')}: {err.get('error', '?')}")
        return "\n".join(lines)


# ─── Batch Generator ──────────────────────────────────────────────────────────

class ISBatchGenerator:
    """
    Генератор комплекта ИС для проекта.

    Оборачивает ISGenerator для массовой обработки:
      - Параллельная генерация (ThreadPoolExecutor)
      - Единый event stream
      - Единый отчёт

    Args:
        output_dir: Базовый каталог для выходных файлов.
        max_workers: Максимум параллельных задач (1 = последовательно).
        anchor_points: Опорные точки для CRS-привязки.
        axis_layers: Слои с проектными осями.
        tolerance_map: Переопределение допусков.
    """

    def __init__(
        self,
        output_dir: str | Path = "/tmp/is_output",
        max_workers: int = 1,
        anchor_points: list | None = None,
        axis_layers: list[str] | None = None,
        tolerance_map: dict[str, float] | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers
        self._anchor_points = anchor_points
        self._axis_layers = axis_layers
        self._tolerance_map = tolerance_map
        self._emitter = get_event_emitter()

    # ─── Публичный метод ──────────────────────────────────────────────────────

    def generate_for_project(
        self,
        project_id: str,
        tasks: list[ISBatchTask],
        batch_id: str | None = None,
    ) -> ISBatchResult:
        """
        Генерирует комплект ИС для проекта.

        Args:
            project_id: Идентификатор проекта.
            tasks: Список задач генерации (по одному на АОСР/захватку).
            batch_id: Идентификатор batch (None → UUID4).

        Returns:
            ISBatchResult с результатами всех генераций.
        """
        batch_id = batch_id or uuid.uuid4().hex[:10]

        # Создаём один ISGenerator на весь batch
        gen = ISGenerator(
            output_dir=self.output_dir / project_id,
            anchor_points=self._anchor_points,
            axis_layers=self._axis_layers,
            tolerance_map=self._tolerance_map,
        )

        batch_result = ISBatchResult(
            batch_id=batch_id,
            project_id=project_id,
            total_tasks=len(tasks),
            started_at=time.time(),
        )

        # Событие: batch запущен
        self._emitter.emit(ISEvent(
            event_type=EventType.BATCH_STARTED,
            run_id=batch_id,
            project_id=project_id,
            module="batch_generator",
            count=len(tasks),
            detail=f"Batch started with {len(tasks)} tasks",
        ))

        # ── Последовательная или параллельная обработка ────────────────
        if self.max_workers <= 1:
            # Последовательно (без потоков — проще отладка)
            for task in tasks:
                self._process_task(
                    gen=gen,
                    task=task,
                    project_id=project_id,
                    batch_id=batch_id,
                    batch_result=batch_result,
                )
        else:
            # Параллельно (ThreadPoolExecutor)
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(
                        self._run_single,
                        gen, task, project_id, batch_id,
                    ): task
                    for task in tasks
                }
                for future in as_completed(futures):
                    task = futures[future]
                    try:
                        result = future.result()
                        batch_result.results.append(result)
                        batch_result.completed += 1
                    except Exception as e:
                        batch_result.failed += 1
                        batch_result.errors.append({
                            "aosr_id": task.aosr_id,
                            "error": str(e),
                        })
                        logger.error(f"Batch task failed: АОСР={task.aosr_id}: {e}")

        batch_result.completed_at = time.time()

        # Событие: batch завершён
        self._emitter.emit(ISEvent(
            event_type=EventType.BATCH_COMPLETED,
            run_id=batch_id,
            project_id=project_id,
            module="batch_generator",
            duration_ms=(batch_result.completed_at - batch_result.started_at) * 1000,
            count=batch_result.completed,
            status="OK" if batch_result.all_acceptable else "CRITICAL",
            detail=f"Batch completed: {batch_result.completed}/{batch_result.total_tasks} OK, "
                   f"{batch_result.total_critical} critical deviations",
            extra={
                "success_rate": batch_result.success_rate,
                "all_acceptable": batch_result.all_acceptable,
                "total_critical": batch_result.total_critical,
            },
        ))

        logger.info(batch_result.summary())
        return batch_result

    # ─── Внутренние методы ────────────────────────────────────────────────────

    def _process_task(
        self,
        gen: ISGenerator,
        task: ISBatchTask,
        project_id: str,
        batch_id: str,
        batch_result: ISBatchResult,
    ) -> None:
        """Обрабатывает одну задачу (последовательный режим)."""
        try:
            result = gen.generate(
                project_id=project_id,
                aosr_id=task.aosr_id,
                rd_sheet=task.rd_sheet,
                design_dxf=task.design_dxf,
                survey_file=task.survey_file,
                survey_format=task.survey_format,
                fact_marks=task.fact_marks or None,
                fact_dimensions=task.fact_dimensions or None,
                stamp_data=task.stamp_data,
                run_id=f"{batch_id}_{task.aosr_id}",
            )
            batch_result.results.append(result)
            batch_result.completed += 1

            self._emitter.emit(ISEvent(
                event_type=EventType.BATCH_ITEM_DONE,
                run_id=batch_id,
                project_id=project_id,
                aosr_id=task.aosr_id,
                module="batch_generator",
                status="OK" if result.is_acceptable else "CRITICAL",
                detail=f"АОСР={task.aosr_id}: acceptable={result.is_acceptable}",
            ))

        except Exception as e:
            batch_result.failed += 1
            batch_result.errors.append({
                "aosr_id": task.aosr_id,
                "error": str(e),
            })
            logger.error(f"Batch task failed: АОСР={task.aosr_id}: {e}")

    @staticmethod
    def _run_single(
        gen: ISGenerator,
        task: ISBatchTask,
        project_id: str,
        batch_id: str,
    ) -> ISResult:
        """Запускает одну задачу генерации (для ThreadPoolExecutor)."""
        return gen.generate(
            project_id=project_id,
            aosr_id=task.aosr_id,
            rd_sheet=task.rd_sheet,
            design_dxf=task.design_dxf,
            survey_file=task.survey_file,
            survey_format=task.survey_format,
            fact_marks=task.fact_marks or None,
            fact_dimensions=task.fact_dimensions or None,
            stamp_data=task.stamp_data,
            run_id=f"{batch_id}_{task.aosr_id}",
        )
