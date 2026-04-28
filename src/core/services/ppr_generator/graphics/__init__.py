"""
PPR Generator — Graphics module v0.1.

Placeholder generators that return GraphicResult metadata
describing each drawing. Actual SVG/DXF rendering is deferred.
"""

from __future__ import annotations

from .site_plan import generate_site_plan
from .tech_schemes import generate_tech_schemes
from .slinging import generate_slinging_schemes
from .equipment_table import generate_equipment_table
from .schedule import generate_schedule

__all__ = [
    "generate_site_plan",
    "generate_tech_schemes",
    "generate_slinging_schemes",
    "generate_equipment_table",
    "generate_schedule",
]
