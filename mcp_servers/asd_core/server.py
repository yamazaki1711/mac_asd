"""
ASD Core — Unified MCP Server for Autonomous Support Department.

Provides exactly 23 tools mapped from CONCEPT_v11.md for:
- Jurist (Legal parsing, analysis, document generation)
- PTO (VOR checking, PD analysis, Act Generation)
- Smeta (Estimate comparing, LSR Generation)
- Deloproizvoditel (Registration, Tracking, Shipment preparation)
- Procurement (Tender search, Profitability analysis)
- Logistics (Vendor sourcing, Price tracking)
"""

from fastmcp import FastMCP
from typing import Dict, Any, List
import asyncio

# Импорты ядра ASD
from src.agents.workflow import asd_app
from src.agents.state import AgentState

# Imports - 18 Tools Implementation
from mcp_servers.asd_core.tools.jurist_tools import (
    asd_upload_document, asd_analyze_contract, asd_normative_search,
    asd_generate_protocol, asd_generate_claim, asd_generate_lawsuit,
    asd_add_trap
)
from mcp_servers.asd_core.tools.pto_tools import (
    asd_vor_check, asd_pd_analysis, asd_generate_act, asd_id_completeness
)
from mcp_servers.asd_core.tools.smeta_tools import (
    asd_estimate_compare, asd_create_lsr, asd_supplement_estimate
)
from mcp_servers.asd_core.tools.delo_tools import (
    asd_register_document, asd_generate_letter, asd_prepare_shipment, asd_track_deadlines
)
from mcp_servers.asd_core.tools.procurement_tools import (
    asd_tender_search, asd_analyze_lot_profitability
)
from mcp_servers.asd_core.tools.logistics_tools import (
    asd_source_vendors, asd_add_price_list, asd_compare_quotes
)
from mcp_servers.asd_core.tools.general_tools import (
    asd_get_system_status
)

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="asd_core",
    version="11.0.0",
)

# ---------------------------------------------------------------------------
# Register tools — grouped by agent role (access controlled via agent prompts)
# ---------------------------------------------------------------------------

# Группа 1: Юрист (6 инструментов)
mcp.add_tool(asd_upload_document)
mcp.add_tool(asd_analyze_contract)
mcp.add_tool(asd_normative_search)
mcp.add_tool(asd_generate_protocol)
mcp.add_tool(asd_generate_claim)
mcp.add_tool(asd_generate_lawsuit)
mcp.add_tool(asd_add_trap)

# Группа 2: ПТО-инженер (4 инструмента)
mcp.add_tool(asd_vor_check)
mcp.add_tool(asd_pd_analysis)
mcp.add_tool(asd_generate_act)
mcp.add_tool(asd_id_completeness)

# Группа 3: Инженер-сметчик (3 инструмента)
mcp.add_tool(asd_estimate_compare)
mcp.add_tool(asd_create_lsr)
mcp.add_tool(asd_supplement_estimate)

# Группа 4: Делопроизводитель (4 инструмента)
mcp.add_tool(asd_register_document)
mcp.add_tool(asd_generate_letter)
mcp.add_tool(asd_prepare_shipment)
mcp.add_tool(asd_track_deadlines)

# Группа 5: Закупщик (2 инструмента)
mcp.add_tool(asd_tender_search)
mcp.add_tool(asd_analyze_lot_profitability)

# Группа 6: Логист (3 инструмента)
mcp.add_tool(asd_source_vendors)
mcp.add_tool(asd_add_price_list)
mcp.add_tool(asd_compare_quotes)

# Группа 7: Общий (1 инструмент)
mcp.add_tool(asd_get_system_status)

# ---------------------------------------------------------------------------
# Pipeline Execution (Testing)
# ---------------------------------------------------------------------------
@mcp.tool()
async def run_tender_pipeline(project_id: int, task_description: str) -> Dict[str, Any]:
    """
    E2E ТЕСТ: Запускает полный цикл анализа тендера: Архив -> Закупки -> ПТО -> Логистика -> Сметчик -> Юрист -> Рефлексия.
    Будет использовать LangGraph для автоматизированного конвейера.
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
        "summary": "Тендер обработан всеми 7 агентами и оптимизирован.",
        "findings": final_state.get("findings", []),
        "intermediate_data_keys": list(final_state.get("intermediate_data", {}).keys())
    }

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
