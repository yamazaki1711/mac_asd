"""
MCP Tools for Evidence Graph v2.

3 tools: query, summary, get_chain.
Uses EvidenceGraph singleton from src.core.evidence_graph.
"""

import logging
from typing import Any, Dict, List, Optional

from src.core.evidence_graph import evidence_graph
from src.core.chain_builder import chain_builder

logger = logging.getLogger(__name__)


async def asd_evidence_query(
    node_type: str = "all",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    confidence_min: float = 0.0,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Запрос к графу доказательств с фильтрацией по типу узла, диапазону дат и confidence.

    Args:
        node_type: Тип узла: "WorkUnit", "MaterialBatch", "Document", "Person",
                   "DateEvent", "Volume", "Location", "all"
        date_from: Начальная дата (ISO формат, YYYY-MM-DD)
        date_to: Конечная дата (ISO формат)
        confidence_min: Минимальный confidence (0.0–1.0)
        project_id: Фильтр по project_id в метаданных

    Returns:
        {"status": "ok", "nodes": [...], "edges": [...], "total_nodes": N, "total_edges": M}
    """
    nodes = []
    edges = []

    for nid, data in evidence_graph.graph.nodes(data=True):
        nt = data.get("node_type", "Unknown")

        # Filter by node_type
        if node_type != "all" and nt != node_type:
            continue

        # Filter by confidence
        conf = data.get("confidence", 1.0)
        if conf < confidence_min:
            continue

        # Filter by project_id
        if project_id:
            meta = data.get("metadata", {}) or {}
            if meta.get("project_id", "") != project_id:
                continue

        # Filter by date range
        node_date = data.get("date") or data.get("created_at") or data.get("event_date")
        if node_date and (date_from or date_to):
            if date_from and str(node_date) < date_from:
                continue
            if date_to and str(node_date) > date_to:
                continue

        nodes.append({"id": nid, **data})

    # Collect edges for filtered nodes
    filtered_ids = {n["id"] for n in nodes}
    for src, dst, data in evidence_graph.graph.edges(data=True):
        if src in filtered_ids or dst in filtered_ids:
            edges.append({"source": src, "target": dst, **data})

    return {
        "status": "ok",
        "nodes": nodes,
        "edges": edges,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "filters_applied": {
            "node_type": node_type,
            "date_from": date_from,
            "date_to": date_to,
            "confidence_min": confidence_min,
            "project_id": project_id,
        },
    }


async def asd_evidence_summary(
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Статистика графа доказательств: количество узлов по типам, рёбер по отношениям.

    Args:
        project_id: Опциональный фильтр по проекту

    Returns:
        {"status": "ok", "node_counts": {...}, "edge_counts": {...}, ...}
    """
    summary = evidence_graph.summary()

    if project_id:
        # Filter: only count nodes with matching project_id in metadata
        proj_nodes = 0
        proj_edges = 0
        for nid, data in evidence_graph.graph.nodes(data=True):
            meta = data.get("metadata", {}) or {}
            if meta.get("project_id", "") == project_id:
                proj_nodes += 1
        summary["project_nodes"] = proj_nodes
        summary["project_id"] = project_id

    return {
        "status": "ok",
        **summary,
    }


async def asd_evidence_get_chain(
    work_unit_id: str,
    direction: str = "both",
) -> Dict[str, Any]:
    """Получить документальную цепочку для конкретного WorkUnit.

    Args:
        work_unit_id: ID WorkUnit (например "WU_001")
        direction: "forward" (к подтверждающим документам),
                   "backward" (к материалам и предшественникам),
                   "both" (в обе стороны)

    Returns:
        {"status": "ok", "chain": {"work_unit": {...}, "materials": [...],
         "documents": [...], "predecessors": [...], "successors": [...]}}
    """
    if not evidence_graph.graph.has_node(work_unit_id):
        return {
            "status": "error",
            "error_code": "NOT_FOUND",
            "message": f"WorkUnit '{work_unit_id}' не найден в графе доказательств",
        }

    chain = evidence_graph.get_work_unit_chain(work_unit_id)

    if direction == "forward":
        chain.pop("materials", None)
        chain.pop("predecessors", None)
    elif direction == "backward":
        chain.pop("documents", None)
        chain.pop("events", None)
        chain.pop("successors", None)

    # Build human-readable chain steps
    steps = []
    for mat in chain.get("materials", []):
        steps.append({"step": len(steps) + 1, "type": "material",
                       "label": mat.get("material_name", mat["id"]),
                       "node_id": mat["id"]})
    for doc in chain.get("documents", []):
        steps.append({"step": len(steps) + 1, "type": doc.get("doc_type", "document"),
                       "label": doc.get("doc_number", doc["id"]),
                       "node_id": doc["id"]})
    for evt in chain.get("events", []):
        steps.append({"step": len(steps) + 1, "type": "event",
                       "label": evt.get("label", evt["id"]),
                       "node_id": evt["id"]})

    return {
        "status": "ok",
        "work_unit_id": work_unit_id,
        "chain": chain,
        "chain_steps": steps,
        "chain_length": len(steps),
        "completeness": "full" if chain.get("documents") else "partial",
    }
