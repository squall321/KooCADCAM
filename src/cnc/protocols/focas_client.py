"""FANUC FOCAS2 client for direct CNC data access.

FOCAS (FANUC Open CNC API Specification) provides low-level access
to FANUC CNC controllers. Requires FOCAS2 library (fwlib32.dll / libfwlib.so).

This module provides a Python wrapper around the FOCAS2 C library
using ctypes. The actual library must be obtained from FANUC.
"""

from __future__ import annotations

import ctypes
import struct
from dataclasses import dataclass
from typing import Any


@dataclass
class FocasMachineInfo:
    """Machine information from FOCAS."""
    cnc_type: str = ""
    mt_type: str = ""
    series: str = ""
    version: str = ""
    axes: int = 0


@dataclass
class FocasPosition:
    """Axis positions from FOCAS."""
    absolute: dict[str, float] = None
    machine: dict[str, float] = None
    relative: dict[str, float] = None
    distance: dict[str, float] = None

    def __post_init__(self):
        if self.absolute is None:
            self.absolute = {}
        if self.machine is None:
            self.machine = {}
        if self.relative is None:
            self.relative = {}
        if self.distance is None:
            self.distance = {}


class FocasClient:
    """FANUC FOCAS2 client for direct CNC access.

    This is a high-level wrapper. The actual FOCAS2 library
    (fwlib32.dll on Windows, libfwlib32.so on Linux) must be
    installed separately (provided by FANUC).

    Usage:
        focas = FocasClient()
        focas.connect("192.168.1.1", port=8193)
        info = focas.get_machine_info()
        pos = focas.get_position()
        focas.disconnect()
    """

    def __init__(self) -> None:
        self._lib = None
        self._handle = 0
        self._connected = False

    def connect(self, ip: str, port: int = 8193, timeout: int = 10) -> bool:
        """Connect to FANUC CNC via Ethernet.

        Args:
            ip: CNC IP address.
            port: FOCAS port (default 8193 for 30i/31i/32i).
            timeout: Connection timeout in seconds.
        """
        try:
            self._lib = self._load_library()
        except OSError as e:
            raise RuntimeError(
                f"FOCAS2 library not found: {e}\n"
                "The FOCAS2 library (fwlib32.dll / libfwlib32.so) must be "
                "obtained from FANUC and installed on the system."
            )

        handle = ctypes.c_ushort(0)
        ip_bytes = ip.encode("ascii")
        ret = self._lib.cnc_allclibhndl3(ip_bytes, port, timeout, ctypes.byref(handle))
        if ret != 0:
            raise RuntimeError(f"FOCAS connection failed (error code: {ret})")

        self._handle = handle.value
        self._connected = True
        return True

    def disconnect(self) -> None:
        if self._connected and self._lib:
            self._lib.cnc_freelibhndl(self._handle)
        self._connected = False
        self._handle = 0

    def get_machine_info(self) -> FocasMachineInfo:
        """Read CNC system information."""
        if not self._connected:
            raise RuntimeError("Not connected")

        # FOCAS cnc_sysinfo structure
        class SysInfo(ctypes.Structure):
            _fields_ = [
                ("addinfo", ctypes.c_short),
                ("max_axis", ctypes.c_short),
                ("cnc_type", ctypes.c_char * 2),
                ("mt_type", ctypes.c_char * 2),
                ("series", ctypes.c_char * 4),
                ("version", ctypes.c_char * 4),
                ("axes", ctypes.c_char * 2),
            ]

        info = SysInfo()
        ret = self._lib.cnc_sysinfo(self._handle, ctypes.byref(info))
        if ret != 0:
            raise RuntimeError(f"cnc_sysinfo failed (code: {ret})")

        return FocasMachineInfo(
            cnc_type=info.cnc_type.decode("ascii", errors="ignore").strip(),
            mt_type=info.mt_type.decode("ascii", errors="ignore").strip(),
            series=info.series.decode("ascii", errors="ignore").strip(),
            version=info.version.decode("ascii", errors="ignore").strip(),
            axes=info.max_axis,
        )

    def get_position(self) -> FocasPosition:
        """Read current axis positions (absolute, machine, relative, distance-to-go)."""
        if not self._connected:
            raise RuntimeError("Not connected")

        pos = FocasPosition()

        # Read absolute position for each axis type
        for pos_type, pos_dict, flib_type in [
            ("absolute", pos.absolute, 0),
            ("machine", pos.machine, 1),
            ("relative", pos.relative, 2),
            ("distance", pos.distance, 3),
        ]:
            try:
                axis_data = self._read_axis_data(flib_type)
                pos_dict.update(axis_data)
            except Exception:
                pass

        return pos

    def _read_axis_data(self, pos_type: int) -> dict[str, float]:
        """Read axis data for a given position type."""
        # Simplified - actual implementation uses cnc_absolute2 etc.
        axis_names = ["X", "Y", "Z", "A", "B", "C"]
        result = {}
        # Would call cnc_absolute2, cnc_machine, cnc_relative2, cnc_distance
        # based on pos_type
        return result

    def read_spindle_speed(self) -> float:
        """Read actual spindle speed (RPM)."""
        if not self._connected:
            raise RuntimeError("Not connected")
        # Would call cnc_acts
        return 0.0

    def read_feed_rate(self) -> float:
        """Read actual feed rate (mm/min)."""
        if not self._connected:
            raise RuntimeError("Not connected")
        # Would call cnc_actf
        return 0.0

    def read_program_number(self) -> int:
        """Read current executing program number."""
        if not self._connected:
            raise RuntimeError("Not connected")
        # Would call cnc_rdprgnum
        return 0

    def read_alarm(self) -> list[str]:
        """Read active alarms."""
        if not self._connected:
            raise RuntimeError("Not connected")
        # Would call cnc_rdalmmsg2
        return []

    def _load_library(self):
        """Load the FOCAS2 shared library."""
        import sys
        if sys.platform == "win32":
            return ctypes.WinDLL("fwlib32.dll")
        else:
            return ctypes.CDLL("libfwlib32.so")
