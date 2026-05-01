"""
ASD v12.0 — PM-driven Agent Nodes.

PM-оркестрация вместо статического Hermes-роутера:
  pm_planning_node  — создаёт WorkPlan, диспетчеризует первого агента
  agent_executor_node — выполняет задачу текущего агента
  pm_evaluate_node  — оценивает результат, обновляет план, решает что дальше
  pm_dispatch_router — conditional edge: определяет следующего агента или END

Все агенты используют те же функции из nodes.py, но обёрнуты в
pm-контекст (получают task_description из WorkPlan, а не из state напрямую).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from langgraph.types import Send

from src.agents.nodes import (
    archive_node,
    procurement_node,
    pto_node,
    smeta_node,
    legal_node,
    logistics_node,
    pto_inventory_node,
    pto_verify_trail_node,
    smeta_estimate_node,
    smeta_compare_node,
    delo_registry_node,
    procurement_analyze_node,
    logistics_plan_node,
    _safe_agent_chat,
    _compute_agent_confidence,
    _get_lessons_context,
    _extract_work_type,
)
from src.core.exceptions import (
    LLMUnavailableError,
    LLMResponseError,
    NetworkError,
)
from src.agents.state import (
    AgentState,
    StepLog,
    StepStatus,
    add_revision,
    start_step,
    complete_step,
    fail_step,
    create_initial_state,
)
from src.core.llm_engine import llm_engine
from src.core.pm_agent import (
    ProjectManager,
    WorkPlan,
    TaskNode,
    TaskStatus,
    EvaluationVerdict,
    PlanStatus,
)
from src.core.ram_manager import ram_manager, TaskPriority

logger = logging.getLogger(__name__)

# Module-level PM instance
_pm = ProjectManager(llm_engine=llm_engine, completeness_matrix=None)

# Кэш планов по project_id (в production — в БД)
_plan_cache: Dict[int, WorkPlan] = {}


# =============================================================================
# Agent → Node mapping
# =============================================================================

AGENT_NODE_MAP = {
    "archive": archive_node,
    "procurement": procurement_node,
    "pto": pto_node,
    "pto_inventory": pto_inventory_node,
    "pto_verify_trail": pto_verify_trail_node,
    "smeta": smeta_node,
    "smeta_estimate": smeta_estimate_node,
    "smeta_compare": smeta_compare_node,
    "delo": delo_registry_node,
    "procurement_analyze": procurement_analyze_node,
    "logistics_plan": logistics_plan_node,
    "legal": legal_node,
    "logistics": logistics_node,
}


# =============================================================================
# PM Planning Node
# =============================================================================

async def pm_planning_node(state: AgentState) -> Dict[str, Any]:
    """
    PM Planning Node — точка входа в граф.

    Первый вызов: строит WorkPlan через LLM.
    Возвращает управление через pm_dispatch_router.
    """
    project_id = state["project_id"]
    workflow_mode = state["workflow_mode"]
    task_description = state["task_description"]

    step_id = start_step(state, "pm", "create_plan")

    # Проверяем RAM
    snapshot = ram_manager.get_snapshot(force=True)
    state["ram_status"] = snapshot.status.value
    state["ram_snapshot"] = snapshot.to_dict()

    if snapshot.status.value in ("oom_danger",):
        logger.error("PM cannot create plan: RAM %s", snapshot.status.value)
        fail_step(state, step_id, f"RAM {snapshot.status.value}: cannot start planning")
        return {"next_step": "__end__", "is_complete": True}

    # Строим план (из кэша или через LLM)
    if project_id in _plan_cache and _plan_cache[project_id].status not in (
        PlanStatus.COMPLETED.value,
        PlanStatus.ABORTED.value,
    ):
        plan = _plan_cache[project_id]
        logger.info("PM reusing cached plan %s for project %d", plan.plan_id, project_id)
    else:
        plan = await _pm.create_plan(
            task_description=task_description,
            workflow_mode=workflow_mode,
            project_id=project_id,
            compliance_target="344/пр",
        )
        _plan_cache[project_id] = plan

    state["work_plan"] = plan.to_dict()
    state["pm_reasoning"] = plan.pm_reasoning
    state["compliance_delta"] = plan.compliance_delta

    complete_step(state, step_id, f"Plan {plan.plan_id}: {len(plan.tasks)} tasks, ETA {plan.estimated_duration_hours}h")

    logger.info(
        "PM plan created: %s — %d tasks, ETA %.1fh. Reasoning: %s",
        plan.plan_id, len(plan.tasks), plan.estimated_duration_hours,
        plan.pm_reasoning[:100] if plan.pm_reasoning else "N/A",
    )

    # Диспетчеризуем первую задачу
    return _dispatch_next(state, plan)


# =============================================================================
# Agent Executor Node
# =============================================================================

async def agent_executor_node(state: AgentState) -> Dict[str, Any]:
    """
    Выполнить задачу текущего агента.

    Использует AGENT_NODE_MAP для выбора правильного обработчика.
    Временно подменяет task_description на описание задачи из WorkPlan.
    """
    agent_name = state.get("current_agent")
    task_id = state.get("current_task_id")

    if not agent_name:
        logger.error("agent_executor_node: no current_agent in state")
        return {"next_step": "__end__"}

    node_func = AGENT_NODE_MAP.get(agent_name)
    if not node_func:
        logger.error("agent_executor_node: unknown agent %s", agent_name)
        return {"next_step": "__end__"}

    # Временно подменяем task_description на описание задачи из плана
    original_task = state["task_description"]
    plan = _get_plan(state)
    if plan:
        task = _find_task(plan, task_id)
        if task:
            state["task_description"] = task.description

    step_id = start_step(state, agent_name, f"execute_{task_id}")

    # RAM check + register
    if not ram_manager.can_accept_task(agent_name, priority=TaskPriority.NORMAL):
        logger.warning("RAM rejected task for %s. Skipping.", agent_name)
        state["task_description"] = original_task
        fail_step(state, step_id, "RAM rejected")
        return {
            "next_step": "pm_evaluate",
            "intermediate_data": {
                **state.get("intermediate_data", {}),
                f"{agent_name}_ram_rejected": True,
            },
        }

    ram_manager.register_task_start(agent_name)

    try:
        result = await node_func(state)
    except (LLMUnavailableError, NetworkError) as e:
        logger.error("Agent %s unavailable: %s", agent_name, e)
        ram_manager.register_task_end(agent_name)
        state["task_description"] = original_task
        fail_step(state, step_id, str(e))
        return {
            "next_step": "pm_evaluate",
            "intermediate_data": {
                **state.get("intermediate_data", {}),
                f"{agent_name}_error": str(e),
            },
        }
    except Exception as e:
        logger.error("Agent %s failed: %s", agent_name, e)
        ram_manager.register_task_end(agent_name)
        state["task_description"] = original_task
        fail_step(state, step_id, str(e))
        return {
            "next_step": "pm_evaluate",
            "intermediate_data": {
                **state.get("intermediate_data", {}),
                f"{agent_name}_error": str(e),
            },
        }
    finally:
        ram_manager.register_task_end(agent_name)

    state["task_description"] = original_task

    # Сохраняем результат агента в completed_task_ids
    completed = state.get("completed_task_ids", [])
    if task_id and task_id not in completed:
        completed.append(task_id)
        state["completed_task_ids"] = completed

    complete_step(state, step_id, f"Agent {agent_name} completed task {task_id}")

    # Добавляем результат в audit
    add_revision(state, "agent_step", agent_name, task_id or "unknown", "completed")

    return {"next_step": "pm_evaluate"}


# =============================================================================
# PM Evaluate Node
# =============================================================================

async def pm_evaluate_node(state: AgentState) -> Dict[str, Any]:
    """
    PM оценивает результат агента и решает, что делать дальше.
    """
    plan = _get_plan(state)
    if not plan:
        logger.error("pm_evaluate_node: no plan in state")
        return {"next_step": "__end__", "is_complete": True}

    task_id = state.get("current_task_id")
    if not task_id:
        logger.warning("pm_evaluate_node: no current_task_id")
        return _dispatch_next(state, plan)

    task = _find_task(plan, task_id)
    if not task:
        logger.warning("pm_evaluate_node: task %s not found in plan", task_id)
        return _dispatch_next(state, plan)

    agent_name = state.get("current_agent", "unknown")

    # Проверить RAM-отказ
    intermediate = state.get("intermediate_data", {})
    if intermediate.get(f"{agent_name}_ram_rejected"):
        task.status = TaskStatus.PENDING.value  # Вернуть в очередь
        logger.info("PM: task %s requeued (RAM rejection)", task_id)
        plan.updated_at = datetime.utcnow().isoformat()
        state["work_plan"] = plan.to_dict()
        return _dispatch_next(state, plan)

    # Проверить ошибку агента
    if intermediate.get(f"{agent_name}_error"):
        error_msg = intermediate[f"{agent_name}_error"]
        logger.warning("PM: task %s failed with error: %s", task_id, error_msg)
        task.mark_failed(error_msg)
        if task.status == TaskStatus.FAILED.value:
            # Исчерпаны попытки — адаптируем план
            plan = await _pm.replan(plan, task, error_msg)
            _update_plan_cache(state, plan)
        plan.updated_at = datetime.utcnow().isoformat()
        state["work_plan"] = plan.to_dict()
        return _dispatch_next(state, plan)

    # Определить уверенность агента
    confidence = state.get("confidence_scores", {}).get(agent_name, 0.5)

    # Собрать summary результата
    result_summary = _extract_result_summary(state, agent_name)

    # PM оценивает
    step_id = start_step(state, "pm", f"evaluate_{task_id}")

    verdict = await _pm.evaluate_result(
        plan=plan,
        task=task,
        result_summary=result_summary,
        confidence=confidence,
        previous_errors=[
            t.result_summary
            for t in plan.get_failed_tasks()
            if t.result_summary
        ],
    )

    state["pm_decision"] = verdict.value
    state["pm_reasoning"] = f"Task {task_id}: {verdict.value} (confidence={confidence:.2f})"

    if verdict == EvaluationVerdict.ABORT:
        complete_step(state, step_id, f"Plan ABORTED after task {task_id}")
        plan.status = PlanStatus.ABORTED.value
        state["work_plan"] = plan.to_dict()
        state["is_complete"] = True
        return {"next_step": "__end__", "is_complete": True}

    complete_step(state, step_id, f"Task {task_id}: {verdict.value}")

    # Если RETRY_OTHER — поменять агента в задаче
    if verdict == EvaluationVerdict.RETRY_OTHER_AGENT:
        # Пробуем другой агент (простой выбор: следующий по приоритету)
        alternative = _suggest_alternative_agent(task.agent)
        task.agent = alternative
        task.retry_count = 0
        task.status = TaskStatus.PENDING.value
        logger.info("PM: task %s reassigned from %s to %s", task_id, agent_name, alternative)

    plan.updated_at = datetime.utcnow().isoformat()
    state["work_plan"] = plan.to_dict()
    _update_plan_cache(state, plan)

    return _dispatch_next(state, plan)


# =============================================================================
# PM Dispatch Router (conditional edge)
# =============================================================================

def pm_dispatch_router(state: AgentState) -> str:
    """
    Определить следующего агента или END.

    Используется как conditional edge function.
    """
    next_step = state.get("next_step", "")

    # Явное завершение
    if next_step == "__end__" or state.get("is_complete"):
        return "__end__"

    # RAM safety gate: проверяем статус памяти перед диспетчеризацией
    ram_status = state.get("ram_status", "normal")
    if ram_status in ("oom_danger",):
        logger.error("PM dispatch BLOCKED: RAM %s", ram_status)
        state["is_complete"] = True
        return "__end__"

    # Если уже указан агент
    current_agent = state.get("current_agent")
    if current_agent and current_agent in AGENT_NODE_MAP:
        return current_agent

    # Иначе — смотрим план
    plan = _get_plan(state)
    if not plan:
        return "__end__"

    result = _pm.dispatch(plan)
    if result is None:
        logger.info("PM: plan %s completed or blocked", plan.plan_id)
        # Log revision history summary at pipeline end
        rev_history = state.get("revision_history", [])
        if rev_history:
            logger.info("Revision history: %d entries", len(rev_history))
            for entry in rev_history[-5:]:  # Last 5 entries
                logger.debug("  %s: %s → %s", 
                           entry.get("revision_id", "?"),
                           entry.get("agent", "?"), 
                           entry.get("changes_summary", "?")[:80])
        state["is_complete"] = True
        state["work_plan"] = plan.to_dict()
        return "__end__"

    agent_name, task = result

    # Обновить state
    state["current_agent"] = agent_name
    state["current_task_id"] = task.task_id
    state["work_plan"] = plan.to_dict()

    logger.info(
        "PM dispatch: %s → %s (task %s, priority %d)",
        plan.plan_id, agent_name, task.task_id, task.priority,
    )

    return agent_name


# =============================================================================
# PM Fan-Out Router (Send() parallel dispatch)
# =============================================================================

# Predecessor context keys to propagate to parallel workers
_PREDECESSOR_KEYS = [
    "vor_result", "legal_result", "smeta_result",
    "procurement_result", "logistics_result", "archive_result",
    "intermediate_data", "findings", "confidence_scores",
    "compliance_delta", "ram_status", "ram_snapshot",
]


def pm_fan_out_router(state: AgentState):
    """
    Conditional edge: return list[Send] for parallel tasks, or str for sequential.

    When multiple tasks are ready (dependencies satisfied), dispatches them
    as parallel Send() calls. When only one, or RAM is under pressure,
    dispatches sequentially.

    Returns:
        list[Send] — parallel dispatch to agent_worker nodes
        or str — "__end__" or "agent_executor" for sequential mode
    """
    from src.core.ram_manager import RamStatus

    plan = _get_plan(state)
    if not plan:
        return "__end__"

    if state.get("is_complete"):
        return "__end__"

    ram_status = state.get("ram_status", "normal")

    # RAM throttle: fewer parallel tasks under memory pressure
    if ram_status == RamStatus.CRITICAL.value:
        max_parallel = 1  # Sequential only
    elif ram_status == RamStatus.WARNING.value:
        max_parallel = 2
    else:
        max_parallel = 5

    ready = plan.get_parallel_ready_tasks(max_parallel=max_parallel)

    if not ready:
        state["is_complete"] = True
        state["work_plan"] = plan.to_dict()
        return "__end__"

    # If only one task or RAM critical — sequential mode
    if len(ready) == 1 or max_parallel == 1:
        task = ready[0]
        task.mark_started()
        plan.updated_at = datetime.utcnow().isoformat()
        state["current_agent"] = task.agent
        state["current_task_id"] = task.task_id
        state["work_plan"] = plan.to_dict()
        state["last_evaluated_index"] = len(state.get("parallel_results", []))
        return task.agent if task.agent in AGENT_NODE_MAP else "agent_executor"

    # Multiple independent tasks — fan-out via Send()
    # Collect predecessor context from main state
    predecessor_context: Dict[str, Any] = {}
    for key in _PREDECESSOR_KEYS:
        val = state.get(key)
        if val is not None and val != [] and val != {}:
            predecessor_context[key] = val

    sends = []
    for i, task in enumerate(ready):
        task.mark_started()

        # Minimal payload for each worker
        worker_payload = {
            "project_id": state["project_id"],
            "current_lot_id": state.get("current_lot_id"),
            "task_description": task.description,
            "workflow_mode": state.get("workflow_mode", "lot_search"),
            "current_agent": task.agent,
            "current_task_id": task.task_id,
            "task_type": task.task_type,
            "parallel_index": i,
            "parallel_total": len(ready),
            "_llm_fallback_triggered": state.get("_llm_fallback_triggered", False),
            "_llm_fallback_agents": list(state.get("_llm_fallback_agents", [])),
            "confidence_scores": dict(state.get("confidence_scores", {})),
            **predecessor_context,
        }

        sends.append(Send("agent_worker", worker_payload))

    plan.updated_at = datetime.utcnow().isoformat()
    state["work_plan"] = plan.to_dict()
    state["last_evaluated_index"] = len(state.get("parallel_results", []))

    logger.info("PM fan-out: %d parallel tasks dispatched", len(sends))
    for s in sends:
        logger.debug("  → %s: %s", s.node, s.arg.get("current_agent", "?"))

    return sends


# =============================================================================
# Agent Worker Node (parallel execution unit)
# =============================================================================

async def agent_worker_node(state: AgentState) -> Dict[str, Any]:
    """
    Parallel agent worker — receives minimal context from Send() and executes.

    Returns results via parallel_results (Annotated[List, operator.add]).
    The pm_evaluate_node reads new results and updates the plan incrementally.
    """
    agent_name = state.get("current_agent")
    task_id = state.get("current_task_id")
    task_desc = state.get("task_description", "")
    parallel_index = state.get("parallel_index", 0)

    if not agent_name:
        logger.error("agent_worker_node: no current_agent")
        return {"parallel_results": [{"agent": "unknown", "error": "no agent"}]}

    node_func = AGENT_NODE_MAP.get(agent_name)
    if not node_func:
        logger.error("agent_worker_node: unknown agent %s", agent_name)
        return {"parallel_results": [{"agent": agent_name, "error": "unknown agent"}]}

    step_id = start_step(state, agent_name, f"worker_{task_id}")

    # RAM check
    if not ram_manager.can_accept_task(agent_name, priority=TaskPriority.NORMAL):
        logger.warning("RAM rejected worker %s", agent_name)
        fail_step(state, step_id, "RAM rejected")
        return {
            "parallel_results": [{
                "agent": agent_name,
                "task_id": task_id,
                "task_type": state.get("task_type", ""),
                "ram_rejected": True,
                "parallel_index": parallel_index,
            }]
        }

    ram_manager.register_task_start(agent_name)

    try:
        result = await node_func(state)
    except (LLMUnavailableError, NetworkError) as e:
        logger.error("Worker %s unavailable: %s", agent_name, e)
        ram_manager.register_task_end(agent_name)
        fail_step(state, step_id, str(e))
        return {
            "parallel_results": [{
                "agent": agent_name,
                "task_id": task_id,
                "task_type": state.get("task_type", ""),
                "error": str(e),
                "parallel_index": parallel_index,
            }]
        }
    except Exception as e:
        logger.error("Worker %s failed: %s", agent_name, e)
        ram_manager.register_task_end(agent_name)
        fail_step(state, step_id, str(e))
        return {
            "parallel_results": [{
                "agent": agent_name,
                "task_id": task_id,
                "task_type": state.get("task_type", ""),
                "error": str(e),
                "parallel_index": parallel_index,
            }]
        }
    finally:
        ram_manager.register_task_end(agent_name)

    complete_step(state, step_id, f"Worker {agent_name} completed {task_id}")

    # Determine confidence
    confidence = state.get("confidence_scores", {}).get(agent_name, 0.5)

    # Return result through parallel_results accumulator
    return {
        "parallel_results": [{
            "agent": agent_name,
            "task_id": task_id,
            "task_type": state.get("task_type", ""),
            "status": "completed",
            "confidence": confidence,
            "parallel_index": parallel_index,
            "result_snapshot": _extract_result_summary(state, agent_name),
            "intermediate_data_snapshot": dict(state.get("intermediate_data", {})),
        }]
    }


# =============================================================================
# PM Evaluate Node (updated for parallel execution)
# =============================================================================

async def pm_evaluate_node(state: AgentState) -> Dict[str, Any]:
    """
    PM оценивает результаты — инкрементально обрабатывает новые parallel_results.

    Поддерживает два режима:
    1. Последовательный (через agent_executor_node) — task_id из state
    2. Параллельный (через agent_worker_node) — результаты в parallel_results
    """
    plan = _get_plan(state)
    if not plan:
        logger.error("pm_evaluate_node: no plan")
        return {"next_step": "__end__", "is_complete": True}

    # Получить новые результаты (ещё не обработанные)
    parallel_results = state.get("parallel_results", [])
    last_idx = state.get("last_evaluated_index", 0)
    new_results = parallel_results[last_idx:]

    task_id = state.get("current_task_id")

    # Если нет новых параллельных результатов — обрабатываем текущую задачу
    if not new_results:
        if not task_id:
            return _dispatch_next(state, plan)
        return await _evaluate_single_task(state, plan, task_id)

    # Инкрементально обрабатываем каждый новый результат
    for result in new_results:
        r_agent = result.get("agent", "unknown")
        r_task_id = result.get("task_id", "")
        r_status = result.get("status", "")
        r_confidence = result.get("confidence", 0.5)
        r_error = result.get("error")
        r_ram_rejected = result.get("ram_rejected")

        task = _find_task(plan, r_task_id)
        if not task:
            logger.warning("pm_evaluate: task %s not found in plan", r_task_id)
            continue

        if r_ram_rejected:
            task.status = TaskStatus.PENDING.value
            continue

        if r_error:
            task.mark_failed(r_error)
            if task.status == TaskStatus.FAILED.value:
                plan = await _pm.replan(plan, task, r_error)
                _update_plan_cache(state, plan)
            continue

        # Success — merge agent-specific results into main state
        result_snapshot = result.get("result_snapshot", "")
        intermediate_snapshot = result.get("intermediate_data_snapshot", {})
        if intermediate_snapshot:
            current_intermediate = state.get("intermediate_data", {})
            state["intermediate_data"] = {**current_intermediate, **intermediate_snapshot}

        task.mark_completed(result_snapshot)

        confidence_scores = state.get("confidence_scores", {})
        confidence_scores[r_agent] = r_confidence
        state["confidence_scores"] = confidence_scores

        # Mark completed
        completed = state.get("completed_task_ids", [])
        if r_task_id not in completed:
            completed.append(r_task_id)
            state["completed_task_ids"] = completed

    # Update last evaluated index
    state["last_evaluated_index"] = len(parallel_results)
    plan.updated_at = datetime.utcnow().isoformat()
    state["work_plan"] = plan.to_dict()
    _update_plan_cache(state, plan)

    # Check if all tasks complete
    pending = [t for t in plan.tasks if t.status in (TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value)]
    if not pending:
        plan.status = PlanStatus.COMPLETED.value
        state["work_plan"] = plan.to_dict()
        state["is_complete"] = True
        logger.info("PM: plan %s completed — all tasks done", plan.plan_id)
        return {"next_step": "__end__", "is_complete": True}

    return _dispatch_next(state, plan)


async def _evaluate_single_task(
    state: AgentState, plan: WorkPlan, task_id: str
) -> Dict[str, Any]:
    """Evaluate a single task (sequential mode)."""
    task = _find_task(plan, task_id)
    if not task:
        return _dispatch_next(state, plan)

    agent_name = state.get("current_agent", "unknown")
    intermediate = state.get("intermediate_data", {})

    if intermediate.get(f"{agent_name}_ram_rejected"):
        task.status = TaskStatus.PENDING.value
        plan.updated_at = datetime.utcnow().isoformat()
        state["work_plan"] = plan.to_dict()
        return _dispatch_next(state, plan)

    if intermediate.get(f"{agent_name}_error"):
        error_msg = intermediate[f"{agent_name}_error"]
        task.mark_failed(error_msg)
        if task.status == TaskStatus.FAILED.value:
            plan = await _pm.replan(plan, task, error_msg)
            _update_plan_cache(state, plan)
        plan.updated_at = datetime.utcnow().isoformat()
        state["work_plan"] = plan.to_dict()
        return _dispatch_next(state, plan)

    confidence = state.get("confidence_scores", {}).get(agent_name, 0.5)
    result_summary = _extract_result_summary(state, agent_name)

    step_id = start_step(state, "pm", f"evaluate_{task_id}")

    verdict = await _pm.evaluate_result(
        plan=plan, task=task, result_summary=result_summary,
        confidence=confidence,
        previous_errors=[
            t.result_summary for t in plan.get_failed_tasks() if t.result_summary
        ],
    )

    state["pm_decision"] = verdict.value
    state["pm_reasoning"] = f"Task {task_id}: {verdict.value} (confidence={confidence:.2f})"

    if verdict == EvaluationVerdict.ABORT:
        complete_step(state, step_id, f"Plan ABORTED")
        plan.status = PlanStatus.ABORTED.value
        state["work_plan"] = plan.to_dict()
        state["is_complete"] = True
        return {"next_step": "__end__", "is_complete": True}

    complete_step(state, step_id, f"Task {task_id}: {verdict.value}")

    if verdict == EvaluationVerdict.RETRY_OTHER_AGENT:
        alternative = _suggest_alternative_agent(task.agent)
        task.agent = alternative
        task.retry_count = 0
        task.status = TaskStatus.PENDING.value

    plan.updated_at = datetime.utcnow().isoformat()
    state["work_plan"] = plan.to_dict()
    _update_plan_cache(state, plan)

    return _dispatch_next(state, plan)


# =============================================================================
# Helpers
# =============================================================================

def _get_plan(state: AgentState) -> Optional[WorkPlan]:
    """Извлечь WorkPlan из state (сначала из кэша, потом из state)."""
    plan_dict = state.get("work_plan")
    if not plan_dict:
        return _plan_cache.get(state["project_id"])
    return WorkPlan.from_dict(plan_dict)


def _find_task(plan: WorkPlan, task_id: Optional[str]) -> Optional[TaskNode]:
    """Найти задачу в плане по ID."""
    if not task_id:
        return None
    for t in plan.tasks:
        if t.task_id == task_id:
            return t
    return None


def _update_plan_cache(state: AgentState, plan: WorkPlan) -> None:
    """Обновить кэш плана."""
    _plan_cache[state["project_id"]] = plan
    state["work_plan"] = plan.to_dict()


def _dispatch_next(state: AgentState, plan: WorkPlan) -> Dict[str, Any]:
    """Выбрать следующую задачу и вернуть обновление state."""
    result = _pm.dispatch(plan)
    if result is None:
        state["is_complete"] = True
        state["work_plan"] = plan.to_dict()
        return {"next_step": "__end__", "is_complete": True, "work_plan": plan.to_dict()}

    agent_name, task = result
    state["current_agent"] = agent_name
    state["current_task_id"] = task.task_id
    state["work_plan"] = plan.to_dict()
    state["next_step"] = agent_name

    return {
        "current_agent": agent_name,
        "current_task_id": task.task_id,
        "work_plan": plan.to_dict(),
        "next_step": agent_name,
    }


def _extract_result_summary(state: AgentState, agent_name: str) -> str:
    """Извлечь краткое описание результата агента."""
    if agent_name == "pto":
        vor = state.get("vor_result")
        return f"PTO extracted {vor.get('total_positions', 0) if vor else 0} VOR positions"
    elif agent_name == "legal":
        legal = state.get("legal_result")
        return f"Legal verdict: {legal.get('verdict', 'N/A') if legal else 'N/A'}"
    elif agent_name == "smeta":
        smeta = state.get("smeta_result")
        return f"Smeta: total={smeta.get('total_cost', 0) if smeta else 0}"
    elif agent_name == "procurement":
        proc = state.get("procurement_result")
        return f"Procurement: decision={proc.get('decision', 'N/A') if proc else 'N/A'}"
    elif agent_name == "logistics":
        logi = state.get("logistics_result")
        return f"Logistics: {logi.get('vendors_found', 0) if logi else 0} vendors"
    elif agent_name == "archive":
        arch = state.get("archive_result")
        return f"Archive: doc_id={arch.get('doc_id', 'N/A') if arch else 'N/A'}"
    return f"{agent_name}: done"


def _suggest_alternative_agent(current_agent: str) -> str:
    """Предложить альтернативного агента, если текущий не справился."""
    alternatives = {
        "archive": "pto",
        "procurement": "smeta",
        "pto": "legal",
        "smeta": "pto",
        "legal": "smeta",
        "logistics": "procurement",
    }
    return alternatives.get(current_agent, "pto")
