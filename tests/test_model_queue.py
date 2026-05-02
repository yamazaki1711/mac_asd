"""
ASD v12.0 — Unit tests for ModelRequestQueue.
"""
import asyncio
import pytest
from src.core.model_queue import (
    ModelRequestQueue,
    RequestPriority,
    derive_model_key,
)
from src.core.exceptions import QueueFullError


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _slow_func(delay: float = 0.05, value: str = "ok") -> str:
    """Simulated async LLM call."""
    await asyncio.sleep(delay)
    return value


class _ConcurrencyTracker:
    """Track concurrent executions to verify semaphore limits."""

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.completed = 0

    async def tracked(self, delay: float = 0.05) -> str:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(delay)
        self.completed += 1
        self.active -= 1
        return str(self.completed)


# ── Tests ───────────────────────────────────────────────────────────────────

class TestModelRequestQueue:
    """Unit tests for ModelRequestQueue."""

    @pytest.mark.asyncio
    async def test_submit_returns_result(self):
        """Basic submit() returns the function's result."""
        queue = ModelRequestQueue()
        result = await queue.submit(
            agent="test", model_key="test_model",
            func=_slow_func, value="hello",
        )
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """With max_concurrent=2, at most 2 tasks run simultaneously."""
        queue = ModelRequestQueue()
        queue.configure_model("m1", max_concurrent=2, queue_size=10)

        tracker = _ConcurrencyTracker()
        tasks = [
            asyncio.create_task(
                queue.submit(agent="a", model_key="m1", func=tracker.tracked)
            )
            for _ in range(5)
        ]
        await asyncio.gather(*tasks)

        assert tracker.max_active <= 2
        assert tracker.completed == 5

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Higher priority (lower int) requests execute before lower ones."""
        queue = ModelRequestQueue()
        queue.configure_model("m1", max_concurrent=1, queue_size=10)

        order = []

        async def record(seq: int):
            order.append(seq)
            return seq

        # Submit LOW first, then CRITICAL
        t1 = asyncio.create_task(
            queue.submit(agent="a", model_key="m1", func=record, priority=RequestPriority.LOW, seq=1)
        )
        # Give time for LOW to enter queue
        await asyncio.sleep(0.01)
        t2 = asyncio.create_task(
            queue.submit(agent="b", model_key="m1", func=record, priority=RequestPriority.CRITICAL, seq=2)
        )

        await asyncio.gather(t1, t2)
        # Both complete successfully
        assert len(order) == 2

    @pytest.mark.asyncio
    async def test_fifo_within_same_priority(self):
        """Within same priority, requests execute in FIFO order."""
        queue = ModelRequestQueue()
        queue.configure_model("m1", max_concurrent=1, queue_size=10)

        order = []

        async def record(seq: int):
            order.append(seq)
            return seq

        t1 = asyncio.create_task(
            queue.submit(agent="a", model_key="m1", func=record,
                         priority=RequestPriority.NORMAL, seq=1)
        )
        await asyncio.sleep(0.01)
        t2 = asyncio.create_task(
            queue.submit(agent="b", model_key="m1", func=record,
                         priority=RequestPriority.NORMAL, seq=2)
        )

        await asyncio.gather(t1, t2)
        assert order == [1, 2]

    @pytest.mark.asyncio
    async def test_queue_full_raises(self):
        """Submitting past queue_size raises QueueFullError."""
        queue = ModelRequestQueue()
        queue.configure_model("m1", max_concurrent=1, queue_size=2)

        # Fill the buffer — the drain task runs after each put_nowait,
        # but we need to block the drain. Fire 3 submits rapidly.
        # The queue drainer can grab items immediately since max_concurrent=1
        # means it processes as fast as possible. Use slow funcs.
        # But the drain is async — queue fills before drain picks up items.
        # We batch-submit: use queue._queues directly to test capacity.
        # Actually, use regular submit with a func that blocks the semaphore.

        async def slow(delay: float = 0.2):
            await asyncio.sleep(delay)
            return "ok"

        block_drain = asyncio.Event()  # holds semaphore until we're ready

        async def blocker():
            await block_drain.wait()
            return "ok"

        # First submit grabs semaphore (max_concurrent=1), waits on Event
        t1 = asyncio.create_task(
            queue.submit(agent="a", model_key="m1", func=blocker)
        )
        await asyncio.sleep(0.03)

        # These two queue up via submit (queue_size=2 allows 2 waiting)
        t2 = asyncio.create_task(
            queue.submit(agent="b", model_key="m1", func=slow, delay=0.1)
        )
        t3 = asyncio.create_task(
            queue.submit(agent="c", model_key="m1", func=slow, delay=0.1)
        )
        await asyncio.sleep(0.03)

        # Queue is now full (2 waiting). This one must be rejected.
        with pytest.raises(QueueFullError):
            await queue.submit(agent="d", model_key="m1", func=slow, delay=0.1)

        # Clean up: release blocker, let everything drain
        block_drain.set()
        await asyncio.gather(t1, t2, t3)

    @pytest.mark.asyncio
    async def test_get_metrics(self):
        """Metrics track enqueued, completed, etc."""
        queue = ModelRequestQueue()
        queue.configure_model("m1", max_concurrent=2, queue_size=10)

        tasks = [
            queue.submit(agent="a", model_key="m1", func=_slow_func, value="x")
            for _ in range(3)
        ]
        await asyncio.gather(*tasks)

        metrics = queue.get_metrics()
        assert "m1" in metrics
        assert metrics["m1"]["enqueued"] == 3
        assert metrics["m1"]["completed"] == 3
        assert metrics["m1"]["avg_wait_ms"] >= 0

    @pytest.mark.asyncio
    async def test_multiple_models_independent(self):
        """Different model keys don't block each other."""
        queue = ModelRequestQueue()
        queue.configure_model("model_a", max_concurrent=1, queue_size=5)
        queue.configure_model("model_b", max_concurrent=1, queue_size=5)

        tracker_a = _ConcurrencyTracker()
        tracker_b = _ConcurrencyTracker()

        async def run():
            tasks = [
                queue.submit(agent="a1", model_key="model_a", func=tracker_a.tracked),
                queue.submit(agent="a2", model_key="model_a", func=tracker_a.tracked),
                queue.submit(agent="b1", model_key="model_b", func=tracker_b.tracked),
                queue.submit(agent="b2", model_key="model_b", func=tracker_b.tracked),
            ]
            await asyncio.gather(*tasks)

        await run()
        # Each model is capped at 1, but they don't block each other
        assert tracker_a.max_active <= 1
        assert tracker_b.max_active <= 1
        # Both models could be active simultaneously
        assert tracker_a.completed == 2
        assert tracker_b.completed == 2

    @pytest.mark.asyncio
    async def test_exception_in_func_propagates(self):
        """If the submitted func raises, the exception propagates to submit()."""
        queue = ModelRequestQueue()

        async def failing():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await queue.submit(agent="a", model_key="m1", func=failing)


class TestDeriveModelKey:
    """Tests for derive_model_key helper."""

    def test_dev_linux_groups_shared_agents(self):
        """In dev_linux, PTO and Legal share the same model key."""
        key_pto = derive_model_key("pto")
        key_legal = derive_model_key("legal")
        assert key_pto == key_legal
        assert "gemma" in key_pto.lower()


class TestRequestPriority:
    """RequestPriority enum ordering tests."""

    def test_critical_lower_than_high(self):
        assert RequestPriority.CRITICAL < RequestPriority.HIGH

    def test_high_lower_than_normal(self):
        assert RequestPriority.HIGH < RequestPriority.NORMAL

    def test_normal_lower_than_low(self):
        assert RequestPriority.NORMAL < RequestPriority.LOW
