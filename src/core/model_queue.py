"""
ASD v12.0 — Shared Model Request Queue.

Async priority queue that limits concurrent LLM calls per model via
asyncio.Semaphore. Integrates with RamManager for memory-aware gating.

Groups agents sharing the same model (e.g., PTO/Legal/Smeta on Gemma 4 31B)
behind a single semaphore, preventing resource contention.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Optional

from src.core.exceptions import QueueFullError

logger = logging.getLogger(__name__)


# ── Priority ───────────────────────────────────────────────────────────────

class RequestPriority(IntEnum):
    """Request priority. Lower integer = higher priority (for PriorityQueue)."""
    CRITICAL = 0   # PM orchestration decisions
    HIGH = 1       # Legal, Smeta (user-facing)
    NORMAL = 2     # PTO, Procurement, Archive (background)
    LOW = 3        # Logistics (deferrable)


# ── Internal wrapper ───────────────────────────────────────────────────────

@dataclass(order=True)
class _PrioritizedRequest:
    """Comparable wrapper for asyncio.PriorityQueue. Sorted by (priority, sequence)."""
    priority: int
    sequence: int
    agent: str = field(compare=False)
    func: Callable[..., Any] = field(compare=False)
    args: tuple = field(compare=False, default_factory=tuple)
    kwargs: dict = field(compare=False, default_factory=dict)
    future: asyncio.Future = field(compare=False, default_factory=asyncio.Future)
    enqueued_at: float = field(compare=False, default_factory=time.monotonic)


# ── Queue ──────────────────────────────────────────────────────────────────

class ModelRequestQueue:
    """
    Async request queue with per-model concurrency limiting.

    For each model_key, an asyncio.Semaphore caps concurrent in-flight
    requests. Overflow is parked in a PriorityQueue and processed when
    a semaphore slot opens.

    Integrates with RamManager: before dispatch, checks
    ram_manager.can_accept_task(). If RAM is under pressure, the
    request is requeued with backoff.
    """

    def __init__(
        self,
        default_max_concurrent: int = 2,
        default_queue_size: int = 100,
    ) -> None:
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._queues: dict[str, asyncio.PriorityQueue] = {}
        self._default_max_concurrent = default_max_concurrent
        self._default_queue_size = default_queue_size
        self._model_configs: dict[str, dict[str, int]] = {}

        # Monotonic sequence for FIFO within same priority
        self._sequence: int = 0
        self._seq_lock = asyncio.Lock()

        # RamManager reference (set after construction)
        self._ram_manager: Any = None

        # Metrics
        self._enqueued: dict[str, int] = {}
        self._rejected: dict[str, int] = {}
        self._completed: dict[str, int] = {}
        self._total_wait_seconds: dict[str, float] = {}
        self._total_wall_seconds: dict[str, float] = {}
        self._active_count: dict[str, int] = {}
        self._drain_running: dict[str, bool] = {}

    # ── Configuration ──────────────────────────────────────────────────

    def configure_model(
        self,
        model_key: str,
        max_concurrent: int,
        queue_size: int = 100,
    ) -> None:
        """Set concurrency limit for a specific model key."""
        self._model_configs[model_key] = {
            "max_concurrent": max_concurrent,
            "queue_size": queue_size,
        }
        self._semaphores[model_key] = asyncio.Semaphore(max_concurrent)
        if model_key not in self._queues:
            self._queues[model_key] = asyncio.PriorityQueue(maxsize=queue_size)
        self._active_count.setdefault(model_key, 0)
        logger.info(
            "Model queue configured: %s max_concurrent=%d queue_size=%d",
            model_key, max_concurrent, queue_size,
        )

    def set_ram_manager(self, ram_manager: Any) -> None:
        """Integrate with RamManager for memory-aware gating."""
        self._ram_manager = ram_manager

    # ── Submission ─────────────────────────────────────────────────────

    async def submit(
        self,
        agent: str,
        model_key: str,
        func: Callable[..., Any],
        *args: Any,
        priority: RequestPriority = RequestPriority.NORMAL,
        **kwargs: Any,
    ) -> Any:
        """
        Submit an async callable to the model's queue.

        Returns the callable's result once granted a semaphore slot.

        Raises QueueFullError if the queue for this model is full.
        """
        # Lazy default config
        if model_key not in self._semaphores:
            self.configure_model(model_key, self._default_max_concurrent)

        # Allocate monotonic sequence
        async with self._seq_lock:
            self._sequence += 1
            seq = self._sequence

        future: asyncio.Future = asyncio.Future()
        request = _PrioritizedRequest(
            priority=priority.value,
            sequence=seq,
            agent=agent,
            func=func,
            args=args,
            kwargs=kwargs,
            future=future,
        )

        try:
            self._queues[model_key].put_nowait(request)
        except asyncio.QueueFull:
            self._rejected[model_key] = self._rejected.get(model_key, 0) + 1
            logger.warning(
                "Model queue FULL for %s. Rejecting agent=%s request.",
                model_key, agent,
            )
            raise QueueFullError(
                f"Model queue '{model_key}' is full (capacity="
                f"{self._model_configs.get(model_key, {}).get('queue_size', '?')})"
            )

        self._enqueued[model_key] = self._enqueued.get(model_key, 0) + 1

        # Fire drain task if not already running for this model
        if not self._drain_running.get(model_key, False):
            self._drain_running[model_key] = True
            asyncio.create_task(self._drain_queue(model_key))

        return await future

    # ── Internal drain ─────────────────────────────────────────────────

    async def _drain_queue(self, model_key: str) -> None:
        """
        Worker coroutine. Acquires semaphore, pops one request, executes it,
        then recurses to check for more queued items. Items stay in the
        queue until a semaphore slot is available, maintaining backpressure.
        """
        queue = self._queues.get(model_key)
        semaphore = self._semaphores.get(model_key)
        if queue is None or semaphore is None:
            self._drain_running[model_key] = False
            return

        # Acquire semaphore first — this provides backpressure so items
        # stay in the PriorityQueue until capacity is available.
        async with semaphore:
            try:
                request: _PrioritizedRequest = queue.get_nowait()
            except asyncio.QueueEmpty:
                self._drain_running[model_key] = False
                return

            # RAM gate
            if self._ram_manager is not None:
                if not self._ram_manager.can_accept_task(
                    request.agent,
                    priority=_map_priority(RequestPriority(request.priority)),
                ):
                    # Requeue with backoff
                    try:
                        queue.put_nowait(request)
                    except asyncio.QueueFull:
                        request.future.set_exception(
                            QueueFullError("RAM rejected and queue is full")
                        )
                    await asyncio.sleep(0.5)
                    # Recurse to retry after backoff
                    asyncio.create_task(self._drain_queue(model_key))
                    return

            # Execute under the already-held semaphore
            await self._execute_request(request, model_key)

        # Check for more items (recurse)
        asyncio.create_task(self._drain_queue(model_key))

    async def _execute_request(
        self,
        request: _PrioritizedRequest,
        model_key: str,
    ) -> None:
        """Execute a single request (semaphore already held by drain)."""
        start = time.monotonic()
        self._active_count[model_key] = self._active_count.get(model_key, 0) + 1
        try:
            if asyncio.iscoroutinefunction(request.func):
                result = await request.func(*request.args, **request.kwargs)
            else:
                result = request.func(*request.args, **request.kwargs)
            request.future.set_result(result)
        except Exception as exc:
            request.future.set_exception(exc)
        finally:
            self._active_count[model_key] = max(
                0, self._active_count.get(model_key, 0) - 1
            )

        elapsed = time.monotonic() - start
        wait = start - request.enqueued_at
        self._total_wall_seconds[model_key] = (
            self._total_wall_seconds.get(model_key, 0.0) + elapsed
        )
        self._total_wait_seconds[model_key] = (
            self._total_wait_seconds.get(model_key, 0.0) + wait
        )
        self._completed[model_key] = self._completed.get(model_key, 0) + 1

    # ── Metrics ────────────────────────────────────────────────────────

    def get_metrics(self) -> dict[str, Any]:
        """Return queue metrics keyed by model_key."""
        metrics: dict[str, Any] = {}
        all_keys = set(self._model_configs) | set(self._semaphores)
        for model_key in all_keys:
            comp = self._completed.get(model_key, 0)
            queue = self._queues.get(model_key)
            metrics[model_key] = {
                "enqueued": self._enqueued.get(model_key, 0),
                "rejected": self._rejected.get(model_key, 0),
                "completed": comp,
                "queue_depth": queue.qsize() if queue else 0,
                "active": self._active_count.get(model_key, 0),
                "avg_wait_ms": round(
                    self._total_wait_seconds.get(model_key, 0.0) / max(comp, 1) * 1000, 1
                ),
                "avg_wall_ms": round(
                    self._total_wall_seconds.get(model_key, 0.0) / max(comp, 1) * 1000, 1
                ),
                "max_concurrent": self._model_configs.get(model_key, {}).get(
                    "max_concurrent", self._default_max_concurrent
                ),
            }
        return metrics


# ── Helpers ────────────────────────────────────────────────────────────────

def _map_priority(rp: RequestPriority) -> Any:
    """Map RequestPriority to RamManager's TaskPriority."""
    try:
        from src.core.ram_manager import TaskPriority
        mapping = {
            RequestPriority.CRITICAL: TaskPriority.CRITICAL,
            RequestPriority.HIGH: TaskPriority.HIGH,
            RequestPriority.NORMAL: TaskPriority.NORMAL,
            RequestPriority.LOW: TaskPriority.LOW,
        }
        return mapping.get(rp, TaskPriority.NORMAL)
    except ImportError:
        return None


def derive_model_key(agent: str) -> str:
    """
    Derive a queue model_key from the agent name.

    Uses the model field from Settings.get_model_config(), which
    naturally groups agents that share a model.

    Example:
        "pto"   -> "mlx-community/gemma-4-31b-it-4bit"
        "legal" -> "mlx-community/gemma-4-31b-it-4bit"  (same key)
        "pm"    -> "mlx-community/Llama-3.3-70B-Instruct-4bit"
    """
    from src.config import settings
    config = settings.get_model_config(agent)
    return config["model"]
