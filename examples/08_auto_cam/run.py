#!/usr/bin/env python3
"""Example 08: Automatic CAM for arbitrary CAD shapes.

Shows how AutoCAM automatically analyzes any shape and generates G-code.
No manual toolpath programming needed - just give it a CAD model.

Demonstrates 4 different shapes, all auto-processed:
1. Simple plate with fillet
2. Bracket with holes
3. Stepped block with chamfers
4. Domed surface
"""

import sys, math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import cadquery as cq
from src.cad.primitives import create_box
from src.cad.operations import apply_fillet, apply_chamfer, boolean_cut
from src.cad.exporter import export_step
from src.cam.auto_cam import AutoCAM


def make_plate_with_fillet():
    """Simple plate 60x60x15 with R3 fillet on top edges."""
    solid = create_box(60, 60, 15)
    solid = apply_fillet(solid, 3.0, ">Z")
    return solid, "Plate with R3 Fillet"


def make_bracket_with_holes():
    """L-bracket with 4 bolt holes."""
    # Base plate
    base = cq.Workplane("XY").box(80, 60, 10, centered=(True, True, False))
    # Vertical wall
    wall = cq.Workplane("XY").transformed(offset=(0, -25, 10)).box(80, 10, 30, centered=(True, True, False))
    bracket = base.union(wall)
    # 4 holes in base
    for x, y in [(-25, 10), (25, 10), (-25, -10), (25, -10)]:
        hole = cq.Workplane("XY").transformed(offset=(x, y, 0)).circle(4).extrude(10)
        bracket = bracket.cut(hole)
    # Fillet at base-wall junction
    bracket = bracket.edges("|X").edges(">Z").fillet(3)
    return bracket, "Bracket with 4 Holes"


def make_stepped_block():
    """Stepped block with 3 levels + chamfers."""
    # Bottom level
    bottom = cq.Workplane("XY").box(70, 70, 8, centered=(True, True, False))
    # Middle level
    mid = cq.Workplane("XY").transformed(offset=(0, 0, 8)).box(50, 50, 7, centered=(True, True, False))
    # Top level
    top = cq.Workplane("XY").transformed(offset=(0, 0, 15)).box(30, 30, 5, centered=(True, True, False))
    stepped = bottom.union(mid).union(top)
    # Chamfer top edges
    stepped = stepped.edges(">Z").chamfer(2)
    return stepped, "Stepped Block with Chamfer"


def make_dome():
    """Domed surface (hemisphere on a plate)."""
    base = cq.Workplane("XY").box(60, 60, 5, centered=(True, True, False))
    dome = cq.Workplane("XY").transformed(offset=(0, 0, 5)).sphere(25)
    # Cut dome to only keep top half above base
    cutter = cq.Workplane("XY").box(80, 80, 30, centered=(True, True, False)).translate((0, 0, -30))
    dome = dome.cut(cutter)
    result = base.union(dome)
    return result, "Dome on Plate"


def process_shape(solid, name, stock_dims, index):
    """Run AutoCAM on a shape and report results."""
    print(f"\n{'='*60}")
    print(f"  Shape {index}: {name}")
    print(f"  Stock: {stock_dims[0]}x{stock_dims[1]}x{stock_dims[2]} mm")
    print(f"{'='*60}")

    # Export STEP
    step_path = f"output/step/auto_{index}_{name.lower().replace(' ', '_')}.step"
    export_step(solid, step_path)
    print(f"  STEP: {step_path}")

    # Auto CAM
    cam = AutoCAM(stock_dims=stock_dims, post_processor="fanuc")
    cam.load_target_solid(solid)
    result = cam.plan_and_generate()

    # Report
    print(f"\n  Process Plan:")
    print(f"  {result.plan.summary()}")
    print(f"\n  G-code: {len(result.gcode.splitlines())} lines")
    print(f"  Segments: {sum(len(s.points) for s in result.segments)} points")

    if result.optimization_report:
        print(f"  {result.optimization_report}")
    if result.collision_report:
        print(f"  Collisions: {result.collision_report.error_count} errors, "
              f"{result.collision_report.warning_count} warnings")

    # Save G-code
    gcode_path = f"output/gcode/auto_{index}.nc"
    result.save(gcode_path)
    print(f"  G-code saved: {gcode_path}")

    return result


def main():
    print("=" * 60)
    print("  KooCADCAM - Automatic CAM for Arbitrary Shapes")
    print("  No manual toolpath programming needed!")
    print("=" * 60)

    shapes = [
        (make_plate_with_fillet, (100, 100, 20)),
        (make_bracket_with_holes, (100, 80, 45)),
        (make_stepped_block, (90, 90, 25)),
        (make_dome, (80, 80, 35)),
    ]

    for i, (make_fn, stock_dims) in enumerate(shapes, 1):
        solid, name = make_fn()
        process_shape(solid, name, stock_dims, i)

    print(f"\n{'='*60}")
    print(f"  All 4 shapes processed automatically!")
    print(f"  STEP files: output/step/auto_*.step")
    print(f"  G-code files: output/gcode/auto_*.nc")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
