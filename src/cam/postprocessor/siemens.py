"""Siemens 840D / Sinumerik post-processor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import PostProcessor

if TYPE_CHECKING:
    from ..tools import CuttingTool


class SiemensPost(PostProcessor):
    """Siemens 840D Sinumerik G-code format.

    Features: CYCLE macros, D1 compensation, SPOS spindle orientation.
    """

    name = "Siemens 840D"
    file_extension = ".mpf"
    decimal_places = 3
    use_line_numbers = True
    line_number_increment = 1

    def format_comment(self, text: str) -> str:
        return f"; {text}"

    def format_header(self, program_name: str) -> list[str]:
        return [
            f"; {program_name}",
            self.format_comment("KooCADCAM - Siemens 840D Post"),
            f"{self._n()}G90 G71 G40 G49 G80",  # Absolute, Metric
            f"{self._n()}G54",
            f"{self._n()}DIAMOF",  # Diameter mode off (radius programming)
        ]

    def format_footer(self) -> list[str]:
        return [
            f"{self._n()}G0 Z200",
            f"{self._n()}M5",
            f"{self._n()}M9",
            f"{self._n()}G0 X0 Y0",
            f"{self._n()}M30",
        ]

    def format_tool_change(self, tool: CuttingTool) -> list[str]:
        return [
            self.format_comment(f"Tool: {tool.name}"),
            f"{self._n()}T{tool.tool_number:d}",
            f"{self._n()}M6",
            f"{self._n()}D1",  # Tool compensation
        ]

    def format_spindle_on(self, rpm: int, cw: bool = True) -> list[str]:
        m = "M3" if cw else "M4"
        return [f"{self._n()}S{rpm} {m}"]

    def format_spindle_off(self) -> list[str]:
        return [f"{self._n()}M5"]

    def format_coolant_on(self, flood: bool = True) -> list[str]:
        return [f"{self._n()}M8"]

    def format_coolant_off(self) -> list[str]:
        return [f"{self._n()}M9"]
