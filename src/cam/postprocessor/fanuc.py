"""FANUC post-processor - most widely used CNC controller."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import PostProcessor

if TYPE_CHECKING:
    from ..tools import CuttingTool


class FanucPost(PostProcessor):
    """FANUC controller G-code format.

    Features: G54 work coordinates, T/M6 tool change, M3/M5 spindle, M8/M9 coolant.
    """

    name = "FANUC"
    file_extension = ".nc"
    decimal_places = 3
    use_line_numbers = True
    line_number_increment = 10

    def format_comment(self, text: str) -> str:
        return f"({text})"

    def format_header(self, program_name: str) -> list[str]:
        return [
            f"%",
            f"{program_name}",
            self.format_comment(f"KooCADCAM - FANUC Post"),
            f"{self._n()}G90 G21 G40 G49 G80",  # Absolute, Metric, Cancel comp
            f"{self._n()}G54",                    # Work coordinate system
        ]

    def format_footer(self) -> list[str]:
        return [
            f"{self._n()}G91 G28 Z0",   # Return to reference Z
            f"{self._n()}G28 X0 Y0",     # Return to reference XY
            f"{self._n()}M30",           # Program end & rewind
            f"%",
        ]

    def format_tool_change(self, tool: CuttingTool) -> list[str]:
        return [
            f"{self._n()}G91 G28 Z0",
            self.format_comment(f"Tool: {tool.name}"),
            f"{self._n()}T{tool.tool_number:02d} M6",
            f"{self._n()}G90 G54",
        ]

    def format_spindle_on(self, rpm: int, cw: bool = True) -> list[str]:
        m = "M3" if cw else "M4"
        return [f"{self._n()}{m} S{rpm}"]

    def format_spindle_off(self) -> list[str]:
        return [f"{self._n()}M5"]

    def format_coolant_on(self, flood: bool = True) -> list[str]:
        return [f"{self._n()}M8" if flood else f"{self._n()}M7"]

    def format_coolant_off(self) -> list[str]:
        return [f"{self._n()}M9"]
