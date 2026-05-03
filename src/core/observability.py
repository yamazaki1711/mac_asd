"""
ASD v12.0 — Observability Module.

Structured JSON logging + pipeline metrics for monitoring.
Designed for Grafana dashboards and operational visibility.

Features:
- JSON-structured logs for every pipeline stage
- Per-agent timing metrics
- LLM call counters and latency tracking
- Veto/failure/warning event counters
- Pipeline latency percentiles (p50, p95, p99)

Usage:
    from src.core.observability import PipelineMetrics, observe_step

    metrics = PipelineMetrics()

    @observe_step("pto_extract_vor")
    async def pto_node(state):
        ...
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple


# =============================================================================
# Structured JSON Logger
# =============================================================================

class JsonFormatter(logging.Formatter):
    """Форматирует логи в JSON для парсинга Grafana/Prometheus."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])

        # Attach extra fields
        for key in ("agent", "step", "project_id", "lot_id", "duration_ms", "metrics"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_json_logging():
    """Настроить JSON-логирование для всех логгеров ASD."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger("src")
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

    return root_logger


# =============================================================================
# Pipeline Metrics
# =============================================================================

@dataclass
class AgentStepMetric:
    """Метрики одного шага агента."""
    agent: str
    step: str
    started_at: float
    completed_at: float = 0.0
    success: bool = True
    fallback_used: bool = False
    error: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return 0.0


@dataclass
class PipelineRunMetrics:
    """Метрики одного прогона конвейера."""
    run_id: str
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    agent_steps: List[AgentStepMetric] = field(default_factory=list)
    llm_calls: int = 0
    llm_fallbacks: int = 0
    veto_triggered: Optional[str] = None
    verdict: Optional[str] = None
    decision_method: Optional[str] = None
    auditor_verdict: Optional[str] = None

    @property
    def total_duration_ms(self) -> float:
        end = self.completed_at or time.time()
        return (end - self.started_at) * 1000

    def add_step(self, step: AgentStepMetric):
        self.agent_steps.append(step)

    def to_dict(self) -> Dict:
        return {
            "run_id": self.run_id,
            "duration_ms": round(self.total_duration_ms, 1),
            "agent_steps": len(self.agent_steps),
            "llm_calls": self.llm_calls,
            "llm_fallbacks": self.llm_fallbacks,
            "veto_triggered": self.veto_triggered,
            "verdict": self.verdict,
            "decision_method": self.decision_method,
            "auditor_verdict": self.auditor_verdict,
            "per_agent_duration": {
                s.agent: round(s.duration_ms, 1)
                for s in self.agent_steps
            },
            "total_fallback_agents": [
                s.agent for s in self.agent_steps if s.fallback_used
            ],
        }


# =============================================================================
# Metrics Collector (Singleton)
# =============================================================================

class MetricsCollector:
    """
    Коллектор метрик для мониторинга конвейера.

    Накапливает:
    - Счётчики успешных/неудачных шагов
    - Процентили latency (P50, P95, P99)
    - Частоту LLM fallback'ов
    - Частоту VETO-срабатываний
    """

    def __init__(self):
        self._runs: List[PipelineRunMetrics] = []
        self._step_durations: Dict[str, List[float]] = defaultdict(list)
        self._verdict_counts: Dict[str, int] = defaultdict(int)
        self._veto_counts: Dict[str, int] = defaultdict(int)
        self._fallback_counts: Dict[str, int] = defaultdict(int)

    def record_run(self, run: PipelineRunMetrics):
        self._runs.append(run)
        self._verdict_counts[run.verdict or "unknown"] += 1
        if run.veto_triggered:
            self._veto_counts[run.veto_triggered] += 1

        for step in run.agent_steps:
            key = f"{step.agent}:{step.step}"
            self._step_durations[key].append(step.duration_ms)
            if step.fallback_used:
                self._fallback_counts[step.agent] += 1

    def stats(self) -> Dict[str, Any]:
        """Сводная статистика для дашборда."""
        return {
            "total_runs": len(self._runs),
            "verdicts": dict(self._verdict_counts),
            "veto_triggers": dict(self._veto_counts),
            "fallback_by_agent": dict(self._fallback_counts),
            "avg_pipeline_duration_ms": self._avg_duration(),
            "p95_latency_ms": self._percentile(95),
            "fallback_rate_pct": self._fallback_rate(),
        }

    def _avg_duration(self) -> float:
        if not self._runs:
            return 0.0
        return sum(r.total_duration_ms for r in self._runs) / len(self._runs)

    def _percentile(self, pct: int) -> float:
        durations = sorted(r.total_duration_ms for r in self._runs)
        if not durations:
            return 0.0
        idx = int(len(durations) * pct / 100)
        return durations[min(idx, len(durations) - 1)]

    def _fallback_rate(self) -> float:
        if not self._runs:
            return 0.0
        runs_with_fallback = sum(1 for r in self._runs if r.llm_fallbacks > 0)
        return (runs_with_fallback / len(self._runs)) * 100

    def reset(self):
        self._runs.clear()
        self._step_durations.clear()
        self._verdict_counts.clear()
        self._veto_counts.clear()
        self._fallback_counts.clear()


# Global collector
metrics_collector = MetricsCollector()


# =============================================================================
# Decorator: observe_step
# =============================================================================

def observe_step(step_name: str):
    """
    Декоратор для отслеживания метрик шага агента.

    Автоматически записывает:
    - duration_ms
    - success/failure
    - fallback_used (если агент использовал fallback_response)

    Usage:
        @observe_step("pto_extract_vor")
        async def pto_node(state):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            state = args[0] if args else kwargs.get("state", {})
            agent = step_name.split("_")[0] if "_" in step_name else step_name

            metric = AgentStepMetric(
                agent=agent,
                step=step_name,
                started_at=time.time(),
            )

            try:
                result = await func(*args, **kwargs)

                metric.completed_at = time.time()
                metric.success = True

                # Check for fallback
                if isinstance(result, dict) and result.get("_llm_fallback_triggered"):
                    metric.fallback_used = True

                # Update global LLM counters
                if isinstance(state, dict):
                    state.setdefault("_pipeline_metrics", {}).setdefault("llm_calls", 0)
                    state["_pipeline_metrics"]["llm_calls"] += 1
                    if metric.fallback_used:
                        state["_pipeline_metrics"].setdefault("llm_fallbacks", 0)
                        state["_pipeline_metrics"]["llm_fallbacks"] += 1

                return result

            except Exception as e:
                metric.completed_at = time.time()
                metric.success = False
                metric.error = str(e)
                raise

        return async_wrapper
    return decorator


# =============================================================================
# Context manager: PipelineTimer
# =============================================================================

@contextmanager
def pipeline_timer(run_id: str = "") -> PipelineRunMetrics:
    """Контекстный менеджер для замера полного времени конвейера."""
    import uuid
    run = PipelineRunMetrics(run_id=run_id or str(uuid.uuid4())[:8])
    try:
        yield run
    finally:
        run.completed_at = time.time()
        metrics_collector.record_run(run)


# =============================================================================
# Health Check Endpoint
# =============================================================================

def health_check() -> Dict[str, Any]:
    """
    Проверка здоровья системы.

    Возвращает статус всех компонентов.
    """
    stats = metrics_collector.stats()

    return {
        "status": "healthy" if stats["fallback_rate_pct"] < 20 else "degraded",
        "version": "12.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": stats,
        "checks": {
            "fallback_rate": {
                "status": "ok" if stats["fallback_rate_pct"] < 10 else "warn",
                "value": f"{stats['fallback_rate_pct']:.1f}%",
            },
            "pipeline_latency_p95": {
                "status": "ok",
                "value": f"{stats['p95_latency_ms']:.0f}ms",
            },
            "total_runs": {
                "status": "ok",
                "value": stats["total_runs"],
            },
        },
    }
