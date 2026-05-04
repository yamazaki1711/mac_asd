"""
ASD v13.0 — Core Services.

Lazy imports to avoid cascading failures: each service module is loaded
on first access, not at package import time.
"""

__all__ = [
    "LegalService", "legal_service",
    "PTOAgent", "pto_agent",
    "DeloAgent", "delo_agent",
    "JournalRestorer", "journal_restorer",
]


def __getattr__(name: str):
    """Lazy service imports — load module only when accessed."""
    _LAZY_IMPORTS = {
        "LegalService": "src.core.services.legal_service",
        "legal_service": "src.core.services.legal_service",
        "PTOAgent": "src.core.services.pto_agent",
        "pto_agent": "src.core.services.pto_agent",
        "DeloAgent": "src.core.services.delo_agent",
        "delo_agent": "src.core.services.delo_agent",
        "JournalRestorer": "src.core.services.journal_restorer",
        "journal_restorer": "src.core.services.journal_restorer",
    }
    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = __import__(_LAZY_IMPORTS[name], fromlist=[name])
    attr = getattr(module, name)
    # Cache in globals so __getattr__ is only called once per name
    globals()[name] = attr
    return attr


def get_batch_id_generator():
    """Lazy import to avoid hard dependency on python-docx."""
    from src.core.services.batch_id_generator import BatchIDGenerator, batch_id_generator
    return BatchIDGenerator, batch_id_generator
