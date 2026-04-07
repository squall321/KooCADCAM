"""Step 3: Shapely-based 2D pocket path planning.

Generates toolpaths for arbitrary-shape pockets (not just rectangles)
by computing inward offsets of the pocket boundary loop using Shapely.

Falls back to bounding-box zigzag if Shapely is not installed.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .toolpath import MoveType, ToolpathPoint, ToolpathSegment

if TYPE_CHECKING:
    from .tools import CuttingTool

try:
    from shapely.geometry import Polygon, MultiPolygon, LineString
    from shapely.ops import unary_union
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


def _polygon_to_points(
    poly,
    z: float,
    feed_rate: float,
    plunge_rate: float,
    safe_z: float,
) -> list[ToolpathPoint]:
    """Convert a Shapely polygon exterior to toolpath points at a given Z."""
    pts: list[ToolpathPoint] = []
    try:
        coords = list(poly.exterior.coords)
    except AttributeError:
        return pts

    if not coords:
        return pts

    # Rapid to first point
    pts.append(ToolpathPoint(coords[0][0], coords[0][1], safe_z, MoveType.RAPID))
    pts.append(ToolpathPoint(coords[0][0], coords[0][1], z, MoveType.LINEAR, plunge_rate))

    for x, y in coords[1:]:
        pts.append(ToolpathPoint(x, y, z, MoveType.LINEAR, feed_rate))

    # Close and retract
    pts.append(ToolpathPoint(coords[0][0], coords[0][1], z, MoveType.LINEAR, feed_rate))
    pts.append(ToolpathPoint(coords[0][0], coords[0][1], safe_z, MoveType.RAPID))
    return pts


class PocketPlanner:
    """Plan inward-offset pocket toolpaths for arbitrary 2D outlines.

    Strategy: contour-parallel (offset inward by stepover repeatedly).

    Usage:
        planner = PocketPlanner(tool, stepover_ratio=0.45)
        segments = planner.plan_rect(x_min, x_max, y_min, y_max, z_top, z_bottom, ...)
        segments = planner.plan_polygon(outer_coords, z_top, z_bottom, ...)
    """

    def __init__(
        self,
        tool: CuttingTool,
        stepover_ratio: float = 0.45,
        depth_per_pass: float = 2.0,
        feed_rate: float = 500.0,
        plunge_rate: float = 200.0,
        spindle_rpm: int = 8000,
    ) -> None:
        self.tool = tool
        self.stepover_ratio = stepover_ratio
        self.depth_per_pass = depth_per_pass
        self.feed_rate = feed_rate
        self.plunge_rate = plunge_rate
        self.spindle_rpm = spindle_rpm

    # ─── Public API ────────────────────────────────────────────────

    def plan_rect(
        self,
        x_min: float, x_max: float,
        y_min: float, y_max: float,
        z_top: float, z_bottom: float,
        islands: list[list[tuple[float, float]]] | None = None,
    ) -> list[ToolpathSegment]:
        """Plan pocket for a rectangular boundary."""
        outer = [
            (x_min, y_min), (x_max, y_min),
            (x_max, y_max), (x_min, y_max),
        ]
        return self.plan_polygon(outer, z_top, z_bottom, islands)

    def plan_polygon(
        self,
        outer_coords: list[tuple[float, float]],
        z_top: float,
        z_bottom: float,
        islands: list[list[tuple[float, float]]] | None = None,
    ) -> list[ToolpathSegment]:
        """Plan pocket for an arbitrary polygon boundary.

        Args:
            outer_coords: XY vertices of outer pocket boundary
            z_top: top Z of pocket
            z_bottom: floor Z of pocket
            islands: list of inner obstacle polygons (will not be cut)
        """
        if HAS_SHAPELY:
            return self._plan_shapely(outer_coords, z_top, z_bottom, islands or [])
        else:
            # Fallback: rectangular zigzag from bounding box
            xs = [p[0] for p in outer_coords]
            ys = [p[1] for p in outer_coords]
            return self._plan_zigzag_fallback(
                min(xs), max(xs), min(ys), max(ys), z_top, z_bottom
            )

    # ─── Shapely implementation ────────────────────────────────────

    def _plan_shapely(
        self,
        outer_coords: list[tuple[float, float]],
        z_top: float,
        z_bottom: float,
        islands: list[list[tuple[float, float]]],
    ) -> list[ToolpathSegment]:
        tool_r = self.tool.radius
        stepover = self.tool.diameter * self.stepover_ratio
        safe_z = z_top + 5.0

        # Build pocket polygon
        try:
            pocket = Polygon(outer_coords)
            for isl in islands:
                if len(isl) >= 3:
                    pocket = pocket.difference(Polygon(isl))
        except Exception:
            # Fallback on geometry error
            xs = [p[0] for p in outer_coords]
            ys = [p[1] for p in outer_coords]
            return self._plan_zigzag_fallback(
                min(xs), max(xs), min(ys), max(ys), z_top, z_bottom
            )

        # Z levels
        z_passes = self._z_levels(z_top, z_bottom)
        all_points: list[ToolpathPoint] = []

        for z_level in z_passes:
            # Start from tool-radius inset, then step inward
            current = pocket.buffer(-tool_r)
            if current.is_empty:
                continue

            # Collect all offset loops for this Z level (outside→in)
            loops = []
            while not current.is_empty and current.area > 0.01:
                if current.geom_type == "Polygon":
                    loops.append(current)
                elif current.geom_type in ("MultiPolygon", "GeometryCollection"):
                    for geom in current.geoms:
                        if geom.geom_type == "Polygon":
                            loops.append(geom)
                inner = current.buffer(-stepover)
                if inner.area >= current.area:   # no progress
                    break
                current = inner

            # Add center pass (innermost point)
            # Reverse for inside-out order (better for machining)
            for loop in reversed(loops):
                pts = _polygon_to_points(
                    loop, z_level,
                    self.feed_rate, self.plunge_rate, safe_z
                )
                all_points.extend(pts)

        if not all_points:
            return []

        seg = ToolpathSegment(
            "Pocket (Shapely)",
            self.tool, all_points, self.spindle_rpm
        )
        return [seg]

    # ─── Fallback: bounding box zigzag ────────────────────────────

    def _plan_zigzag_fallback(
        self,
        x_min: float, x_max: float,
        y_min: float, y_max: float,
        z_top: float, z_bottom: float,
    ) -> list[ToolpathSegment]:
        """Simple rectangular zigzag – used when Shapely not available."""
        r = self.tool.radius
        stepover = self.tool.diameter * self.stepover_ratio
        safe_z = z_top + 5.0
        z_passes = self._z_levels(z_top, z_bottom)

        x0 = x_min + r
        x1 = x_max - r
        y0 = y_min + r
        y1 = y_max - r

        if x0 >= x1 or y0 >= y1:
            return []

        points: list[ToolpathPoint] = []
        for z_level in z_passes:
            y = y0
            forward = True
            while y <= y1:
                if forward:
                    points.append(ToolpathPoint(x0, y, safe_z, MoveType.RAPID))
                    points.append(ToolpathPoint(x0, y, z_level, MoveType.LINEAR, self.plunge_rate))
                    points.append(ToolpathPoint(x1, y, z_level, MoveType.LINEAR, self.feed_rate))
                else:
                    points.append(ToolpathPoint(x1, y, safe_z, MoveType.RAPID))
                    points.append(ToolpathPoint(x1, y, z_level, MoveType.LINEAR, self.plunge_rate))
                    points.append(ToolpathPoint(x0, y, z_level, MoveType.LINEAR, self.feed_rate))
                forward = not forward
                y += stepover
            points.append(ToolpathPoint(points[-1].x, points[-1].y, safe_z, MoveType.RAPID))

        seg = ToolpathSegment("Pocket (zigzag)", self.tool, points, self.spindle_rpm)
        return [seg]

    # ─── Helpers ──────────────────────────────────────────────────

    def _z_levels(self, z_top: float, z_bottom: float) -> list[float]:
        levels = []
        z = z_top - self.depth_per_pass
        while z > z_bottom:
            levels.append(round(z, 4))
            z -= self.depth_per_pass
        if not levels or abs(levels[-1] - z_bottom) > 0.001:
            levels.append(z_bottom)
        return levels
