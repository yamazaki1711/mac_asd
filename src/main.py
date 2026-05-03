"""
MAC_ASD v12.0 — Main Entry Point.

Runs the demonstration pipeline:
  Archive → Procurement → PTO → [Smeta + Legal] → Logistics → Hermes Verdict → Reflection

Model Lineup (mac_studio):
    PM:     Llama 3.3 70B 4-bit
    ПТО:    Gemma 4 31B 4-bit (VLM, shared)
    Юрист:  Gemma 4 31B 4-bit (shared, 128K контекст)
    Сметчик:Gemma 4 31B 4-bit (shared)
    Закупщик:Gemma 4 31B 4-bit (shared)
    Логист: Gemma 4 31B 4-bit (shared)
    Дело:   Gemma 4 E4B 4-bit
"""

"""
MAC_ASD v12.0 — Main Entry Point.

Runs the PM-driven LangGraph pipeline:
  PM Planning → Agent Fan-Out (Send) → PM Evaluate → [cycle] → END

Two modes:
  lot_search           — tender pipeline (default demo)
  construction_support — forensic ID restoration

Usage:
  PYTHONPATH=. python -m src.main
  PYTHONPATH=. python -m src.main --mode construction_support
"""

import asyncio
import logging
import sys

from src.agents.workflow import asd_app
from src.agents.state import create_initial_state
from src.db.init_db import Session
from src.db.models import Project
from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ASD_MAIN")


async def run_demo(mode: str = "lot_search"):
    logger.info("--- MAC_ASD v12.0 | profile=%s | mode=%s ---", settings.ASD_PROFILE, mode)
    logger.info("Project root: %s", settings.BASE_DIR)
    logger.info("Wiki path: %s", settings.wiki_path)

    # 1. Create test project
    with Session() as session:
        project = Project(name=f"Demo: {mode}")
        session.add(project)
        session.commit()
        project_id = project.id
        logger.info("Project #%d created", project_id)

    # 2. Initial state via AgentState v2.0 factory
    task = (
        "Проверить ВОР и Смету на соответствие чертежам. "
        "Выявить юридические риски по БЛС (61 ловушка)."
    )
    initial_state = create_initial_state(
        project_id=project_id,
        task_description=task,
        workflow_mode=mode,
    )
    logger.info("AgentState v2.0 initialized (schema=%s)", initial_state["schema_version"])

    # 3. Run the graph (parallel by default)
    logger.info("Starting LangGraph pipeline...")
    try:
        final_output = await asd_app.ainvoke(initial_state)
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        return

    # 4. Results
    logger.info("--- PIPELINE COMPLETE ---")
    logger.info("Plan status: %s", final_output.get("work_plan", {}).get("status", "N/A"))
    logger.info("PM decision: %s", final_output.get("pm_decision", "N/A"))
    logger.info("Confidence scores: %s", final_output.get("confidence_scores", {}))
    logger.info("Completed tasks: %s", final_output.get("completed_task_ids", []))
    logger.info("Audit trail entries: %d", len(final_output.get("audit_trail", [])))
    logger.info("Revision history entries: %d", len(final_output.get("revision_history", [])))

    findings = final_output.get("findings", [])
    if findings:
        logger.info("Findings: %d", len(findings))


if __name__ == "__main__":
    mode = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--mode" else "lot_search"
    asyncio.run(run_demo(mode))
