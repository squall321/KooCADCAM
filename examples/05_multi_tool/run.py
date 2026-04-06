#!/usr/bin/env python3
"""Example 05: Multi-tool machining with helical entry + trochoidal slot.

Demonstrates:
- HelicalStrategy for safe plunge entry
- TrocoidalStrategy for slot milling
- FacingStrategy for top surface
- RestMachiningStrategy for corner cleanup
- Automatic tool changes in G-code
- Full optimization + collision checking pipeline
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.cam.stock import Stock
from src.cam.tools import TOOL_LIBRARY, CuttingTool, ToolType
from src.cam.toolpath import FacingStrategy
from src.cam.toolpath_advanced import (
    HelicalStrategy, TrocoidalStrategy, RestMachiningStrategy,
)
from src.cam.gcode_writer import GcodeWriter
from src.cam.postprocessor import get_postprocessor
from src.cam.optimizer import optimize_all
from src.cam.collision import check_all


def main():
    print("=" * 60)
    print("KooCADCAM - Example 05: Multi-Tool Process")
    print("=" * 60)

    stock = Stock(120, 60, 25)

    # --- Tool 1: Face mill ---
    face_tool = TOOL_LIBRARY["flat_20mm"]
    facing = FacingStrategy()
    segs_face = facing.generate(
        tool=face_tool,
        stock_bounds=stock.bounds,
        target_z=20.0,
        depth_per_pass=5.0,
        stepover_ratio=0.5,
        feed_rate=800,
        plunge_rate=300,
        spindle_rpm=6000,
    )
    print(f"  Op 1 - Facing (D20 flat): {sum(len(s.points) for s in segs_face)} pts")

    # --- Tool 2: Helical entry + trochoidal slot ---
    slot_tool = TOOL_LIBRARY["flat_6mm"]

    helical = HelicalStrategy()
    segs_helical = helical.generate(
        tool=slot_tool,
        center_x=0, center_y=0,
        z_top=20, z_bottom=10,
        helix_radius=2.0,
        ramp_angle=3.0,
        feed_rate=300,
        spindle_rpm=10000,
    )
    print(f"  Op 2 - Helical entry (D6): {sum(len(s.points) for s in segs_helical)} pts")

    trochoid = TrocoidalStrategy()
    segs_troch = trochoid.generate(
        tool=slot_tool,
        x_start=-50, y_center=0, x_end=50,
        slot_width=12,
        z_top=20, z_bottom=10,
        depth_per_pass=2.0,
        feed_rate=400,
        spindle_rpm=10000,
    )
    print(f"  Op 3 - Trochoidal slot (D6): {sum(len(s.points) for s in segs_troch)} pts")

    # --- Tool 3: Rest machining corners ---
    rest_tool = TOOL_LIBRARY["flat_6mm"]
    rest_tool = CuttingTool("3mm Flat Endmill", ToolType.FLAT_ENDMILL, 3.0, 15.0, flutes=2, tool_number=11)

    rest = RestMachiningStrategy()
    segs_rest = rest.generate(
        tool=rest_tool,
        prev_tool_diameter=6.0,
        x_min=-50, y_min=-6, x_max=50, y_max=6,
        z_top=20, z_bottom=10,
        depth_per_pass=1.0,
        feed_rate=300,
        spindle_rpm=15000,
    )
    print(f"  Op 4 - Rest machining (D3): {sum(len(s.points) for s in segs_rest)} pts")

    # --- Combine all ---
    all_segments = segs_face + segs_helical + segs_troch + segs_rest

    # Optimize
    all_segments, report = optimize_all(all_segments, base_feed=500)
    print(f"\n  {report}")

    # Collision check
    col_report = check_all(all_segments, stock.bounds, target_z_min=0.0)
    print(f"  {col_report}")

    # G-code (FANUC)
    post = get_postprocessor("fanuc")
    writer = GcodeWriter(post)
    gcode_path = writer.save(all_segments, "output/gcode/multi_tool.nc")
    gcode = writer.generate(all_segments)
    print(f"\n  G-code: {gcode_path} ({gcode.count(chr(10))} lines)")

    # Show tool changes
    tool_changes = [l for l in gcode.splitlines() if "M6" in l or "Tool:" in l]
    print(f"  Tool changes: {len([l for l in tool_changes if 'M6' in l])}")
    for tc in tool_changes:
        print(f"    {tc.strip()}")

    print("\nDone!")


if __name__ == "__main__":
    main()
