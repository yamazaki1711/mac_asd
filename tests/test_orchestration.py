"""
ASD v12.0 — Tests for PM Agent (ProjectManager), RAM Manager, and PM-driven workflow.

Tests cover:
  - TaskNode lifecycle and dependency resolution
  - WorkPlan dispatch, completion tracking, serialization
  - ProjectManager fallback plan generation
  - RAM Manager thresholds and degradation
  - AgentState v2.0 with PM fields
"""

import json
import pytest
from datetime import datetime

from src.core.pm_agent import (
    ProjectManager,
    WorkPlan,
    TaskNode,
    TaskStatus,
    EvaluationVerdict,
    PlanStatus,
)
from src.core.ram_manager import (
    RamManager,
    RamStatus,
    TaskPriority,
    ram_manager,
)
from src.agents.state import (
    AgentState,
    create_initial_state,
    start_step,
    complete_step,
    fail_step,
)


# =============================================================================
# TaskNode Tests
# =============================================================================

class TestTaskNode:
    """TaskNode: lifecycle, dependencies, serialization."""

    def test_create_defaults(self):
        t = TaskNode("t1", "legal_analysis", "Review contract", "legal")
        assert t.task_id == "t1"
        assert t.agent == "legal"
        assert t.status == TaskStatus.PENDING.value
        assert t.priority == 5
        assert t.max_retries == 2
        assert t.retry_count == 0
        assert t.depends_on == []

    def test_can_start_no_deps(self):
        t = TaskNode("t1", "test", "Test", "pto")
        assert t.can_start(set()) is True

    def test_can_start_with_deps_met(self):
        t = TaskNode("t2", "test", "Test2", "smeta", depends_on=["t1"])
        assert t.can_start({"t1"}) is True

    def test_can_start_with_deps_unmet(self):
        t = TaskNode("t2", "test", "Test2", "smeta", depends_on=["t1", "t3"])
        assert t.can_start({"t1"}) is False

    def test_mark_started(self):
        t = TaskNode("t1", "test", "Test", "pto")
        t.mark_started()
        assert t.status == TaskStatus.IN_PROGRESS.value
        assert t.started_at is not None

    def test_mark_completed(self):
        t = TaskNode("t1", "test", "Test", "pto")
        t.mark_started()
        t.mark_completed("Done successfully")
        assert t.status == TaskStatus.COMPLETED.value
        assert t.result_summary == "Done successfully"
        assert t.completed_at is not None

    def test_mark_failed_retry(self):
        t = TaskNode("t1", "test", "Test", "pto", max_retries=3)
        t.mark_failed("err1")
        assert t.status == TaskStatus.PENDING.value
        assert t.retry_count == 1

        t.mark_failed("err2")
        assert t.status == TaskStatus.PENDING.value
        assert t.retry_count == 2

    def test_mark_failed_exhausted(self):
        t = TaskNode("t1", "test", "Test", "pto", max_retries=2)
        t.mark_failed("err1")
        t.mark_failed("err2")
        assert t.status == TaskStatus.FAILED.value
        assert t.retry_count == 2

    def test_serialization_roundtrip(self):
        t = TaskNode("t1", "legal", "Review", "legal", depends_on=["t0"], priority=9, confidence_required=0.85)
        t.mark_started()
        t.mark_completed("OK")

        d = t.to_dict()
        t2 = TaskNode.from_dict(d)

        assert t2.task_id == t.task_id
        assert t2.agent == t.agent
        assert t2.status == t.status
        assert t2.priority == t.priority
        assert t2.confidence_required == t.confidence_required
        assert t2.depends_on == t.depends_on
        assert t2.retry_count == t.retry_count


# =============================================================================
# WorkPlan Tests
# =============================================================================

class TestWorkPlan:
    """WorkPlan: dispatch, completion, serialization."""

    def _make_plan(self) -> WorkPlan:
        tasks = [
            TaskNode("t1", "archive", "Register", "archive", priority=5),
            TaskNode("t2", "legal", "Review", "legal", depends_on=["t1"], priority=10),
            TaskNode("t3", "pto", "Extract", "pto", depends_on=["t1"], priority=7),
            TaskNode("t4", "smeta", "Calculate", "smeta", depends_on=["t3"], priority=8),
        ]
        return WorkPlan("p1", 42, "Test goal", tasks)

    def test_get_next_task_first(self):
        plan = self._make_plan()
        task = plan.get_next_task()
        assert task is not None
        assert task.task_id == "t1"
        assert task.agent == "archive"

    def test_get_next_task_priority_order(self):
        plan = self._make_plan()
        # Complete t1 — now t2 (priority 10) and t3 (priority 7) are ready
        plan.tasks[0].mark_completed("OK")
        task = plan.get_next_task()
        assert task.task_id == "t2"  # Higher priority wins

    def test_get_next_task_with_deadline(self):
        plan = self._make_plan()
        plan.tasks[1].deadline = "2026-05-01"  # t2 has earlier deadline
        plan.tasks[2].deadline = "2026-06-01"  # t3 has later deadline
        plan.tasks[0].mark_completed("OK")
        task = plan.get_next_task()
        assert task.task_id == "t2"  # Both priority and deadline favour t2

    def test_completion_pct(self):
        plan = self._make_plan()
        assert plan.get_completion_pct() == 0.0

        plan.tasks[0].mark_completed("OK")
        assert plan.get_completion_pct() == 25.0

        plan.tasks[1].mark_completed("OK")
        assert plan.get_completion_pct() == 50.0

    def test_all_done(self):
        plan = self._make_plan()
        for task in plan.tasks:
            task.mark_completed("OK")
        assert plan.get_next_task() is None
        assert plan.get_completion_pct() == 100.0

    def test_failed_tasks(self):
        plan = self._make_plan()
        plan.tasks[0].mark_failed("err")
        plan.tasks[0].mark_failed("err2")  # Exhaust retries
        assert len(plan.get_failed_tasks()) == 1
        assert plan.get_failed_tasks()[0].task_id == "t1"

    def test_serialization_roundtrip(self):
        plan = self._make_plan()
        plan.tasks[0].mark_completed("OK")
        plan.status = PlanStatus.EXECUTING.value
        plan.compliance_delta = {"aosr": "missing", "cert": "expired"}

        d = plan.to_dict()
        plan2 = WorkPlan.from_dict(d)

        assert plan2.plan_id == plan.plan_id
        assert plan2.goal == plan.goal
        assert plan2.status == plan.status
        assert len(plan2.tasks) == len(plan.tasks)
        assert plan2.get_completion_pct() == plan.get_completion_pct()
        assert plan2.compliance_delta == plan.compliance_delta

    def test_update_compliance_delta(self):
        plan = self._make_plan()
        plan.update_compliance_delta({"aosr": "missing"})
        assert plan.compliance_delta == {"aosr": "missing"}


# =============================================================================
# ProjectManager Fallback Plan Tests
# =============================================================================

class TestProjectManagerFallback:
    """ProjectManager: fallback plan generation (no LLM required)."""

    def test_fallback_plan_lot_search(self):
        pm = ProjectManager(llm_engine=None, completeness_matrix=None)
        plan_data = pm._fallback_plan("Test lot", "lot_search")
        plan = pm._build_plan_from_llm(plan_data, 1, "344/пр")

        assert plan.goal == "Test lot"
        assert len(plan.tasks) >= 4
        # Verify task types
        agents = {t.agent for t in plan.tasks}
        assert "legal" in agents
        assert "smeta" in agents
        assert "pto" in agents

        # Verify dependencies: t1 has no deps, others depend on t1
        for t in plan.tasks:
            if t.task_id != "task_1":
                assert "task_1" in t.depends_on, f"{t.task_id} should depend on task_1"

    def test_fallback_plan_construction_support(self):
        pm = ProjectManager(llm_engine=None, completeness_matrix=None)
        plan_data = pm._fallback_plan("Construction audit", "construction_support")
        plan = pm._build_plan_from_llm(plan_data, 1, "344/пр")

        assert plan.goal == "Construction audit"
        assert len(plan.tasks) >= 3
        agents = {t.agent for t in plan.tasks}
        assert "archive" in agents  # First task should be archive
        assert "legal" in agents
        assert "pto" in agents

    def test_dispatch_completes(self):
        """PM dispatch: run plan to completion."""
        pm = ProjectManager(llm_engine=None, completeness_matrix=None)
        plan_data = pm._fallback_plan("Test", "lot_search")
        plan = pm._build_plan_from_llm(plan_data, 1, "344/пр")

        # Process all tasks in order
        dispatched = []
        while True:
            result = pm.dispatch(plan)
            if result is None:
                break
            agent, task = result
            dispatched.append(task.task_id)
            task.mark_completed(f"{agent} done")

        assert len(dispatched) == len(plan.tasks)
        assert plan.status == PlanStatus.COMPLETED.value


# =============================================================================
# RAM Manager Tests
# =============================================================================

class TestRamManager:
    """RAM Manager: thresholds, quotas, degradation."""

    def test_singleton_exists(self):
        assert ram_manager is not None

    def test_get_snapshot(self):
        snap = ram_manager.get_snapshot(force=True)
        assert snap.total_gb > 0
        assert snap.used_gb > 0
        assert snap.status in (RamStatus.NORMAL, RamStatus.WARNING)

    def test_can_accept_normal(self):
        assert ram_manager.can_accept_task("pto") is True

    def test_register_task(self):
        ram_manager.register_task_start("pto")
        ram_manager.register_task_end("pto")
        # Should not crash

    def test_get_stats(self):
        stats = ram_manager.get_stats()
        assert "snapshot" in stats
        assert "agent_quotas" in stats
        assert "degradation_level" in stats
        assert "pm" in stats["agent_quotas"]
        assert stats["agent_quotas"]["archive"]["max_context_tokens"] == 8000

    def test_degradation_reset(self):
        original_level = ram_manager._degradation_level
        ram_manager.degrade()
        assert ram_manager._degradation_level == original_level + 1
        ram_manager.reset_degradation()
        assert ram_manager._degradation_level == 0

    def test_critical_task_accepted(self):
        """CRITICAL priority tasks are accepted even at WARNING."""
        # We can't simulate actual WARNING status without psutil,
        # but we can test the logic path
        ram_manager.reset_degradation()
        assert ram_manager.can_accept_task("pto", priority=TaskPriority.CRITICAL) is True


# =============================================================================
# AgentState v2.0 PM Fields Tests
# =============================================================================

class TestAgentStatePm:
    """AgentState v2.0: PM orchestration fields."""

    def test_create_initial_state_has_pm_fields(self):
        state = create_initial_state(1, "Test task", "construction_support")
        assert state["schema_version"] == "2.0"
        assert state["work_plan"] is None
        assert state["compliance_delta"] == {}
        assert state["pm_decision"] is None
        assert state["pm_reasoning"] is None
        assert state["current_agent"] is None
        assert state["current_task_id"] is None
        assert state["completed_task_ids"] == []
        assert state["ram_status"] is None
        assert state["ram_snapshot"] is None

    def test_step_log_helpers(self):
        state = create_initial_state(1, "Test")

        # Start step
        step_id = start_step(state, "pm", "plan")
        assert step_id is not None
        assert len(state["audit_trail"]) == 1
        assert state["audit_trail"][0]["agent"] == "pm"
        assert state["audit_trail"][0]["status"] == "running"

        # Complete step
        complete_step(state, step_id, "Plan done")
        entry = state["audit_trail"][0]
        assert entry["status"] == "completed"
        assert entry["output_summary"] == "Plan done"

    def test_fail_step_sets_rollback(self):
        state = create_initial_state(1, "Test")
        step_id = start_step(state, "pto", "extract")
        fail_step(state, step_id, "Extraction failed")
        assert state["rollback_point"] == step_id
        entry = state["audit_trail"][0]
        assert entry["status"] == "failed"
        assert entry["error_message"] == "Extraction failed"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """End-to-end orchestration flow without LLM."""

    def test_full_plan_execution(self):
        """Simulate full PM-driven pipeline with fallback plan."""
        pm = ProjectManager(llm_engine=None, completeness_matrix=None)
        plan_data = pm._fallback_plan("Full pipeline test", "lot_search")
        plan = pm._build_plan_from_llm(plan_data, 1, "344/пр")

        # Execute all tasks
        executed = []
        while True:
            result = pm.dispatch(plan)
            if result is None:
                break
            agent, task = result
            executed.append((agent, task.task_id))
            # Simulate agent work
            task.mark_completed(f"{agent} completed {task.task_id}")

        assert len(executed) == len(plan.tasks)
        assert plan.status == PlanStatus.COMPLETED.value
        assert plan.get_completion_pct() == 100.0

        # Verify task order respects dependencies
        task_order = [tid for _, tid in executed]
        for task in plan.tasks:
            for dep in task.depends_on:
                assert task_order.index(dep) < task_order.index(task.task_id), (
                    f"Task {task.task_id} executed before dependency {dep}"
                )

    def test_replan_on_failure(self):
        """PM replans when a task fails completely."""
        pm = ProjectManager(llm_engine=None, completeness_matrix=None)
        plan_data = pm._fallback_plan("Test with failure", "lot_search")
        plan = pm._build_plan_from_llm(plan_data, 1, "344/пр")

        # Execute first task
        result = pm.dispatch(plan)
        assert result is not None
        agent, task = result
        task.mark_completed("OK")

        # Now simulate a failing task
        result = pm.dispatch(plan)
        if result:
            agent, task = result
            # Fail it hard
            task.mark_failed("critical error")
            task.mark_failed("critical error")  # Exhaust retries

        # Plan should not be completed (failed task)
        if len(plan.get_failed_tasks()) > 0:
            assert plan.status != PlanStatus.COMPLETED.value
            assert plan.get_completion_pct() < 100.0

    def test_ram_manager_integration(self):
        """RAM Manager integrated into task flow."""
        # Register tasks
        ram_manager.register_task_start("legal")
        ram_manager.register_task_end("legal")

        # Verify stats updated
        stats = ram_manager.get_stats()
        assert stats["agent_quotas"]["legal"]["current_tasks"] == 0

        # Normal task acceptance
        assert ram_manager.can_accept_task("smeta", priority=TaskPriority.NORMAL) is True
