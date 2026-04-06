#!/usr/bin/env python3
"""Example 03: Grid array of pockets with spiral clearing.

Demonstrates:
- Grid pattern from modular assembly
- SpiralPocketStrategy for efficient pocket clearing
- Toolpath optimization pipeline
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.cad.primitives import create_plate
from src.cad.modular import ModularAssembly
from src.cad.library.pockets import RectPocket
from src.cad.exporter import export_step
from src.cam.stock import Stock
from src.cam.tools import TOOL_LIBRARY
from src.cam.toolpath_advanced import SpiralPocketStrategy
from src.cam.gcode_writer import GcodeWriter
from src.cam.postprocessor import get_postprocessor
from src.cam.optimizer import optimize_all


def main():
    print("=" * 60)
    print("KooCADCAM - Example 03: Pocket Array (3x2 Grid)")
    print("=" * 60)

    # --- CAD: 3x2 grid of rectangular pockets ---
    plate = create_plate(150, 100, 20)
    pocket = RectPocket(lx=30, ly=25, depth=10, corner_radius=3)

    assy = ModularAssembly()
    assy.grid_pattern(
        pocket,
        nx=3, ny=2,
        sx=45, sy=40,
        origin=(-45, -20, 10),  # on top surface
    )
    result = assy.apply_to(plate)
    step_path = export_step(result, "output/step/pocket_array.step")
    print(f"  STEP: {step_path}")

    # --- CAM: Spiral pocket strategy for each pocket ---
    tool = TOOL_LIBRARY["flat_6mm"]
    spiral = SpiralPocketStrategy()
    all_segments = []

    for ix in range(3):
        for iy in range(2):
            cx = -45 + ix * 45
            cy = -20 + iy * 40
            segs = spiral.generate(
                tool=tool,
                x_min=cx - 15, y_min=cy - 12.5,
                x_max=cx + 15, y_max=cy + 12.5,
                z_top=20, z_bottom=10,
                depth_per_pass=2.0,
                stepover_ratio=0.35,
                feed_rate=600,
                plunge_rate=200,
                spindle_rpm=10000,
            )
            all_segments.extend(segs)

    # Optimize
    all_segments, report = optimize_all(all_segments, base_feed=600)
    print(f"\n  {report}")

    # G-code (Haas)
    post = get_postprocessor("haas")
    writer = GcodeWriter(post)
    gcode_path = writer.save(all_segments, "output/gcode/pocket_array.nc")
    gcode = writer.generate(all_segments)
    print(f"  G-code: {gcode_path} ({gcode.count(chr(10))} lines)")
    print("\nDone!")


if __name__ == "__main__":
    main()
