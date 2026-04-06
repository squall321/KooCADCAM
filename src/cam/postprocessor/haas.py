"""Haas VF series post-processor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import PostProcessor

if TYPE_CHECKING:
    from ..tools import CuttingTool


class HaasPost(PostProcessor):
    """Haas VF series G-code format.

    Features: G187 accuracy control, macro variables, probing G65.
    """

    name = "Haas"
    file_extension = ".nc"
    decimal_places = 4
    use_line_numbers = False

    def format_comment(self, text: str) -> str:
        return f"({text})"

    def format_header(self, program_name: str) -> list[str]:
        return [
            f"%",
            f"{program_name}",
            self.format_comment("KooCADCAM - Haas Post"),
            f"G90 G21 G40 G49 G80",
            f"G54",
            f"G187 P1",  # High accuracy mode
        ]

    def format_footer(self) -> list[str]:
        return [
            f"G91 G28 Z0",
            f"G91 G28 X0 Y0",
            f"M30",
            f"%",
        ]

    def format_tool_change(self, tool: CuttingTool) -> list[str]:
        return [
            f"G91 G28 Z0",
            self.format_comment(f"Tool: {tool.name}"),
            f"T{tool.tool_number:02d} M6",
            f"G90 G54",
            f"G43 H{tool.tool_number:02d}",  # Tool length compensation
        ]

    def format_spindle_on(self, rpm: int, cw: bool = True) -> list[str]:
        m = "M3" if cw else "M4"
        return [f"S{rpm} {m}"]

    def format_spindle_off(self) -> list[str]:
        return ["M5"]

    def format_coolant_on(self, flood: bool = True) -> list[str]:
        return ["M8" if flood else "M7"]

    def format_coolant_off(self) -> list[str]:
        return ["M9"]
