"""Hole module library: through holes, counterbore, countersink, tapped."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cadquery as cq

from .base import CadModule


@dataclass
class ThroughHole(CadModule):
    """Simple through hole (cylinder tool)."""
    diameter: float = 10.0
    depth: float = 20.0

    def build(self) -> cq.Workplane:
        return cq.Workplane("XY").circle(self.diameter / 2).extrude(self.depth)

    @classmethod
    def get_param_schema(cls) -> dict[str, dict[str, Any]]:
        return {
            "diameter": {"type": "float", "min": 0.5, "max": 200, "default": 10.0, "unit": "mm"},
            "depth": {"type": "float", "min": 0.5, "max": 500, "default": 20.0, "unit": "mm"},
        }


@dataclass
class CounterboreHole(CadModule):
    """Counterbore hole: stepped diameter at top."""
    d_hole: float = 6.0
    d_cbore: float = 12.0
    cbore_depth: float = 5.0
    depth: float = 20.0

    def build(self) -> cq.Workplane:
        hole = cq.Workplane("XY").circle(self.d_hole / 2).extrude(self.depth)
        cbore = cq.Workplane("XY").transformed(offset=(0, 0, self.depth - self.cbore_depth))
        cbore = cbore.circle(self.d_cbore / 2).extrude(self.cbore_depth)
        return hole.union(cbore)

    @classmethod
    def get_param_schema(cls) -> dict[str, dict[str, Any]]:
        return {
            "d_hole": {"type": "float", "min": 1, "max": 100, "default": 6.0, "unit": "mm"},
            "d_cbore": {"type": "float", "min": 2, "max": 200, "default": 12.0, "unit": "mm"},
            "cbore_depth": {"type": "float", "min": 0.5, "max": 50, "default": 5.0, "unit": "mm"},
            "depth": {"type": "float", "min": 1, "max": 500, "default": 20.0, "unit": "mm"},
        }


@dataclass
class CountersinkHole(CadModule):
    """Countersink hole: conical chamfer at top."""
    d_hole: float = 5.0
    d_csink: float = 10.0
    csink_angle: float = 82.0  # degrees (full angle)
    depth: float = 20.0

    def build(self) -> cq.Workplane:
        import math

        hole = cq.Workplane("XY").circle(self.d_hole / 2).extrude(self.depth)
        # Countersink cone
        half_angle = math.radians(self.csink_angle / 2)
        csink_depth = (self.d_csink / 2 - self.d_hole / 2) / math.tan(half_angle)
        z_start = self.depth - csink_depth
        cone = (
            cq.Workplane("XY")
            .transformed(offset=(0, 0, z_start))
            .circle(self.d_hole / 2)
            .workplane(offset=csink_depth)
            .circle(self.d_csink / 2)
            .loft()
        )
        return hole.union(cone)

    @classmethod
    def get_param_schema(cls) -> dict[str, dict[str, Any]]:
        return {
            "d_hole": {"type": "float", "min": 1, "max": 50, "default": 5.0, "unit": "mm"},
            "d_csink": {"type": "float", "min": 2, "max": 100, "default": 10.0, "unit": "mm"},
            "csink_angle": {"type": "float", "min": 60, "max": 120, "default": 82.0, "unit": "deg"},
            "depth": {"type": "float", "min": 1, "max": 500, "default": 20.0, "unit": "mm"},
        }


@dataclass
class TappedHole(CadModule):
    """Tapped (threaded) hole - modeled as cylindrical cut with tap drill size."""
    nominal_size: str = "M6"
    depth: float = 15.0

    # Standard metric tap drill sizes
    _TAP_DRILL: dict[str, float] = None  # type: ignore

    def __post_init__(self):
        self._TAP_DRILL = {
            "M3": 2.5, "M4": 3.3, "M5": 4.2, "M6": 5.0,
            "M8": 6.8, "M10": 8.5, "M12": 10.2, "M16": 14.0, "M20": 17.5,
        }

    def build(self) -> cq.Workplane:
        diameter = self._TAP_DRILL.get(self.nominal_size, 5.0)
        return cq.Workplane("XY").circle(diameter / 2).extrude(self.depth)

    @classmethod
    def get_param_schema(cls) -> dict[str, dict[str, Any]]:
        return {
            "nominal_size": {
                "type": "enum",
                "values": ["M3", "M4", "M5", "M6", "M8", "M10", "M12", "M16", "M20"],
                "default": "M6",
            },
            "depth": {"type": "float", "min": 3, "max": 200, "default": 15.0, "unit": "mm"},
        }
