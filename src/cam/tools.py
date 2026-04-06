"""CNC cutting tool definitions and preset library."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ToolType(Enum):
    FLAT_ENDMILL = "flat_endmill"
    BALL_ENDMILL = "ball_endmill"
    BULL_ENDMILL = "bull_endmill"  # corner radius endmill
    DRILL = "drill"
    CHAMFER_MILL = "chamfer_mill"
    FACE_MILL = "face_mill"


@dataclass
class CuttingTool:
    """Definition of a CNC cutting tool."""
    name: str
    tool_type: ToolType
    diameter: float          # mm
    flute_length: float      # mm
    shank_diameter: float | None = None
    corner_radius: float = 0.0  # for bull endmill
    flutes: int = 2
    tool_number: int = 1

    @property
    def radius(self) -> float:
        return self.diameter / 2

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CuttingTool:
        return cls(
            name=d["name"],
            tool_type=ToolType(d["type"]),
            diameter=d["diameter"],
            flute_length=d["flute_length"],
            shank_diameter=d.get("shank_diameter"),
            corner_radius=d.get("corner_radius", 0.0),
            flutes=d.get("flutes", 2),
            tool_number=d.get("tool_number", 1),
        )


# Preset tool library
TOOL_LIBRARY: dict[str, CuttingTool] = {
    "flat_6mm": CuttingTool("6mm Flat Endmill", ToolType.FLAT_ENDMILL, 6.0, 20.0, flutes=2, tool_number=1),
    "flat_10mm": CuttingTool("10mm Flat Endmill", ToolType.FLAT_ENDMILL, 10.0, 30.0, flutes=3, tool_number=2),
    "flat_20mm": CuttingTool("20mm Flat Endmill", ToolType.FLAT_ENDMILL, 20.0, 40.0, flutes=4, tool_number=3),
    "ball_3mm": CuttingTool("3mm Ball Endmill", ToolType.BALL_ENDMILL, 3.0, 15.0, flutes=2, tool_number=4),
    "ball_6mm": CuttingTool("6mm Ball Endmill", ToolType.BALL_ENDMILL, 6.0, 20.0, flutes=2, tool_number=5),
    "ball_10mm": CuttingTool("10mm Ball Endmill", ToolType.BALL_ENDMILL, 10.0, 30.0, flutes=2, tool_number=6),
    "drill_5mm": CuttingTool("5mm Drill", ToolType.DRILL, 5.0, 30.0, flutes=2, tool_number=7),
    "drill_8mm": CuttingTool("8mm Drill", ToolType.DRILL, 8.0, 40.0, flutes=2, tool_number=8),
    "chamfer_90": CuttingTool("90deg Chamfer Mill", ToolType.CHAMFER_MILL, 12.0, 10.0, flutes=3, tool_number=9),
    "face_50mm": CuttingTool("50mm Face Mill", ToolType.FACE_MILL, 50.0, 5.0, flutes=5, tool_number=10),
}
