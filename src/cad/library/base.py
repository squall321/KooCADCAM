"""Abstract base class for all parametric CAD modules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import cadquery as cq


@dataclass
class BBox:
    """Axis-aligned bounding box."""
    x_min: float
    y_min: float
    z_min: float
    x_max: float
    y_max: float
    z_max: float

    @property
    def size(self) -> tuple[float, float, float]:
        return (self.x_max - self.x_min, self.y_max - self.y_min, self.z_max - self.z_min)

    @property
    def center(self) -> tuple[float, float, float]:
        return (
            (self.x_min + self.x_max) / 2,
            (self.y_min + self.y_max) / 2,
            (self.z_min + self.z_max) / 2,
        )


class CadModule(ABC):
    """Base class for reusable parametric CAD modules.

    Every module can:
    - build() a CadQuery solid (typically used as a boolean tool)
    - expose its parameter schema for GUI integration
    - compute its bounding box
    """

    @abstractmethod
    def build(self) -> cq.Workplane:
        """Generate the CadQuery solid geometry."""
        ...

    @classmethod
    def get_param_schema(cls) -> dict[str, dict[str, Any]]:
        """Return parameter schema for GUI auto-generation.

        Returns dict like:
            {"diameter": {"type": "float", "min": 0.1, "max": 100, "default": 10}}
        """
        return {}

    def bounding_box(self) -> BBox:
        """Compute bounding box of the built geometry."""
        solid = self.build()
        bb = solid.val().BoundingBox()
        return BBox(bb.xmin, bb.ymin, bb.zmin, bb.xmax, bb.ymax, bb.zmax)
