"""
events — структурированный event stream для модуля ISGenerator.

Каждый шаг пайплайна ИС генерирует событие с полным контекстом.
Поток событий можно визуализировать (n8n, Grafana, custom dashboard)
или анализировать пост-фактум для оптимизации процесса.

События пишутся через structlog — JSON-совместимый, машинно-читаемый формат.
Стандартный logging остаётся для backward compatibility.

v12.0
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# structlog — опциональная зависимость (fallback на стандартный logging)
try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False


# ─── Типы событий ────────────────────────────────────────────────────────────

class EventType(str, Enum):
    """Типы событий пайплайна ИС."""
    PIPELINE_STARTED    = "is_pipeline.started"
    PIPELINE_COMPLETED  = "is_pipeline.completed"
    PIPELINE_FAILED     = "is_pipeline.failed"

    GEODATA_PARSED      = "is_geodata.parsed"
    GEODATA_FAILED      = "is_geodata.failed"

    DXF_PARSED          = "is_dxf.parsed"
    DXF_CLIP            = "is_dxf.clipped"
    DXF_FAILED          = "is_dxf.failed"

    DEVIATIONS_CALC     = "is_deviations.calculated"
    DEVIATIONS_STATUS   = "is_deviations.status_summary"

    ANNOTATION_STARTED  = "is_annotation.started"
    ANNOTATION_DONE     = "is_annotation.completed"

    STAMP_DRAWN         = "is_stamp.drawn"

    EXPORT_STARTED      = "is_export.started"
    EXPORT_SVG          = "is_export.svg_done"
    EXPORT_PDF          = "is_export.pdf_done"
    EXPORT_FAILED       = "is_export.failed"

    OVERLAY_STARTED     = "is_overlay.started"
    OVERLAY_PNG         = "is_overlay.png_extracted"
    OVERLAY_DONE        = "is_overlay.completed"

    OUTPUT_VERIFIED     = "is_output.verified"
    OUTPUT_FAILED       = "is_output.verification_failed"

    BATCH_STARTED       = "is_batch.started"
    BATCH_ITEM_DONE     = "is_batch.item_completed"
    BATCH_COMPLETED     = "is_batch.completed"

    TASK_FORWARDED      = "is_task.forwarded"


class EventSeverity(str, Enum):
    """Уровень важности события."""
    DEBUG   = "debug"
    INFO    = "info"
    WARNING = "warning"
    ERROR   = "error"


# ─── Структура события ───────────────────────────────────────────────────────

@dataclass
class ISEvent:
    """
    Одно событие пайплайна ИС.

    Формат совместим с:
      - structlog JSON renderer
      - n8n webhook payload
      - Grafana Loki labels
    """
    event_type: EventType
    run_id: str                    # UUID одного запуска пайплайна
    project_id: str = ""           # Шифр проекта
    aosr_id: str = ""              # Номер АОСР
    module: str = "is_generator"   # Имя модуля-источника
    severity: EventSeverity = EventSeverity.INFO

    # Метрики
    duration_ms: float = 0.0       # Длительность шага в миллисекундах
    count: int = 0                 # Количество (точек, осей, отклонений)

    # Результат
    status: str = ""               # OK, WARNING, CRITICAL, ERROR
    detail: str = ""               # Человекочитаемое описание

    # Контекст (произвольные данные)
    extra: dict[str, Any] = field(default_factory=dict)

    # Автозаполняемые
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в словарь (JSON-совместимый)."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "aosr_id": self.aosr_id,
            "module": self.module,
            "severity": self.severity.value,
            "timestamp": self.timestamp,
            "duration_ms": round(self.duration_ms, 2),
            "count": self.count,
            "status": self.status,
            "detail": self.detail,
            "extra": self.extra,
        }

    def to_json(self) -> str:
        """Сериализация в JSON-строку."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


# ─── Event Emitter ───────────────────────────────────────────────────────────

class ISEventEmitter:
    """
    Центральный эмиттер событий для IS Generator.

    Пишет события одновременно в:
      1. structlog (JSON) — для машинной обработки
      2. стандартный logging — для backward compatibility
      3. in-memory buffer — для API-эндпоинтов и dashboard

    Использование:
        emitter = ISEventEmitter()
        emitter.emit(ISEvent(
            event_type=EventType.PIPELINE_STARTED,
            run_id="abc123",
            project_id="P001",
        ))
    """

    def __init__(
        self,
        buffer_size: int = 1000,
        json_log_path: str | Path | None = None,
    ) -> None:
        self._buffer: list[ISEvent] = []
        self._buffer_size = buffer_size
        self._json_log_path = Path(json_log_path) if json_log_path else None

        # structlog logger
        if STRUCTLOG_AVAILABLE:
            self._slog = structlog.get_logger("asd.is_generator")
        else:
            self._slog = None

        # Стандартный logger
        self._logger = logging.getLogger("asd.is_generator.events")

        # JSON log file
        if self._json_log_path:
            self._json_log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: ISEvent) -> None:
        """
        Отправляет событие во все каналы.

        Args:
            event: Событие пайплайна.
        """
        # 1. In-memory buffer (кольцевой)
        self._buffer.append(event)
        if len(self._buffer) > self._buffer_size:
            self._buffer = self._buffer[-self._buffer_size:]

        # 2. structlog (JSON)
        if self._slog:
            log_method = {
                EventSeverity.DEBUG: self._slog.debug,
                EventSeverity.INFO: self._slog.info,
                EventSeverity.WARNING: self._slog.warning,
                EventSeverity.ERROR: self._slog.error,
            }.get(event.severity, self._slog.info)
            log_method(
                event.event_type.value,
                **event.to_dict(),
            )

        # 3. Стандартный logging
        log_msg = (
            f"[{event.event_type.value}] "
            f"run={event.run_id} "
            f"project={event.project_id} "
            f"{event.detail}"
        )
        if event.duration_ms > 0:
            log_msg += f" ({event.duration_ms:.0f}ms)"
        if event.count > 0:
            log_msg += f" count={event.count}"

        log_fn = {
            EventSeverity.DEBUG: self._logger.debug,
            EventSeverity.INFO: self._logger.info,
            EventSeverity.WARNING: self._logger.warning,
            EventSeverity.ERROR: self._logger.error,
        }.get(event.severity, self._logger.info)
        log_fn(log_msg)

        # 4. JSON log file (append)
        if self._json_log_path:
            try:
                with open(self._json_log_path, "a", encoding="utf-8") as f:
                    f.write(event.to_json() + "\n")
            except Exception:
                pass  # Не ломаем пайплайн из-за ошибки записи лога

    def get_events(
        self,
        run_id: str | None = None,
        project_id: str | None = None,
        event_type: EventType | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Возвращает события из буфера (для API/dashboard).

        Args:
            run_id: Фильтр по run_id.
            project_id: Фильтр по project_id.
            event_type: Фильтр по типу события.
            limit: Максимум событий.

        Returns:
            Список сериализованных событий (новые последними).
        """
        result = self._buffer

        if run_id:
            result = [e for e in result if e.run_id == run_id]
        if project_id:
            result = [e for e in result if e.project_id == project_id]
        if event_type:
            result = [e for e in result if e.event_type == event_type]

        return [e.to_dict() for e in result[-limit:]]

    def clear_buffer(self) -> None:
        """Очищает буфер событий."""
        self._buffer.clear()


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

_global_emitter: ISEventEmitter | None = None


def get_event_emitter() -> ISEventEmitter:
    """Возвращает глобальный ISEventEmitter (singleton)."""
    global _global_emitter
    if _global_emitter is None:
        _global_emitter = ISEventEmitter()
    return _global_emitter


def set_event_emitter(emitter: ISEventEmitter) -> None:
    """Устанавливает глобальный ISEventEmitter (для тестов и кастомной конфигурации)."""
    global _global_emitter
    _global_emitter = emitter


# ─── Декоратор для замера времени ────────────────────────────────────────────

def timed_event(
    event_type: EventType,
    run_id: str = "",
    project_id: str = "",
    aosr_id: str = "",
    module: str = "is_generator",
    severity: EventSeverity = EventSeverity.INFO,
    count_field: str = "count",
):
    """
    Декоратор для автоматического замера времени и эмита события.

    Использование:
        @timed_event(EventType.DXF_PARSED, module="dxf_parser")
        def parse(self, file_path):
            ...
            return axes  # len(axes) → count

    Результат функции используется как count (если это число)
    или count=len(result) (если это коллекция).
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            emitter = get_event_emitter()
            t0 = time.monotonic()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.monotonic() - t0) * 1000

                # Определяем count
                count = 0
                if isinstance(result, (int, float)):
                    count = int(result)
                elif hasattr(result, '__len__'):
                    count = len(result)

                event = ISEvent(
                    event_type=event_type,
                    run_id=run_id,
                    project_id=project_id,
                    aosr_id=aosr_id,
                    module=module,
                    severity=severity,
                    duration_ms=elapsed_ms,
                    count=count,
                    status="OK",
                    detail=f"{func.__name__} completed",
                )
                emitter.emit(event)
                return result

            except Exception as e:
                elapsed_ms = (time.monotonic() - t0) * 1000
                event = ISEvent(
                    event_type=event_type,
                    run_id=run_id,
                    project_id=project_id,
                    aosr_id=aosr_id,
                    module=module,
                    severity=EventSeverity.ERROR,
                    duration_ms=elapsed_ms,
                    status="ERROR",
                    detail=f"{func.__name__} failed: {e}",
                )
                emitter.emit(event)
                raise

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator
