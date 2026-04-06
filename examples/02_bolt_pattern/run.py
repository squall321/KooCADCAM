#!/usr/bin/env python3
"""Example 02: Bolt pattern plate with counterbore holes.

Demonstrates module library + modular assembly:
- Plate with 4-bolt circular pattern
- Counterbore holes for M8 socket head cap screws
- Center through-hole
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.cad.primitives import create_plate
from src.cad.modular import ModularAssembly
from src.cad.library.holes import CounterboreHole, ThroughHole
from src.cad.exporter import export_step
from src.cam.stock import Stock
from src.cam.tools import CuttingTool, ToolType, TOOL_LIBRARY
from src.cam.toolpath import DrillStrategy
from src.cam.gcode_writer import GcodeWriter
from src.cam.postprocessor import get_postprocessor
from src.cam.optimizer import optimize_all
from src.cam.collision import check_all
import math


def main():
    print("=" * 60)
    print("KooCADCAM - Example 02: Bolt Pattern Plate")
    print("=" * 60)

    # --- CAD ---
    plate = create_plate(120, 120, 15)

    # Module assembly: 4 counterbore holes in circular pattern + center hole
    assy = ModularAssembly()

    # Center through hole (D20)
    center_hole = ThroughHole(diameter=20.0, depth=15.0)
    assy.add_module(center_hole, position=(0, 0, 0))

    # 4x M8 counterbore holes on R40 bolt circle
    cbore = CounterboreHole(d_hole=8.5, d_cbore=14.0, cbore_depth=5.0, depth=15.0)
    bolt_r = 40.0
    for i in range(4):
        angle = math.radians(45 + 90 * i)
        x = bolt_r * math.cos(angle)
        y = bolt_r * math.sin(angle)
        assy.add_module(cbore, position=(x, y, 0))

    result = assy.apply_to(plate)
    step_path = export_step(result, "output/step/bolt_pattern.step")
    print(f"  STEP: {step_path}")

    # --- CAM: Drill cycle ---
    stock = Stock(120, 120, 15)
    drill = TOOL_LIBRARY["drill_8mm"]

    # Hole positions
    positions = [(0, 0)]
    for i in range(4):
        angle = math.radians(45 + 90 * i)
        positions.append((bolt_r * math.cos(angle), bolt_r * math.sin(angle)))

    drill_strat = DrillStrategy()
    segments = drill_strat.generate(
        tool=drill,
        positions=positions,
        z_top=15.0,
        z_bottom=0.0,
        peck_depth=3.0,
        feed_rate=120.0,
        spindle_rpm=2500,
    )

    # Optimize
    segments, opt_report = optimize_all(segments)
    print(f"\n  {opt_report}")

    # Collision check
    col_report = check_all(segments, stock.bounds, target_z_min=0.0)
    print(f"  {col_report}")

    # Write G-code
    post = get_postprocessor("fanuc")
    writer = GcodeWriter(post)
    gcode_path = writer.save(segments, "output/gcode/bolt_pattern.nc")
    gcode = writer.generate(segments)
    print(f"  G-code: {gcode_path} ({gcode.count(chr(10))} lines)")
    print("\nDone!")


if __name__ == "__main__":
    main()
