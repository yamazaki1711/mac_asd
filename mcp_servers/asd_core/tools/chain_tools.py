"""
MCP Tools for Chain Builder.

3 tools: build, report, validate.
Uses ChainBuilder singleton from src.core.chain_builder.
"""

import logging
from typing import Any, Dict, List, Optional

from src.core.evidence_graph import evidence_graph
from src.core.chain_builder import chain_builder, GapSeverity

logger = logging.getLogger(__name__)


async def asd_chain_build(
    project_id: Optional[str] = None,
    rebuild: bool = False,
) -> Dict[str, Any]:
    """Построить документальные цепочки для всех WorkUnit в графе доказательств.

    Цепочка: MaterialBatch → Certificate/Passport → AOSR → KS-2.
    Автоматически выявляет разрывы (CRITICAL/HIGH/MEDIUM/LOW).

    Args:
        project_id: Опциональный фильтр по проекту
        rebuild: Перестроить все цепочки заново (по умолчанию используется кэш)

    Returns:
        {"status": "ok", "chains_built": N, "chains_incomplete": M, ...}
    """
    chains = chain_builder.build_chains(evidence_graph)
    report = chain_builder.generate_report(chains)

    # Filter by project_id if specified
    if project_id:
        chains = [
            c for c in chains
            if project_id in c.work_unit_id or project_id in c.description
        ]
        report = chain_builder.generate_report(chains)

    # Identify incomplete chains
    incomplete = [c for c in chains if c.status != "complete"]
    critical_gaps = []
    for c in chains:
        for g in c.gaps:
            if g.severity == GapSeverity.CRITICAL:
                critical_gaps.append({
                    "work_unit_id": c.work_unit_id,
                    "work_type": c.work_type,
                    "gap_description": g.description,
                    "missing_doc_type": g.missing_doc_type,
                })

    return {
        "status": "ok",
        "chains_built": report.total,
        "chains_complete": report.complete,
        "chains_partial": report.partial,
        "chains_broken": report.broken,
        "chains_empty": report.empty,
        "critical_gaps": critical_gaps,
        "critical_gap_count": len(critical_gaps),
        "overall_confidence": round(report.overall_confidence, 3),
        "chains_incomplete": report.partial + report.broken,
        "rebuild": rebuild,
    }


async def asd_chain_report(
    project_id: Optional[str] = None,
    format: str = "summary",
) -> Dict[str, Any]:
    """Отчёт о состоянии документальных цепочек.

    Args:
        project_id: Фильтр по проекту
        format: "summary" (сводка) или "detailed" (полный отчёт с детализацией)

    Returns:
        {"status": "ok", "report": {...}, "formatted": "..."}
    """
    chains = chain_builder.build_chains(evidence_graph)

    if project_id:
        chains = [
            c for c in chains
            if project_id in c.work_unit_id or project_id in c.description
        ]

    report = chain_builder.generate_report(chains)

    result: Dict[str, Any] = {
        "status": "ok",
        "chains_total": report.total,
        "chains_complete": report.complete,
        "chains_partial": report.partial,
        "chains_broken": report.broken,
        "chains_empty": report.empty,
        "completeness_pct": round(
            report.complete / max(report.total, 1) * 100, 1
        ),
        "critical_gaps": report.critical_gaps,
        "high_gaps": report.high_gaps,
        "medium_gaps": report.medium_gaps,
        "low_gaps": report.low_gaps,
        "overall_confidence": round(report.overall_confidence, 3),
        "formatted": chain_builder.format_report(report),
    }

    if format == "detailed":
        result["chains"] = []
        for c in chains:
            result["chains"].append({
                "work_unit_id": c.work_unit_id,
                "work_type": c.work_type,
                "description": c.description,
                "status": c.status.value,
                "color": c.color,
                "confidence": c.confidence,
                "gaps": [
                    {
                        "severity": g.severity.value,
                        "description": g.description,
                        "missing_doc": g.missing_doc_type,
                        "required_by": g.required_by,
                    }
                    for g in c.gaps
                ],
                "materials_count": len(c.materials),
                "aosr_count": len(c.aosr_docs),
                "ks2_count": len(c.ks2_docs),
                "start_date": c.start_date,
                "end_date": c.end_date,
            })

    return result


async def asd_chain_validate(
    work_unit_id: str,
) -> Dict[str, Any]:
    """Валидировать конкретную документальную цепочку WorkUnit.

    Проверяет корректность связей, временную последовательность и полноту цепочки.

    Args:
        work_unit_id: ID WorkUnit (например "WU_001")

    Returns:
        {"status": "ok", "valid": true/false, "chain_length": N, "issues": [...]}
    """
    if not evidence_graph.graph.has_node(work_unit_id):
        return {
            "status": "error",
            "error_code": "NOT_FOUND",
            "message": f"WorkUnit '{work_unit_id}' не найден",
        }

    chains = chain_builder.build_chains(evidence_graph)
    target_chain = None
    for c in chains:
        if c.work_unit_id == work_unit_id:
            target_chain = c
            break

    if not target_chain:
        return {
            "status": "error",
            "error_code": "NOT_FOUND",
            "message": f"Цепочка для '{work_unit_id}' не построена",
        }

    issues = []
    temporal_ok = True
    all_links_present = True

    # Check temporal sequence
    if target_chain.start_date and target_chain.end_date:
        if target_chain.start_date > target_chain.end_date:
            temporal_ok = False
            issues.append("Нарушена временная последовательность: start_date > end_date")

    # Check gaps
    for gap in target_chain.gaps:
        issues.append(f"[{gap.severity.value}] {gap.description}")
        if gap.severity == GapSeverity.CRITICAL:
            all_links_present = False

    # Check certification chain
    for mat in target_chain.materials:
        if not mat.certificates and not mat.passports:
            issues.append(
                f"Материал '{mat.material_name}' ({mat.node_id}) "
                f"без сертификата качества"
            )

    is_valid = len(target_chain.gaps) == 0 and temporal_ok

    return {
        "status": "ok",
        "work_unit_id": work_unit_id,
        "valid": is_valid,
        "chain_status": target_chain.status.value,
        "chain_color": target_chain.color,
        "chain_length": len(target_chain.materials) + len(target_chain.aosr_docs)
                       + len(target_chain.ks2_docs),
        "confidence": target_chain.confidence,
        "temporal_sequence_ok": temporal_ok,
        "all_links_present": all_links_present,
        "issues": issues,
        "gaps": [
            {
                "severity": g.severity.value,
                "description": g.description,
                "missing_doc": g.missing_doc_type,
                "required_by": g.required_by,
            }
            for g in target_chain.gaps
        ],
    }
