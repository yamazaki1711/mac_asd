"""
ASD v12.0 — Knowledge Base Module.

Hybrid knowledge base for PTO agent:
  - idprosto_loader: 31 work types, 569 doc mappings from id-prosto.ru
  - template_registry: 149 DOCX templates from 39 form packages
  - invalidation_engine: platform-level regulatory change detection & validity checks
"""

from src.core.knowledge.idprosto_loader import idprosto_loader, IDPROSTO_WORK_TYPES
from src.core.knowledge.template_registry import TemplateRegistry, template_registry
from src.core.knowledge.invalidation_engine import (
    InvalidationEngine,
    invalidation_engine,
    ChangeType,
    EntryStatus,
    RegulatoryChange,
    AffectedEntry,
)

__all__ = [
    "idprosto_loader",
    "IDPROSTO_WORK_TYPES",
    "TemplateRegistry",
    "template_registry",
    "InvalidationEngine",
    "invalidation_engine",
    "ChangeType",
    "EntryStatus",
    "RegulatoryChange",
    "AffectedEntry",
]
