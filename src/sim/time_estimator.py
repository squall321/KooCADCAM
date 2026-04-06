"""CNC machining time estimation and analysis.

Provides accurate cycle time prediction based on G-code analysis,
accounting for acceleration/deceleration, tool changes, and dwell times.
Essential for digital twin accuracy and process optimization.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .gcode_parser import PathSegment, PathType


@dataclass
class MachineParams:
    """CNC machine kinematic parameters for time estimation."""
    max_rapid_rate: float = 15000.0     # mm/min (G0 traverse speed)
    max_accel: float = 500.0            # mm/s² (axis acceleration)
    tool_change_time: float = 8.0       # seconds per tool change
    spindle_ramp_time: float = 2.0      # seconds to reach RPM
    coolant_delay: float = 1.0          # seconds for coolant on/off
    program_start_delay: float = 3.0    # seconds (homing, warm-up)
    block_processing_time: float = 0.001  # seconds per G-code block (lookahead)


@dataclass
class TimeBreakdown:
    """Detailed time breakdown of a machining operation."""
    cutting_time: float = 0.0       # seconds
    rapid_time: float = 0.0        # seconds
    tool_change_time: float = 0.0  # seconds
    dwell_time: float = 0.0        # seconds
    accel_decel_time: float = 0.0  # seconds
    overhead_time: float = 0.0     # seconds (spindle ramp, coolant, etc.)

    @property
    def total_time(self) -> float:
        return (self.cutting_time + self.rapid_time + self.tool_change_time +
                self.dwell_time + self.accel_decel_time + self.overhead_time)

    @property
    def cutting_pct(self) -> float:
        t = self.total_time
        return 100 * self.cutting_time / t if t > 0 else 0

    @property
    def non_cutting_pct(self) -> float:
        return 100 - self.cutting_pct

    def format_time(self, seconds: float) -> str:
        """Format seconds into human-readable string."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            m, s = divmod(seconds, 60)
            return f"{int(m)}m {int(s)}s"
        else:
            h, rem = divmod(seconds, 3600)
            m, s = divmod(rem, 60)
            return f"{int(h)}h {int(m)}m {int(s)}s"

    def __str__(self) -> str:
        lines = [
            f"Machining Time Estimate",
            f"{'='*40}",
            f"  Cutting:       {self.format_time(self.cutting_time):>10}  ({self.cutting_pct:.1f}%)",
            f"  Rapid traverse: {self.format_time(self.rapid_time):>9}",
            f"  Accel/decel:   {self.format_time(self.accel_decel_time):>10}",
            f"  Tool change:   {self.format_time(self.tool_change_time):>10}",
            f"  Overhead:      {self.format_time(self.overhead_time):>10}",
            f"  {'─'*38}",
            f"  TOTAL:         {self.format_time(self.total_time):>10}",
            f"",
            f"  Cutting efficiency: {self.cutting_pct:.1f}%",
        ]
        return "\n".join(lines)


@dataclass
class SegmentTiming:
    """Timing for a single path segment."""
    segment_index: int
    distance: float         # mm
    feed_rate: float        # mm/min
    time: float             # seconds
    cumulative_time: float  # seconds from start
    path_type: PathType
    x: float
    y: float
    z: float


class TimeEstimator:
    """Estimates CNC machining cycle time from G-code.

    Accounts for:
    - Cutting feed rates (G1/G2/G3)
    - Rapid traverse speed with limits (G0)
    - Acceleration/deceleration at direction changes
    - Tool change times
    - Spindle ramp-up/down
    - Coolant delays
    - Block processing overhead

    Usage:
        estimator = TimeEstimator()
        breakdown = estimator.estimate(segments)
        print(breakdown)

        # Per-segment timing for animation sync
        timings = estimator.get_segment_timings(segments)
    """

    def __init__(self, params: MachineParams | None = None) -> None:
        self.params = params or MachineParams()

    def estimate(
        self,
        segments: list[PathSegment],
        num_tool_changes: int = 0,
    ) -> TimeBreakdown:
        """Estimate total machining time.

        Args:
            segments: Parsed G-code segments.
            num_tool_changes: Number of tool changes in the program.
        """
        breakdown = TimeBreakdown()

        # Startup overhead
        breakdown.overhead_time += self.params.program_start_delay
        breakdown.overhead_time += self.params.spindle_ramp_time
        breakdown.overhead_time += self.params.coolant_delay

        # Tool changes
        breakdown.tool_change_time = num_tool_changes * self.params.tool_change_time

        prev_dx, prev_dy, prev_dz = 0, 0, 1  # initial direction (Z up)

        for i, seg in enumerate(segments):
            dx = seg.x_end - seg.x_start
            dy = seg.y_end - seg.y_start
            dz = seg.z_end - seg.z_start
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)

            if dist < 1e-9:
                continue

            if seg.path_type == PathType.RAPID:
                # Rapid: limited by machine max rapid rate
                speed = self.params.max_rapid_rate  # mm/min
                t = dist / speed * 60  # seconds
                breakdown.rapid_time += t
            else:
                # Cutting: use programmed feed rate
                feed = seg.feed_rate if seg.feed_rate > 0 else 500.0
                t = dist / feed * 60  # seconds
                breakdown.cutting_time += t

            # Acceleration/deceleration at direction changes
            if i > 0:
                angle = self._direction_change_angle(
                    prev_dx, prev_dy, prev_dz, dx, dy, dz
                )
                if angle > 5.0:  # Significant direction change (>5 degrees)
                    # Time to decelerate and re-accelerate
                    feed = seg.feed_rate if seg.feed_rate > 0 else self.params.max_rapid_rate
                    v = feed / 60  # mm/s
                    accel = self.params.max_accel
                    # Simplified trapezoidal profile
                    decel_time = min(v / accel, 0.5)  # Cap at 0.5s
                    scale = min(angle / 90.0, 1.0)  # Scale by angle severity
                    breakdown.accel_decel_time += decel_time * scale * 2

            # Block processing
            breakdown.overhead_time += self.params.block_processing_time

            prev_dx, prev_dy, prev_dz = dx, dy, dz

        # Final spindle off + coolant off
        breakdown.overhead_time += self.params.spindle_ramp_time * 0.5
        breakdown.overhead_time += self.params.coolant_delay

        return breakdown

    def get_segment_timings(self, segments: list[PathSegment]) -> list[SegmentTiming]:
        """Get per-segment timing for animation synchronization.

        Returns a list of SegmentTiming with cumulative timestamps,
        useful for syncing the visual simulation to real time.
        """
        timings: list[SegmentTiming] = []
        cumulative = 0.0

        for i, seg in enumerate(segments):
            dx = seg.x_end - seg.x_start
            dy = seg.y_end - seg.y_start
            dz = seg.z_end - seg.z_start
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)

            if seg.path_type == PathType.RAPID:
                speed = self.params.max_rapid_rate
            else:
                speed = seg.feed_rate if seg.feed_rate > 0 else 500.0

            t = dist / speed * 60 if speed > 0 else 0  # seconds
            cumulative += t

            timings.append(SegmentTiming(
                segment_index=i,
                distance=dist,
                feed_rate=speed,
                time=t,
                cumulative_time=cumulative,
                path_type=seg.path_type,
                x=seg.x_end, y=seg.y_end, z=seg.z_end,
            ))

        return timings

    def _direction_change_angle(
        self, dx1: float, dy1: float, dz1: float,
        dx2: float, dy2: float, dz2: float,
    ) -> float:
        """Calculate angle between two direction vectors in degrees."""
        len1 = math.sqrt(dx1 * dx1 + dy1 * dy1 + dz1 * dz1)
        len2 = math.sqrt(dx2 * dx2 + dy2 * dy2 + dz2 * dz2)
        if len1 < 1e-9 or len2 < 1e-9:
            return 0.0
        cos_a = (dx1 * dx2 + dy1 * dy2 + dz1 * dz2) / (len1 * len2)
        cos_a = max(-1.0, min(1.0, cos_a))
        return math.degrees(math.acos(cos_a))


@dataclass
class CuttingDistanceStats:
    """Cutting distance statistics for wear/cost estimation."""
    total_cutting_distance: float = 0.0   # mm
    total_rapid_distance: float = 0.0     # mm
    max_cutting_depth: float = 0.0        # mm (Z range)
    avg_feed_rate: float = 0.0            # mm/min
    per_tool: dict[str, float] = field(default_factory=dict)

    def __str__(self) -> str:
        return (
            f"Cutting Distance: {self.total_cutting_distance:.0f} mm\n"
            f"Rapid Distance:   {self.total_rapid_distance:.0f} mm\n"
            f"Max Depth:        {self.max_cutting_depth:.1f} mm\n"
            f"Avg Feed:         {self.avg_feed_rate:.0f} mm/min"
        )


def estimate_distances(segments: list[PathSegment]) -> CuttingDistanceStats:
    """Calculate cutting and rapid travel distances."""
    stats = CuttingDistanceStats()
    feed_sum = 0.0
    feed_count = 0

    z_values = []

    for seg in segments:
        dx = seg.x_end - seg.x_start
        dy = seg.y_end - seg.y_start
        dz = seg.z_end - seg.z_start
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)

        if seg.path_type == PathType.RAPID:
            stats.total_rapid_distance += dist
        else:
            stats.total_cutting_distance += dist
            if seg.feed_rate > 0:
                feed_sum += seg.feed_rate
                feed_count += 1
            z_values.extend([seg.z_start, seg.z_end])

    if z_values:
        stats.max_cutting_depth = max(z_values) - min(z_values)
    if feed_count > 0:
        stats.avg_feed_rate = feed_sum / feed_count

    return stats
