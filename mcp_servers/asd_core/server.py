"""
ASD Core — Unified MCP Server for Autonomous Support Department.

Provides tools for:
- Vision analysis (drawing interpretation, tile processing)
- Smeta operations (rate lookup, index calculation)
- Legal research (federal law lookup, RAG-based compliance)
- Graph operations (Neo4j query/write)
- Artifact management (file storage, task dispatch)
"""

from fastmcp import FastMCP
from typing import Dict, Any, List
import asyncio

# Импорты ядра ASD
from src.agents.workflow import asd_app
from src.agents.state import AgentState

from mcp_servers.asd_core.tools.vision_tools import (
    vision_analyze,
    vision_tile,
)
from mcp_servers.asd_core.tools.smeta_tools import (
    smeta_query,
    smeta_rate_lookup,
    index_lookup,
)
from mcp_servers.asd_core.tools.legal_tools import (
    legal_search,
    fz_lookup,
    rag_query,
)
from mcp_servers.asd_core.tools.artifact_tools import (
    artifact_list,
    artifact_write,
    artifact_version,
)

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="asd_core",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Register tools — grouped by agent role (access controlled via agent prompts)
# ---------------------------------------------------------------------------

# Группа «Vision/ПТО»
mcp.add_tool(vision_analyze)
mcp.add_tool(vision_tile)

# Группа «Сметчик»
mcp.add_tool(smeta_query)
mcp.add_tool(smeta_rate_lookup)
mcp.add_tool(index_lookup)

# Группа «Юрист»
mcp.add_tool(legal_search)
mcp.add_tool(fz_lookup)
mcp.add_tool(rag_query)

# Группа «Делопроизводитель / Архивариус»
mcp.add_tool(artifact_list)
mcp.add_tool(artifact_write)
mcp.add_tool(artifact_version)

# ---------------------------------------------------------------------------
# Pipeline Execution
# ---------------------------------------------------------------------------
@mcp.tool()
async def run_tender_pipeline(project_id: int, task_description: str) -> Dict[str, Any]:
    """
    Запускает полный цикл анализа тендера: ПТО -> Сметчик -> Юрист -> Рефлексия.
    """
    initial_state = {
        "messages": [{"role": "user", "content": task_description}],
        "project_id": project_id,
        "task_description": task_description,
        "intermediate_data": {},
        "findings": [],
        "next_step": "start",
        "is_complete": False
    }
    
    # Запуск графа
    final_state = await asd_app.ainvoke(initial_state)
    
    return {
        "status": "completed",
        "project_id": project_id,
        "summary": "Тендер обработан всеми агентами и оптимизирован.",
        "findings": final_state.get("findings", []),
        "intermediate_data_keys": list(final_state.get("intermediate_data", {}).keys())
    }

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
