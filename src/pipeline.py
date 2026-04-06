"""Pipeline orchestrator: end-to-end CAD → G-code → Visualization flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core.config import Config
from .core.events import EventBus
from .cad.primitives import create_box
from .cad.operations import apply_fillet
from .cad.exporter import export_step, export_stl
from .cam.stock import Stock
from .cam.tools import CuttingTool, ToolType
from .cam.toolpath import (
    FacingStrategy, PocketStrategy, ProfileStrategy, FilletStrategy,
    ToolpathSegment,
)
from .cam.gcode_writer import GcodeWriter
from .cam.postprocessor import get_postprocessor
from .sim.gcode_parser import GcodeParser, PathSegment


@dataclass
class PipelineResult:
    """Result container for a pipeline run."""
    step_path: Path | None = None
    stl_path: Path | None = None
    gcode_path: Path | None = None
    gcode_text: str = ""
    toolpath_segments: list[ToolpathSegment] | None = None
    parsed_paths: list[PathSegment] | None = None
    image_path: Path | None = None


class Pipeline:
    """End-to-end CAD/CAM pipeline.

    Usage:
        config = Config.from_yaml("config.yaml")
        pipeline = Pipeline(config)
        result = pipeline.run()
    """

    def __init__(self, config: Config, bus: EventBus | None = None) -> None:
        self.config = config
        self.bus = bus or EventBus()

    def run(self) -> PipelineResult:
        """Execute the full pipeline: CAD → CAM → Visualization."""
        result = PipelineResult()

        # --- Phase 1: CAD ---
        self.bus.emit("phase_start", "cad")
        solid = self._generate_cad()
        self.bus.emit("model_updated", solid)

        # Export
        step_path = Path(self.config.get("output", "step"))
        stl_path = step_path.with_suffix(".stl")
        result.step_path = export_step(solid, step_path)
        result.stl_path = export_stl(solid, stl_path)
        self.bus.emit("phase_complete", "cad")

        # --- Phase 2: CAM ---
        self.bus.emit("phase_start", "cam")
        segments = self._generate_toolpaths()
        result.toolpath_segments = segments
        self.bus.emit("toolpath_generated", segments)

        # Write G-code
        post_name = self.config.get("postprocessor", default="fanuc")
        post = get_postprocessor(post_name)
        writer = GcodeWriter(post)
        gcode_path = Path(self.config.get("output", "gcode"))
        result.gcode_text = writer.generate(segments)
        result.gcode_path = writer.save(segments, gcode_path)
        self.bus.emit("gcode_ready", result.gcode_text)
        self.bus.emit("phase_complete", "cam")

        # --- Phase 3: Parse for visualization ---
        self.bus.emit("phase_start", "sim")
        parser = GcodeParser()
        result.parsed_paths = parser.parse_text(result.gcode_text)
        self.bus.emit("phase_complete", "sim")

        return result

    def _generate_cad(self):
        """Generate the target CAD solid."""
        target = self.config["target"]
        solid = create_box(target["x"], target["y"], target["z"])
        fillet_r = target.get("fillet_radius", 0)
        if fillet_r > 0:
            solid = apply_fillet(solid, fillet_r, ">Z")
        return solid

    def _generate_toolpaths(self) -> list[ToolpathSegment]:
        """Generate all toolpath segments."""
        stock_cfg = self.config["stock"]
        target_cfg = self.config["target"]
        cutting = self.config["cutting"]
        tools_cfg = self.config.get("tools", default=[])

        stock = Stock(stock_cfg["x"], stock_cfg["y"], stock_cfg["z"], stock_cfg.get("material", ""))
        target_bounds = {
            "x_min": -target_cfg["x"] / 2, "x_max": target_cfg["x"] / 2,
            "y_min": -target_cfg["y"] / 2, "y_max": target_cfg["y"] / 2,
        }

        # Build tool instances
        roughing_tool = None
        finishing_tool = None
        for t in tools_cfg:
            tool = CuttingTool.from_dict(t)
            if tool.tool_type == ToolType.FLAT_ENDMILL and roughing_tool is None:
                roughing_tool = tool
            elif tool.tool_type == ToolType.BALL_ENDMILL and finishing_tool is None:
                finishing_tool = tool

        if roughing_tool is None:
            roughing_tool = CuttingTool("10mm Flat Endmill", ToolType.FLAT_ENDMILL, 10.0, 30.0, flutes=3)
        if finishing_tool is None:
            finishing_tool = CuttingTool("6mm Ball Endmill", ToolType.BALL_ENDMILL, 6.0, 20.0, flutes=2, tool_number=2)

        segments: list[ToolpathSegment] = []

        # 1. Facing
        facing = FacingStrategy()
        segments.extend(facing.generate(
            tool=roughing_tool,
            stock_bounds=stock.bounds,
            target_z=target_cfg["z"],
            depth_per_pass=cutting["depth_per_pass"],
            stepover_ratio=cutting["stepover_ratio"],
            feed_rate=cutting["feed_rate"],
            plunge_rate=cutting["plunge_rate"],
            spindle_rpm=cutting["spindle_rpm"],
        ))

        # 2. Pocket clearing
        pocket = PocketStrategy()
        segments.extend(pocket.generate(
            tool=roughing_tool,
            stock_bounds=stock.bounds,
            target_bounds=target_bounds,
            z_top=target_cfg["z"],
            z_bottom=0,
            depth_per_pass=cutting["depth_per_pass"],
            stepover_ratio=cutting["stepover_ratio"],
            feed_rate=cutting["feed_rate"],
            plunge_rate=cutting["plunge_rate"],
            spindle_rpm=cutting["spindle_rpm"],
        ))

        # 3. Fillet
        fillet_r = target_cfg.get("fillet_radius", 0)
        if fillet_r > 0:
            fillet = FilletStrategy()
            segments.extend(fillet.generate(
                tool=finishing_tool,
                target_bounds=target_bounds,
                target_z=target_cfg["z"],
                fillet_radius=fillet_r,
                feed_rate=cutting["feed_rate"] * 0.6,
                spindle_rpm=cutting["spindle_rpm"],
            ))

        return segments
