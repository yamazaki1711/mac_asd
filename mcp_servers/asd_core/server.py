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

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="asd_core",
    version="0.1.0",
    description="ASD Unified MCP Server — чертежи, сметы, право",
)

# ---------------------------------------------------------------------------
# Register tools
# ---------------------------------------------------------------------------
# Vision
mcp.add_tool(vision_analyze)
mcp.add_tool(vision_tile)

# Smeta
mcp.add_tool(smeta_query)
mcp.add_tool(smeta_rate_lookup)
mcp.add_tool(index_lookup)

# Legal
mcp.add_tool(legal_search)
mcp.add_tool(fz_lookup)
mcp.add_tool(rag_query)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
