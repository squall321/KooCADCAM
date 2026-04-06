"""Toolpath optimization: rapid minimization, feed override, path smoothing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from .toolpath import ToolpathSegment, ToolpathPoint, MoveType


class RapidOptimizer:
    """Minimize total rapid (non-cutting) travel distance.

    Uses nearest-neighbor heuristic (TSP approximation) to reorder
    independent cutting segments for minimal rapid repositioning.
    """

    def optimize(self, segments: list[ToolpathSegment]) -> list[ToolpathSegment]:
        """Reorder segments to minimize total rapid travel distance."""
        if len(segments) <= 1:
            return segments

        # Group segments by tool (only reorder within same tool)
        tool_groups: dict[int, list[tuple[int, ToolpathSegment]]] = {}
        for i, seg in enumerate(segments):
            tn = seg.tool.tool_number
            if tn not in tool_groups:
                tool_groups[tn] = []
            tool_groups[tn].append((i, seg))

        result: list[ToolpathSegment] = []
        for tn in sorted(tool_groups.keys()):
            group = tool_groups[tn]
            if len(group) <= 1:
                result.extend(seg for _, seg in group)
                continue

            # Nearest-neighbor starting from first segment
            remaining = list(range(len(group)))
            order = [remaining.pop(0)]
            while remaining:
                last_seg = group[order[-1]][1]
                last_end = _segment_end(last_seg)
                best_idx = min(
                    remaining,
                    key=lambda j: _dist(last_end, _segment_start(group[j][1]))
                )
                order.append(best_idx)
                remaining.remove(best_idx)

            result.extend(group[i][1] for i in order)

        return result


class LinkOptimizer:
    """Optimize link moves between cutting passes within a segment.

    Replaces full-retract links with direct transition moves
    where safe to do so (no collision risk at same Z level).
    """

    def optimize(
        self,
        segment: ToolpathSegment,
        min_retract_height: float = 2.0,
    ) -> ToolpathSegment:
        """Reduce unnecessary retracts within a segment.

        If consecutive cuts are at the same Z and close together,
        replace full retract with a minimal lift.
        """
        if len(segment.points) < 4:
            return segment

        optimized: list[ToolpathPoint] = []
        points = segment.points
        i = 0

        while i < len(points):
            pt = points[i]

            # Detect pattern: cutting -> retract -> rapid_xy -> plunge -> cutting
            if (i + 3 < len(points)
                and pt.move_type == MoveType.LINEAR
                and points[i + 1].move_type == MoveType.RAPID
                and points[i + 2].move_type == MoveType.RAPID
                and points[i + 3].move_type == MoveType.LINEAR):

                retract_pt = points[i + 1]
                rapid_pt = points[i + 2]
                plunge_pt = points[i + 3]

                # Check if same Z level and close enough
                xy_dist = math.sqrt(
                    (rapid_pt.x - pt.x) ** 2 + (rapid_pt.y - pt.y) ** 2
                )

                if abs(plunge_pt.z - pt.z) < 0.01 and xy_dist < 20.0:
                    # Replace with minimal lift + direct move
                    lift_z = pt.z + min_retract_height
                    optimized.append(pt)
                    optimized.append(ToolpathPoint(pt.x, pt.y, lift_z, MoveType.RAPID))
                    optimized.append(ToolpathPoint(plunge_pt.x, plunge_pt.y, lift_z, MoveType.RAPID))
                    optimized.append(ToolpathPoint(plunge_pt.x, plunge_pt.y, plunge_pt.z, MoveType.LINEAR, plunge_pt.feed_rate))
                    i += 4
                    continue

            optimized.append(pt)
            i += 1

        return ToolpathSegment(
            segment.name, segment.tool, optimized,
            segment.spindle_rpm, segment.coolant
        )


class FeedOverride:
    """Adjust feed rate based on local curvature and engagement.

    Slows down in tight curves and corners, speeds up on straight sections
    to maintain constant chip load.
    """

    def optimize(
        self,
        segment: ToolpathSegment,
        base_feed: float = 500.0,
        min_feed_ratio: float = 0.3,
        corner_threshold: float = 30.0,
    ) -> ToolpathSegment:
        """Apply feed rate modulation based on direction changes.

        Args:
            base_feed: Nominal feed rate.
            min_feed_ratio: Minimum feed as fraction of base (at sharp corners).
            corner_threshold: Angle change (degrees) considered a corner.
        """
        points = segment.points
        if len(points) < 3:
            return segment

        optimized: list[ToolpathPoint] = [points[0]]

        for i in range(1, len(points) - 1):
            prev, curr, nxt = points[i - 1], points[i], points[i + 1]

            if curr.move_type != MoveType.LINEAR:
                optimized.append(curr)
                continue

            # Calculate direction change angle
            dx1 = curr.x - prev.x
            dy1 = curr.y - prev.y
            dx2 = nxt.x - curr.x
            dy2 = nxt.y - curr.y

            len1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
            len2 = math.sqrt(dx2 * dx2 + dy2 * dy2)

            if len1 < 1e-9 or len2 < 1e-9:
                optimized.append(curr)
                continue

            cos_angle = (dx1 * dx2 + dy1 * dy2) / (len1 * len2)
            cos_angle = max(-1.0, min(1.0, cos_angle))
            angle_deg = math.degrees(math.acos(cos_angle))

            # Calculate feed ratio based on corner sharpness
            if angle_deg > corner_threshold:
                ratio = max(min_feed_ratio, 1.0 - (angle_deg - corner_threshold) / (180 - corner_threshold))
            else:
                ratio = 1.0

            adjusted_feed = base_feed * ratio
            optimized.append(ToolpathPoint(
                curr.x, curr.y, curr.z, curr.move_type,
                adjusted_feed, curr.i, curr.j, curr.k,
            ))

        optimized.append(points[-1])

        return ToolpathSegment(
            segment.name, segment.tool, optimized,
            segment.spindle_rpm, segment.coolant,
        )


class ToolpathSmoother:
    """Smooth toolpath by fitting splines through dense point sequences.

    Replaces series of short linear segments with fewer, smoother segments.
    Reduces G-code size and improves surface finish.
    """

    def smooth(
        self,
        segment: ToolpathSegment,
        tolerance: float = 0.01,
        min_segment_length: float = 0.5,
    ) -> ToolpathSegment:
        """Apply Douglas-Peucker simplification to cutting paths.

        Args:
            tolerance: Maximum allowed deviation from original path (mm).
            min_segment_length: Minimum segment length to keep.
        """
        points = segment.points
        if len(points) < 3:
            return segment

        # Split into cutting and non-cutting groups
        groups: list[tuple[bool, list[int]]] = []
        current_is_cutting = points[0].move_type == MoveType.LINEAR
        current_indices = [0]

        for i in range(1, len(points)):
            is_cutting = points[i].move_type == MoveType.LINEAR
            if is_cutting == current_is_cutting:
                current_indices.append(i)
            else:
                groups.append((current_is_cutting, current_indices))
                current_is_cutting = is_cutting
                current_indices = [i]
        groups.append((current_is_cutting, current_indices))

        # Simplify only cutting groups
        result_indices: list[int] = []
        for is_cutting, indices in groups:
            if is_cutting and len(indices) >= 3:
                coords = np.array([[points[i].x, points[i].y, points[i].z] for i in indices])
                simplified = _douglas_peucker(coords, tolerance)
                # Map back to original indices
                for si in simplified:
                    result_indices.append(indices[si])
            else:
                result_indices.extend(indices)

        # Deduplicate and sort
        result_indices = sorted(set(result_indices))
        optimized = [points[i] for i in result_indices]

        return ToolpathSegment(
            segment.name, segment.tool, optimized,
            segment.spindle_rpm, segment.coolant,
        )


@dataclass
class OptimizationReport:
    """Summary of optimization results."""
    original_points: int
    optimized_points: int
    original_rapid_dist: float
    optimized_rapid_dist: float
    reduction_pct: float

    def __str__(self) -> str:
        return (
            f"Optimization Report:\n"
            f"  Points: {self.original_points} → {self.optimized_points} "
            f"({100 * (1 - self.optimized_points / max(self.original_points, 1)):.1f}% reduced)\n"
            f"  Rapid distance: {self.original_rapid_dist:.1f} → {self.optimized_rapid_dist:.1f} mm "
            f"({self.reduction_pct:.1f}% reduced)"
        )


def optimize_all(
    segments: list[ToolpathSegment],
    base_feed: float = 500.0,
    smooth_tolerance: float = 0.01,
) -> tuple[list[ToolpathSegment], OptimizationReport]:
    """Apply all optimizations in sequence.

    Returns optimized segments and a report.
    """
    original_pts = sum(len(s.points) for s in segments)
    original_rapid = _total_rapid_distance(segments)

    # 1. Reorder segments
    rapid_opt = RapidOptimizer()
    segments = rapid_opt.optimize(segments)

    # 2. Optimize links within each segment
    link_opt = LinkOptimizer()
    segments = [link_opt.optimize(s) for s in segments]

    # 3. Feed override
    feed_opt = FeedOverride()
    segments = [feed_opt.optimize(s, base_feed) for s in segments]

    # 4. Smooth
    smoother = ToolpathSmoother()
    segments = [smoother.smooth(s, smooth_tolerance) for s in segments]

    optimized_pts = sum(len(s.points) for s in segments)
    optimized_rapid = _total_rapid_distance(segments)

    report = OptimizationReport(
        original_points=original_pts,
        optimized_points=optimized_pts,
        original_rapid_dist=original_rapid,
        optimized_rapid_dist=optimized_rapid,
        reduction_pct=100 * (1 - optimized_rapid / max(original_rapid, 1e-9)),
    )

    return segments, report


# --- Internal helpers ---

def _segment_start(seg: ToolpathSegment) -> tuple[float, float, float]:
    if seg.points:
        p = seg.points[0]
        return (p.x, p.y, p.z)
    return (0, 0, 0)


def _segment_end(seg: ToolpathSegment) -> tuple[float, float, float]:
    if seg.points:
        p = seg.points[-1]
        return (p.x, p.y, p.z)
    return (0, 0, 0)


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _total_rapid_distance(segments: list[ToolpathSegment]) -> float:
    total = 0.0
    for seg in segments:
        for i in range(1, len(seg.points)):
            if seg.points[i].move_type == MoveType.RAPID:
                p0 = seg.points[i - 1]
                p1 = seg.points[i]
                total += _dist((p0.x, p0.y, p0.z), (p1.x, p1.y, p1.z))
    return total


def _douglas_peucker(points: np.ndarray, tolerance: float) -> list[int]:
    """Douglas-Peucker polyline simplification. Returns indices to keep."""
    if len(points) <= 2:
        return list(range(len(points)))

    # Find point with max distance from line(start, end)
    start = points[0]
    end = points[-1]
    line_vec = end - start
    line_len = np.linalg.norm(line_vec)

    if line_len < 1e-12:
        return [0, len(points) - 1]

    line_unit = line_vec / line_len
    dists = np.zeros(len(points))
    for i in range(1, len(points) - 1):
        v = points[i] - start
        proj = np.dot(v, line_unit)
        proj = max(0, min(line_len, proj))
        closest = start + line_unit * proj
        dists[i] = np.linalg.norm(points[i] - closest)

    max_idx = np.argmax(dists)
    max_dist = dists[max_idx]

    if max_dist > tolerance:
        left = _douglas_peucker(points[:max_idx + 1], tolerance)
        right = _douglas_peucker(points[max_idx:], tolerance)
        return left + [i + max_idx for i in right[1:]]
    else:
        return [0, len(points) - 1]
