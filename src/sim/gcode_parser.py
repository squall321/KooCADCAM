"""G-code parser: converts G-code text to structured path data for visualization."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pygcode import Line, GCodeRapidMove, GCodeLinearMove, GCodeArcMoveCW, GCodeArcMoveCCW


class PathType(Enum):
    RAPID = "rapid"
    CUTTING = "cutting"
    ARC_CW = "arc_cw"
    ARC_CCW = "arc_ccw"


@dataclass
class PathSegment:
    """A single movement segment parsed from G-code."""
    x_start: float
    y_start: float
    z_start: float
    x_end: float
    y_end: float
    z_end: float
    path_type: PathType
    feed_rate: float = 0.0


class GcodeParser:
    """Parse G-code text or file into a list of PathSegments.

    Usage:
        parser = GcodeParser()
        segments = parser.parse_file("output.nc")
        # or
        segments = parser.parse_text(gcode_string)
    """

    def parse_file(self, path: str | Path) -> list[PathSegment]:
        text = Path(path).read_text()
        return self.parse_text(text)

    def parse_text(self, text: str) -> list[PathSegment]:
        segments: list[PathSegment] = []
        cx, cy, cz = 0.0, 0.0, 0.0  # current position
        feed = 0.0

        for line_text in text.splitlines():
            line_text = line_text.strip()
            if not line_text or line_text.startswith("%") or line_text.startswith("(") or line_text.startswith(";"):
                continue

            try:
                line = Line(line_text)
            except Exception:
                continue

            for block in line.block.gcodes:
                nx, ny, nz = cx, cy, cz

                if isinstance(block, (GCodeRapidMove, GCodeLinearMove)):
                    if hasattr(block, 'X') and block.X is not None:
                        nx = float(block.X)
                    if hasattr(block, 'Y') and block.Y is not None:
                        ny = float(block.Y)
                    if hasattr(block, 'Z') and block.Z is not None:
                        nz = float(block.Z)
                    if hasattr(block, 'F') and block.F is not None:
                        feed = float(block.F)

                    ptype = PathType.RAPID if isinstance(block, GCodeRapidMove) else PathType.CUTTING
                    segments.append(PathSegment(cx, cy, cz, nx, ny, nz, ptype, feed))
                    cx, cy, cz = nx, ny, nz

                elif isinstance(block, (GCodeArcMoveCW, GCodeArcMoveCCW)):
                    if hasattr(block, 'X') and block.X is not None:
                        nx = float(block.X)
                    if hasattr(block, 'Y') and block.Y is not None:
                        ny = float(block.Y)
                    if hasattr(block, 'Z') and block.Z is not None:
                        nz = float(block.Z)
                    if hasattr(block, 'F') and block.F is not None:
                        feed = float(block.F)

                    ptype = PathType.ARC_CW if isinstance(block, GCodeArcMoveCW) else PathType.ARC_CCW
                    segments.append(PathSegment(cx, cy, cz, nx, ny, nz, ptype, feed))
                    cx, cy, cz = nx, ny, nz

        return segments

    def get_bounds(self, segments: list[PathSegment]) -> dict[str, float]:
        """Calculate bounding box of all path segments."""
        if not segments:
            return {"x_min": 0, "x_max": 0, "y_min": 0, "y_max": 0, "z_min": 0, "z_max": 0}

        all_x = [s.x_start for s in segments] + [s.x_end for s in segments]
        all_y = [s.y_start for s in segments] + [s.y_end for s in segments]
        all_z = [s.z_start for s in segments] + [s.z_end for s in segments]
        return {
            "x_min": min(all_x), "x_max": max(all_x),
            "y_min": min(all_y), "y_max": max(all_y),
            "z_min": min(all_z), "z_max": max(all_z),
        }
