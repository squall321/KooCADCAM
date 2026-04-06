"""G-code generation from toolpath data via post-processor."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .toolpath import MoveType, ToolpathSegment

if TYPE_CHECKING:
    from .postprocessor.base import PostProcessor


class GcodeWriter:
    """Converts toolpath segments to G-code text using a post-processor.

    Usage:
        from src.cam.postprocessor.fanuc import FanucPost
        writer = GcodeWriter(FanucPost())
        gcode = writer.generate(segments)
        writer.save(segments, "output.nc")
    """

    def __init__(self, post_processor: PostProcessor) -> None:
        self.post = post_processor

    def generate(self, segments: list[ToolpathSegment], program_name: str = "O0001") -> str:
        """Generate complete G-code string from toolpath segments."""
        lines: list[str] = []

        # Header
        lines.extend(self.post.format_header(program_name))

        current_tool = None
        for seg in segments:
            # Tool change if needed
            if current_tool is None or current_tool.tool_number != seg.tool.tool_number:
                if current_tool is not None:
                    lines.extend(self.post.format_spindle_off())
                lines.extend(self.post.format_tool_change(seg.tool))
                lines.extend(self.post.format_spindle_on(seg.spindle_rpm))
                if seg.coolant:
                    lines.extend(self.post.format_coolant_on())
                current_tool = seg.tool

            # Comment for operation name
            lines.append(self.post.format_comment(f"--- {seg.name} ---"))

            # Toolpath moves
            prev_feed = None
            for pt in seg.points:
                if pt.move_type == MoveType.RAPID:
                    lines.append(self.post.format_rapid(pt.x, pt.y, pt.z))
                elif pt.move_type == MoveType.LINEAR:
                    feed = pt.feed_rate if pt.feed_rate != prev_feed else None
                    lines.append(self.post.format_linear(pt.x, pt.y, pt.z, feed))
                    prev_feed = pt.feed_rate
                elif pt.move_type == MoveType.ARC_CW:
                    lines.append(self.post.format_arc_cw(
                        pt.x, pt.y, pt.z, pt.i, pt.j, pt.k, pt.feed_rate
                    ))
                elif pt.move_type == MoveType.ARC_CCW:
                    lines.append(self.post.format_arc_ccw(
                        pt.x, pt.y, pt.z, pt.i, pt.j, pt.k, pt.feed_rate
                    ))

        # End
        if current_tool is not None:
            lines.extend(self.post.format_coolant_off())
            lines.extend(self.post.format_spindle_off())
        lines.extend(self.post.format_footer())

        return "\n".join(lines) + "\n"

    def save(
        self,
        segments: list[ToolpathSegment],
        path: str | Path,
        program_name: str = "O0001",
    ) -> Path:
        """Generate and save G-code to file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        gcode = self.generate(segments, program_name)
        path.write_text(gcode)
        return path
