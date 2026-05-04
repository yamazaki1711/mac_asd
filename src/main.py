"""
MAC_ASD v13.0 — Main Entry Point.

Runs the PM-driven LangGraph pipeline:
  PM Planning → Agent Fan-Out (Send) → PM Evaluate → [cycle] → END

Two modes:
  lot_search           — tender pipeline (default demo)
  construction_support — forensic ID restoration

Usage:
  PYTHONPATH=. python -m src.main
  PYTHONPATH=. python -m src.main --mode construction_support
"""

import argparse
import asyncio
import logging
import signal
import sys

from src.agents.workflow import asd_app
from src.agents.state import create_initial_state
from src.db.init_db import Session, engine
from src.config import settings
from src.core.observability import setup_json_logging

# Structured JSON logging (Grafana/Prometheus)
logger = setup_json_logging()


async def _shutdown(loop: asyncio.AbstractEventLoop):
    """Graceful shutdown: close DB connections, cancel pending tasks."""
    logger.info("Shutting down gracefully...")
    engine.dispose()
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Shutdown complete.")


def _handle_signal(sig, frame):
    """Signal handler for SIGTERM/SIGINT."""
    logger.info("Received signal %s — initiating shutdown", sig)
    loop = asyncio.get_event_loop()
    loop.create_task(_shutdown(loop))
    loop.call_later(5, lambda: sys.exit(0))


async def run_demo(mode: str = "lot_search"):
    logger.info("--- MAC_ASD v13.0 | profile=%s | mode=%s ---", settings.ASD_PROFILE, mode)
    logger.info("Project root: %s", settings.BASE_DIR)
    logger.info("Wiki path: %s", settings.wiki_path)

    # 1. Bootstrap DI container
    from src.core.container_setup import bootstrap
    bootstrap()

    # 2. Create test project
    with Session() as session:
        project = Project(name=f"Demo: {mode}")
        session.add(project)
        session.commit()
        project_id = project.id
        logger.info("Project #%d created", project_id)

    # 3. Initial state via AgentState v2.0 factory
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

    # 4. Run the graph (parallel by default)
    logger.info("Starting LangGraph pipeline...")
    try:
        final_output = await asd_app.ainvoke(initial_state)
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        return

    # 5. Results
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


def main():
    parser = argparse.ArgumentParser(description="MAC_ASD v13.0 — AI Subcontractor Documentation")
    parser.add_argument(
        "--mode", default="lot_search",
        choices=["lot_search", "construction_support"],
        help="Workflow mode (default: lot_search)",
    )
    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Graceful shutdown on SIGTERM/SIGINT
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: _handle_signal(s, None))
        except NotImplementedError:
            # Windows does not support add_signal_handler
            signal.signal(sig, _handle_signal)

    try:
        loop.run_until_complete(run_demo(args.mode))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        loop.run_until_complete(_shutdown(loop))
        loop.close()


if __name__ == "__main__":
    from src.db.models import Project
    main()
