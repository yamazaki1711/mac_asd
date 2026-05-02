"""
Pytest conftest — injects mock langgraph modules for environments where
langgraph cannot be installed (Python < 3.11, 32-bit, etc.).

The mocks are functional enough for:
  - StateGraph compilation and ainvoke execution
  - Send() parallel fan-out (list[Send] from conditional edges)
  - Annotated reducers (operator.add for parallel_results, add_messages)
  - State merging with TypedDict fields

Also sets DATABASE_URL to sqlite to prevent import-time PostgreSQL connection
attempts in src.db.init_db.
"""

import operator
import os
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

# Prevent import-time DB connection in src.db.init_db
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("ASD_PROFILE", "dev_linux")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")


# ═══════════════════════════════════════════════════════════════════════════════
# Mock langgraph.types
# ═══════════════════════════════════════════════════════════════════════════════

class Send:
    """Mock langgraph.types.Send — parallel dispatch payload."""

    def __init__(self, node: str, arg: dict):
        self.node = node
        self.arg = arg

    def __repr__(self):
        return f"Send(node={self.node!r}, arg={...})"


# ═══════════════════════════════════════════════════════════════════════════════
# Mock langgraph.graph
# ═══════════════════════════════════════════════════════════════════════════════

END = "__end__"

# add_messages is operator.add in real langgraph
add_messages = operator.add


class _CompiledGraph:
    """Minimal LangGraph runtime that executes the graph and merges state."""

    def __init__(self, nodes, edges, conditional_edges, entry_point):
        self._nodes = nodes          # {name: func}
        self._edges = edges          # {from: to}
        self._conditional_edges = conditional_edges  # {from: (router, edge_map)}
        self._entry_point = entry_point

    async def ainvoke(self, state: dict) -> dict:
        """Execute the graph asynchronously from entry point to END."""
        current_node = self._entry_point
        max_steps = 50  # Safety limit

        for _ in range(max_steps):
            if current_node == END or current_node is None:
                break

            node_func = self._nodes.get(current_node)
            if node_func is None:
                break

            # Call node
            result = node_func(state)
            if hasattr(result, '__await__'):
                result = await result

            # Merge result into state (handle Annotated reducers)
            if isinstance(result, dict):
                state = _merge_state(state, result)

            # Follow edges
            next_nodes = self._follow_edges(current_node, state)

            if not next_nodes:
                break

            if len(next_nodes) == 1:
                current_node = next_nodes[0][0]  # (node_name, state) tuple
            else:
                # Parallel fan-out via Send(): execute all workers, then follow
                # the static edge from the worker node to the next (evaluate) node.
                worker_node_name = None
                for target_node, worker_state in next_nodes:
                    if target_node == END or target_node is None:
                        continue
                    worker_node_name = target_node
                    worker_func = self._nodes.get(target_node)
                    if worker_func is None:
                        continue
                    worker_result = worker_func(worker_state)
                    if hasattr(worker_result, '__await__'):
                        worker_result = await worker_result
                    if isinstance(worker_result, dict):
                        state = _merge_state(state, worker_result)
                # After parallel workers, follow static edge from worker → evaluate
                if worker_node_name and worker_node_name in self._edges:
                    current_node = self._edges[worker_node_name]
                else:
                    current_node = END

        return state

    def _follow_edges(self, node_name: str, state: dict) -> List:
        """Determine next node(s) from current node. Returns list of (node, state)."""
        # Check conditional edges first
        if node_name in self._conditional_edges:
            router, edge_map = self._conditional_edges[node_name]
            route_result = router(state)

            # list[Send] → parallel fan-out
            if isinstance(route_result, list):
                sends = []
                for item in route_result:
                    if isinstance(item, Send):
                        sends.append((item.node, {**state, **item.arg}))
                return sends

            # str → single dispatch
            if isinstance(route_result, str):
                target = edge_map.get(route_result, END)
                return [(target, state)]

            return []

        # Static edge
        if node_name in self._edges:
            return [(self._edges[node_name], state)]

        return [(END, state)]

    def invoke(self, state: dict) -> dict:
        """Synchronous wrapper."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
        except RuntimeError:
            pass
        return asyncio.run(self.ainvoke(state))


class StateGraph:
    """Mock langgraph.graph.StateGraph — graph builder."""

    def __init__(self, state_schema=None):
        self._state_schema = state_schema
        self._nodes: Dict[str, Any] = {}
        self._edges: Dict[str, str] = {}
        self._conditional_edges: Dict[str, tuple] = {}
        self._entry_point: Optional[str] = None

    def add_node(self, name: str, func):
        self._nodes[name] = func
        return self

    def add_edge(self, from_node: str, to_node: str):
        self._edges[from_node] = to_node
        return self

    def add_conditional_edges(self, from_node: str, router, edge_map: dict):
        self._conditional_edges[from_node] = (router, edge_map)
        return self

    def set_entry_point(self, name: str):
        self._entry_point = name
        return self

    def compile(self):
        return _CompiledGraph(
            nodes=self._nodes,
            edges=self._edges,
            conditional_edges=self._conditional_edges,
            entry_point=self._entry_point,
        )


def _merge_state(state: dict, update: dict) -> dict:
    """Merge update into state, respecting Annotated reducers (operator.add for lists)."""
    merged = {**state}
    for key, value in update.items():
        if key not in merged:
            merged[key] = value
        elif isinstance(merged[key], list) and isinstance(value, list):
            # operator.add reducer for Annotated[List, operator.add]
            merged[key] = merged[key] + value
        else:
            merged[key] = value
    return merged


# ═══════════════════════════════════════════════════════════════════════════════
# Inject mocks into sys.modules BEFORE any src imports
# ═══════════════════════════════════════════════════════════════════════════════

_mock_langgraph_types = MagicMock()
_mock_langgraph_types.Send = Send

_mock_langgraph_graph = MagicMock()
_mock_langgraph_graph.StateGraph = StateGraph
_mock_langgraph_graph.END = END
_mock_langgraph_graph.add_messages = add_messages

_mock_langgraph = MagicMock()
_mock_langgraph.graph = _mock_langgraph_graph
_mock_langgraph.types = _mock_langgraph_types

sys.modules["langgraph"] = _mock_langgraph
sys.modules["langgraph.graph"] = _mock_langgraph_graph
sys.modules["langgraph.types"] = _mock_langgraph_types

# ═══════════════════════════════════════════════════════════════════════════════
# Prevent src.db.init_db import-time PostgreSQL connection
# The module-level `engine = create_engine(...)` runs on import and fails
# without psycopg2. We mock the entire module before any src code imports it.
# ═══════════════════════════════════════════════════════════════════════════════

_mock_init_db = MagicMock()
_mock_init_db.engine = MagicMock()
_mock_init_db.Session = MagicMock()
_mock_init_db.SessionLocal = _mock_init_db.Session
_mock_init_db.create_engine = MagicMock()  # re-exported for nodes.py
_mock_init_db.init_postgres = MagicMock()
_mock_init_db.init_graph = MagicMock()
sys.modules["src.db.init_db"] = _mock_init_db

# Also mock heavy backends that won't install on Python 3.8
_mock_ollama_backend = MagicMock()
_mock_mlx_backend = MagicMock()
_mock_deepseek_backend = MagicMock()
sys.modules["src.core.backends.ollama_backend"] = MagicMock()
sys.modules["src.core.backends.mlx_backend"] = MagicMock()
sys.modules["src.core.backends.deepseek_backend"] = MagicMock()

# ═══════════════════════════════════════════════════════════════════════════════
# DI Container test fixtures
# ═══════════════════════════════════════════════════════════════════════════════

import pytest
from src.core.container import container as global_container


@pytest.fixture(autouse=True)
def reset_container_overrides():
    """Reset DI container overrides after each test."""
    yield
    global_container.reset_overrides()


@pytest.fixture
def clean_container():
    """Return a completely fresh ServiceContainer for isolated testing."""
    from src.core.container import ServiceContainer
    return ServiceContainer()
