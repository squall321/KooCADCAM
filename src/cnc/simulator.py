"""Software CNC simulator - runs G-code without real hardware.

Useful for verification, timing estimation, and GUI development
without a physical CNC machine connected.
"""

from __future__ import annotations

import time
import threading
from typing import Any

from .base import CncConnection, ConnectionState, MachineStatus, MachinePosition
from ..sim.gcode_parser import GcodeParser, PathSegment, PathType


class SoftSimulator(CncConnection):
    """Software-based CNC simulator.

    Parses G-code and simulates execution in real-time or accelerated.
    Provides position and status updates as if connected to a real machine.

    Usage:
        sim = SoftSimulator(speed_factor=10.0)  # 10x speed
        sim.connect()
        sim.send_program(gcode)
        sim.on_status(lambda s: print(f"Pos: {s.position.x}, {s.position.y}, {s.position.z}"))
        sim.start()
    """

    def __init__(self, speed_factor: float = 1.0, update_rate: float = 20.0) -> None:
        """
        Args:
            speed_factor: Simulation speed multiplier (1.0 = real-time).
            update_rate: Status update frequency (Hz).
        """
        super().__init__()
        self._speed_factor = speed_factor
        self._update_interval = 1.0 / update_rate
        self._parser = GcodeParser()
        self._segments: list[PathSegment] = []
        self._gcode_text = ""
        self._gcode_lines: list[str] = []

        self._position = MachinePosition()
        self._spindle_rpm = 0.0
        self._feed_rate = 0.0
        self._current_segment = 0
        self._running = False
        self._paused = False
        self._thread: threading.Thread | None = None

    def connect(self, **kwargs) -> bool:
        self._state = ConnectionState.CONNECTED
        self._position = MachinePosition()
        return True

    def disconnect(self) -> None:
        self.stop()
        self._state = ConnectionState.DISCONNECTED

    def get_status(self) -> MachineStatus:
        status = MachineStatus(
            state=self._state,
            position=MachinePosition(
                self._position.x, self._position.y, self._position.z
            ),
            work_position=MachinePosition(
                self._position.x, self._position.y, self._position.z
            ),
            feed_rate=self._feed_rate,
            spindle_rpm=self._spindle_rpm,
            current_line=self._current_segment,
            total_lines=len(self._segments),
            program_name="simulation",
        )
        return status

    def send_program(self, gcode: str, name: str = "program") -> bool:
        self._gcode_text = gcode
        self._gcode_lines = gcode.splitlines()
        self._segments = self._parser.parse_text(gcode)
        self._current_segment = 0
        return True

    def start(self) -> bool:
        if not self._segments:
            return False
        self._running = True
        self._paused = False
        self._state = ConnectionState.RUNNING
        self._thread = threading.Thread(target=self._simulate, daemon=True)
        self._thread.start()
        return True

    def _simulate(self) -> None:
        """Run simulation loop."""
        import math

        for i, seg in enumerate(self._segments):
            if not self._running:
                break

            while self._paused and self._running:
                time.sleep(0.05)

            self._current_segment = i

            # Calculate move distance and time
            dx = seg.x_end - seg.x_start
            dy = seg.y_end - seg.y_start
            dz = seg.z_end - seg.z_start
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)

            if seg.path_type == PathType.RAPID:
                # Rapid at 5000 mm/min
                feed = 5000.0
                self._feed_rate = 0.0
            else:
                feed = seg.feed_rate if seg.feed_rate > 0 else 500.0
                self._feed_rate = feed

            move_time = (dist / feed * 60.0) / self._speed_factor if feed > 0 else 0

            # Interpolate position
            if move_time > 0:
                steps = max(1, int(move_time / self._update_interval))
                for step in range(steps):
                    if not self._running:
                        break
                    while self._paused and self._running:
                        time.sleep(0.05)

                    t = (step + 1) / steps
                    self._position.x = seg.x_start + dx * t
                    self._position.y = seg.y_start + dy * t
                    self._position.z = seg.z_start + dz * t

                    self._notify_status(self.get_status())
                    time.sleep(self._update_interval / self._speed_factor)
            else:
                self._position.x = seg.x_end
                self._position.y = seg.y_end
                self._position.z = seg.z_end

        self._running = False
        self._state = ConnectionState.CONNECTED
        self._feed_rate = 0.0
        self._notify_status(self.get_status())

    def pause(self) -> bool:
        self._paused = True
        self._state = ConnectionState.PAUSED
        return True

    def resume(self) -> bool:
        self._paused = False
        self._state = ConnectionState.RUNNING
        return True

    def stop(self) -> bool:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._state = ConnectionState.CONNECTED
        return True

    def send_mdi(self, command: str) -> str:
        return f"SIM: {command} (simulated)"

    def set_work_offset(self, x: float = 0, y: float = 0, z: float = 0,
                        coordinate_system: str = "G54") -> bool:
        return True

    def home(self, axes: str = "XYZ") -> bool:
        self._position = MachinePosition()
        return True

    @property
    def progress(self) -> float:
        """Current progress as percentage."""
        if not self._segments:
            return 0.0
        return 100.0 * self._current_segment / len(self._segments)
