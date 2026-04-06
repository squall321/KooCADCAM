"""CNC connection layer: machine control, serial streaming, industrial protocols."""

from .base import CncConnection, ConnectionState, MachineStatus
from .simulator import SoftSimulator

__all__ = [
    "CncConnection", "ConnectionState", "MachineStatus",
    "SoftSimulator",
]
