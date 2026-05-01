"""
ASD v12.0 — WorkPlan & TaskNode Tests.

Tests the PM orchestration core: TaskNode lifecycle, WorkPlan dependency
resolution, parallel-ready task selection, PM dispatch, plan serialization.
"""

import pytest
from datetime import datetime

from src.core.pm_agent import (
    TaskNode,
    WorkPlan,
    TaskStatus,
    PlanStatus,
    EvaluationVerdict,
    ProjectManager,
)


class TestTaskNode:
    """TaskNode lifecycle and dependency resolution."""

    def test_create_minimal(self):
        t = TaskNode(task_id="t1", task_type="test", description="Run test", agent="pto")
        assert t.task_id == "t1"
        assert t.agent == "pto"
        assert t.status == TaskStatus.PENDING.value
        assert t.depends_on == []
        assert t.retry_count == 0
        assert t.max_retries == 2

    def test_create_with_deps(self):
        t = TaskNode(
            task_id="t2", task_type="analyze", description="Analyze",
            agent="legal", depends_on=["t1"], priority=8,
            confidence_required=0.9, max_retries=3,
        )
        assert t.depends_on == ["t1"]
        assert t.priority == 8
        assert t.confidence_required == 0.9
        assert t.max_retries == 3

    def test_mark_started(self):
        t = TaskNode(task_id="t1", task_type="test", description="desc", agent="pto")
        t.mark_started()
        assert t.status == TaskStatus.IN_PROGRESS.value
        assert t.started_at is not None

    def test_mark_completed(self):
        t = TaskNode(task_id="t1", task_type="test", description="desc", agent="pto")
        t.mark_completed("All good")
        assert t.status == TaskStatus.COMPLETED.value
        assert t.completed_at is not None
        assert t.result_summary == "All good"

    def test_mark_failed_retry(self):
        t = TaskNode(task_id="t1", task_type="test", description="desc", agent="pto", max_retries=3)
        t.mark_failed("Error 1")
        assert t.retry_count == 1
        assert t.status == TaskStatus.PENDING.value  # Returned to queue

    def test_mark_failed_exhausted(self):
        t = TaskNode(task_id="t1", task_type="test", description="desc", agent="pto", max_retries=1)
        t.mark_failed("Error")
        assert t.retry_count == 1
        assert t.status == TaskStatus.FAILED.value

    def test_can_start_no_deps(self):
        t = TaskNode(task_id="t1", task_type="test", description="desc", agent="pto")
        assert t.can_start(set())

    def test_can_start_deps_satisfied(self):
        t = TaskNode(task_id="t2", task_type="test", description="desc", agent="smeta", depends_on=["t1"])
        assert t.can_start({"t1"})

    def test_can_start_deps_blocked(self):
        t = TaskNode(task_id="t2", task_type="test", description="desc", agent="smeta", depends_on=["t1", "t3"])
        assert not t.can_start({"t1"})  # t3 missing

    def test_uses_shared_model(self):
        t_pto = TaskNode(task_id="t1", task_type="test", description="d", agent="pto")
        t_archive = TaskNode(task_id="t2", task_type="test", description="d", agent="archive")
        assert t_pto.uses_shared_model is True
        assert t_archive.uses_shared_model is False

    def test_roundtrip_serialization(self):
        t1 = TaskNode(
            task_id="t1", task_type="analyze", description="Analyze contract",
            agent="legal", depends_on=["t0"], priority=9,
            deadline="2026-05-10", confidence_required=0.85, max_retries=3,
            parallel_group="analysis",
        )
        t1.mark_started()
        t1.mark_completed("Done")

        d = t1.to_dict()
        t2 = TaskNode.from_dict(d)

        assert t2.task_id == t1.task_id
        assert t2.agent == t1.agent
        assert t2.priority == t1.priority
        assert t2.depends_on == t1.depends_on
        assert t2.parallel_group == t1.parallel_group
        assert t2.status == TaskStatus.COMPLETED.value
        assert t2.result_summary == "Done"


class TestWorkPlan:
    """WorkPlan construction, dependency resolution, parallel-ready selection."""

    def _make_linear_tasks(self, n=3):
        """Create a linear dependency chain: t1 → t2 → t3."""
        return [TaskNode(
            task_id=f"t{i+1}",
            task_type="test",
            description=f"Task {i+1}",
            agent="pto",
            depends_on=[f"t{i}"] if i > 0 else [],
            priority=10 - i,
        ) for i in range(n)]

    def _make_parallel_tasks(self):
        """Create tasks with a fan-out structure: t1 → t2, t3 (parallel)."""
        return [
            TaskNode(task_id="t1", task_type="register", description="Register", agent="archive", depends_on=[], priority=10),
            TaskNode(task_id="t2", task_type="analyze", description="Analyze docs", agent="pto", depends_on=["t1"], priority=8),
            TaskNode(task_id="t3", task_type="review", description="Legal review", agent="legal", depends_on=["t1"], priority=8),
            TaskNode(task_id="t4", task_type="finalize", description="Finalize", agent="archive", depends_on=["t2", "t3"], priority=5),
        ]

    def test_create_empty(self):
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=[])
        assert plan.plan_id == "P1"
        assert plan.status == PlanStatus.DRAFT.value
        assert plan.get_completion_pct() == 0.0

    def test_get_next_task_first(self):
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=self._make_linear_tasks())
        next_task = plan.get_next_task()
        assert next_task is not None
        assert next_task.task_id == "t1"

    def test_get_next_task_blocked(self):
        """All tasks have pending dependencies — should return None."""
        tasks = [
            TaskNode(task_id="t1", task_type="t", description="d", agent="pto", depends_on=["t0"]),
        ]
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=tasks)
        assert plan.get_next_task() is None

    def test_get_next_task_after_completion(self):
        """After completing t1, t2 should be next."""
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=self._make_linear_tasks())
        plan.tasks[0].mark_completed("OK")
        next_task = plan.get_next_task()
        assert next_task is not None
        assert next_task.task_id == "t2"

    def test_parallel_ready_single(self):
        """Only one task ready at start — t1 with no deps."""
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=self._make_linear_tasks())
        ready = plan.get_parallel_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "t1"

    def test_parallel_ready_fan_out(self):
        """After t1 completes, t2 and t3 should both be ready."""
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=self._make_parallel_tasks())
        plan.tasks[0].mark_completed("OK")
        ready = plan.get_parallel_ready_tasks()
        assert len(ready) == 2
        ids = {t.task_id for t in ready}
        assert ids == {"t2", "t3"}

    def test_parallel_ready_max_parallel(self):
        """max_parallel limits the returned tasks."""
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=self._make_parallel_tasks())
        plan.tasks[0].mark_completed("OK")
        ready = plan.get_parallel_ready_tasks(max_parallel=1)
        assert len(ready) == 1

    def test_parallel_ready_priority_order(self):
        """Higher priority tasks come first."""
        t1 = TaskNode(task_id="t_low", task_type="t", description="d", agent="pto", priority=3)
        t2 = TaskNode(task_id="t_high", task_type="t", description="d", agent="legal", priority=10)
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=[t1, t2])
        ready = plan.get_parallel_ready_tasks()
        assert ready[0].task_id == "t_high"  # priority 10 > 3

    def test_completion_pct(self):
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=self._make_linear_tasks(3))
        assert plan.get_completion_pct() == 0.0
        plan.tasks[0].mark_completed("OK")
        assert plan.get_completion_pct() == pytest.approx(33.3, abs=0.2)
        plan.tasks[1].mark_completed("OK")
        assert plan.get_completion_pct() == pytest.approx(66.7, abs=0.2)
        plan.tasks[2].mark_completed("OK")
        assert plan.get_completion_pct() == 100.0

    def test_get_failed_tasks(self):
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=self._make_linear_tasks(2))
        plan.tasks[0].mark_completed("OK")
        plan.tasks[1].mark_failed("Error")
        plan.tasks[1].mark_failed("Error")  # second retry (max_retries=2)
        failed = plan.get_failed_tasks()
        assert len(failed) == 1
        assert failed[0].task_id == "t2"

    def test_roundtrip_serialization(self):
        plan = WorkPlan(
            plan_id="P1", project_id=42, goal="Build a bridge",
            tasks=self._make_parallel_tasks(),
            compliance_target="344/пр",
            estimated_duration_hours=4.5,
            pm_reasoning="Standard build plan",
        )
        plan.status = PlanStatus.EXECUTING.value
        plan.compliance_delta = {"act_aosr": "missing 2 docs"}
        plan.tasks[0].mark_completed("OK")

        d = plan.to_dict()
        plan2 = WorkPlan.from_dict(d)

        assert plan2.plan_id == "P1"
        assert plan2.project_id == 42
        assert plan2.goal == "Build a bridge"
        assert plan2.compliance_target == "344/пр"
        assert plan2.estimated_duration_hours == 4.5
        assert plan2.pm_reasoning == "Standard build plan"
        assert plan2.status == PlanStatus.EXECUTING.value
        assert plan2.compliance_delta == {"act_aosr": "missing 2 docs"}
        assert len(plan2.tasks) == 4
        assert plan2.tasks[0].status == TaskStatus.COMPLETED.value

    def test_update_compliance_delta(self):
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=[])
        plan.update_compliance_delta({"igs": "incomplete"})
        assert plan.compliance_delta == {"igs": "incomplete"}


class TestPMDispatch:
    """PM agent dispatch and plan lifecycle."""

    def test_dispatch_first_task(self):
        pm = ProjectManager()
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=[
            TaskNode(task_id="t1", task_type="register", description="Register", agent="archive", depends_on=[], priority=10),
        ])
        result = pm.dispatch(plan)
        assert result is not None
        agent_name, task = result
        assert agent_name == "archive"
        assert task.task_id == "t1"
        assert task.status == TaskStatus.IN_PROGRESS.value

    def test_dispatch_completed_plan(self):
        pm = ProjectManager()
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=[
            TaskNode(task_id="t1", task_type="t", description="d", agent="pto"),
        ])
        plan.tasks[0].mark_completed("OK")
        plan.status = PlanStatus.COMPLETED.value
        assert pm.dispatch(plan) is None

    def test_dispatch_aborted_plan(self):
        pm = ProjectManager()
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=[
            TaskNode(task_id="t1", task_type="t", description="d", agent="pto"),
        ])
        plan.status = PlanStatus.ABORTED.value
        assert pm.dispatch(plan) is None

    def test_dispatch_all_blocked(self):
        pm = ProjectManager()
        tasks = [
            TaskNode(task_id="t1", task_type="t", description="d", agent="pto", depends_on=["t0"]),
            TaskNode(task_id="t2", task_type="t", description="d", agent="legal", depends_on=["t1"]),
        ]
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=tasks)
        assert pm.dispatch(plan) is None

    def test_fallback_plan_lot_search(self):
        pm = ProjectManager()
        plan_data = pm._fallback_plan("Test lot", "lot_search")
        plan = pm._build_plan_from_llm(plan_data, 1, "344/пр")
        assert len(plan.tasks) >= 4
        agents = {t.agent for t in plan.tasks}
        assert "legal" in agents
        assert "smeta" in agents
        assert "pto" in agents

    def test_fallback_plan_construction(self):
        pm = ProjectManager()
        plan_data = pm._fallback_plan("Audit", "construction_support")
        plan = pm._build_plan_from_llm(plan_data, 1, "344/пр")
        assert len(plan.tasks) >= 3
        agents = {t.agent for t in plan.tasks}
        assert "archive" in agents
        assert "legal" in agents
        assert "pto" in agents


class TestPMEvaluation:
    """PM evaluation verdicts."""

    def test_auto_accept_high_confidence(self):
        pm = ProjectManager()
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=[
            TaskNode(task_id="t1", task_type="t", description="d", agent="pto", confidence_required=0.6),
        ])
        task = plan.tasks[0]
        verdict = pm.evaluate_result_sync(plan, task, "Result", confidence=0.9)
        assert verdict == EvaluationVerdict.ACCEPT

    def test_auto_retry_low_confidence(self):
        pm = ProjectManager()
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=[
            TaskNode(task_id="t1", task_type="t", description="d", agent="pto", confidence_required=0.6, max_retries=5),
        ])
        task = plan.tasks[0]
        verdict = pm.evaluate_result_sync(plan, task, "Result", confidence=0.05)
        assert verdict == EvaluationVerdict.RETRY

    def test_abort_on_exhausted_retries(self):
        pm = ProjectManager()
        plan = WorkPlan(plan_id="P1", project_id=1, goal="Test", tasks=[
            TaskNode(task_id="t1", task_type="t", description="d", agent="pto", confidence_required=0.6, max_retries=1),
        ])
        task = plan.tasks[0]
        verdict = pm.evaluate_result_sync(plan, task, "Bad result", confidence=0.05)
        assert verdict == EvaluationVerdict.ABORT


class TestWeightedScoring:
    """Weighted scoring from agent signals (pure functions, no LLM)."""

    def test_go_zone(self):
        from src.core.pm_agent import compute_weighted_score
        from src.schemas.verdict import AgentSignal
        signals = [
            AgentSignal(agent_name="legal", signal=0.90, confidence=0.9, weight=0.35, reasoning=""),
            AgentSignal(agent_name="smeta", signal=0.85, confidence=0.9, weight=0.25, reasoning=""),
            AgentSignal(agent_name="pto", signal=0.80, confidence=0.9, weight=0.20, reasoning=""),
            AgentSignal(agent_name="procurement", signal=0.75, confidence=0.9, weight=0.12, reasoning=""),
            AgentSignal(agent_name="logistics", signal=0.70, confidence=0.9, weight=0.08, reasoning=""),
        ]
        result = compute_weighted_score(signals)
        assert result.zone == "go_zone"
        assert result.normalized_score >= 0.70

    def test_grey_zone(self):
        from src.core.pm_agent import compute_weighted_score
        from src.schemas.verdict import AgentSignal
        signals = [
            AgentSignal(agent_name="legal", signal=0.50, confidence=0.8, weight=0.35, reasoning=""),
            AgentSignal(agent_name="smeta", signal=0.45, confidence=0.8, weight=0.25, reasoning=""),
            AgentSignal(agent_name="pto", signal=0.50, confidence=0.8, weight=0.20, reasoning=""),
            AgentSignal(agent_name="procurement", signal=0.40, confidence=0.8, weight=0.12, reasoning=""),
            AgentSignal(agent_name="logistics", signal=0.45, confidence=0.8, weight=0.08, reasoning=""),
        ]
        result = compute_weighted_score(signals)
        assert result.zone == "grey_zone"

    def test_no_go_zone(self):
        from src.core.pm_agent import compute_weighted_score
        from src.schemas.verdict import AgentSignal
        signals = [
            AgentSignal(agent_name="legal", signal=0.10, confidence=0.8, weight=0.35, reasoning=""),
            AgentSignal(agent_name="smeta", signal=0.15, confidence=0.8, weight=0.25, reasoning=""),
            AgentSignal(agent_name="pto", signal=0.20, confidence=0.8, weight=0.20, reasoning=""),
            AgentSignal(agent_name="procurement", signal=0.10, confidence=0.8, weight=0.12, reasoning=""),
            AgentSignal(agent_name="logistics", signal=0.15, confidence=0.8, weight=0.08, reasoning=""),
        ]
        result = compute_weighted_score(signals)
        assert result.zone == "no_go_zone"

    def test_normalized_score_range(self):
        """Property: normalized_score always in [0, 1]."""
        from src.core.pm_agent import compute_weighted_score
        from src.schemas.verdict import AgentSignal
        import random
        random.seed(42)
        for _ in range(50):
            signals = [
                AgentSignal(
                    agent_name=name, signal=random.random(),
                    confidence=random.random(), weight=random.random(), reasoning=""
                )
                for name in ["legal", "smeta", "pto", "procurement", "logistics"]
            ]
            result = compute_weighted_score(signals)
            assert 0.0 <= result.normalized_score <= 1.0
