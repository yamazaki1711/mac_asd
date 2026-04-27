"""
ASD v12.0 — Pydantic Schemas.

Typed input/output contracts for all agents and services.
"""

from src.schemas.legal import (
    LegalFinding,
    LegalSeverity,
    LegalFindingCategory,
    LegalVerdict,
    LegalAnalysisRequest,
    LegalAnalysisResult,
    ContractUploadResult,
)

__all__ = [
    "LegalFinding",
    "LegalSeverity",
    "LegalFindingCategory",
    "LegalVerdict",
    "LegalAnalysisRequest",
    "LegalAnalysisResult",
    "ContractUploadResult",
]
