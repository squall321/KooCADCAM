#!/usr/bin/env python3
"""Example 06: Digital Twin - Animated Material Removal Simulation.

Full digital twin workflow:
1. Generate parametric CAD (STEP)
2. Generate optimized G-code
3. Estimate machining time
4. Animate material removal in real-time 3D
5. Show cutting statistics and time prediction
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.core.config import Config
from src.cad.primitives import create_box
from src.cad.operations import apply_fillet
from src.cad.exporter import export_step, export_stl
from src.cam.stock import Stock
from src.cam.tools import TOOL_LIBRARY
from src.cam.toolpath import FacingStrategy, PocketStrategy, FilletStrategy
from src.cam.gcode_writer import GcodeWriter
from src.cam.postprocessor import get_postprocessor
from src.cam.optimizer import optimize_all
from src.cam.collision import check_all
from src.sim.gcode_parser import GcodeParser
from src.sim.time_estimator import TimeEstimator, MachineParams, estimate_distances
from src.sim.removal_animator import RemovalAnimator, AnimatorConfig
from src.sim.voxel_engine import ToolShape


def main():
    print("=" * 60)
    print("  KooCADCAM Digital Twin")
    print("  Animated Material Removal Simulation")
    print("=" * 60)

    # === Parameters ===
    stock_x, stock_y, stock_z = 100, 100, 20
    target_x, target_y, target_z = 60, 60, 15
    fillet_r = 3.0

    # === Phase 1: CAD ===
    print("\n[1/5] Generating CAD model...")
    solid = create_box(target_x, target_y, target_z)
    solid = apply_fillet(solid, fillet_r, ">Z")
    export_step(solid, "output/step/digital_twin.step")
    export_stl(solid, "output/step/digital_twin.stl")
    print(f"  Target: {target_x}x{target_y}x{target_z}mm + R{fillet_r} fillet")

    # === Phase 2: CAM ===
    print("\n[2/5] Generating toolpaths...")
    stock = Stock(stock_x, stock_y, stock_z)
    roughing = TOOL_LIBRARY["flat_10mm"]
    finishing = TOOL_LIBRARY["ball_6mm"]
    target_bounds = {
        "x_min": -target_x / 2, "x_max": target_x / 2,
        "y_min": -target_y / 2, "y_max": target_y / 2,
    }

    segments = []

    # Facing
    segments.extend(FacingStrategy().generate(
        tool=roughing, stock_bounds=stock.bounds,
        target_z=target_z, depth_per_pass=2.5,
        stepover_ratio=0.4, feed_rate=600, plunge_rate=200, spindle_rpm=8000,
    ))

    # Pocket
    segments.extend(PocketStrategy().generate(
        tool=roughing, stock_bounds=stock.bounds, target_bounds=target_bounds,
        z_top=target_z, z_bottom=0,
        depth_per_pass=2.5, stepover_ratio=0.4,
        feed_rate=600, plunge_rate=200, spindle_rpm=8000,
    ))

    # Fillet
    segments.extend(FilletStrategy().generate(
        tool=finishing, target_bounds=target_bounds,
        target_z=target_z, fillet_radius=fillet_r,
        feed_rate=300, spindle_rpm=10000,
    ))

    # Optimize
    segments, opt_report = optimize_all(segments, base_feed=600)
    print(f"  {opt_report}")

    # Collision check
    col_report = check_all(segments, stock.bounds)
    print(f"  {col_report}")

    # G-code
    post = get_postprocessor("fanuc")
    writer = GcodeWriter(post)
    gcode = writer.generate(segments)
    writer.save(segments, "output/gcode/digital_twin.nc")
    print(f"  G-code: {gcode.count(chr(10))} lines")

    # === Phase 3: Time Estimation ===
    print("\n[3/5] Estimating machining time...")
    parser = GcodeParser()
    parsed = parser.parse_text(gcode)

    machine = MachineParams(
        max_rapid_rate=15000, max_accel=500,
        tool_change_time=8, spindle_ramp_time=2,
    )
    estimator = TimeEstimator(machine)
    time_est = estimator.estimate(parsed, num_tool_changes=1)
    print(f"\n{time_est}")

    dist_stats = estimate_distances(parsed)
    print(f"\n  {dist_stats}")

    # === Phase 4: Animated Simulation ===
    print("\n[4/5] Starting material removal simulation...")
    print("  (Close the 3D window when done viewing)\n")

    config = AnimatorConfig(
        voxel_resolution=1.5,    # 1.5mm voxels for speed
        update_interval=10,      # update every 10 moves
        show_toolpath_trail=True,
    )
    animator = RemovalAnimator(
        stock_dims=(stock_x, stock_y, stock_z),
        tool_diameter=roughing.diameter,
        tool_shape=ToolShape.FLAT,
        config=config,
    )

    def on_progress(current, total, stats):
        if current % 100 == 0:
            pct = 100 * current / total
            print(f"  Simulating: {pct:.0f}% ({current}/{total})", end="\r")

    sim_stats = animator.run(gcode, on_progress=on_progress)

    # === Phase 5: Summary ===
    print("\n\n[5/5] Digital Twin Summary")
    print("=" * 60)
    print(f"  Stock:     {stock_x}x{stock_y}x{stock_z} mm")
    print(f"  Target:    {target_x}x{target_y}x{target_z} mm + R{fillet_r}")
    print(f"  Tools:     {roughing.name}, {finishing.name}")
    print(f"  G-code:    {gcode.count(chr(10))} lines ({post.name})")
    print(f"  Cycle time: {time_est.format_time(time_est.total_time)}")
    print(f"  Cutting:    {time_est.format_time(time_est.cutting_time)} ({time_est.cutting_pct:.0f}%)")
    print(f"  Material removed: {sim_stats.get('volume_removed', 0):.0f} mm³ "
          f"({sim_stats.get('removal_pct', 0):.1f}%)")
    print(f"  Cutting distance: {dist_stats.total_cutting_distance:.0f} mm")
    print("=" * 60)
    print("\nDone!")


if __name__ == "__main__":
    main()
