"""Step 4: Cutter Radius Compensation (CRC) via software offset.

Offsets profile/contour paths by the tool radius so that the
tool edge (not center) follows the programmed profile.

This is the software-side alternative to G41/G42 machine compensation.
Software offset is preferred because it's verifiable in simulation.

Usage:
    from src.cam.crc import offset_segment_profile, offset_xy_path
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .toolpath import MoveType, ToolpathPoint, ToolpathSegment

if TYPE_CHECKING:
    pass

try:
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


def _offset_polyline_manual(
    points_2d: list[tuple[float, float]],
    offset: float,
    side: str = "left",
) -> list[tuple[float, float]]:
    """Manual parallel offset of a polyline (no Shapely).

    Works by offsetting each segment along its left/right normal
    and intersecting adjacent segment offsets.
    """
    if len(points_2d) < 2:
        return points_2d

    sign = 1.0 if side == "left" else -1.0
    n = len(points_2d)
    result = []

    for i in range(n):
        if i == 0:
            # Use direction of first segment
            dx = points_2d[1][0] - points_2d[0][0]
            dy = points_2d[1][1] - points_2d[0][1]
        elif i == n - 1:
            dx = points_2d[-1][0] - points_2d[-2][0]
            dy = points_2d[-1][1] - points_2d[-2][1]
        else:
            # Average of two adjacent segment normals (miter)
            dx1 = points_2d[i][0] - points_2d[i-1][0]
            dy1 = points_2d[i][1] - points_2d[i-1][1]
            dx2 = points_2d[i+1][0] - points_2d[i][0]
            dy2 = points_2d[i+1][1] - points_2d[i][1]
            dx = dx1 + dx2
            dy = dy1 + dy2

        length = math.hypot(dx, dy)
        if length < 1e-9:
            if result:
                result.append(result[-1])
            else:
                result.append(points_2d[i])
            continue

        # Left normal: rotate dx,dy by +90°
        nx = -dy / length * sign
        ny = dx / length * sign
        result.append((
            points_2d[i][0] + nx * offset,
            points_2d[i][1] + ny * offset,
        ))

    return result


def offset_xy_path(
    xy_points: list[tuple[float, float]],
    offset_dist: float,
    side: str = "left",
    closed: bool = False,
) -> list[tuple[float, float]]:
    """Offset a 2D polyline by offset_dist.

    Args:
        xy_points: list of (x, y) tuples
        offset_dist: positive offset distance (mm)
        side: "left" = G41 climb, "right" = G42 conventional
        closed: True if the path is a closed loop (adds closing segment)

    Returns:
        Offset 2D polyline.
    """
    if HAS_SHAPELY and len(xy_points) >= 2:
        try:
            sign = 1.0 if side == "left" else -1.0
            if closed:
                poly = Polygon(xy_points)
                offset_poly = poly.buffer(-offset_dist * sign)
                if not offset_poly.is_empty:
                    return list(offset_poly.exterior.coords)
                return xy_points
            else:
                line = LineString(xy_points)
                offset_line = line.parallel_offset(
                    offset_dist,
                    side,
                    join_style=2,   # mitered
                    mitre_limit=5.0,
                )
                if hasattr(offset_line, "coords"):
                    return list(offset_line.coords)
        except Exception:
            pass

    # Fallback: manual offset
    return _offset_polyline_manual(xy_points, offset_dist, side)


def offset_segment_profile(
    segment: ToolpathSegment,
    side: str = "left",
    extra_offset: float = 0.0,
) -> ToolpathSegment:
    """Apply cutter radius compensation to a profile/contour segment.

    Offsets all LINEAR cutting moves by the tool radius so the
    cutting edge (not center) traces the programmed geometry.

    Args:
        segment: original toolpath segment
        side: "left" (G41, climb) or "right" (G42, conventional)
        extra_offset: additional offset beyond tool radius (finishing allowance)

    Returns:
        New segment with offset toolpath.
    """
    offset = segment.tool.radius + extra_offset
    if offset < 0.001:
        return segment

    # Split into Z-level groups (separate loops per depth)
    # Each group of LINEAR points at the same Z gets offset together
    import copy

    new_points: list[ToolpathPoint] = []
    i = 0
    pts = segment.points

    while i < len(pts):
        pt = pts[i]

        if pt.move_type == MoveType.RAPID:
            new_points.append(pt)
            i += 1
            continue

        # Collect consecutive LINEAR points at same Z
        group: list[ToolpathPoint] = []
        j = i
        current_z = pt.z
        while j < len(pts) and pts[j].move_type == MoveType.LINEAR:
            if abs(pts[j].z - current_z) > 0.01:
                break
            group.append(pts[j])
            j += 1

        if len(group) < 2:
            new_points.extend(group)
            i = j
            continue

        # Extract XY and offset
        xy = [(p.x, p.y) for p in group]
        is_closed = math.hypot(xy[0][0] - xy[-1][0], xy[0][1] - xy[-1][1]) < 0.1
        xy_off = offset_xy_path(xy, offset, side, closed=is_closed)

        # Rebuild points with offset XY
        for k, (x_off, y_off) in enumerate(xy_off[:len(group)]):
            orig = group[k]
            new_points.append(ToolpathPoint(
                x_off, y_off, orig.z,
                orig.move_type, orig.feed_rate,
                orig.i, orig.j, orig.k,
            ))

        i = j

    new_seg = copy.copy(segment)
    new_seg.points = new_points
    new_seg.name = segment.name + f" (CRC {side})"
    return new_seg


def apply_crc_to_profiles(
    segments: list[ToolpathSegment],
    side: str = "left",
    finishing_allowance: float = 0.0,
    segment_name_filter: str | None = None,
) -> list[ToolpathSegment]:
    """Apply CRC to matching segments in a list.

    Args:
        segments: all toolpath segments
        side: "left" or "right"
        finishing_allowance: extra stock to leave (mm, use 0 for finishing)
        segment_name_filter: only apply to segments whose name contains this string.
                             None = apply to Profile/Contour segments only.

    Returns:
        Segments list with CRC applied to matching segments.
    """
    profile_keywords = {"profile", "contour", "outline", "Profile", "Contour"}
    result = []
    for seg in segments:
        apply = False
        if segment_name_filter is not None:
            apply = segment_name_filter.lower() in seg.name.lower()
        else:
            apply = any(k in seg.name for k in profile_keywords)

        if apply:
            try:
                seg = offset_segment_profile(seg, side, finishing_allowance)
            except Exception:
                pass
        result.append(seg)
    return result
