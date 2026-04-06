"""LinuxCNC connection via Python API (linuxcnc module).

Requires LinuxCNC to be installed on the system.
The linuxcnc Python module provides direct access to the
LinuxCNC motion controller via shared memory.
"""

from __future__ import annotations

import time
from typing import Any

from .base import CncConnection, ConnectionState, MachineStatus, MachinePosition


class LinuxCncClient(CncConnection):
    """Direct connection to LinuxCNC via its Python API.

    Prerequisites:
        - LinuxCNC installed (provides `linuxcnc` Python module)
        - LinuxCNC running with a valid configuration
        - User has permissions for LinuxCNC shared memory

    Usage:
        cnc = LinuxCncClient()
        cnc.connect()
        cnc.send_program(gcode_text)
        cnc.start()
    """

    def __init__(self) -> None:
        super().__init__()
        self._stat = None
        self._cmd = None
        self._error = None

    def connect(self, **kwargs) -> bool:
        try:
            import linuxcnc
            self._stat = linuxcnc.stat()
            self._cmd = linuxcnc.command()
            self._error = linuxcnc.error_channel()
            self._stat.poll()
            self._state = ConnectionState.CONNECTED
            return True
        except ImportError:
            self._state = ConnectionState.ERROR
            raise RuntimeError(
                "LinuxCNC Python module not found. "
                "Install LinuxCNC or run on a LinuxCNC-enabled system."
            )
        except Exception as e:
            self._state = ConnectionState.ERROR
            raise RuntimeError(f"Failed to connect to LinuxCNC: {e}")

    def disconnect(self) -> None:
        self._stat = None
        self._cmd = None
        self._error = None
        self._state = ConnectionState.DISCONNECTED

    def get_status(self) -> MachineStatus:
        if self._stat is None:
            return MachineStatus(state=ConnectionState.DISCONNECTED)

        self._stat.poll()
        s = self._stat

        # Map LinuxCNC interp state to our state
        import linuxcnc
        if s.estop:
            state = ConnectionState.ALARM
        elif s.task_mode == linuxcnc.MODE_AUTO and s.interp_state == linuxcnc.INTERP_READING:
            state = ConnectionState.RUNNING
        elif s.paused:
            state = ConnectionState.PAUSED
        else:
            state = ConnectionState.CONNECTED

        pos = s.actual_position
        wpos = s.g5x_offset

        # Check for errors
        alarms = []
        error = self._error.poll()
        if error:
            kind, text = error
            alarms.append(text)

        status = MachineStatus(
            state=state,
            position=MachinePosition(pos[0], pos[1], pos[2], pos[3], pos[4], pos[5]),
            work_position=MachinePosition(
                pos[0] - wpos[0], pos[1] - wpos[1], pos[2] - wpos[2],
                pos[3] - wpos[3], pos[4] - wpos[4], pos[5] - wpos[5],
            ),
            feed_rate=s.current_vel * 60,  # Convert to mm/min
            feed_override=s.feedrate * 100,
            spindle_rpm=abs(s.spindle[0].get("speed", 0)),
            spindle_override=s.spindlerate * 100,
            current_line=s.current_line,
            total_lines=s.line_count if hasattr(s, "line_count") else 0,
            program_name=s.file or "",
            alarms=alarms,
        )
        self._notify_status(status)
        return status

    def send_program(self, gcode: str, name: str = "program") -> bool:
        import tempfile
        import os
        # Write G-code to temp file (LinuxCNC loads from file)
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".ngc", delete=False, prefix="koocadcam_")
        tmp.write(gcode)
        tmp.close()
        self._temp_file = tmp.name

        import linuxcnc
        self._cmd.mode(linuxcnc.MODE_AUTO)
        self._cmd.wait_complete()
        self._cmd.program_open(tmp.name)
        return True

    def start(self) -> bool:
        import linuxcnc
        self._cmd.mode(linuxcnc.MODE_AUTO)
        self._cmd.wait_complete()
        self._cmd.auto(linuxcnc.AUTO_RUN, 0)
        self._state = ConnectionState.RUNNING
        return True

    def pause(self) -> bool:
        import linuxcnc
        self._cmd.auto(linuxcnc.AUTO_PAUSE)
        self._state = ConnectionState.PAUSED
        return True

    def resume(self) -> bool:
        import linuxcnc
        self._cmd.auto(linuxcnc.AUTO_RESUME)
        self._state = ConnectionState.RUNNING
        return True

    def stop(self) -> bool:
        import linuxcnc
        self._cmd.abort()
        self._state = ConnectionState.CONNECTED
        return True

    def send_mdi(self, command: str) -> str:
        import linuxcnc
        self._cmd.mode(linuxcnc.MODE_MDI)
        self._cmd.wait_complete()
        self._cmd.mdi(command)
        self._cmd.wait_complete()
        return "OK"

    def set_work_offset(self, x: float = 0, y: float = 0, z: float = 0,
                        coordinate_system: str = "G54") -> bool:
        self.send_mdi(f"{coordinate_system}")
        self.send_mdi(f"G10 L20 P1 X{x} Y{y} Z{z}")
        return True

    def home(self, axes: str = "XYZ") -> bool:
        import linuxcnc
        self._cmd.mode(linuxcnc.MODE_MANUAL)
        self._cmd.wait_complete()
        axis_map = {"X": 0, "Y": 1, "Z": 2, "A": 3, "B": 4, "C": 5}
        for axis_char in axes.upper():
            if axis_char in axis_map:
                self._cmd.home(axis_map[axis_char])
        self._cmd.wait_complete(60)
        return True
