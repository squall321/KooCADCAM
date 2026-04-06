"""GRBL serial connection for open-source CNC controllers.

Communicates with GRBL firmware (Arduino/ESP32) via serial port.
Supports real-time status queries, streaming, and buffer management.
"""

from __future__ import annotations

import re
import time
import threading
from typing import Any

from .base import CncConnection, ConnectionState, MachineStatus, MachinePosition


class GrblSerial(CncConnection):
    """Serial connection to GRBL-based CNC controllers.

    Supports:
        - Character-counting streaming protocol
        - Real-time status reports (? command)
        - Feed hold/resume (~, !)
        - Soft reset (Ctrl-X)

    Usage:
        cnc = GrblSerial()
        cnc.connect(port="/dev/ttyUSB0", baudrate=115200)
        cnc.send_program(gcode_text)
        cnc.start()
    """

    GRBL_BUFFER_SIZE = 128  # GRBL serial buffer size in bytes

    def __init__(self) -> None:
        super().__init__()
        self._serial = None
        self._gcode_lines: list[str] = []
        self._current_line = 0
        self._streaming = False
        self._stream_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def connect(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200, **kwargs) -> bool:
        try:
            import serial
            self._serial = serial.Serial(port, baudrate, timeout=2)
            time.sleep(2)  # Wait for GRBL to wake up
            self._serial.flushInput()

            # Send soft reset and wait for welcome
            self._serial.write(b"\x18")
            time.sleep(0.5)
            welcome = self._serial.readline().decode("ascii", errors="ignore").strip()

            if "Grbl" in welcome:
                self._state = ConnectionState.CONNECTED
                return True

            # Try reading one more line
            welcome2 = self._serial.readline().decode("ascii", errors="ignore").strip()
            if "Grbl" in welcome2:
                self._state = ConnectionState.CONNECTED
                return True

            self._state = ConnectionState.ERROR
            raise RuntimeError(f"GRBL not detected. Got: {welcome} {welcome2}")

        except ImportError:
            raise RuntimeError("pyserial not installed. Run: pip install pyserial")
        except Exception as e:
            self._state = ConnectionState.ERROR
            raise RuntimeError(f"Failed to connect to GRBL: {e}")

    def disconnect(self) -> None:
        self._streaming = False
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=5)
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None
        self._state = ConnectionState.DISCONNECTED

    def get_status(self) -> MachineStatus:
        if self._serial is None or not self._serial.is_open:
            return MachineStatus(state=ConnectionState.DISCONNECTED)

        with self._lock:
            self._serial.write(b"?")
            response = self._serial.readline().decode("ascii", errors="ignore").strip()

        status = self._parse_status(response)
        self._notify_status(status)
        return status

    def _parse_status(self, response: str) -> MachineStatus:
        """Parse GRBL status response like <Idle|MPos:0.000,0.000,0.000|...>"""
        status = MachineStatus()

        match = re.match(r"<(\w+)\|(.*)>", response)
        if not match:
            status.state = ConnectionState.CONNECTED
            return status

        grbl_state = match.group(1)
        state_map = {
            "Idle": ConnectionState.CONNECTED,
            "Run": ConnectionState.RUNNING,
            "Hold": ConnectionState.PAUSED,
            "Alarm": ConnectionState.ALARM,
            "Check": ConnectionState.CONNECTED,
            "Home": ConnectionState.CONNECTED,
            "Sleep": ConnectionState.CONNECTED,
        }
        status.state = state_map.get(grbl_state, ConnectionState.CONNECTED)

        fields = match.group(2)
        for field in fields.split("|"):
            if field.startswith("MPos:"):
                coords = field[5:].split(",")
                if len(coords) >= 3:
                    status.position = MachinePosition(
                        float(coords[0]), float(coords[1]), float(coords[2])
                    )
            elif field.startswith("WPos:"):
                coords = field[5:].split(",")
                if len(coords) >= 3:
                    status.work_position = MachinePosition(
                        float(coords[0]), float(coords[1]), float(coords[2])
                    )
            elif field.startswith("FS:") or field.startswith("F:"):
                parts = field.split(":")[1].split(",")
                status.feed_rate = float(parts[0])
                if len(parts) > 1:
                    status.spindle_rpm = float(parts[1])
            elif field.startswith("Ov:"):
                parts = field[3:].split(",")
                if len(parts) >= 2:
                    status.feed_override = float(parts[0])
                    status.spindle_override = float(parts[2]) if len(parts) > 2 else 100

        status.current_line = self._current_line
        status.total_lines = len(self._gcode_lines)
        return status

    def send_program(self, gcode: str, name: str = "program") -> bool:
        self._gcode_lines = [
            line.strip() for line in gcode.splitlines()
            if line.strip() and not line.strip().startswith("%")
        ]
        self._current_line = 0
        return True

    def start(self) -> bool:
        if not self._gcode_lines:
            return False
        self._streaming = True
        self._stream_thread = threading.Thread(target=self._stream_gcode, daemon=True)
        self._stream_thread.start()
        self._state = ConnectionState.RUNNING
        return True

    def _stream_gcode(self) -> None:
        """Character-counting streaming protocol."""
        buffer_used = 0
        line_index = 0

        while self._streaming and line_index < len(self._gcode_lines):
            line = self._gcode_lines[line_index]
            line_bytes = (line + "\n").encode("ascii")

            # Wait for buffer space
            while buffer_used + len(line_bytes) >= self.GRBL_BUFFER_SIZE:
                with self._lock:
                    response = self._serial.readline().decode("ascii", errors="ignore").strip()
                if response.startswith("ok"):
                    buffer_used -= len(line_bytes)
                elif response.startswith("error"):
                    self._state = ConnectionState.ERROR
                    return

            with self._lock:
                self._serial.write(line_bytes)
            buffer_used += len(line_bytes)
            line_index += 1
            self._current_line = line_index

        # Wait for remaining responses
        while buffer_used > 0 and self._streaming:
            with self._lock:
                response = self._serial.readline().decode("ascii", errors="ignore").strip()
            if response:
                buffer_used = max(0, buffer_used - 10)

        if self._streaming:
            self._state = ConnectionState.CONNECTED
        self._streaming = False

    def pause(self) -> bool:
        if self._serial:
            with self._lock:
                self._serial.write(b"!")  # Feed hold
            self._state = ConnectionState.PAUSED
            return True
        return False

    def resume(self) -> bool:
        if self._serial:
            with self._lock:
                self._serial.write(b"~")  # Cycle resume
            self._state = ConnectionState.RUNNING
            return True
        return False

    def stop(self) -> bool:
        self._streaming = False
        if self._serial:
            with self._lock:
                self._serial.write(b"\x18")  # Soft reset
            self._state = ConnectionState.CONNECTED
            return True
        return False

    def send_mdi(self, command: str) -> str:
        if not self._serial:
            return "Error: Not connected"
        with self._lock:
            self._serial.write((command + "\n").encode("ascii"))
            response = self._serial.readline().decode("ascii", errors="ignore").strip()
        return response

    def set_work_offset(self, x: float = 0, y: float = 0, z: float = 0,
                        coordinate_system: str = "G54") -> bool:
        self.send_mdi(f"G10 L20 P1 X{x} Y{y} Z{z}")
        return True

    def home(self, axes: str = "XYZ") -> bool:
        self.send_mdi("$H")
        return True
