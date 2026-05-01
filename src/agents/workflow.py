"""
ASD v12.0 — PM-driven LangGraph Workflow with Send() Parallel Execution.

Two graph variants:
  1. asd_app (parallel) — uses Send() to execute independent tasks concurrently
  2. asd_app_sequential (legacy) — one agent at a time, backward compatible

Parallel Graph:
  START → pm_planning → pm_fan_out_router
                              ↓
              [Send("agent_worker")] × N  ← parallel fan-out
                              ↓ (all complete)
                        pm_evaluate
                              ↓
                     pm_fan_out_router (cycle until all done)
                              ↓ or END

Sequential Graph:
  START → pm_planning → agent_executor → pm_evaluate → [cycle] → END

Model Lineup (mac_studio):
  PM:     Llama 3.3 70B 4-bit (dedicated, ~40GB)
  Agents: Gemma 4 31B 4-bit (shared, 5 agents, ~23GB)
  Archive: Gemma 4 E4B 4-bit (separate, ~3GB)
"""

from langgraph.graph import StateGraph, END
from src.agents.state import AgentState
from src.agents.nodes_v2 import (
    pm_planning_node,
    pm_evaluate_node,
    pm_dispatch_router,
    pm_fan_out_router,
    agent_executor_node,
    agent_worker_node,
)

# All agent names that map to agent_executor (sequential mode)
ALL_AGENT_KEYS = [
    "archive", "procurement", "pto", "pto_inventory", "pto_verify_trail",
    "smeta", "smeta_estimate", "smeta_compare", "delo",
    "procurement_analyze", "logistics_plan", "legal", "logistics",
    "legal_protocol", "legal_claim", "legal_lawsuit",
]

# Conditional edge map for sequential dispatch
AGENT_EDGE_MAP = {k: "agent_executor" for k in ALL_AGENT_KEYS}
AGENT_EDGE_MAP["__end__"] = END

# Conditional edge map for parallel dispatch (agent_worker, not agent_executor)
AGENT_PARALLEL_EDGE_MAP = {k: "agent_worker" for k in ALL_AGENT_KEYS}
AGENT_PARALLEL_EDGE_MAP["__end__"] = END


def create_parallel_workflow():
    """
    Create PM-driven graph with Send() parallel execution.

    Agents with satisfied dependencies are dispatched simultaneously.
    Archive (E4B) can execute in true parallel with shared-model agents.
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("pm_planning", pm_planning_node)
    workflow.add_node("agent_worker", agent_worker_node)
    workflow.add_node("pm_evaluate", pm_evaluate_node)

    workflow.set_entry_point("pm_planning")

    # PM planning → fan-out to parallel workers
    workflow.add_conditional_edges(
        "pm_planning",
        pm_fan_out_router,
        AGENT_PARALLEL_EDGE_MAP,  # Str returns → agent_worker (sequential fallback)
    )

    # Parallel workers → PM evaluate
    workflow.add_edge("agent_worker", "pm_evaluate")

    # PM evaluate → fan-out again or END
    workflow.add_conditional_edges(
        "pm_evaluate",
        pm_fan_out_router,
        AGENT_PARALLEL_EDGE_MAP,
    )

    return workflow.compile()


def create_sequential_workflow():
    """
    [DEPRECATED] Legacy PM-driven graph (one agent at a time).

    Superseded by create_parallel_workflow() with Send() fan-out.
    Kept for backward-compatible testing and debugging.

    Used when:
    - RAM is under pressure (CRITICAL → sequential forced)
    - Debugging
    - Backward compatibility testing
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("pm_planning", pm_planning_node)
    workflow.add_node("agent_executor", agent_executor_node)
    workflow.add_node("pm_evaluate", pm_evaluate_node)

    workflow.set_entry_point("pm_planning")

    workflow.add_conditional_edges(
        "pm_planning",
        pm_dispatch_router,
        AGENT_EDGE_MAP,
    )

    workflow.add_edge("agent_executor", "pm_evaluate")

    workflow.add_conditional_edges(
        "pm_evaluate",
        pm_dispatch_router,
        AGENT_EDGE_MAP,
    )

    return workflow.compile()


# Compiled graph instances
asd_app = create_parallel_workflow()
# [DEPRECATED] Legacy sequential graph — use asd_app (parallel) instead
asd_app_sequential = create_sequential_workflow()
