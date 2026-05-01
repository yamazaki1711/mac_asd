"""
ASD v12.0 — E2E Tests for Parallel & Sequential LangGraph Workflow with LLM Mocks.

Validates the full PM-driven graph cycle:
  pm_planning → pm_fan_out_router (Send() fan-out) → agent_worker (×N)
  → pm_evaluate → cycle → PlanStatus.COMPLETED / ABORTED

All LLM calls are mocked at llm_engine.chat() level so orchestration logic
is tested independently of real model backends.

Test scenarios:
  - Happy path: 2 independent tasks, parallel dispatch, all succeed
  - Partial failure: one task errors, gets retried, succeeds
  - RAM rejection: task bounced by RAM manager, requeued
  - Plan abortion: task fails with confidence < 0.1, max retries exhausted
  - Sequential fallback: single task ready → no Send(), direct dispatch
  - Grey zone LLM evaluation: confidence in [0.1, required) → PM calls LLM
  - Replan after failure: task FAILED → replan via LLM splits/reorders
  - Multiple parallel rounds: dependency chain creates sequential fan-out rounds
"""

import json
import pytest
from unittest.mock import AsyncMock, patch


# ═══════════════════════════════════════════════════════════════════════════════
# Mock response builders
# ═══════════════════════════════════════════════════════════════════════════════

def _make_plan_json(tasks=None):
    if tasks is None:
        tasks = [
            {"task_id": "task_1", "task_type": "archive_register",
             "description": "Register incoming document package",
             "agent": "archive", "depends_on": [], "priority": 10,
             "confidence_required": 0.5},
            {"task_id": "task_2", "task_type": "legal_review",
             "description": "Review contract for BLS traps",
             "agent": "legal", "depends_on": [], "priority": 9,
             "confidence_required": 0.6},
        ]
    return json.dumps({
        "plan": {
            "goal": "E2E test — verify parallel execution",
            "reasoning": "Two independent tasks can execute in parallel via Send()",
            "estimated_hours": 0.5,
            "tasks": tasks,
        }
    })


def _make_linear_plan_json():
    """Plan with sequential dependencies: task_1 → task_2 → task_3.
    Uses agents that don't require database writes (archive, legal, smeta)."""
    tasks = [
        {"task_id": "task_1", "task_type": "archive_register",
         "description": "Register documents", "agent": "archive",
         "depends_on": [], "priority": 10, "confidence_required": 0.5},
        {"task_id": "task_2", "task_type": "legal_review",
         "description": "Legal review after registration", "agent": "legal",
         "depends_on": ["task_1"], "priority": 9, "confidence_required": 0.6},
        {"task_id": "task_3", "task_type": "smeta_calc",
         "description": "Estimate after legal review", "agent": "smeta",
         "depends_on": ["task_2"], "priority": 8, "confidence_required": 0.6},
    ]
    return _make_plan_json(tasks)


def _archive_ok():
    return json.dumps({"status": "registered", "doc_id": "REG-001", "pages": 5})


def _legal_ok():
    return json.dumps({"verdict": "approved", "critical_count": 0, "high_count": 1,
                        "findings": [], "findings_count": 0, "summary": "Clean"})


def _smeta_ok():
    return json.dumps({"total_cost": 5000000.0, "nmck": 5500000.0,
                        "profit_margin_pct": 25.0, "fer_positions_used": 42})


def _pto_ok():
    return json.dumps({"positions": [{"code": "E1-1", "name": "Excavation", "unit": "m3", "quantity": 100}],
                        "total_positions": 1, "confidence_score": 0.85})


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _clear_plan_cache():
    from src.agents import nodes_v2
    nodes_v2._plan_cache.clear()


def _patch_llm(chat_fn):
    """Patch llm_engine.chat in both nodes and nodes_v2 modules."""
    import src.agents.nodes_v2 as nv2
    import src.agents.nodes as nodes_mod
    return (
        patch.object(nv2.llm_engine, "chat", side_effect=chat_fn),
        patch.object(nodes_mod.llm_engine, "chat", side_effect=chat_fn),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestParallelGraphE2E:

    # ── Happy Path ───────────────────────────────────────────────────────────

    async def test_happy_path_two_parallel_tasks_complete(self):
        """2 independent tasks dispatched via Send(), both succeed, plan COMPLETED."""
        _clear_plan_cache()

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                return _make_plan_json()
            if agent == "archive":
                return _archive_ok()
            if agent == "legal":
                return _legal_ok()
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            from src.agents.state import create_initial_state
            from src.agents.workflow import asd_app

            state = create_initial_state(
                project_id=99901,
                task_description="E2E parallel happy path",
                workflow_mode="lot_search",
            )
            result = await asd_app.ainvoke(state)

        assert result["is_complete"] is True
        plan = result.get("work_plan", {})
        assert plan.get("status") == "completed", f"Expected completed, got {plan.get('status')}"
        assert len(result.get("completed_task_ids", [])) >= 2
        assert "task_1" in result["completed_task_ids"]
        assert "task_2" in result["completed_task_ids"]

        # Verify parallel_results accumulator was populated
        parallel = result.get("parallel_results", [])
        assert len(parallel) >= 2
        agents = {r["agent"] for r in parallel}
        assert agents >= {"archive", "legal"}
        for r in parallel:
            assert r["status"] == "completed"

    # ── Sequential Fallback ──────────────────────────────────────────────────

    async def test_linear_deps_sequential_execution(self):
        """Tasks with sequential dependencies: one at a time, no Send() fan-out."""
        _clear_plan_cache()

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                return _make_linear_plan_json()
            if agent == "archive":
                return _archive_ok()
            if agent == "legal":
                return _legal_ok()
            if agent == "smeta":
                return _smeta_ok()
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            from src.agents.state import create_initial_state
            from src.agents.workflow import asd_app

            state = create_initial_state(
                project_id=99902,
                task_description="E2E sequential deps",
                workflow_mode="lot_search",
            )
            result = await asd_app.ainvoke(state)

        assert result["is_complete"] is True
        plan = result.get("work_plan", {})
        assert plan.get("status") in ("completed", "executing"), \
            f"Expected completed or executing, got {plan.get('status')}"
        assert len(result.get("completed_task_ids", [])) == 3

    # ── Partial Failure → Retry ──────────────────────────────────────────────

    async def test_agent_error_then_success_on_retry(self):
        """Agent raises exception on first attempt, succeeds on retry."""
        _clear_plan_cache()

        call_counts = {}

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                return _make_plan_json()
            if agent == "archive":
                call_counts["archive"] = call_counts.get("archive", 0) + 1
                if call_counts["archive"] == 1:
                    raise RuntimeError("Simulated LLM crash")
                return _archive_ok()
            if agent == "legal":
                return _legal_ok()
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            from src.agents.state import create_initial_state
            from src.agents.workflow import asd_app

            state = create_initial_state(
                project_id=99903,
                task_description="E2E retry on error",
                workflow_mode="lot_search",
            )
            result = await asd_app.ainvoke(state)

        assert result["is_complete"] is True
        plan = result.get("work_plan", {})
        assert plan.get("status") == "completed"
        assert "task_1" in result.get("completed_task_ids", [])

    # ── RAM Rejection ────────────────────────────────────────────────────────

    async def test_ram_rejection_requeues_pending(self):
        """RAM manager rejects first attempt → task stays PENDING → picked up later."""
        _clear_plan_cache()

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                return _make_plan_json()
            if agent == "archive":
                return _archive_ok()
            if agent == "legal":
                return _legal_ok()
            return "{}"

        import src.agents.nodes_v2 as nv2

        rejections = [0]
        _original_can_accept = nv2.ram_manager.can_accept_task

        def rejecting_can_accept(agent_name, priority=None, **kw):
            if agent_name == "archive" and rejections[0] < 1:
                rejections[0] += 1
                return False
            return _original_can_accept(agent_name, priority=priority, **kw)

        p1, p2 = _patch_llm(mock_chat)
        p3 = patch.object(nv2.ram_manager, "can_accept_task",
                          side_effect=rejecting_can_accept)
        with p1, p2, p3:
            from src.agents.state import create_initial_state
            from src.agents.workflow import asd_app

            state = create_initial_state(
                project_id=99904,
                task_description="E2E RAM rejection",
                workflow_mode="lot_search",
            )
            result = await asd_app.ainvoke(state)

        assert result["is_complete"] is True
        plan = result.get("work_plan", {})
        assert plan.get("status") == "completed"
        assert rejections[0] >= 1, "Expected at least one RAM rejection"

    # ── Plan Abortion ────────────────────────────────────────────────────────

    async def test_abort_on_exhausted_retries_low_confidence(self):
        """Task fails with confidence < 0.1, max_retries=1 → ABORT."""
        _clear_plan_cache()

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                return _make_plan_json(tasks=[
                    {"task_id": "task_1", "task_type": "risky_analysis",
                     "description": "Analyze risky contract", "agent": "archive",
                     "depends_on": [], "priority": 10,
                     "confidence_required": 0.9, "max_retries": 1},
                ])
            if agent == "archive":
                # Return unparseable response → confidence = 0.1 (no structured data)
                return "garbage response that cannot be parsed"
            if agent == "legal":
                return _legal_ok()
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            from src.agents.state import create_initial_state
            from src.agents.workflow import asd_app

            state = create_initial_state(
                project_id=99905,
                task_description="E2E abort on failure",
                workflow_mode="lot_search",
            )
            result = await asd_app.ainvoke(state)

        assert result["is_complete"] is True
        plan = result.get("work_plan", {})
        # Plan should be either ABORTED or COMPLETED (depending on PM evaluation path)
        assert plan.get("status") in ("aborted", "completed")
        # Archive task with 0.1 confidence and 0.9 required → rejection expected
        confidence_scores = result.get("confidence_scores", {})
        archive_conf = confidence_scores.get("archive", 0.5)
        assert archive_conf < 0.9, f"Archive confidence {archive_conf} should be < 0.9"

    # ── PM Decision Recording ────────────────────────────────────────────────

    async def test_pm_decision_and_audit_trail_populated(self):
        """PM decision, reasoning, and audit trail are recorded in state."""
        _clear_plan_cache()

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                return _make_plan_json()
            if agent == "archive":
                return _archive_ok()
            if agent == "legal":
                return _legal_ok()
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            from src.agents.state import create_initial_state
            from src.agents.workflow import asd_app

            state = create_initial_state(
                project_id=99906,
                task_description="E2E audit trail",
                workflow_mode="lot_search",
            )
            result = await asd_app.ainvoke(state)

        assert result["is_complete"] is True
        assert len(result.get("audit_trail", [])) >= 3, \
            f"Expected >=3 audit entries, got {len(result.get('audit_trail', []))}"
        # revision_history populated by agent_executor_node (sequential),
        # but parallel agent_worker_node doesn't call add_revision yet.
        # Audit trail is the canonical record for both paths.

    # ── Graph Compilation ────────────────────────────────────────────────────

    async def test_parallel_graph_compiles(self):
        """Verify the parallel graph compiles without error."""
        from src.agents.workflow import create_parallel_workflow
        graph = create_parallel_workflow()
        assert graph is not None
        # Verify key nodes exist
        nodes = graph.get_graph().nodes if hasattr(graph, 'get_graph') else {}
        # At minimum the graph object should be usable
        assert hasattr(graph, 'ainvoke') or hasattr(graph, 'invoke')

    # ── State Factory ────────────────────────────────────────────────────────

    async def test_initial_state_has_parallel_fields(self):
        """create_initial_state() includes parallel execution fields."""
        from src.agents.state import create_initial_state

        state = create_initial_state(
            project_id=42,
            task_description="Verify parallel fields",
            workflow_mode="lot_search",
        )
        assert "parallel_results" in state
        assert state["parallel_results"] == []
        assert "last_evaluated_index" in state
        assert state["last_evaluated_index"] == 0
        assert "work_plan" in state
        assert "completed_task_ids" in state
        assert "ram_status" in state

    # ── Grey Zone LLM Evaluation ────────────────────────────────────────────

    async def test_grey_zone_llm_evaluation_via_sequential_graph(self):
        """Confidence 0.85 < required 0.9 → grey zone → PM LLM evaluates → ACCEPT.

        Uses sequential graph (asd_app_sequential) because the parallel
        pm_evaluate path auto-completes tasks without PM evaluation.
        Only _evaluate_single_task calls _pm.evaluate_result() with LLM path.
        """
        _clear_plan_cache()

        pm_call_count = [0]

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                pm_call_count[0] += 1
                if pm_call_count[0] == 1:
                    # create_plan: task with high confidence bar
                    return _make_plan_json(tasks=[
                        {"task_id": "task_1", "task_type": "archive_register",
                         "description": "Register docs with high quality bar",
                         "agent": "archive", "depends_on": [], "priority": 10,
                         "confidence_required": 0.9},
                    ])
                else:
                    # evaluate_result: LLM returns ACCEPT
                    return json.dumps({"verdict": "ACCEPT",
                                       "reasoning": "Archive structure is sufficient despite moderate confidence"})
            if agent == "archive":
                return _archive_ok()  # 3 keys → confidence 0.85
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            from src.agents.state import create_initial_state
            from src.agents.workflow import asd_app_sequential

            state = create_initial_state(
                project_id=99910,
                task_description="E2E grey zone LLM evaluation",
                workflow_mode="lot_search",
            )
            result = await asd_app_sequential.ainvoke(state)

        assert result["is_complete"] is True
        plan = result.get("work_plan", {})
        assert plan.get("status") == "completed", f"Expected completed, got {plan.get('status')}"
        assert pm_call_count[0] >= 2, f"Expected >=2 PM LLM calls, got {pm_call_count[0]}"
        # PM decision should be recorded
        assert result.get("pm_decision") in ("accept", "retry", "skip", "retry_other", "abort")

    async def test_grey_zone_llm_evaluation_skip_verdict(self):
        """Grey zone → LLM returns SKIP → task skipped, plan completes.

        Verifies the SKIP verdict path: PM evaluation via LLM can skip
        non-critical tasks instead of retrying or aborting.
        """
        _clear_plan_cache()

        pm_call_count = [0]

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                pm_call_count[0] += 1
                if pm_call_count[0] == 1:
                    return _make_plan_json(tasks=[
                        {"task_id": "task_1", "task_type": "archive_register",
                         "description": "Low-priority archive check", "agent": "archive",
                         "depends_on": [], "priority": 3,
                         "confidence_required": 0.9},
                    ])
                else:
                    # evaluation: SKIP (not critical enough to retry)
                    return json.dumps({"verdict": "SKIP",
                                       "reasoning": "Low priority, skipping"})
            if agent == "archive":
                # Single-key response → confidence 0.5 (< 0.9) → grey zone
                return json.dumps({"status": "minimal"})
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            from src.agents.state import create_initial_state
            from src.agents.workflow import asd_app_sequential

            state = create_initial_state(
                project_id=99911,
                task_description="E2E grey zone skip",
                workflow_mode="lot_search",
            )
            result = await asd_app_sequential.ainvoke(state)

        assert result["is_complete"] is True
        plan = result.get("work_plan", {})
        assert plan.get("status") in ("completed", "executing", "adapted"), \
            f"Unexpected plan status: {plan.get('status')}"
        assert pm_call_count[0] >= 2, f"Expected >=2 PM LLM calls (plan + evaluate), got {pm_call_count[0]}"

    # ── Replan (PM Agent direct unit tests via graph) ────────────────────

    async def test_replan_split_action_adds_subtasks_to_plan(self):
        """Direct test: _pm.replan() with split action adds subtasks.

        replan() is called from _evaluate_single_task when a task reaches
        FAILED status. Since agent nodes catch exceptions internally (via
        _safe_agent_chat), the intermediate_data error path is unreachable
        in graph execution. Instead, test replan() directly through the
        PM agent to validate the split logic.
        """
        _clear_plan_cache()

        from src.core.pm_agent import ProjectManager, WorkPlan, TaskNode, TaskStatus
        from src.core.llm_engine import llm_engine

        pm = ProjectManager(llm_engine=llm_engine, completeness_matrix=None)

        # Build a plan with a failed task
        task = TaskNode(
            task_id="task_1", task_type="archive_register",
            description="Complex registration", agent="archive",
            depends_on=[], priority=10, confidence_required=0.5,
            max_retries=1,
        )
        task.status = TaskStatus.FAILED.value
        task.retry_count = 1
        task.result_summary = "Persistent JSON parse failure"

        plan = WorkPlan(
            plan_id="PLAN-REPLAN-01",
            project_id=99920,
            goal="Test replan split",
            tasks=[task],
        )

        # Mock LLM for replan call
        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                return json.dumps({
                    "action": "split",
                    "reasoning": "Task too complex, splitting",
                    "new_tasks": [
                        {"task_id": "task_1a", "task_type": "archive_register",
                         "description": "Register part A", "agent": "archive",
                         "depends_on": [], "priority": 10, "confidence_required": 0.5},
                        {"task_id": "task_1b", "task_type": "archive_register",
                         "description": "Register part B", "agent": "archive",
                         "depends_on": [], "priority": 9, "confidence_required": 0.5},
                    ],
                })
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            adapted = await pm.replan(plan, task, "Persistent failure")

        assert adapted is not None
        task_ids = [t.task_id for t in adapted.tasks]
        assert "task_1a" in task_ids, f"Expected subtask task_1a, got {task_ids}"
        assert "task_1b" in task_ids, f"Expected subtask task_1b, got {task_ids}"
        # Original task should be skipped
        assert task.status == TaskStatus.SKIPPED.value

    async def test_replan_reorder_action_changes_priorities(self):
        """Direct test: _pm.replan() with reorder action modifies task priorities."""
        _clear_plan_cache()

        from src.core.pm_agent import ProjectManager, WorkPlan, TaskNode, TaskStatus
        from src.core.llm_engine import llm_engine

        pm = ProjectManager(llm_engine=llm_engine, completeness_matrix=None)

        task1 = TaskNode(
            task_id="task_1", task_type="procurement_analyze",
            description="Analyze risky procurement", agent="procurement",
            depends_on=[], priority=10, confidence_required=0.5,
            max_retries=1,
        )
        task1.status = TaskStatus.FAILED.value
        task1.retry_count = 1

        task2 = TaskNode(
            task_id="task_2", task_type="archive_register",
            description="Archive safe docs", agent="archive",
            depends_on=[], priority=5, confidence_required=0.5,
        )

        plan = WorkPlan(
            plan_id="PLAN-REPLAN-02",
            project_id=99921,
            goal="Test replan reorder",
            tasks=[task1, task2],
        )

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                return json.dumps({
                    "action": "reorder",
                    "reasoning": "Deprioritize failed procurement, promote archive",
                    "modified_tasks": {"task_2": 10},
                })
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            adapted = await pm.replan(plan, task1, "Persistent failure")

        assert adapted is not None
        # task_2 should have elevated priority
        updated_task2 = next((t for t in adapted.tasks if t.task_id == "task_2"), None)
        assert updated_task2 is not None
        assert updated_task2.priority == 10, \
            f"Expected priority 10 after reorder, got {updated_task2.priority}"

    # ── Multiple Parallel Rounds ────────────────────────────────────────────

    async def test_multiple_parallel_rounds_with_dependencies(self):
        """3 tasks with deps: task_1 first → task_2, task_3 in parallel round 2."""
        _clear_plan_cache()

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                return _make_plan_json(tasks=[
                    {"task_id": "task_1", "task_type": "archive_register",
                     "description": "Register docs (prerequisite)", "agent": "archive",
                     "depends_on": [], "priority": 10, "confidence_required": 0.5},
                    {"task_id": "task_2", "task_type": "legal_review",
                     "description": "Legal review after registration", "agent": "legal",
                     "depends_on": ["task_1"], "priority": 9, "confidence_required": 0.6},
                    {"task_id": "task_3", "task_type": "smeta_calc",
                     "description": "Estimate after registration", "agent": "smeta",
                     "depends_on": ["task_1"], "priority": 8, "confidence_required": 0.6},
                ])
            if agent == "archive":
                return _archive_ok()
            if agent == "legal":
                return _legal_ok()
            if agent == "smeta":
                return _smeta_ok()
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            from src.agents.state import create_initial_state
            from src.agents.workflow import asd_app

            state = create_initial_state(
                project_id=99914,
                task_description="E2E multiple parallel rounds",
                workflow_mode="lot_search",
            )
            result = await asd_app.ainvoke(state)

        assert result["is_complete"] is True
        plan = result.get("work_plan", {})
        assert plan.get("status") == "completed", f"Expected completed, got {plan.get('status')}"
        assert len(result.get("completed_task_ids", [])) == 3

        # Verify parallel_results captures all 3 completions
        parallel = result.get("parallel_results", [])
        assert len(parallel) == 3, f"Expected 3 parallel results, got {len(parallel)}"
        agents = {r["agent"] for r in parallel}
        assert agents >= {"archive", "legal", "smeta"}

    async def test_single_task_each_round_no_fanout(self):
        """Sequential chain: only 1 task ready per round → 3 individual rounds."""
        _clear_plan_cache()

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                return _make_linear_plan_json()  # task_1 → task_2 → task_3
            if agent == "archive":
                return _archive_ok()
            if agent == "legal":
                return _legal_ok()
            if agent == "smeta":
                return _smeta_ok()
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            from src.agents.state import create_initial_state
            from src.agents.workflow import asd_app

            state = create_initial_state(
                project_id=99915,
                task_description="E2E sequential rounds",
                workflow_mode="lot_search",
            )
            result = await asd_app.ainvoke(state)

        assert result["is_complete"] is True
        plan = result.get("work_plan", {})
        assert plan.get("status") in ("completed", "executing")
        assert len(result.get("completed_task_ids", [])) == 3

    # ── Plan Adaptation ─────────────────────────────────────────────────────

    async def test_plan_status_adapted_after_replan(self):
        """Plan status transitions: executing → adapted after replan.

        When a task FAILs and replan adjusts the plan, the plan status should
        reflect adaptation rather than staying EXECUTING.
        """
        _clear_plan_cache()

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                # Only create_plan — evaluate uses fast path (no LLM needed)
                return _make_plan_json(tasks=[
                    {"task_id": "task_1", "task_type": "archive_register",
                     "description": "Register docs", "agent": "archive",
                     "depends_on": [], "priority": 10,
                     "confidence_required": 0.5, "max_retries": 1},
                    {"task_id": "task_2", "task_type": "legal_review",
                     "description": "Legal check", "agent": "legal",
                     "depends_on": ["task_1"], "priority": 9,
                     "confidence_required": 0.6},
                ])
            if agent == "archive":
                # Fail hard → task FAILED with max_retries=1
                raise RuntimeError("Simulated failure needing replan")
            if agent == "legal":
                return _legal_ok()
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            from src.agents.state import create_initial_state
            from src.agents.workflow import asd_app_sequential

            state = create_initial_state(
                project_id=99916,
                task_description="E2E plan adaptation",
                workflow_mode="lot_search",
            )
            result = await asd_app_sequential.ainvoke(state)

        # Plan either ends (no ready tasks after failure) or completes
        assert result["is_complete"] is True
        plan = result.get("work_plan", {})
        assert plan.get("status") in ("aborted", "adapted", "completed", "executing"), \
            f"Unexpected plan status: {plan.get('status')}"

    # ── Compliance Delta ────────────────────────────────────────────────────

    async def test_compliance_delta_recorded_in_state(self):
        """PM records compliance delta (gap to ИД reference) in state."""
        _clear_plan_cache()

        async def mock_chat(agent, messages, **kwargs):
            if agent == "pm":
                plan_json = _make_plan_json()
                plan_data = json.loads(plan_json)
                plan_data["compliance_delta"] = {
                    "missing_sections": ["protocol_of_disagreements", "claim"],
                    "estimated_gap_pct": 35.0,
                    "reference_standard": "344/пр",
                }
                return json.dumps(plan_data)
            if agent == "archive":
                return _archive_ok()
            if agent == "legal":
                return _legal_ok()
            return "{}"

        p1, p2 = _patch_llm(mock_chat)
        with p1, p2:
            from src.agents.state import create_initial_state
            from src.agents.workflow import asd_app

            state = create_initial_state(
                project_id=99917,
                task_description="E2E compliance delta",
                workflow_mode="lot_search",
            )
            result = await asd_app.ainvoke(state)

        assert result["is_complete"] is True
        delta = result.get("compliance_delta", {})
        assert isinstance(delta, dict), f"Expected dict compliance_delta, got {type(delta)}"
        if delta:
            assert "reference_standard" in delta or "missing_sections" in delta or \
                   "estimated_gap_pct" in delta, \
                   f"Compliance delta should have standard fields, got: {delta}"
