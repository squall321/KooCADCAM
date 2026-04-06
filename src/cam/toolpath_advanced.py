"""Advanced toolpath strategies: helical, trochoidal, spiral, contour, scanline, rest machining."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .tools import CuttingTool
from .toolpath import ToolpathStrategy, ToolpathSegment, ToolpathPoint, MoveType


class HelicalStrategy(ToolpathStrategy):
    """Helical entry strategy - replaces vertical plunging.

    Generates a helical ramp into the material, reducing tool load
    and eliminating the need for center-cutting endmills.
    Can be used standalone or as entry motion for pocket operations.
    """

    def generate(
        self,
        tool: CuttingTool,
        center_x: float = 0.0,
        center_y: float = 0.0,
        z_top: float = 20.0,
        z_bottom: float = 0.0,
        helix_radius: float | None = None,
        ramp_angle: float = 3.0,
        feed_rate: float = 300.0,
        spindle_rpm: int = 8000,
        points_per_rev: int = 36,
        **kwargs: Any,
    ) -> list[ToolpathSegment]:
        """Generate helical entry toolpath.

        Args:
            center_x, center_y: Center of helix.
            z_top, z_bottom: Start/end Z heights.
            helix_radius: Helix radius (default: 0.8 * tool radius).
            ramp_angle: Helix ramp angle in degrees.
            points_per_rev: Resolution (points per revolution).
        """
        if helix_radius is None:
            helix_radius = tool.radius * 0.8
        safe_z = z_top + 5.0

        # Z drop per revolution
        circumference = 2 * math.pi * helix_radius
        z_per_rev = circumference * math.tan(math.radians(ramp_angle))
        total_depth = z_top - z_bottom
        total_revs = total_depth / z_per_rev if z_per_rev > 0 else 1
        total_points = int(total_revs * points_per_rev) + 1

        points: list[ToolpathPoint] = []

        # Rapid to start position
        start_x = center_x + helix_radius
        start_y = center_y
        points.append(ToolpathPoint(start_x, start_y, safe_z, MoveType.RAPID))
        points.append(ToolpathPoint(start_x, start_y, z_top, MoveType.RAPID))

        # Helical descent
        for i in range(total_points):
            t = i / max(total_points - 1, 1)
            angle = 2 * math.pi * total_revs * t
            z = z_top - total_depth * t
            x = center_x + helix_radius * math.cos(angle)
            y = center_y + helix_radius * math.sin(angle)
            points.append(ToolpathPoint(x, y, max(z, z_bottom), MoveType.LINEAR, feed_rate))

        # Final full circle at bottom to clean
        for i in range(points_per_rev + 1):
            angle = 2 * math.pi * i / points_per_rev
            x = center_x + helix_radius * math.cos(angle)
            y = center_y + helix_radius * math.sin(angle)
            points.append(ToolpathPoint(x, y, z_bottom, MoveType.LINEAR, feed_rate))

        # Retract
        points.append(ToolpathPoint(points[-1].x, points[-1].y, safe_z, MoveType.RAPID))

        return [ToolpathSegment("Helical Entry", tool, points, spindle_rpm)]


class TrocoidalStrategy(ToolpathStrategy):
    """Trochoidal milling - circular looping cuts advancing along a slot.

    Ideal for hard materials (steel, titanium, Inconel) as it maintains
    constant chip load and reduces radial engagement.
    """

    def generate(
        self,
        tool: CuttingTool,
        x_start: float = -50.0,
        y_center: float = 0.0,
        x_end: float = 50.0,
        slot_width: float = 15.0,
        z_top: float = 20.0,
        z_bottom: float = 15.0,
        depth_per_pass: float = 2.0,
        trochoid_radius: float | None = None,
        step_forward: float | None = None,
        feed_rate: float = 400.0,
        spindle_rpm: int = 8000,
        points_per_loop: int = 24,
        **kwargs: Any,
    ) -> list[ToolpathSegment]:
        """Generate trochoidal slot milling path.

        Args:
            x_start, x_end: Slot extent along X.
            y_center: Slot center Y.
            slot_width: Width of the slot.
            trochoid_radius: Loop radius (default: slot_width/2 - tool.radius*0.1).
            step_forward: Forward step per loop (default: tool.diameter * 0.1).
        """
        if trochoid_radius is None:
            trochoid_radius = slot_width / 2 - tool.radius * 0.1
        if step_forward is None:
            step_forward = tool.diameter * 0.1

        safe_z = z_top + 5.0

        z_passes = _calc_z_passes(z_top, z_bottom, depth_per_pass)

        points: list[ToolpathPoint] = []

        for z_level in z_passes:
            # Start position
            points.append(ToolpathPoint(x_start, y_center, safe_z, MoveType.RAPID))
            points.append(ToolpathPoint(x_start, y_center, z_level, MoveType.LINEAR, feed_rate * 0.3))

            # Trochoidal loops advancing along X
            cx = x_start
            while cx < x_end:
                for i in range(points_per_loop + 1):
                    angle = 2 * math.pi * i / points_per_loop
                    x = cx + trochoid_radius * math.sin(angle)
                    y = y_center + trochoid_radius * math.cos(angle)
                    # Advance forward as we loop
                    x += step_forward * (i / points_per_loop)
                    points.append(ToolpathPoint(x, y, z_level, MoveType.LINEAR, feed_rate))
                cx += step_forward

            # Retract
            points.append(ToolpathPoint(points[-1].x, points[-1].y, safe_z, MoveType.RAPID))

        return [ToolpathSegment("Trochoidal", tool, points, spindle_rpm)]


class SpiralPocketStrategy(ToolpathStrategy):
    """Spiral pocket clearing - outward or inward spiral within a rectangular boundary.

    More efficient than zigzag for pockets: continuous engagement,
    no full-width cuts, constant chip load.
    """

    def generate(
        self,
        tool: CuttingTool,
        x_min: float = -30.0,
        y_min: float = -20.0,
        x_max: float = 30.0,
        y_max: float = 20.0,
        z_top: float = 20.0,
        z_bottom: float = 15.0,
        depth_per_pass: float = 2.0,
        stepover_ratio: float = 0.4,
        feed_rate: float = 500.0,
        plunge_rate: float = 200.0,
        spindle_rpm: int = 8000,
        outward: bool = True,
        **kwargs: Any,
    ) -> list[ToolpathSegment]:
        """Generate spiral pocket path.

        Args:
            outward: If True, spiral from center outward. If False, inward.
        """
        r = tool.radius
        stepover = tool.diameter * stepover_ratio
        safe_z = z_top + 5.0
        z_passes = _calc_z_passes(z_top, z_bottom, depth_per_pass)

        # Inner boundary (tool-compensated)
        bx_min = x_min + r
        by_min = y_min + r
        bx_max = x_max - r
        by_max = y_max - r

        cx = (bx_min + bx_max) / 2
        cy = (by_min + by_max) / 2
        half_w = (bx_max - bx_min) / 2
        half_h = (by_max - by_min) / 2

        points: list[ToolpathPoint] = []

        for z_level in z_passes:
            # Start at center
            points.append(ToolpathPoint(cx, cy, safe_z, MoveType.RAPID))
            points.append(ToolpathPoint(cx, cy, z_level, MoveType.LINEAR, plunge_rate))

            # Expanding rectangular spiral
            n_loops = int(max(half_w, half_h) / stepover) + 1
            loops = range(1, n_loops + 1) if outward else range(n_loops, 0, -1)

            for loop_i in loops:
                frac = loop_i / n_loops
                hw = half_w * frac
                hh = half_h * frac
                # Rectangular loop: 4 corners
                corners = [
                    (cx - hw, cy - hh),
                    (cx + hw, cy - hh),
                    (cx + hw, cy + hh),
                    (cx - hw, cy + hh),
                    (cx - hw, cy - hh),  # close
                ]
                for px, py in corners:
                    # Clamp to boundary
                    px = max(bx_min, min(bx_max, px))
                    py = max(by_min, min(by_max, py))
                    points.append(ToolpathPoint(px, py, z_level, MoveType.LINEAR, feed_rate))

            points.append(ToolpathPoint(points[-1].x, points[-1].y, safe_z, MoveType.RAPID))

        return [ToolpathSegment("Spiral Pocket", tool, points, spindle_rpm)]


class ContourStrategy(ToolpathStrategy):
    """Z-level contour (waterline) machining for 3D surfaces.

    Generates horizontal contour passes at constant Z intervals,
    following the intersection of the surface with Z-planes.
    For the simplified case, generates concentric rectangular contours
    that approximate a dome/fillet shape.
    """

    def generate(
        self,
        tool: CuttingTool,
        x_min: float = -30.0,
        y_min: float = -30.0,
        x_max: float = 30.0,
        y_max: float = 30.0,
        z_top: float = 15.0,
        z_bottom: float = 5.0,
        z_step: float = 0.5,
        feed_rate: float = 400.0,
        spindle_rpm: int = 8000,
        taper_angle: float = 5.0,
        **kwargs: Any,
    ) -> list[ToolpathSegment]:
        """Generate Z-level contour passes.

        Args:
            z_step: Z interval between contour levels.
            taper_angle: Wall taper angle (degrees) - boundary shrinks as Z decreases.
        """
        safe_z = z_top + 5.0
        r = tool.radius
        tan_a = math.tan(math.radians(taper_angle))

        z_levels = []
        z = z_top - z_step
        while z >= z_bottom:
            z_levels.append(z)
            z -= z_step

        points: list[ToolpathPoint] = []

        for z_level in z_levels:
            # Boundary shrinks with depth (simulating tapered wall)
            depth = z_top - z_level
            shrink = depth * tan_a
            cxmin = x_min + shrink + r
            cymin = y_min + shrink + r
            cxmax = x_max - shrink - r
            cymax = y_max - shrink - r

            if cxmin >= cxmax or cymin >= cymax:
                break

            # Rapid to start
            points.append(ToolpathPoint(cxmin, cymin, safe_z, MoveType.RAPID))
            points.append(ToolpathPoint(cxmin, cymin, z_level, MoveType.LINEAR, feed_rate * 0.5))
            # Rectangular contour
            points.append(ToolpathPoint(cxmax, cymin, z_level, MoveType.LINEAR, feed_rate))
            points.append(ToolpathPoint(cxmax, cymax, z_level, MoveType.LINEAR, feed_rate))
            points.append(ToolpathPoint(cxmin, cymax, z_level, MoveType.LINEAR, feed_rate))
            points.append(ToolpathPoint(cxmin, cymin, z_level, MoveType.LINEAR, feed_rate))
            # Retract
            points.append(ToolpathPoint(cxmin, cymin, safe_z, MoveType.RAPID))

        return [ToolpathSegment("Contour Z-Level", tool, points, spindle_rpm)]


class ScanlineStrategy(ToolpathStrategy):
    """Scanline (raster) finishing for 3D surfaces.

    Generates parallel passes across the surface at constant Y intervals,
    following the surface profile in Z. Used with ball endmills for
    smooth surface finish.
    """

    def generate(
        self,
        tool: CuttingTool,
        x_min: float = -30.0,
        y_min: float = -30.0,
        x_max: float = 30.0,
        y_max: float = 30.0,
        z_base: float = 10.0,
        z_top: float = 15.0,
        stepover_ratio: float = 0.15,
        feed_rate: float = 300.0,
        spindle_rpm: int = 10000,
        surface_func: Any = None,
        x_resolution: float = 0.5,
        **kwargs: Any,
    ) -> list[ToolpathSegment]:
        """Generate scanline finishing passes.

        Args:
            z_base: Base Z level (flat area).
            z_top: Maximum Z height.
            stepover_ratio: Stepover as ratio of tool diameter (small = finer finish).
            surface_func: Optional callable(x, y) -> z for arbitrary surface.
                          If None, uses a dome approximation.
            x_resolution: X step resolution along each scanline.
        """
        safe_z = z_top + 5.0
        stepover = tool.diameter * stepover_ratio
        ball_r = tool.radius

        # Default surface: dome shape
        if surface_func is None:
            cx = (x_min + x_max) / 2
            cy = (y_min + y_max) / 2
            rx = (x_max - x_min) / 2
            ry = (y_max - y_min) / 2
            dome_h = z_top - z_base

            def surface_func(x, y):
                nx = (x - cx) / rx if rx != 0 else 0
                ny = (y - cy) / ry if ry != 0 else 0
                r2 = nx * nx + ny * ny
                if r2 >= 1.0:
                    return z_base
                return z_base + dome_h * math.sqrt(max(0, 1 - r2))

        points: list[ToolpathPoint] = []
        y = y_min
        forward = True

        while y <= y_max:
            x_range = _frange(x_min, x_max, x_resolution) if forward else _frange(x_max, x_min, -x_resolution)
            first = True

            for x in x_range:
                z_surface = surface_func(x, y)
                # Ball endmill: tool tip at surface contact + ball radius offset
                z_tool = z_surface + ball_r

                if first:
                    points.append(ToolpathPoint(x, y, safe_z, MoveType.RAPID))
                    points.append(ToolpathPoint(x, y, z_tool, MoveType.LINEAR, feed_rate * 0.5))
                    first = False
                else:
                    points.append(ToolpathPoint(x, y, z_tool, MoveType.LINEAR, feed_rate))

            # Retract at end of line
            if points:
                points.append(ToolpathPoint(points[-1].x, points[-1].y, safe_z, MoveType.RAPID))

            forward = not forward
            y += stepover

        return [ToolpathSegment("Scanline Finish", tool, points, spindle_rpm)]


class RestMachiningStrategy(ToolpathStrategy):
    """Rest (residual) machining - clean up material left by a larger tool.

    After roughing with a large endmill, corners and small features
    have leftover material. This strategy generates paths using a smaller
    tool to machine only the remaining stock.
    """

    def generate(
        self,
        tool: CuttingTool,
        prev_tool_diameter: float = 10.0,
        x_min: float = -30.0,
        y_min: float = -30.0,
        x_max: float = 30.0,
        y_max: float = 30.0,
        z_top: float = 15.0,
        z_bottom: float = 0.0,
        depth_per_pass: float = 1.0,
        stepover_ratio: float = 0.3,
        feed_rate: float = 400.0,
        plunge_rate: float = 150.0,
        spindle_rpm: int = 10000,
        corner_radius: float = 0.0,
        **kwargs: Any,
    ) -> list[ToolpathSegment]:
        """Generate rest machining paths for internal corners.

        Args:
            prev_tool_diameter: Diameter of the previous (larger) roughing tool.
            corner_radius: Target part internal corner radius.
        """
        prev_r = prev_tool_diameter / 2
        new_r = tool.radius
        safe_z = z_top + 5.0
        stepover = tool.diameter * stepover_ratio
        z_passes = _calc_z_passes(z_top, z_bottom, depth_per_pass)

        if new_r >= prev_r:
            return []  # Smaller tool needed

        # Rest material exists in corners where previous tool couldn't reach
        # For a rectangular pocket, corners have radius = prev_tool_radius
        corners = [
            (x_min + prev_r, y_min + prev_r),  # bottom-left
            (x_max - prev_r, y_min + prev_r),  # bottom-right
            (x_max - prev_r, y_max - prev_r),  # top-right
            (x_min + prev_r, y_max - prev_r),  # top-left
        ]

        points: list[ToolpathPoint] = []

        for z_level in z_passes:
            for cx, cy in corners:
                # Arc passes in each corner to remove rest material
                target_r = max(corner_radius, new_r)
                num_passes = max(1, int((prev_r - target_r) / stepover))

                for p in range(num_passes):
                    arc_r = prev_r - stepover * p
                    if arc_r < new_r:
                        break

                    # Determine which quadrant this corner is in
                    dx = 1 if cx < (x_min + x_max) / 2 else -1
                    dy = 1 if cy < (y_min + y_max) / 2 else -1

                    arc_pts = 12
                    start_angle = math.atan2(-dy, -dx)

                    # Rapid to entry
                    entry_x = cx + (arc_r - new_r) * math.cos(start_angle)
                    entry_y = cy + (arc_r - new_r) * math.sin(start_angle)
                    points.append(ToolpathPoint(entry_x, entry_y, safe_z, MoveType.RAPID))
                    points.append(ToolpathPoint(entry_x, entry_y, z_level, MoveType.LINEAR, plunge_rate))

                    # Quarter arc in the corner
                    for i in range(arc_pts + 1):
                        a = start_angle + (math.pi / 2) * i / arc_pts
                        px = cx + (arc_r - new_r) * math.cos(a)
                        py = cy + (arc_r - new_r) * math.sin(a)
                        points.append(ToolpathPoint(px, py, z_level, MoveType.LINEAR, feed_rate))

                    points.append(ToolpathPoint(points[-1].x, points[-1].y, safe_z, MoveType.RAPID))

        return [ToolpathSegment("Rest Machining", tool, points, spindle_rpm)]


# --- Utility ---

def _calc_z_passes(z_top: float, z_bottom: float, depth_per_pass: float) -> list[float]:
    """Calculate Z-level passes from top to bottom."""
    passes = []
    z = z_top - depth_per_pass
    while z > z_bottom:
        passes.append(z)
        z -= depth_per_pass
    if not passes or abs(passes[-1] - z_bottom) > 1e-6:
        passes.append(z_bottom)
    return passes


def _frange(start: float, stop: float, step: float) -> list[float]:
    """Float range generator."""
    result = []
    x = start
    if step > 0:
        while x <= stop + 1e-9:
            result.append(x)
            x += step
    elif step < 0:
        while x >= stop - 1e-9:
            result.append(x)
            x += step
    return result
