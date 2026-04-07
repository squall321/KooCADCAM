"""Step 6: Approach (lead-in) and retract (lead-out) path generation.

Replaces vertical plunge moves with safer helical entry, ramp entry,
or tangential arc lead-in. Improves tool life and surface finish.

Usage:
    from src.cam.approach import add_helical_entry, add_ramp_entry, add_arc_lead_in
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .toolpath import MoveType, ToolpathPoint, ToolpathSegment

if TYPE_CHECKING:
    pass


# ─── Helical entry ─────────────────────────────────────────────────

def make_helical_entry(
    cx: float, cy: float,
    z_start: float,
    z_end: float,
    helix_radius: float,
    pitch: float = 1.0,
    feed_rate: float = 200.0,
    plunge_rate: float = 150.0,
    n_turns_min: int = 2,
) -> list[ToolpathPoint]:
    """Generate a helical entry move (spiral down to z_end).

    The tool spirals around (cx, cy) descending from z_start to z_end.
    Used for pocket entry: avoids full-face plunging.

    Args:
        cx, cy: center of helix (pocket center)
        z_start: Z to start helix (above pocket)
        z_end: Z of pocket floor (where helix ends)
        helix_radius: radius of the helix (< pocket inscribed circle - tool_r)
        pitch: Z drop per full turn (mm)
        n_turns_min: minimum number of full turns
    """
    total_drop = z_start - z_end
    if total_drop <= 0:
        return []

    n_turns = max(n_turns_min, math.ceil(total_drop / pitch))
    total_angle = n_turns * 2 * math.pi
    # Steps: 36 points per turn for smooth arc approximation
    n_steps = n_turns * 36

    points: list[ToolpathPoint] = []
    for i in range(n_steps + 1):
        frac = i / n_steps
        angle = frac * total_angle
        z = z_start - frac * total_drop
        x = cx + helix_radius * math.cos(angle)
        y = cy + helix_radius * math.sin(angle)
        points.append(ToolpathPoint(x, y, z, MoveType.LINEAR, plunge_rate))

    return points


def prepend_helical_entry(
    segment: ToolpathSegment,
    pocket_cx: float,
    pocket_cy: float,
    helix_radius: float,
    safe_z: float | None = None,
    pitch: float = 1.0,
    plunge_rate: float = 150.0,
) -> ToolpathSegment:
    """Prepend a helical entry to an existing toolpath segment.

    Finds the first cutting move and replaces the plunge before it
    with a helical approach.
    """
    if not segment.points:
        return segment

    # Find first Z-descending LINEAR move (the original plunge)
    first_cut_idx = None
    first_cut_z = None
    for i, pt in enumerate(segment.points):
        if pt.move_type == MoveType.LINEAR and i > 0:
            first_cut_idx = i
            first_cut_z = pt.z
            break

    if first_cut_idx is None or first_cut_z is None:
        return segment

    z_safe = safe_z or (first_cut_z + 10.0)

    # Build: RAPID to helix start, then helix, then original points from first cut
    helix_start_x = pocket_cx + helix_radius
    helix_start_y = pocket_cy

    new_points: list[ToolpathPoint] = [
        ToolpathPoint(helix_start_x, helix_start_y, z_safe, MoveType.RAPID),
    ]
    new_points += make_helical_entry(
        pocket_cx, pocket_cy,
        z_start=z_safe,
        z_end=first_cut_z,
        helix_radius=helix_radius,
        pitch=pitch,
        plunge_rate=plunge_rate,
    )
    # Skip original rapid+plunge, keep everything from first linear cut onward
    new_points += segment.points[first_cut_idx:]

    import copy
    new_seg = copy.copy(segment)
    new_seg.points = new_points
    new_seg.name = segment.name + " (helical entry)"
    return new_seg


# ─── Ramp entry ────────────────────────────────────────────────────

def make_ramp_entry(
    x_start: float, y_start: float,
    x_end: float, y_end: float,
    z_start: float, z_end: float,
    ramp_angle_deg: float = 3.0,
    feed_rate: float = 250.0,
) -> list[ToolpathPoint]:
    """Generate a linear ramp-in move.

    Tool descends at a shallow angle (typically 3°) along the path
    instead of plunging vertically.

    Args:
        x_start/y_start: ramp start XY (above material)
        x_end/y_end: ramp end XY
        z_start: Z above material
        z_end: final cutting Z
        ramp_angle_deg: descent angle in degrees (2–5° typical)
    """
    dist_xy = math.hypot(x_end - x_start, y_end - y_start)
    if dist_xy < 0.01:
        return [ToolpathPoint(x_end, y_end, z_end, MoveType.LINEAR, feed_rate)]

    total_drop = z_start - z_end
    ramp_length = total_drop / math.tan(math.radians(ramp_angle_deg))
    n_segments = max(4, int(ramp_length / 2.0))

    points: list[ToolpathPoint] = []
    for i in range(1, n_segments + 1):
        frac = i / n_segments
        x = x_start + frac * (x_end - x_start)
        y = y_start + frac * (y_end - y_start)
        z = z_start - frac * total_drop
        points.append(ToolpathPoint(x, y, z, MoveType.LINEAR, feed_rate))

    return points


def prepend_ramp_entry(
    segment: ToolpathSegment,
    ramp_angle_deg: float = 3.0,
) -> ToolpathSegment:
    """Replace the first vertical plunge in a segment with a ramp move."""
    if not segment.points:
        return segment

    # Find the vertical plunge: two consecutive LINEAR points with same XY but dropping Z
    for i in range(1, len(segment.points)):
        prev = segment.points[i - 1]
        curr = segment.points[i]
        if (curr.move_type == MoveType.LINEAR
                and abs(curr.x - prev.x) < 0.01
                and abs(curr.y - prev.y) < 0.01
                and curr.z < prev.z - 0.1):
            # Found the plunge at index i
            # We need a second point to define the ramp direction
            if i + 1 < len(segment.points):
                next_pt = segment.points[i + 1]
                ramp_pts = make_ramp_entry(
                    curr.x, curr.y,
                    next_pt.x, next_pt.y,
                    z_start=prev.z,
                    z_end=curr.z,
                    ramp_angle_deg=ramp_angle_deg,
                    feed_rate=curr.feed_rate or 200.0,
                )
                import copy
                new_seg = copy.copy(segment)
                new_seg.points = (
                    segment.points[:i]    # keep rapid up to this point
                    + ramp_pts
                    + segment.points[i + 1:]  # skip original plunge
                )
                new_seg.name = segment.name + " (ramp entry)"
                return new_seg
            break

    return segment


# ─── Tangential arc lead-in (for profile/contour) ─────────────────

def make_arc_lead_in(
    entry_x: float, entry_y: float,
    path_dir_x: float, path_dir_y: float,
    z: float,
    arc_radius: float,
    feed_rate: float = 300.0,
    n_points: int = 12,
) -> list[ToolpathPoint]:
    """Generate a tangential arc approach to a profile start point.

    The tool approaches in a quarter-circle arc tangent to the profile
    direction, preventing a dwell mark at the entry point.

    Args:
        entry_x/y: the point where cutting begins
        path_dir_x/y: unit vector of path direction at entry (normalized)
        z: cutting Z level
        arc_radius: radius of the lead-in arc
        n_points: number of arc points
    """
    # Normalize direction
    length = math.hypot(path_dir_x, path_dir_y)
    if length < 1e-6:
        return []
    dx = path_dir_x / length
    dy = path_dir_y / length

    # Perpendicular (90° CCW from path direction)
    px = -dy
    py = dx

    # Arc center: offset from entry perpendicular to path by arc_radius
    arc_cx = entry_x + px * arc_radius
    arc_cy = entry_y + py * arc_radius

    # Arc start point: arc_radius away from center, opposite to entry
    start_x = arc_cx - px * arc_radius
    start_y = arc_cy - py * arc_radius

    points: list[ToolpathPoint] = [
        ToolpathPoint(start_x, start_y, z, MoveType.RAPID),
    ]

    # Quarter-circle arc from start to entry
    start_angle = math.atan2(start_y - arc_cy, start_x - arc_cx)
    end_angle = math.atan2(entry_y - arc_cy, entry_x - arc_cx)

    # Ensure CCW direction
    if end_angle < start_angle:
        end_angle += 2 * math.pi

    for i in range(1, n_points + 1):
        frac = i / n_points
        angle = start_angle + frac * (end_angle - start_angle)
        x = arc_cx + arc_radius * math.cos(angle)
        y = arc_cy + arc_radius * math.sin(angle)
        points.append(ToolpathPoint(x, y, z, MoveType.LINEAR, feed_rate))

    return points


# ─── Convenience: apply approach to all segments ──────────────────

def apply_approach_to_segments(
    segments: list[ToolpathSegment],
    strategy: str = "ramp",
    helical_radius_factor: float = 0.4,
    ramp_angle_deg: float = 3.0,
) -> list[ToolpathSegment]:
    """Apply entry approach to all segments.

    Args:
        segments: list of toolpath segments
        strategy: "helical", "ramp", or "none"
        helical_radius_factor: helix radius = tool_radius * factor
        ramp_angle_deg: ramp descent angle

    Returns:
        Modified segments list.
    """
    if strategy == "none":
        return segments

    result = []
    for seg in segments:
        try:
            if strategy == "ramp":
                seg = prepend_ramp_entry(seg, ramp_angle_deg)
            elif strategy == "helical":
                # Find pocket center from segment bounding box
                if seg.points:
                    xs = [p.x for p in seg.points]
                    ys = [p.y for p in seg.points]
                    cx = (min(xs) + max(xs)) / 2
                    cy = (min(ys) + max(ys)) / 2
                    hr = seg.tool.radius * helical_radius_factor
                    if hr > 0.5:
                        seg = prepend_helical_entry(seg, cx, cy, hr)
        except Exception:
            pass
        result.append(seg)
    return result
