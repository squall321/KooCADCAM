"""Abstract base for CNC machine connections."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RUNNING = "running"
    PAUSED = "paused"
    ALARM = "alarm"
    ERROR = "error"


@dataclass
class MachinePosition:
    """Current machine position in all axes."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    a: float = 0.0
    b: float = 0.0
    c: float = 0.0


@dataclass
class MachineStatus:
    """Complete machine status snapshot."""
    state: ConnectionState = ConnectionState.DISCONNECTED
    position: MachinePosition = field(default_factory=MachinePosition)
    work_position: MachinePosition = field(default_factory=MachinePosition)
    feed_rate: float = 0.0
    feed_override: float = 100.0
    spindle_rpm: float = 0.0
    spindle_override: float = 100.0
    current_line: int = 0
    total_lines: int = 0
    program_name: str = ""
    alarms: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    @property
    def progress_pct(self) -> float:
        if self.total_lines == 0:
            return 0.0
        return 100.0 * self.current_line / self.total_lines


class CncConnection(ABC):
    """Abstract base class for CNC machine connections.

    All CNC controllers (LinuxCNC, GRBL, FANUC FOCAS, etc.)
    implement this interface for unified access.
    """

    def __init__(self) -> None:
        self._state = ConnectionState.DISCONNECTED
        self._status_callbacks: list[Callable[[MachineStatus], None]] = []

    @property
    def state(self) -> ConnectionState:
        return self._state

    def on_status(self, callback: Callable[[MachineStatus], None]) -> None:
        """Register a callback for status updates."""
        self._status_callbacks.append(callback)

    def _notify_status(self, status: MachineStatus) -> None:
        for cb in self._status_callbacks:
            cb(status)

    @abstractmethod
    def connect(self, **kwargs) -> bool:
        """Establish connection to CNC controller."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection."""
        ...

    @abstractmethod
    def get_status(self) -> MachineStatus:
        """Poll current machine status."""
        ...

    @abstractmethod
    def send_program(self, gcode: str, name: str = "program") -> bool:
        """Upload a G-code program."""
        ...

    @abstractmethod
    def start(self) -> bool:
        """Start program execution."""
        ...

    @abstractmethod
    def pause(self) -> bool:
        """Pause execution (feed hold)."""
        ...

    @abstractmethod
    def resume(self) -> bool:
        """Resume after pause."""
        ...

    @abstractmethod
    def stop(self) -> bool:
        """Stop execution (emergency or controlled)."""
        ...

    @abstractmethod
    def send_mdi(self, command: str) -> str:
        """Send a single MDI (Manual Data Input) command."""
        ...

    @abstractmethod
    def set_work_offset(self, x: float = 0, y: float = 0, z: float = 0,
                        coordinate_system: str = "G54") -> bool:
        """Set work coordinate offset."""
        ...

    @abstractmethod
    def home(self, axes: str = "XYZ") -> bool:
        """Home specified axes."""
        ...
