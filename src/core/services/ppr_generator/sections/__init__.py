"""PPR Generator — Section generators."""
from .general_data import generate_general_data
from .work_organization import generate_work_organization
from .ps_works import generate_ps_works
from .quality_control import generate_quality_control
from .manpower import generate_manpower
from .machinery import generate_machinery
from .safety import generate_safety
from .attestation import generate_attestation
from .title_page import generate_title_page
from .approval_sheet import generate_approval_sheet

# Trigger TTK generator auto-registration
from . import ttk  # noqa: F401

__all__ = [
    "generate_general_data",
    "generate_work_organization",
    "generate_ps_works",
    "generate_quality_control",
    "generate_manpower",
    "generate_machinery",
    "generate_safety",
    "generate_attestation",
    "generate_title_page",
    "generate_approval_sheet",
]
