"""TTK generators package — auto-registration on import."""
from .ttk_welding import TTKWelding
from .ttk_sheet_pile import TTKSheetPile
from .ttk_anticorrosion import TTKAnticorrosion
from .ttk_concrete import TTKConcrete
from .ttk_earthwork import TTKEarthwork
from .ttk_metalwork import TTKMetalwork

__all__ = [
    "TTKWelding",
    "TTKSheetPile",
    "TTKAnticorrosion",
    "TTKConcrete",
    "TTKEarthwork",
    "TTKMetalwork",
]