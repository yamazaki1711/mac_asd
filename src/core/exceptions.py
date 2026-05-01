"""
ASD v12.0 — Domain-specific exceptions.

Replaces broad except Exception with typed, actionable error classes.
Each exception maps to a specific recovery strategy.
"""


class ASDError(Exception):
    """Base exception for all ASD domain errors."""
    pass


# --- Network & Integration ---

class NetworkError(ASDError):
    """Network-level failure: timeout, DNS, connection refused."""
    pass


class IntegrationAuthError(ASDError):
    """Authentication failure for external integration."""
    pass


class IntegrationRateLimitError(ASDError):
    """Rate limit hit on external API."""
    pass


class IntegrationParseError(ASDError):
    """Failed to parse response from external integration."""
    pass


# --- Document Processing ---

class DocumentParseError(ASDError):
    """Failed to parse a document (PDF, DOCX, DXF, etc.)."""
    pass


class DocumentNotFoundError(ASDError):
    """Document not found in repository."""
    pass


# --- LLM ---

class LLMUnavailableError(ASDError):
    """LLM backend is unavailable."""
    pass


class LLMResponseError(ASDError):
    """LLM returned an invalid/unparseable response."""
    pass


# --- Storage ---

class StorageError(ASDError):
    """Storage operation failed (DB, filesystem, cache)."""
    pass


class EntityNotFoundError(StorageError):
    """Entity not found in storage."""
    pass


# --- Workflow ---

class WorkflowError(ASDError):
    """Workflow execution error."""
    pass


class PlanExecutionError(WorkflowError):
    """WorkPlan execution failed."""
    pass


class RAMRejectedError(WorkflowError):
    """Task rejected due to RAM constraints."""
    pass
