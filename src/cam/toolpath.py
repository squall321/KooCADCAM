"""Toolpath generation strategies for CNC machining."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .tools import CuttingTool


class MoveType(Enum):
    RAPID = "rapid"       # G0
    LINEAR = "linear"     # G1
    ARC_CW = "arc_cw"     # G2
    ARC_CCW = "arc_ccw"   # G3


@dataclass
class ToolpathPoint:
    """A single point in a toolpath."""
    x: float
    y: float
    z: float
    move_type: MoveType = MoveType.LINEAR
    feed_rate: float | None = None
    # Arc parameters (relative to start point)
    i: float = 0.0
    j: float = 0.0
    k: float = 0.0


@dataclass
class ToolpathSegment:
    """A sequence of toolpath points forming a machining operation."""
    name: str
    tool: CuttingTool
    points: list[ToolpathPoint] = field(default_factory=list)
    spindle_rpm: int = 8000
    coolant: bool = True


class ToolpathStrategy(ABC):
    """Abstract base for toolpath generation strategies."""

    @abstractmethod
    def generate(self, **kwargs: Any) -> list[ToolpathSegment]:
        """Generate toolpath segments."""
        ...


class FacingStrategy(ToolpathStrategy):
    """Face milling: zig-zag passes to flatten the top surface.

    Cuts the top of stock down to target Z height.
    """

    def generate(
        self,
        tool: CuttingTool,
        stock_bounds: dict[str, float],
        target_z: float,
        depth_per_pass: float = 2.0,
        stepover_ratio: float = 0.4,
        feed_rate: float = 500.0,
        plunge_rate: float = 200.0,
        spindle_rpm: int = 8000,
        **kwargs: Any,
    ) -> list[ToolpathSegment]:
        segments = []
        x_min = stock_bounds["x_min"] - tool.radius
        x_max = stock_bounds["x_max"] + tool.radius
        y_min = stock_bounds["y_min"] - tool.radius
        y_max = stock_bounds["y_max"] + tool.radius
        z_top = stock_bounds["z_max"]
        stepover = tool.diameter * stepover_ratio
        safe_z = z_top + 5.0

        # Calculate Z passes
        z_passes = []
        z = z_top - depth_per_pass
        while z > target_z:
            z_passes.append(z)
            z -= depth_per_pass
        if not z_passes or z_passes[-1] != target_z:
            z_passes.append(target_z)

        points: list[ToolpathPoint] = []
        for z_level in z_passes:
            # Zig-zag at this Z level
            y = y_min
            forward = True
            while y <= y_max:
                if forward:
                    # Rapid to start
                    points.append(ToolpathPoint(x_min, y, safe_z, MoveType.RAPID))
                    # Plunge
                    points.append(ToolpathPoint(x_min, y, z_level, MoveType.LINEAR, plunge_rate))
                    # Cut across
                    points.append(ToolpathPoint(x_max, y, z_level, MoveType.LINEAR, feed_rate))
                else:
                    points.append(ToolpathPoint(x_max, y, safe_z, MoveType.RAPID))
                    points.append(ToolpathPoint(x_max, y, z_level, MoveType.LINEAR, plunge_rate))
                    points.append(ToolpathPoint(x_min, y, z_level, MoveType.LINEAR, feed_rate))
                forward = not forward
                y += stepover

            # Retract after each Z level
            points.append(ToolpathPoint(points[-1].x, points[-1].y, safe_z, MoveType.RAPID))

        seg = ToolpathSegment("Facing", tool, points, spindle_rpm)
        segments.append(seg)
        return segments


class ProfileStrategy(ToolpathStrategy):
    """Profile (contour) milling around a rectangular boundary.

    Cuts the 2.5D outline, stepping down in Z.
    """

    def generate(
        self,
        tool: CuttingTool,
        target_bounds: dict[str, float],
        z_top: float,
        z_bottom: float,
        depth_per_pass: float = 2.0,
        feed_rate: float = 500.0,
        plunge_rate: float = 200.0,
        spindle_rpm: int = 8000,
        **kwargs: Any,
    ) -> list[ToolpathSegment]:
        # Offset boundary by tool radius (climb milling = outside)
        r = tool.radius
        x_min = target_bounds["x_min"] - r
        x_max = target_bounds["x_max"] + r
        y_min = target_bounds["y_min"] - r
        y_max = target_bounds["y_max"] + r
        safe_z = z_top + 5.0

        z_passes = []
        z = z_top - depth_per_pass
        while z > z_bottom:
            z_passes.append(z)
            z -= depth_per_pass
        if not z_passes or z_passes[-1] != z_bottom:
            z_passes.append(z_bottom)

        points: list[ToolpathPoint] = []
        for z_level in z_passes:
            # Move to start corner
            points.append(ToolpathPoint(x_min, y_min, safe_z, MoveType.RAPID))
            points.append(ToolpathPoint(x_min, y_min, z_level, MoveType.LINEAR, plunge_rate))
            # Rectangular profile loop (CCW for climb milling)
            points.append(ToolpathPoint(x_max, y_min, z_level, MoveType.LINEAR, feed_rate))
            points.append(ToolpathPoint(x_max, y_max, z_level, MoveType.LINEAR, feed_rate))
            points.append(ToolpathPoint(x_min, y_max, z_level, MoveType.LINEAR, feed_rate))
            points.append(ToolpathPoint(x_min, y_min, z_level, MoveType.LINEAR, feed_rate))
            # Retract
            points.append(ToolpathPoint(x_min, y_min, safe_z, MoveType.RAPID))

        seg = ToolpathSegment("Profile", tool, points, spindle_rpm)
        return [seg]


class PocketStrategy(ToolpathStrategy):
    """Pocket milling: clear material inside a rectangular boundary.

    Uses zig-zag clearing with Z-level stepping.
    """

    def generate(
        self,
        tool: CuttingTool,
        stock_bounds: dict[str, float],
        target_bounds: dict[str, float],
        z_top: float,
        z_bottom: float,
        depth_per_pass: float = 2.0,
        stepover_ratio: float = 0.4,
        feed_rate: float = 500.0,
        plunge_rate: float = 200.0,
        spindle_rpm: int = 8000,
        **kwargs: Any,
    ) -> list[ToolpathSegment]:
        r = tool.radius
        stepover = tool.diameter * stepover_ratio
        safe_z = z_top + 5.0

        # Define pocket regions (material to remove is OUTSIDE target, INSIDE stock)
        # For simplicity, we'll cut 4 rectangular pocket regions
        regions = [
            # Region below target Y
            (stock_bounds["x_min"] + r, stock_bounds["y_min"] + r,
             stock_bounds["x_max"] - r, target_bounds["y_min"] - r),
            # Region above target Y
            (stock_bounds["x_min"] + r, target_bounds["y_max"] + r,
             stock_bounds["x_max"] - r, stock_bounds["y_max"] - r),
            # Region left of target X
            (stock_bounds["x_min"] + r, target_bounds["y_min"] - r,
             target_bounds["x_min"] - r, target_bounds["y_max"] + r),
            # Region right of target X
            (target_bounds["x_max"] + r, target_bounds["y_min"] - r,
             stock_bounds["x_max"] - r, target_bounds["y_max"] + r),
        ]

        z_passes = []
        z = z_top - depth_per_pass
        while z > z_bottom:
            z_passes.append(z)
            z -= depth_per_pass
        if not z_passes or z_passes[-1] != z_bottom:
            z_passes.append(z_bottom)

        points: list[ToolpathPoint] = []

        for region in regions:
            rx_min, ry_min, rx_max, ry_max = region
            if rx_min >= rx_max or ry_min >= ry_max:
                continue

            for z_level in z_passes:
                y = ry_min
                forward = True
                while y <= ry_max:
                    if forward:
                        points.append(ToolpathPoint(rx_min, y, safe_z, MoveType.RAPID))
                        points.append(ToolpathPoint(rx_min, y, z_level, MoveType.LINEAR, plunge_rate))
                        points.append(ToolpathPoint(rx_max, y, z_level, MoveType.LINEAR, feed_rate))
                    else:
                        points.append(ToolpathPoint(rx_max, y, safe_z, MoveType.RAPID))
                        points.append(ToolpathPoint(rx_max, y, z_level, MoveType.LINEAR, plunge_rate))
                        points.append(ToolpathPoint(rx_min, y, z_level, MoveType.LINEAR, feed_rate))
                    forward = not forward
                    y += stepover
                points.append(ToolpathPoint(points[-1].x, points[-1].y, safe_z, MoveType.RAPID))

        seg = ToolpathSegment("Pocket", tool, points, spindle_rpm)
        return [seg]


class FilletStrategy(ToolpathStrategy):
    """Fillet machining on top edges using a ball endmill.

    Generates 3D arc passes along the top edge corners of a rectangular part.
    """

    def generate(
        self,
        tool: CuttingTool,
        target_bounds: dict[str, float],
        target_z: float,
        fillet_radius: float,
        num_passes: int = 10,
        feed_rate: float = 300.0,
        spindle_rpm: int = 8000,
        **kwargs: Any,
    ) -> list[ToolpathSegment]:
        r = fillet_radius
        ball_r = tool.radius
        safe_z = target_z + 10.0

        xmin = target_bounds["x_min"]
        xmax = target_bounds["x_max"]
        ymin = target_bounds["y_min"]
        ymax = target_bounds["y_max"]

        points: list[ToolpathPoint] = []

        # For each of the 4 top edges, generate fillet passes
        # Edge definition: (start_x, start_y, end_x, end_y, normal_x, normal_y)
        edges = [
            (xmin, ymin, xmax, ymin, 0, -1),  # bottom edge
            (xmax, ymin, xmax, ymax, 1, 0),   # right edge
            (xmax, ymax, xmin, ymax, 0, 1),   # top edge
            (xmin, ymax, xmin, ymin, -1, 0),  # left edge
        ]

        for sx, sy, ex, ey, nx, ny in edges:
            for i in range(num_passes + 1):
                angle = (math.pi / 2) * i / num_passes
                # Ball endmill contact point on the fillet arc
                offset_h = r * math.sin(angle)  # horizontal offset from edge
                offset_v = r - r * math.cos(angle)  # vertical offset from top

                # Tool center position (compensate for ball radius)
                tool_h = offset_h + ball_r * math.sin(angle)
                tool_v = offset_v - ball_r * (1 - math.cos(angle))
                z = target_z - tool_v

                # Points along the edge
                px_s = sx + nx * tool_h
                py_s = sy + ny * tool_h
                px_e = ex + nx * tool_h
                py_e = ey + ny * tool_h

                points.append(ToolpathPoint(px_s, py_s, safe_z, MoveType.RAPID))
                points.append(ToolpathPoint(px_s, py_s, z, MoveType.LINEAR, feed_rate * 0.5))
                points.append(ToolpathPoint(px_e, py_e, z, MoveType.LINEAR, feed_rate))
                points.append(ToolpathPoint(px_e, py_e, safe_z, MoveType.RAPID))

        seg = ToolpathSegment("Fillet", tool, points, spindle_rpm)
        return [seg]


class DrillStrategy(ToolpathStrategy):
    """Drilling strategy: peck drill at specified locations."""

    def generate(
        self,
        tool: CuttingTool,
        positions: list[tuple[float, float]],
        z_top: float,
        z_bottom: float,
        peck_depth: float = 3.0,
        feed_rate: float = 150.0,
        spindle_rpm: int = 3000,
        **kwargs: Any,
    ) -> list[ToolpathSegment]:
        safe_z = z_top + 5.0
        points: list[ToolpathPoint] = []

        for px, py in positions:
            z = z_top
            while z > z_bottom:
                z_next = max(z - peck_depth, z_bottom)
                points.append(ToolpathPoint(px, py, safe_z, MoveType.RAPID))
                points.append(ToolpathPoint(px, py, z_next, MoveType.LINEAR, feed_rate))
                points.append(ToolpathPoint(px, py, safe_z, MoveType.RAPID))
                z = z_next
                if z <= z_bottom:
                    break

        seg = ToolpathSegment("Drilling", tool, points, spindle_rpm)
        return [seg]
