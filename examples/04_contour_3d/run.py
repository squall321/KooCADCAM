#!/usr/bin/env python3
"""Example 04: 3D contour + scanline finishing on a dome shape.

Demonstrates:
- ContourStrategy for Z-level roughing
- ScanlineStrategy for 3D surface finishing
- Voxel simulation for material removal verification
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.cam.tools import TOOL_LIBRARY
from src.cam.toolpath_advanced import ContourStrategy, ScanlineStrategy
from src.cam.toolpath import FacingStrategy
from src.cam.gcode_writer import GcodeWriter
from src.cam.postprocessor import get_postprocessor
from src.cam.optimizer import optimize_all
from src.sim.gcode_parser import GcodeParser
from src.sim.voxel_engine import VoxelEngine, VoxelGrid, ToolShape


def main():
    print("=" * 60)
    print("KooCADCAM - Example 04: 3D Contour + Scanline Finishing")
    print("=" * 60)

    stock_x, stock_y, stock_z = 80, 80, 25
    target_base = 10.0
    target_top = 20.0

    # --- Roughing: Contour strategy ---
    rough_tool = TOOL_LIBRARY["flat_10mm"]
    contour = ContourStrategy()
    segments = contour.generate(
        tool=rough_tool,
        x_min=-30, y_min=-30, x_max=30, y_max=30,
        z_top=target_top, z_bottom=target_base,
        z_step=1.0,
        feed_rate=500,
        spindle_rpm=8000,
        taper_angle=8.0,
    )
    print(f"  Roughing: {sum(len(s.points) for s in segments)} points")

    # --- Finishing: Scanline strategy ---
    finish_tool = TOOL_LIBRARY["ball_6mm"]
    scanline = ScanlineStrategy()
    finish_segs = scanline.generate(
        tool=finish_tool,
        x_min=-30, y_min=-30, x_max=30, y_max=30,
        z_base=target_base, z_top=target_top,
        stepover_ratio=0.1,
        feed_rate=300,
        spindle_rpm=12000,
        x_resolution=0.5,
    )
    segments.extend(finish_segs)
    print(f"  Finishing: {sum(len(s.points) for s in finish_segs)} points")

    # Optimize
    segments, report = optimize_all(segments, base_feed=400)
    print(f"\n  {report}")

    # G-code (Siemens)
    post = get_postprocessor("siemens")
    writer = GcodeWriter(post)
    gcode_path = writer.save(segments, "output/gcode/contour_3d.mpf")
    gcode = writer.generate(segments)
    print(f"  G-code: {gcode_path} ({gcode.count(chr(10))} lines)")

    # --- Voxel simulation ---
    print("\n  Running voxel simulation...")
    grid = VoxelGrid.from_stock(
        -stock_x / 2, stock_x / 2,
        -stock_y / 2, stock_y / 2,
        0, stock_z,
        resolution=1.0,
    )
    parser = GcodeParser()
    parsed = parser.parse_text(gcode)

    engine = VoxelEngine(grid, rough_tool.diameter, ToolShape.FLAT)
    stats = engine.simulate_all(parsed)

    print(f"  Voxel grid: {grid.shape}")
    print(f"  Stock volume: {stats['volume_total']:.0f} mm³")
    print(f"  Removed: {stats['volume_removed']:.0f} mm³ ({stats['removal_pct']:.1f}%)")
    print(f"  Remaining: {stats['volume_remaining']:.0f} mm³")
    print(f"  Gouge voxels: {stats['gouge_voxels']}")
    print("\nDone!")


if __name__ == "__main__":
    main()
