"""
ASD Core — Unified MCP Server for Autonomous Support Department.

Provides 60+ tools mapped from CONCEPT_v12.md for:
- Jurist (Legal parsing, analysis, document generation)
- PTO (VOR checking, PD analysis, Act Generation, WorkSpec, ID search)
- Smeta (Estimate comparing, LSR Generation)
- Deloproizvoditel (Registration, Tracking, Shipment preparation)
- Procurement (Tender search, Profitability analysis)
- Logistics (Vendor sourcing, Price tracking)
- Lab Control (Full lab cycle: plan → sample → test → report → file)
- Google Workspace (Drive, Sheets, Docs, Gmail integration)
"""

from fastmcp import FastMCP
from typing import Dict, Any, List
import asyncio

# Импорты ядра ASD
from src.agents.workflow import asd_app
from src.agents.state import AgentState

# Imports - 60+ Tools Implementation
from mcp_servers.asd_core.tools.jurist_tools import (
    asd_upload_document, asd_analyze_contract, asd_normative_search,
    asd_generate_protocol, asd_generate_claim, asd_generate_lawsuit,
    asd_add_trap
)
from mcp_servers.asd_core.tools.pto_tools import (
    asd_vor_check, asd_pd_analysis, asd_generate_act, asd_id_completeness,
    # WorkSpec tools
    asd_get_work_type_info, asd_list_work_types, asd_get_tech_sequence,
    asd_get_date_rules, asd_get_input_control, asd_id_search, asd_id_download
)
from mcp_servers.asd_core.tools.smeta_tools import (
    asd_estimate_compare, asd_create_lsr, asd_supplement_estimate,
    asd_rate_lookup, asd_get_minstroy_index
)
from mcp_servers.asd_core.tools.delo_tools import (
    asd_register_document, asd_generate_letter, asd_prepare_shipment, asd_track_deadlines,
    asd_get_template, asd_validate_template, asd_list_templates
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
from mcp_servers.asd_core.tools.lab_tools import (
    asd_lab_control_plan_create, asd_lab_sample_register, asd_lab_report_review,
    asd_lab_organization_search, asd_lab_quote_request, asd_lab_quote_compare,
    asd_lab_sample_delivery, asd_lab_request_letter_generate,
    asd_lab_contract_register, asd_lab_act_register, asd_lab_report_file,
    asd_lab_register_report, asd_lab_request_update_status
)
from mcp_servers.asd_core.tools.google_tools import (
    asd_drive_search, asd_drive_list_folder, asd_drive_get_file,
    asd_drive_copy_file, asd_drive_create_folder, asd_drive_export_pdf,
    asd_sheets_read, asd_sheets_write, asd_sheets_append,
    asd_sheets_get_names, asd_sheets_create,
    asd_docs_get_content, asd_docs_replace_text, asd_docs_from_template,
    asd_gmail_send, asd_google_status
)

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="asd_core",
    version="12.0.0",
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

# Группа 2b: ПТО WorkSpec (7 инструментов)
mcp.add_tool(asd_get_work_type_info)
mcp.add_tool(asd_list_work_types)
mcp.add_tool(asd_get_tech_sequence)
mcp.add_tool(asd_get_date_rules)
mcp.add_tool(asd_get_input_control)
mcp.add_tool(asd_id_search)
mcp.add_tool(asd_id_download)

# Группа 3: Инженер-сметчик (5 инструментов)
mcp.add_tool(asd_estimate_compare)
mcp.add_tool(asd_create_lsr)
mcp.add_tool(asd_supplement_estimate)
mcp.add_tool(asd_rate_lookup)
mcp.add_tool(asd_get_minstroy_index)

# Группа 4: Делопроизводитель (7 инструментов)
mcp.add_tool(asd_register_document)
mcp.add_tool(asd_generate_letter)
mcp.add_tool(asd_prepare_shipment)
mcp.add_tool(asd_track_deadlines)
mcp.add_tool(asd_get_template)
mcp.add_tool(asd_validate_template)
mcp.add_tool(asd_list_templates)

# Группа 5: Закупщик (2 инструмента)
mcp.add_tool(asd_tender_search)
mcp.add_tool(asd_analyze_lot_profitability)

# Группа 6: Логист (3 инструмента)
mcp.add_tool(asd_source_vendors)
mcp.add_tool(asd_add_price_list)
mcp.add_tool(asd_compare_quotes)

# Группа 7: Общий (1 инструмент)
mcp.add_tool(asd_get_system_status)

# Группа 8: Лабораторный контроль — ПТО (3 инструмента)
mcp.add_tool(asd_lab_control_plan_create)
mcp.add_tool(asd_lab_sample_register)
mcp.add_tool(asd_lab_report_review)

# Группа 9: Лабораторный контроль — Закупщик (3 инструмента)
mcp.add_tool(asd_lab_organization_search)
mcp.add_tool(asd_lab_quote_request)
mcp.add_tool(asd_lab_quote_compare)

# Группа 10: Лабораторный контроль — Логист (1 инструмент)
mcp.add_tool(asd_lab_sample_delivery)

# Группа 11: Лабораторный контроль — Делопроизводитель (6 инструментов)
mcp.add_tool(asd_lab_request_letter_generate)
mcp.add_tool(asd_lab_contract_register)
mcp.add_tool(asd_lab_act_register)
mcp.add_tool(asd_lab_report_file)
mcp.add_tool(asd_lab_register_report)
mcp.add_tool(asd_lab_request_update_status)

# Группа 12: Google Workspace — Drive (6 инструментов)
mcp.add_tool(asd_drive_search)
mcp.add_tool(asd_drive_list_folder)
mcp.add_tool(asd_drive_get_file)
mcp.add_tool(asd_drive_copy_file)
mcp.add_tool(asd_drive_create_folder)
mcp.add_tool(asd_drive_export_pdf)

# Группа 13: Google Workspace — Sheets (5 инструментов)
mcp.add_tool(asd_sheets_read)
mcp.add_tool(asd_sheets_write)
mcp.add_tool(asd_sheets_append)
mcp.add_tool(asd_sheets_get_names)
mcp.add_tool(asd_sheets_create)

# Группа 14: Google Workspace — Docs (3 инструмента)
mcp.add_tool(asd_docs_get_content)
mcp.add_tool(asd_docs_replace_text)
mcp.add_tool(asd_docs_from_template)

# Группа 15: Google Workspace — Gmail + Status (2 инструмента)
mcp.add_tool(asd_gmail_send)
mcp.add_tool(asd_google_status)

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
