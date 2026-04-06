from .base import CadModule
from .holes import ThroughHole, CounterboreHole, CountersinkHole, TappedHole
from .pockets import RectPocket, CircularPocket, ObroundPocket
from .slots import TSlot, Dovetail, KeySlot

__all__ = [
    "CadModule",
    "ThroughHole", "CounterboreHole", "CountersinkHole", "TappedHole",
    "RectPocket", "CircularPocket", "ObroundPocket",
    "TSlot", "Dovetail", "KeySlot",
]
