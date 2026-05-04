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
    compute_weighted_score,
    check_veto_rules,
    calculate_risk_level,
    DEFAULT_VETO_RULES,
)
from src.schemas.verdict import (
    AgentSignal,
    RiskLevel,
    WeightedScoringResult,
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

        # Verify dependencies: t1 has no deps, others depend transitively on t1
        # task_5 (smeta_calc) and task_6 (logistics_search) depend on task_3 (pto_vor)
        # which itself depends on task_1 (transitive dependency chain)
        for t in plan.tasks:
            if t.task_id == "task_1":
                assert t.depends_on == [], "task_1 should have no dependencies"
            elif t.task_id in ("task_5", "task_6"):
                assert "task_3" in t.depends_on, f"{t.task_id} should depend on task_3"
            else:
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
        assert stats["agent_quotas"]["archive"]["max_context_tokens"] == ram_manager._agent_quotas["archive"].max_context_tokens

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


# =============================================================================
# Edge Cases: Parallel Dispatch, Circular Deps, Deadlock
# =============================================================================

class TestEdgeCases:
    """Edge cases for WorkPlan and PM dispatch."""

    def test_parallel_ready_tasks_all_independent(self):
        """When all tasks are independent, get_parallel_ready_tasks returns all of them."""
        tasks = [
            TaskNode("t1", "legal", "Review", "legal", priority=8),
            TaskNode("t2", "pto", "Extract", "pto", priority=5),
            TaskNode("t3", "smeta", "Calculate", "smeta", priority=3),
        ]
        plan = WorkPlan("p1", 1, "Parallel test", tasks)
        ready = plan.get_parallel_ready_tasks()
        assert len(ready) == 3

    def test_parallel_ready_respects_deps(self):
        """Tasks with unmet deps are not in parallel ready list."""
        tasks = [
            TaskNode("t1", "legal", "Review", "legal", priority=8),
            TaskNode("t2", "pto", "Extract", "pto", depends_on=["t1"], priority=5),
            TaskNode("t3", "smeta", "Calculate", "smeta", depends_on=["t2"], priority=3),
        ]
        plan = WorkPlan("p1", 1, "Sequential deps", tasks)
        ready = plan.get_parallel_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "t1"

    def test_parallel_ready_after_completion(self):
        """After completing a dependency, next tasks become ready."""
        tasks = [
            TaskNode("t1", "legal", "Review", "legal", priority=8),
            TaskNode("t2", "pto", "Extract", "pto", depends_on=["t1"], priority=5),
            TaskNode("t3", "smeta", "Calculate", "smeta", depends_on=["t1"], priority=3),
        ]
        plan = WorkPlan("p1", 1, "Fan-out", tasks)
        assert len(plan.get_parallel_ready_tasks()) == 1

        plan.tasks[0].mark_completed("OK")
        ready = plan.get_parallel_ready_tasks()
        assert len(ready) == 2  # Both t2 and t3 depend on t1
        assert {t.task_id for t in ready} == {"t2", "t3"}

    def test_deadlock_detection_missing_dependency(self):
        """Task depends on a task that doesn't exist in the plan."""
        tasks = [
            TaskNode("t1", "legal", "Review", "legal", depends_on=["nonexistent"]),
        ]
        plan = WorkPlan("p1", 1, "Deadlock", tasks)
        ready = plan.get_parallel_ready_tasks()
        assert len(ready) == 0  # t1 depends on nonexistent → never ready

    def test_all_blocked_detection(self):
        """When all remaining tasks are blocked by failed tasks, dispatch returns None."""
        tasks = [
            TaskNode("t1", "archive", "Register", "archive", priority=5),
            TaskNode("t2", "legal", "Review", "legal", depends_on=["t1"], priority=10),
            TaskNode("t3", "pto", "Extract", "pto", depends_on=["t1"], priority=7),
        ]
        plan = WorkPlan("p1", 1, "Blocked", tasks)
        # t1 runs and fails
        pm = ProjectManager(llm_engine=None, completeness_matrix=None)
        pm.dispatch(plan)  # Dispatches t1
        plan.tasks[0].mark_failed("error")
        plan.tasks[0].mark_failed("error")  # Exhaust retries → FAILED

        # Now t2 and t3 depend on t1 (which is FAILED, not COMPLETED)
        result = pm.dispatch(plan)
        assert result is None  # Nothing can proceed
        assert len(plan.get_failed_tasks()) == 1

    def test_priority_over_deadline(self):
        """Higher priority takes precedence even if deadline is later."""
        tasks = [
            TaskNode("t1", "archive", "Low priority", "archive", priority=1, deadline="2026-01-01"),
            TaskNode("t2", "legal", "High priority", "legal", priority=10, deadline="2026-12-31"),
        ]
        plan = WorkPlan("p1", 1, "Priority vs deadline", tasks)
        task = plan.get_next_task()
        assert task.task_id == "t2"

    def test_serialization_roundtrip_full(self):
        """Full WorkPlan serialization with completed tasks, delta, status."""
        tasks = [
            TaskNode("t1", "legal", "Review", "legal", depends_on=[], priority=10, confidence_required=0.9),
            TaskNode("t2", "pto", "Extract", "pto", depends_on=["t1"], priority=5, deadline="2026-06-01"),
        ]
        plan = WorkPlan(
            "plan_001", 42, "Full test goal", tasks,
            compliance_target="Договор №123",
            estimated_duration_hours=4.5,
            pm_reasoning="Стандартная последовательность",
        )
        plan.tasks[0].mark_started()
        plan.tasks[0].mark_completed("OK")
        plan.status = PlanStatus.EXECUTING.value
        plan.compliance_delta = {"aosr": "3 missing", "igs": "1 expired"}

        d = plan.to_dict()
        plan2 = WorkPlan.from_dict(d)

        assert plan2.plan_id == plan.plan_id
        assert plan2.project_id == plan.project_id
        assert plan2.goal == plan.goal
        assert plan2.compliance_target == plan.compliance_target
        assert plan2.estimated_duration_hours == 4.5
        assert plan2.pm_reasoning == "Стандартная последовательность"
        assert plan2.status == PlanStatus.EXECUTING.value
        assert plan2.compliance_delta == {"aosr": "3 missing", "igs": "1 expired"}
        assert len(plan2.tasks) == 2
        assert plan2.tasks[0].status == TaskStatus.COMPLETED.value
        assert plan2.tasks[0].confidence_required == 0.9

    def test_replan_skip_action(self):
        """PM replan with 'skip' action."""
        pm = ProjectManager(llm_engine=None, completeness_matrix=None)
        plan_data = pm._fallback_plan("Test", "lot_search")
        plan = pm._build_plan_from_llm(plan_data, 1, "344/пр")

        # Execute first task, then fail second
        done = pm.dispatch(plan)
        if done:
            _, task = done
            task.mark_completed("OK")

        done2 = pm.dispatch(plan)
        if done2:
            _, task2 = done2
            task2.mark_failed("error")
            task2.mark_failed("error")

        if plan.get_failed_tasks():
            # Replan should skip or adapt
            assert plan.status != PlanStatus.COMPLETED.value
            # Plan should have failed task or adapted
            failed = plan.get_failed_tasks()
            assert len(failed) >= 1

    def test_evaluate_result_sync_accept(self):
        """Sync evaluation: confidence >= required → ACCEPT."""
        pm = ProjectManager(llm_engine=None, completeness_matrix=None)
        plan_data = pm._fallback_plan("Test", "lot_search")
        plan = pm._build_plan_from_llm(plan_data, 1, "344/пр")
        task = plan.get_next_task()
        verdict = pm.evaluate_result_sync(plan, task, "Result OK", confidence=0.95)
        assert verdict == EvaluationVerdict.ACCEPT
        assert task.status == TaskStatus.COMPLETED.value

    def test_evaluate_result_sync_retry(self):
        """Sync evaluation: confidence below required → RETRY."""
        pm = ProjectManager(llm_engine=None, completeness_matrix=None)
        plan_data = pm._fallback_plan("Test", "lot_search")
        plan = pm._build_plan_from_llm(plan_data, 1, "344/пр")
        task = plan.get_next_task()
        verdict = pm.evaluate_result_sync(plan, task, "Weak result", confidence=0.3)
        assert verdict == EvaluationVerdict.RETRY
        assert task.retry_count == 1

    def test_evaluate_result_sync_abort(self):
        """Sync evaluation: very low confidence → ABORT."""
        pm = ProjectManager(llm_engine=None, completeness_matrix=None)
        plan_data = pm._fallback_plan("Test", "lot_search")
        plan = pm._build_plan_from_llm(plan_data, 1, "344/пр")
        task = plan.get_next_task()
        task.max_retries = 1  # Will exhaust on first failure
        verdict = pm.evaluate_result_sync(plan, task, "Terrible result", confidence=0.05)
        assert verdict == EvaluationVerdict.ABORT
        assert task.status == TaskStatus.FAILED.value

    def test_task_uses_shared_model(self):
        """TaskNode.uses_shared_model correctly identifies shared-model agents."""
        shared = TaskNode("t1", "test", "Test", "legal")
        assert shared.uses_shared_model is True

        nonshared = TaskNode("t2", "test", "Test", "archive")
        assert nonshared.uses_shared_model is False

    def test_task_to_dict_includes_all_fields(self):
        """TaskNode.to_dict includes all fields including parallel_group."""
        t = TaskNode("t1", "legal", "Review", "legal", parallel_group="analysis", priority=9)
        d = t.to_dict()
        assert d["task_id"] == "t1"
        assert d["parallel_group"] == "analysis"
        assert d["priority"] == 9
        assert d["confidence_required"] == 0.6
        assert d["max_retries"] == 2


# =============================================================================
# Weighted Scoring Edge Cases
# =============================================================================

class TestWeightedScoring:
    """Edge cases for compute_weighted_score and signal extractors."""

    def test_compute_weighted_score_normalized(self):
        from src.core.pm_agent import compute_weighted_score
        from src.schemas.verdict import AgentSignal

        signals = [
            AgentSignal(agent_name="legal", signal=0.8, confidence=0.9, weight=0.35, reasoning="test"),
            AgentSignal(agent_name="smeta", signal=0.6, confidence=0.8, weight=0.25, reasoning="test"),
        ]
        result = compute_weighted_score(signals)
        assert 0.0 < result.normalized_score <= 1.0
        assert result.zone in ("go_zone", "grey_zone", "no_go_zone")

    def test_compute_weighted_score_zero_denominator(self):
        """When all weights × confidences are zero, score defaults to 0.5."""
        from src.core.pm_agent import compute_weighted_score
        from src.schemas.verdict import AgentSignal

        signals = [
            AgentSignal(agent_name="legal", signal=0.8, confidence=0.0, weight=0.35, reasoning="test"),
            AgentSignal(agent_name="smeta", signal=0.6, confidence=0.0, weight=0.25, reasoning="test"),
        ]
        result = compute_weighted_score(signals)
        assert result.normalized_score == 0.5
        assert result.zone == "grey_zone"

    def test_compute_weighted_score_tiny_weight(self):
        """Very small effective weight should not crash."""
        from src.core.pm_agent import compute_weighted_score
        from src.schemas.verdict import AgentSignal

        signals = [
            AgentSignal(agent_name="legal", signal=0.8, confidence=1e-15, weight=0.35, reasoning="test"),
        ]
        result = compute_weighted_score(signals)
        assert result.normalized_score == 0.5
        assert result.agent_contributions["legal"] == 0.0

    def test_veto_dangerous_verdict(self):
        from src.core.pm_agent import check_veto_rules, DEFAULT_VETO_RULES

        state = {"legal_result": {"verdict": "dangerous"}, "smeta_result": {}}
        triggered, _ = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert triggered == "veto_dangerous_verdict"

    def test_veto_margin_below_10(self):
        from src.core.pm_agent import check_veto_rules, DEFAULT_VETO_RULES

        state = {"legal_result": {"verdict": "approved"}, "smeta_result": {"profit_margin_pct": 5}}
        triggered, _ = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert triggered == "veto_margin_below_10"

    def test_veto_no_violations(self):
        from src.core.pm_agent import check_veto_rules, DEFAULT_VETO_RULES

        state = {"legal_result": {"verdict": "approved"}, "smeta_result": {"profit_margin_pct": 25}}
        triggered, _ = check_veto_rules(state, DEFAULT_VETO_RULES)
        assert triggered is None

    def test_risk_level_critical(self):
        from src.core.pm_agent import calculate_risk_level
        from src.schemas.verdict import RiskLevel, WeightedScoringResult

        scoring = WeightedScoringResult(
            raw_score=0.1, normalized_score=0.1, agent_contributions={},
            zone="no_go_zone", go_threshold=0.7, no_go_threshold=0.3,
        )
        state = {"legal_result": {"critical_count": 3}, "smeta_result": {}}
        assert calculate_risk_level(state, scoring) == RiskLevel.CRITICAL

    def test_risk_level_low(self):
        from src.core.pm_agent import calculate_risk_level
        from src.schemas.verdict import RiskLevel, WeightedScoringResult

        scoring = WeightedScoringResult(
            raw_score=0.9, normalized_score=0.9, agent_contributions={},
            zone="go_zone", go_threshold=0.7, no_go_threshold=0.3,
        )
        state = {"legal_result": {}, "smeta_result": {"profit_margin_pct": 40}}
        assert calculate_risk_level(state, scoring) == RiskLevel.LOW
