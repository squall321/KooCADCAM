"""Stock (raw material) definition for CNC machining."""

from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq


@dataclass
class Stock:
    """Rectangular stock material.

    The stock sits with its bottom-left corner at (-lx/2, -ly/2, 0)
    so it is centered on XY and sits on Z=0.
    """
    lx: float
    ly: float
    lz: float
    material: str = "Aluminum 6061"

    def to_solid(self) -> cq.Workplane:
        """Generate the stock as a CadQuery solid."""
        return cq.Workplane("XY").box(self.lx, self.ly, self.lz, centered=(True, True, False))

    @classmethod
    def from_bounding_box(cls, solid: cq.Workplane, margin: float = 5.0) -> Stock:
        """Create stock that encloses a solid with given margin."""
        bb = solid.val().BoundingBox()
        return cls(
            lx=bb.xmax - bb.xmin + 2 * margin,
            ly=bb.ymax - bb.ymin + 2 * margin,
            lz=bb.zmax - bb.zmin + margin,
        )

    @property
    def bounds(self) -> dict[str, float]:
        """Return stock boundaries."""
        return {
            "x_min": -self.lx / 2, "x_max": self.lx / 2,
            "y_min": -self.ly / 2, "y_max": self.ly / 2,
            "z_min": 0.0, "z_max": self.lz,
        }
