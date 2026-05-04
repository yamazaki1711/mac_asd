"""
ASD v12.0 — Core Services.
"""

from src.core.services.legal_service import LegalService, legal_service
from src.core.services.pto_agent import PTOAgent, pto_agent
from src.core.services.delo_agent import DeloAgent, delo_agent
from src.core.services.journal_restorer import JournalRestorer, journal_restorer

__all__ = [
    "LegalService", "legal_service",
    "PTOAgent", "pto_agent",
    "DeloAgent", "delo_agent",
    "JournalRestorer", "journal_restorer",
]


def get_batch_id_generator():
    """Lazy import to avoid hard dependency on python-docx."""
    from src.core.services.batch_id_generator import BatchIDGenerator, batch_id_generator
    return BatchIDGenerator, batch_id_generator
