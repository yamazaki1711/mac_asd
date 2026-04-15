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
    description="ASD Unified MCP Server — чертежи, сметы, право",
)

# ---------------------------------------------------------------------------
# Register tools — grouped by agent role (access controlled via agent prompts)
# ---------------------------------------------------------------------------

# Группа «Vision/ПТО»
mcp.add_tool(vision_analyze, tags={"vision", "pto"})
mcp.add_tool(vision_tile,     tags={"vision", "pto"})

# Группа «Сметчик»
mcp.add_tool(smeta_query,        tags={"smeta"})
mcp.add_tool(smeta_rate_lookup,  tags={"smeta"})
mcp.add_tool(index_lookup,       tags={"smeta"})

# Группа «Юрист»
mcp.add_tool(legal_search, tags={"legal"})
mcp.add_tool(fz_lookup,    tags={"legal"})
mcp.add_tool(rag_query,    tags={"legal", "rag"})

# Группа «Делопроизводитель / Архивариус»
mcp.add_tool(artifact_list,    tags={"artifact", "archive"})
mcp.add_tool(artifact_write,   tags={"artifact", "archive"})
mcp.add_tool(artifact_version, tags={"artifact", "archive"})

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
