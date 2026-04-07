"""Automatic CAM process planner.

Analyzes CAD geometry (target shape vs stock) and automatically
determines the machining operations, tool selection, and toolpath
strategies needed to produce the part.

This is the core of CAD→CAM automation: given any shape, generate G-code.

v2 improvements over v1:
- Step 1: BREP face/edge analysis (BrepAnalyzer) replaces bounding-box heuristics
- Step 3: Shapely contour-parallel pocket (PocketPlanner) replaces rectangular zigzag
- Step 5: Cutting params database (lookup_params) replaces hardcoded Al values
- Step 6: Helical/ramp approach paths (apply_approach_to_segments)
- Step 4: Cutter radius compensation for profiles (apply_crc_to_profiles)
- Step 7: Verification report (estimate_removal_volume + MachiningVerifier)

Usage:
    from src.cam.auto_cam import AutoCAM

    cam = AutoCAM(stock_dims=(100, 100, 20), material="Steel 1045")
    cam.load_target_step("my_part.step")
    # or
    cam.load_target_solid(cadquery_solid)

    result = cam.plan_and_generate()
    print(result.gcode)
    result.save("output.nc")
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cadquery as cq
import numpy as np

from .stock import Stock
from .tools import CuttingTool, ToolType, TOOL_LIBRARY
from .toolpath import (
    ToolpathSegment, FacingStrategy, PocketStrategy,
    ProfileStrategy, FilletStrategy, DrillStrategy,
)
from .toolpath_advanced import (
    HelicalStrategy, SpiralPocketStrategy, ContourStrategy,
    ScanlineStrategy, RestMachiningStrategy,
)
from .gcode_writer import GcodeWriter
from .postprocessor import get_postprocessor
from .optimizer import optimize_all
from .collision import check_all

# ── New v2 modules ────────────────────────────────────────────────
from .feature_recognition import BrepAnalyzer, BrepAnalysisResult
from .pocket_planner import PocketPlanner
from .cutting_params_db import lookup_params, CutParams
from .approach import apply_approach_to_segments
from .crc import apply_crc_to_profiles
from .verification import estimate_removal_volume


@dataclass
class ProcessPlan:
    """Complete machining process plan."""
    features_summary: str = ""
    operations: list[dict[str, Any]] = field(default_factory=list)
    tools_needed: list[CuttingTool] = field(default_factory=list)
    brep_analysis: BrepAnalysisResult | None = None
    material_removal: dict[str, float] | None = None

    def summary(self) -> str:
        lines = ["Process Plan Summary", "=" * 50]
        if self.brep_analysis:
            lines.append(self.brep_analysis.summary())
            lines.append("")
        for i, op in enumerate(self.operations):
            strat = op["strategy"]
            if strat == "_pocket_planner":
                strat_name = "PocketPlanner (Shapely)"
            else:
                strat_name = strat.__class__.__name__
            lines.append(f"  Op {i+1}: {strat_name} "
                         f"(T{op['tool'].tool_number} {op['tool'].name})")
        lines.append(f"  Total operations: {len(self.operations)}")
        lines.append(f"  Tools needed: {len(self.tools_needed)}")
        if self.material_removal:
            mr = self.material_removal
            lines.append(
                f"  Material removal: {mr['removal_vol']:.0f} mm³ "
                f"({mr['removal_pct']:.1f}% of stock)"
            )
        return "\n".join(lines)


@dataclass
class AutoCAMResult:
    """Result of automatic CAM generation."""
    gcode: str = ""
    gcode_path: Path | None = None
    segments: list[ToolpathSegment] = field(default_factory=list)
    plan: ProcessPlan | None = None
    collision_report: Any = None
    optimization_report: Any = None
    verification_report: Any = None   # VerificationReport (if voxel sim run separately)

    def save(self, path: str | Path, post_name: str = "fanuc") -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.gcode)
        self.gcode_path = path
        return path


class AutoCAM:
    """Automatic CAM process planner and G-code generator (v2).

    Takes any CAD geometry and automatically:
    1. Analyzes BREP faces/edges (BrepAnalyzer)
    2. Recognizes features: pockets, holes, fillets, freeform surfaces
    3. Selects appropriate tools and cutting parameters from database
    4. Plans machining operations in optimal order
    5. Generates Shapely-offset pocket toolpaths
    6. Applies helical/ramp entry moves
    7. Applies cutter radius compensation to profiles
    8. Optimizes rapid moves
    9. Checks collisions
    10. Generates G-code

    Supports:
    - Prismatic parts (boxes, plates, brackets)
    - Arbitrary-shape pockets (Shapely contour-parallel)
    - Parts with holes (through/blind)
    - Parts with fillets and chamfers
    - 3D contoured surfaces (domes, ramps)
    - All common materials with correct cutting parameters
    """

    def __init__(
        self,
        stock_dims: tuple[float, float, float] = (100, 100, 20),
        material: str = "Aluminum 6061",
        post_processor: str = "fanuc",
        approach_strategy: str = "ramp",   # "ramp", "helical", "none"
        apply_crc: bool = True,
    ) -> None:
        self.stock = Stock(*stock_dims, material=material)
        self.stock_dims = stock_dims
        self.material = material
        self.post_name = post_processor
        self.approach_strategy = approach_strategy
        self.apply_crc = apply_crc

        # Auto-selected tools (can be overridden)
        self.roughing_tool: CuttingTool | None = None
        self.finishing_tool: CuttingTool | None = None
        self.drill_tool: CuttingTool | None = None

        # Cutting params (loaded from DB after tool selection)
        self._cut_params: CutParams | None = None

        self._target_solid: cq.Workplane | None = None
        self._target_bb: dict[str, float] | None = None
        self._brep_analysis: BrepAnalysisResult | None = None

    # ─── Input ────────────────────────────────────────────────────

    def load_target_step(self, path: str | Path) -> None:
        """Load target part from STEP file."""
        path = Path(path)
        result = cq.importers.importStep(str(path))
        self._target_solid = cq.Workplane("XY").add(result)
        self._analyze_target()

    def load_target_solid(self, solid: cq.Workplane) -> None:
        """Load target part from CadQuery workplane."""
        self._target_solid = solid
        self._analyze_target()

    def _analyze_target(self) -> None:
        """Full BREP analysis of target geometry."""
        bb = self._target_solid.val().BoundingBox()
        self._target_bb = {
            "x_min": bb.xmin, "x_max": bb.xmax,
            "y_min": bb.ymin, "y_max": bb.ymax,
            "z_min": bb.zmin, "z_max": bb.zmax,
            "lx": bb.xmax - bb.xmin,
            "ly": bb.ymax - bb.ymin,
            "lz": bb.zmax - bb.zmin,
        }
        # BREP analysis (Step 1)
        try:
            analyzer = BrepAnalyzer(self._target_solid)
            self._brep_analysis = analyzer.analyze()
        except Exception as e:
            self._brep_analysis = None

    # ─── Tool selection ───────────────────────────────────────────

    def _select_tools(self) -> None:
        """Auto-select tools based on part geometry."""
        bb = self._target_bb
        min_feature = min(bb["lx"], bb["ly"]) / 4

        if min_feature >= 20:
            self.roughing_tool = TOOL_LIBRARY["flat_20mm"]
        elif min_feature >= 10:
            self.roughing_tool = TOOL_LIBRARY["flat_10mm"]
        else:
            self.roughing_tool = TOOL_LIBRARY["flat_6mm"]

        if min_feature >= 10:
            self.finishing_tool = TOOL_LIBRARY["ball_6mm"]
        else:
            self.finishing_tool = TOOL_LIBRARY["ball_3mm"]

        self.drill_tool = TOOL_LIBRARY["drill_5mm"]

        # Load cutting params from DB (Step 5)
        self._cut_params = lookup_params(
            self.material,
            self.roughing_tool.tool_type,
            self.roughing_tool.diameter,
        )

    @property
    def _cp(self) -> CutParams:
        """Current cutting parameters."""
        if self._cut_params is None:
            self._select_tools()
        return self._cut_params

    # ─── Process planning ─────────────────────────────────────────

    def _plan_operations(self) -> ProcessPlan:
        """Build full process plan using BREP analysis."""
        plan = ProcessPlan()
        bb = self._target_bb
        stock_bb = self.stock.bounds
        cp = self._cp
        brep = self._brep_analysis

        target_bounds = {
            "x_min": bb["x_min"], "x_max": bb["x_max"],
            "y_min": bb["y_min"], "y_max": bb["y_max"],
        }

        # ── Op 1: Facing (if stock taller than part) ──────────────
        if self.stock_dims[2] > bb["lz"] + 0.1:
            plan.operations.append({
                "strategy": FacingStrategy(),
                "tool": self.roughing_tool,
                "kwargs": {
                    "tool": self.roughing_tool,
                    "stock_bounds": stock_bb,
                    "target_z": bb["z_max"],
                    "depth_per_pass": cp.depth_per_pass,
                    "stepover_ratio": cp.stepover_ratio,
                    "feed_rate": cp.feed_rate,
                    "plunge_rate": cp.plunge_rate,
                    "spindle_rpm": cp.spindle_rpm,
                },
            })

        # ── Op 2: Pockets (BREP-detected or bounding-box fallback) ─
        pockets_planned = False
        if brep and brep.has_pockets:
            for pocket in brep.pockets:
                plan.operations.append({
                    "strategy": "_pocket_planner",
                    "tool": self.roughing_tool,
                    "_pocket": pocket,
                    "kwargs": {},  # handled in generate step
                })
            pockets_planned = True

        if not pockets_planned:
            # Fallback: clear material around part using stock vs part XY
            stock_area = self.stock_dims[0] * self.stock_dims[1]
            part_area = bb["lx"] * bb["ly"]
            if part_area < stock_area * 0.95:
                plan.operations.append({
                    "strategy": PocketStrategy(),
                    "tool": self.roughing_tool,
                    "kwargs": {
                        "tool": self.roughing_tool,
                        "stock_bounds": stock_bb,
                        "target_bounds": target_bounds,
                        "z_top": bb["z_max"],
                        "z_bottom": bb["z_min"],
                        "depth_per_pass": cp.depth_per_pass,
                        "stepover_ratio": cp.stepover_ratio,
                        "feed_rate": cp.feed_rate,
                        "plunge_rate": cp.plunge_rate,
                        "spindle_rpm": cp.spindle_rpm,
                    },
                })

        # ── Op 3: Holes (BREP-detected) ────────────────────────────
        if brep and brep.has_holes:
            # Select drill closest to hole diameter
            for hole in brep.holes:
                drill = self._select_drill(hole.diameter)
                if drill is None:
                    continue
                drill_cp = lookup_params(self.material, ToolType.DRILL, drill.diameter)
                plan.operations.append({
                    "strategy": DrillStrategy(),
                    "tool": drill,
                    "kwargs": {
                        "tool": drill,
                        "positions": [(hole.x, hole.y)],
                        "z_top": hole.z_top,
                        "z_bottom": hole.z_bottom,
                        "peck_depth": max(1.0, drill.diameter * 0.5),
                        "feed_rate": drill_cp.feed_rate,
                        "spindle_rpm": drill_cp.spindle_rpm,
                    },
                })

        # ── Op 4: Fillets/chamfers ─────────────────────────────────
        if brep and brep.has_fillets:
            for fillet in brep.fillets:
                finish_cp = lookup_params(
                    self.material,
                    self.finishing_tool.tool_type,
                    self.finishing_tool.diameter,
                )
                plan.operations.append({
                    "strategy": FilletStrategy(),
                    "tool": self.finishing_tool,
                    "kwargs": {
                        "tool": self.finishing_tool,
                        "target_bounds": target_bounds,
                        "target_z": bb["z_max"],
                        "fillet_radius": fillet.radius,
                        "feed_rate": finish_cp.finish_feed,
                        "spindle_rpm": finish_cp.finish_rpm,
                    },
                })

        # ── Op 5: 3D freeform surfaces ─────────────────────────────
        has_freeform = brep.has_freeform if brep else False
        if not has_freeform:
            # Fallback: check for any curved BREP edges
            try:
                edges = self._target_solid.val().Edges()
                curved = [e for e in edges if e.geomType() != "LINE"]
                has_freeform = bool(curved)
            except Exception:
                pass

        if has_freeform:
            # Roughing: Z-level contour
            plan.operations.append({
                "strategy": ContourStrategy(),
                "tool": self.roughing_tool,
                "kwargs": {
                    "tool": self.roughing_tool,
                    "x_min": bb["x_min"], "y_min": bb["y_min"],
                    "x_max": bb["x_max"], "y_max": bb["y_max"],
                    "z_top": bb["z_max"], "z_bottom": bb["z_min"],
                    "z_step": cp.depth_per_pass,
                    "feed_rate": cp.feed_rate,
                    "spindle_rpm": cp.spindle_rpm,
                },
            })
            # Finishing: scanline
            finish_cp = lookup_params(
                self.material,
                self.finishing_tool.tool_type,
                self.finishing_tool.diameter,
            )
            plan.operations.append({
                "strategy": ScanlineStrategy(),
                "tool": self.finishing_tool,
                "kwargs": {
                    "tool": self.finishing_tool,
                    "x_min": bb["x_min"], "y_min": bb["y_min"],
                    "x_max": bb["x_max"], "y_max": bb["y_max"],
                    "z_base": bb["z_min"], "z_top": bb["z_max"],
                    "stepover_ratio": finish_cp.finish_stepover,
                    "feed_rate": finish_cp.finish_feed,
                    "spindle_rpm": finish_cp.finish_rpm,
                },
            })

        # ── Print undercut warning ─────────────────────────────────
        if brep and brep.has_undercuts:
            print(f"\n  ⚠  {brep.undercut_warning}")

        # ── Collect unique tools ───────────────────────────────────
        tool_nums: set[int] = set()
        for op in plan.operations:
            t = op["tool"]
            if t.tool_number not in tool_nums:
                plan.tools_needed.append(t)
                tool_nums.add(t.tool_number)

        plan.brep_analysis = brep
        plan.material_removal = estimate_removal_volume(
            self.stock_dims, self._target_solid
        )
        return plan

    def _select_drill(self, hole_diameter: float) -> CuttingTool | None:
        """Select drill closest to hole diameter from library."""
        drills = {
            k: v for k, v in TOOL_LIBRARY.items()
            if v.tool_type == ToolType.DRILL
        }
        if not drills:
            return None
        return min(drills.values(), key=lambda t: abs(t.diameter - hole_diameter))

    # ─── Toolpath generation ──────────────────────────────────────

    def _generate_toolpaths(self, plan: ProcessPlan) -> list[ToolpathSegment]:
        """Generate all toolpath segments from the plan."""
        all_segments: list[ToolpathSegment] = []
        cp = self._cp
        bb = self._target_bb

        for op in plan.operations:
            try:
                if op["strategy"] == "_pocket_planner":
                    # Step 3: Shapely-offset pocket for BREP-detected pocket
                    pocket = op["_pocket"]
                    planner = PocketPlanner(
                        tool=self.roughing_tool,
                        stepover_ratio=cp.stepover_ratio,
                        depth_per_pass=cp.depth_per_pass,
                        feed_rate=cp.feed_rate,
                        plunge_rate=cp.plunge_rate,
                        spindle_rpm=cp.spindle_rpm,
                    )
                    segs = planner.plan_rect(
                        pocket.x_min, pocket.x_max,
                        pocket.y_min, pocket.y_max,
                        pocket.z_top, pocket.z_bottom,
                        islands=[
                            [(isl["x_min"], isl["y_min"]),
                             (isl["x_max"], isl["y_min"]),
                             (isl["x_max"], isl["y_max"]),
                             (isl["x_min"], isl["y_max"])]
                            for isl in pocket.islands
                        ] if pocket.islands else None,
                    )
                else:
                    strategy = op["strategy"]
                    segs = strategy.generate(**op["kwargs"])

                all_segments.extend(segs)
            except Exception as e:
                print(f"  Warning: operation failed ({e}), skipping")
                continue

        return all_segments

    # ─── Main entry point ─────────────────────────────────────────

    def plan_and_generate(
        self,
        optimize: bool = True,
        check_collision: bool = True,
    ) -> AutoCAMResult:
        """Full automatic CAM pipeline (v2).

        Returns AutoCAMResult with G-code and metadata.
        """
        if self._target_solid is None:
            raise ValueError(
                "No target loaded. Call load_target_step() or load_target_solid() first."
            )

        if self.roughing_tool is None:
            self._select_tools()

        # Process planning (uses BREP analysis)
        plan = self._plan_operations()

        # Generate toolpaths
        all_segments = self._generate_toolpaths(plan)

        result = AutoCAMResult(plan=plan, segments=all_segments)

        # Step 6: Apply approach/entry moves
        if self.approach_strategy != "none":
            try:
                all_segments = apply_approach_to_segments(
                    all_segments, strategy=self.approach_strategy
                )
                result.segments = all_segments
            except Exception:
                pass

        # Step 4: Apply cutter radius compensation to profiles
        if self.apply_crc:
            try:
                all_segments = apply_crc_to_profiles(all_segments)
                result.segments = all_segments
            except Exception:
                pass

        # Optimize
        if optimize:
            try:
                all_segments, opt_report = optimize_all(
                    all_segments, base_feed=self._cp.feed_rate
                )
                result.segments = all_segments
                result.optimization_report = opt_report
            except Exception:
                pass

        # Collision check
        if check_collision:
            try:
                col_report = check_all(all_segments, self.stock.bounds)
                result.collision_report = col_report
            except Exception:
                pass

        # Generate G-code
        post = get_postprocessor(self.post_name)
        writer = GcodeWriter(post)
        result.gcode = writer.generate(all_segments)

        return result
