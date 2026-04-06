"""Collision detection: tool holder interference, gouge detection, boundary checking."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .tools import CuttingTool
from .toolpath import ToolpathSegment, ToolpathPoint, MoveType


class CollisionType(Enum):
    HOLDER_INTERFERENCE = "holder_interference"
    GOUGE = "gouge"
    BOUNDARY_VIOLATION = "boundary_violation"
    RAPID_INTO_MATERIAL = "rapid_into_material"


@dataclass
class CollisionEvent:
    """A detected collision or interference."""
    collision_type: CollisionType
    point_index: int
    x: float
    y: float
    z: float
    severity: str  # "warning" or "error"
    message: str

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.collision_type.value} at ({self.x:.2f}, {self.y:.2f}, {self.z:.2f}): {self.message}"


@dataclass
class CollisionReport:
    """Summary of all collision checks."""
    events: list[CollisionEvent] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(e.severity == "error" for e in self.events)

    @property
    def has_warnings(self) -> bool:
        return any(e.severity == "warning" for e in self.events)

    @property
    def error_count(self) -> int:
        return sum(1 for e in self.events if e.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for e in self.events if e.severity == "warning")

    def __str__(self) -> str:
        lines = [f"Collision Report: {self.error_count} errors, {self.warning_count} warnings"]
        for ev in self.events:
            lines.append(f"  {ev}")
        if not self.events:
            lines.append("  No collisions detected.")
        return "\n".join(lines)


class ToolHolderCheck:
    """Check for tool holder interference with stock/part geometry.

    The holder (shank + collet) extends above the cutting flutes.
    If the holder descends into the stock, interference occurs.
    """

    def check(
        self,
        segment: ToolpathSegment,
        stock_z_top: float,
        holder_diameter: float | None = None,
        holder_length: float = 50.0,
        gauge_length: float | None = None,
    ) -> list[CollisionEvent]:
        """Check each point for holder-stock interference.

        Args:
            stock_z_top: Top surface Z of stock.
            holder_diameter: Holder diameter (default: tool shank dia or 2x tool dia).
            holder_length: Length of holder above flutes.
            gauge_length: Total tool gauge length (flute_length + holder visible).
                          Default: tool.flute_length.
        """
        tool = segment.tool
        if holder_diameter is None:
            holder_diameter = tool.shank_diameter or tool.diameter * 2
        if gauge_length is None:
            gauge_length = tool.flute_length

        holder_r = holder_diameter / 2
        events: list[CollisionEvent] = []

        for i, pt in enumerate(segment.points):
            if pt.move_type == MoveType.RAPID:
                continue

            # Holder bottom Z = tool tip Z + flute length
            holder_bottom_z = pt.z + gauge_length

            # If holder bottom is below stock top, potential interference
            if holder_bottom_z < stock_z_top:
                penetration = stock_z_top - holder_bottom_z
                events.append(CollisionEvent(
                    CollisionType.HOLDER_INTERFERENCE,
                    i, pt.x, pt.y, pt.z,
                    "error" if penetration > 1.0 else "warning",
                    f"Holder penetrates stock by {penetration:.2f}mm "
                    f"(holder_dia={holder_diameter}, gauge_len={gauge_length})"
                ))

        return events


class GougeDetector:
    """Detect gouging (over-cutting) where tool cuts below target surface.

    For flat-bottom parts, checks if any cutting point goes below
    the target Z surface. For contoured parts, compares against
    a surface function.
    """

    def check(
        self,
        segment: ToolpathSegment,
        target_z_min: float = 0.0,
        tolerance: float = 0.01,
        surface_func: Any = None,
    ) -> list[CollisionEvent]:
        """Check for gouge events.

        Args:
            target_z_min: Minimum allowed Z (for flat parts).
            tolerance: Allowable undershoot (mm).
            surface_func: Optional callable(x, y) -> z_min for contoured parts.
        """
        events: list[CollisionEvent] = []
        tool = segment.tool

        for i, pt in enumerate(segment.points):
            if pt.move_type == MoveType.RAPID:
                continue

            if surface_func is not None:
                z_limit = surface_func(pt.x, pt.y)
            else:
                z_limit = target_z_min

            # For ball endmill, actual cutting point is at tip (lowest point)
            tool_tip_z = pt.z
            if tool_tip_z < z_limit - tolerance:
                gouge_depth = z_limit - tool_tip_z
                events.append(CollisionEvent(
                    CollisionType.GOUGE,
                    i, pt.x, pt.y, pt.z,
                    "error" if gouge_depth > 0.1 else "warning",
                    f"Gouge detected: {gouge_depth:.3f}mm below target surface"
                ))

        return events


class StockBoundaryCheck:
    """Check for tool paths that extend beyond the stock boundaries.

    Catches cases where the tool moves outside the stock volume,
    indicating a programming error or incorrect offsets.
    """

    def check(
        self,
        segment: ToolpathSegment,
        stock_bounds: dict[str, float],
        margin: float = 0.0,
    ) -> list[CollisionEvent]:
        """Check if cutting moves stay within stock + margin.

        Args:
            stock_bounds: {"x_min", "x_max", "y_min", "y_max", "z_min", "z_max"}
            margin: Extra allowance beyond stock boundary.
        """
        events: list[CollisionEvent] = []
        tool = segment.tool
        r = tool.radius

        x_lo = stock_bounds["x_min"] - margin - r
        x_hi = stock_bounds["x_max"] + margin + r
        y_lo = stock_bounds["y_min"] - margin - r
        y_hi = stock_bounds["y_max"] + margin + r
        z_lo = stock_bounds.get("z_min", 0) - margin
        z_hi = stock_bounds["z_max"] + margin

        for i, pt in enumerate(segment.points):
            if pt.move_type == MoveType.RAPID:
                continue

            violations = []
            if pt.x < x_lo:
                violations.append(f"X={pt.x:.2f} < {x_lo:.2f}")
            if pt.x > x_hi:
                violations.append(f"X={pt.x:.2f} > {x_hi:.2f}")
            if pt.y < y_lo:
                violations.append(f"Y={pt.y:.2f} < {y_lo:.2f}")
            if pt.y > y_hi:
                violations.append(f"Y={pt.y:.2f} > {y_hi:.2f}")
            if pt.z < z_lo:
                violations.append(f"Z={pt.z:.2f} < {z_lo:.2f}")

            if violations:
                events.append(CollisionEvent(
                    CollisionType.BOUNDARY_VIOLATION,
                    i, pt.x, pt.y, pt.z,
                    "warning",
                    f"Outside stock boundary: {', '.join(violations)}"
                ))

        return events


class RapidSafetyCheck:
    """Check for rapid moves that plunge into material.

    A rapid move (G0) into material is dangerous - it should always
    approach from above (Z safe height) or at the same Z level.
    """

    def check(
        self,
        segment: ToolpathSegment,
        stock_z_top: float,
        safe_z_margin: float = 2.0,
    ) -> list[CollisionEvent]:
        """Check for unsafe rapid plunge moves."""
        events: list[CollisionEvent] = []

        for i in range(1, len(segment.points)):
            pt = segment.points[i]
            prev = segment.points[i - 1]

            if pt.move_type != MoveType.RAPID:
                continue

            # Rapid going downward into potential material
            if pt.z < stock_z_top - safe_z_margin and pt.z < prev.z:
                events.append(CollisionEvent(
                    CollisionType.RAPID_INTO_MATERIAL,
                    i, pt.x, pt.y, pt.z,
                    "error",
                    f"Rapid plunge from Z={prev.z:.2f} to Z={pt.z:.2f} "
                    f"(stock top={stock_z_top:.2f})"
                ))

        return events


def check_all(
    segments: list[ToolpathSegment],
    stock_bounds: dict[str, float],
    target_z_min: float = 0.0,
) -> CollisionReport:
    """Run all collision checks on a list of toolpath segments.

    Args:
        segments: Toolpath segments to check.
        stock_bounds: Stock bounding box.
        target_z_min: Minimum target Z surface.

    Returns:
        CollisionReport with all detected events.
    """
    report = CollisionReport()

    holder_check = ToolHolderCheck()
    gouge_check = GougeDetector()
    boundary_check = StockBoundaryCheck()
    rapid_check = RapidSafetyCheck()

    stock_z_top = stock_bounds.get("z_max", 20.0)

    for seg in segments:
        report.events.extend(holder_check.check(seg, stock_z_top))
        report.events.extend(gouge_check.check(seg, target_z_min))
        report.events.extend(boundary_check.check(seg, stock_bounds))
        report.events.extend(rapid_check.check(seg, stock_z_top))

    return report
