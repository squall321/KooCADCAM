"""GRBL post-processor for open-source/hobby CNC machines."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import PostProcessor

if TYPE_CHECKING:
    from ..tools import CuttingTool


class GrblPost(PostProcessor):
    """GRBL G-code format (for Arduino/ESP32-based CNC controllers).

    Features: Compact format, no line numbers, 3 decimal places.
    No tool changer - manual tool change with M0 pause.
    """

    name = "GRBL"
    file_extension = ".gcode"
    decimal_places = 3
    use_line_numbers = False

    def format_comment(self, text: str) -> str:
        return f"; {text}"

    def format_header(self, program_name: str) -> list[str]:
        return [
            self.format_comment(f"Program: {program_name}"),
            self.format_comment("KooCADCAM - GRBL Post"),
            "G90 G21",  # Absolute, Metric
            "G17",      # XY plane
        ]

    def format_footer(self) -> list[str]:
        return [
            "M5",       # Spindle off
            "G0 Z10",   # Retract
            "G0 X0 Y0", # Home XY
            "M2",       # Program end
        ]

    def format_tool_change(self, tool: CuttingTool) -> list[str]:
        return [
            "M5",   # Spindle off
            "G0 Z20",  # Safe retract
            self.format_comment(f"Change to: {tool.name}"),
            "M0",   # Pause for manual tool change
        ]

    def format_spindle_on(self, rpm: int, cw: bool = True) -> list[str]:
        m = "M3" if cw else "M4"
        return [f"{m} S{rpm}"]

    def format_spindle_off(self) -> list[str]:
        return ["M5"]

    def format_coolant_on(self, flood: bool = True) -> list[str]:
        return ["M8" if flood else "M7"]

    def format_coolant_off(self) -> list[str]:
        return ["M9"]
