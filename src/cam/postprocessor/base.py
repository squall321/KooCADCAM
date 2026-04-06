"""Abstract base class for CNC post-processors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..tools import CuttingTool


class PostProcessor(ABC):
    """Base post-processor defining the interface for G-code formatting.

    Subclasses implement machine-specific G-code dialect.
    """

    name: str = "Generic"
    file_extension: str = ".nc"
    decimal_places: int = 3
    use_line_numbers: bool = False
    line_number_increment: int = 10

    def __init__(self) -> None:
        self._line_number = 0

    def _n(self) -> str:
        """Generate optional line number prefix."""
        if not self.use_line_numbers:
            return ""
        self._line_number += self.line_number_increment
        return f"N{self._line_number} "

    def _fmt(self, val: float) -> str:
        """Format a coordinate value."""
        return f"{val:.{self.decimal_places}f}"

    def format_comment(self, text: str) -> str:
        return f"({text})"

    @abstractmethod
    def format_header(self, program_name: str) -> list[str]:
        ...

    @abstractmethod
    def format_footer(self) -> list[str]:
        ...

    @abstractmethod
    def format_tool_change(self, tool: CuttingTool) -> list[str]:
        ...

    @abstractmethod
    def format_spindle_on(self, rpm: int, cw: bool = True) -> list[str]:
        ...

    @abstractmethod
    def format_spindle_off(self) -> list[str]:
        ...

    @abstractmethod
    def format_coolant_on(self, flood: bool = True) -> list[str]:
        ...

    @abstractmethod
    def format_coolant_off(self) -> list[str]:
        ...

    def format_rapid(self, x: float, y: float, z: float) -> str:
        return f"{self._n()}G0 X{self._fmt(x)} Y{self._fmt(y)} Z{self._fmt(z)}"

    def format_linear(self, x: float, y: float, z: float, feed: float | None = None) -> str:
        line = f"{self._n()}G1 X{self._fmt(x)} Y{self._fmt(y)} Z{self._fmt(z)}"
        if feed is not None:
            line += f" F{self._fmt(feed)}"
        return line

    def format_arc_cw(
        self, x: float, y: float, z: float,
        i: float, j: float, k: float, feed: float | None = None,
    ) -> str:
        line = (f"{self._n()}G2 X{self._fmt(x)} Y{self._fmt(y)} Z{self._fmt(z)}"
                f" I{self._fmt(i)} J{self._fmt(j)} K{self._fmt(k)}")
        if feed is not None:
            line += f" F{self._fmt(feed)}"
        return line

    def format_arc_ccw(
        self, x: float, y: float, z: float,
        i: float, j: float, k: float, feed: float | None = None,
    ) -> str:
        line = (f"{self._n()}G3 X{self._fmt(x)} Y{self._fmt(y)} Z{self._fmt(z)}"
                f" I{self._fmt(i)} J{self._fmt(j)} K{self._fmt(k)}")
        if feed is not None:
            line += f" F{self._fmt(feed)}"
        return line
