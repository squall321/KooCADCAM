#!/usr/bin/env python3
"""Example 09: Truly arbitrary shapes → AutoCAM.

Tests AutoCAM v2 on shapes that go beyond simple boxes:
1. Wedge (경사면) — angled surface
2. Round plate with circular pockets — non-rectangular pocket
3. Phone case mold — loft + pocket + holes
4. Turbine blade blank — swept airfoil profile
5. Mounting flange — circular with bolt pattern + keyway
6. Topology test — irregular shape from boolean operations
"""

import sys, math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import cadquery as cq
from src.cam.auto_cam import AutoCAM


def make_wedge():
    """Wedge: tapered block (경사면 형상).
    100x60 base, front height 30mm, back height 10mm.
    """
    pts = [
        (0, 0),    # front-bottom
        (100, 0),  # back-bottom
        (100, 10), # back-top (low)
        (0, 30),   # front-top (high)
    ]
    solid = (
        cq.Workplane("XZ")
        .polyline(pts).close()
        .extrude(60)
        .translate((-50, -30, 0))
    )
    return solid, "Wedge (Tapered Block)"


def make_round_plate_with_pockets():
    """Round plate D=80, thickness=15 with 3 circular pockets."""
    plate = (
        cq.Workplane("XY")
        .circle(40)
        .extrude(15)
    )
    # 3 circular pockets at 120° spacing
    for angle_deg in [0, 120, 240]:
        rad = math.radians(angle_deg)
        cx = 20 * math.cos(rad)
        cy = 20 * math.sin(rad)
        pocket = (
            cq.Workplane("XY")
            .transformed(offset=(cx, cy, 5))
            .circle(8)
            .extrude(10)
        )
        plate = plate.cut(pocket)
    return plate, "Round Plate + 3 Circular Pockets"


def make_phone_case_mold():
    """Phone case mold cavity — lofted rectangle-to-rounded shape.
    Base: 80x50, lofted up to 70x40 with rounded corners at Z=12.
    """
    # Bottom profile
    bottom = (
        cq.Workplane("XY")
        .rect(80, 50)
    )
    # Top profile (smaller, rounded corners)
    top = (
        cq.Workplane("XY")
        .workplane(offset=12)
        .rect(70, 40)
    )
    # Loft between them
    body = (
        cq.Workplane("XY")
        .rect(80, 50)
        .workplane(offset=12)
        .rect(70, 40)
        .loft()
    )
    # Add base plate underneath
    base = (
        cq.Workplane("XY")
        .rect(90, 60)
        .extrude(-5)
    )
    solid = base.union(body)
    # Fillet the top edges
    solid = solid.edges(">Z").fillet(3)
    return solid, "Phone Case Mold (Loft)"


def make_swept_blade():
    """Lofted blade blank — ellipse root tapering to smaller ellipse tip."""
    blade = (
        cq.Workplane("XY")
        .ellipse(22, 5)
        .workplane(offset=40)
        .ellipse(12, 2)
        .loft()
    )
    return blade, "Lofted Blade (Ellipse Taper)"


def make_mounting_flange():
    """Circular flange D=100 with bolt pattern + central bore + keyway."""
    # Main disc
    flange = (
        cq.Workplane("XY")
        .circle(50)
        .circle(15)      # central bore D=30
        .extrude(12)
    )
    # 6 bolt holes at D=80 PCD
    for i in range(6):
        angle = math.radians(i * 60)
        bx = 35 * math.cos(angle)
        by = 35 * math.sin(angle)
        bolt = (
            cq.Workplane("XY")
            .transformed(offset=(bx, by, 0))
            .circle(4)
            .extrude(12)
        )
        flange = flange.cut(bolt)
    # Keyway slot in center bore
    keyway = (
        cq.Workplane("XY")
        .transformed(offset=(13, 0, 0))
        .rect(6, 4)
        .extrude(12)
    )
    flange = flange.cut(keyway)
    return flange, "Mounting Flange + 6 Bolts + Keyway"


def make_boolean_sculpture():
    """Complex boolean: box - sphere - cylinder intersections."""
    base = cq.Workplane("XY").box(60, 60, 25, centered=(True, True, False))
    # Subtract a large sphere from top
    sphere = cq.Workplane("XY").transformed(offset=(0, 0, 25)).sphere(30)
    result = base.cut(sphere)
    # Subtract diagonal cylinder
    cyl = (
        cq.Workplane("XZ")
        .transformed(offset=(0, 0, 0), rotate=(0, 30, 0))
        .circle(8)
        .extrude(80, both=True)
    )
    result = result.cut(cyl)
    # Add a boss on top
    boss = (
        cq.Workplane("XY")
        .transformed(offset=(0, 0, 15))
        .circle(10)
        .extrude(10)
    )
    result = result.union(boss)
    result = result.edges(">Z").fillet(2)
    return result, "Boolean Sculpture (Box-Sphere-Cylinder)"


def process_shape(solid, name, stock_dims, index):
    """Run AutoCAM on a shape and report results."""
    print(f"\n{'='*65}")
    print(f"  Shape {index}: {name}")
    print(f"  Stock: {stock_dims[0]}x{stock_dims[1]}x{stock_dims[2]} mm")
    print(f"{'='*65}")

    cam = AutoCAM(
        stock_dims=stock_dims,
        material="Aluminum 6061",
        post_processor="fanuc",
        approach_strategy="ramp",
    )
    cam.load_target_solid(solid)
    result = cam.plan_and_generate()

    # Report
    print(f"\n{result.plan.summary()}")
    print(f"\n  G-code: {len(result.gcode.splitlines())} lines")
    print(f"  Segments: {len(result.segments)} segs, "
          f"{sum(len(s.points) for s in result.segments)} points")

    if result.optimization_report:
        print(f"  {result.optimization_report}")
    if result.collision_report:
        print(f"  Collisions: {result.collision_report.error_count} errors, "
              f"{result.collision_report.warning_count} warnings")

    # Save
    gcode_path = f"output/gcode/arb_{index}.nc"
    result.save(gcode_path)

    step_path = f"output/step/arb_{index}_{name.lower().replace(' ', '_')[:30]}.step"
    from src.cad.exporter import export_step
    export_step(solid, step_path)
    print(f"  STEP: {step_path}")
    print(f"  G-code: {gcode_path}")

    return result


def main():
    print("=" * 65)
    print("  KooCADCAM - Arbitrary Shape AutoCAM Test")
    print("  6 diverse shapes: wedge, round, loft, blade, flange, boolean")
    print("=" * 65)

    shapes = [
        (make_wedge,                    (120, 80, 35)),
        (make_round_plate_with_pockets, (100, 100, 20)),
        (make_phone_case_mold,          (100, 70, 20)),
        (make_swept_blade,              (60, 20, 50)),
        (make_mounting_flange,          (120, 120, 15)),
        (make_boolean_sculpture,        (80, 80, 30)),
    ]

    results = []
    for i, (make_fn, stock) in enumerate(shapes, 1):
        try:
            solid, name = make_fn()
            r = process_shape(solid, name, stock, i)
            results.append((name, True))
        except Exception as e:
            print(f"\n  FAILED: {e}")
            results.append((make_fn.__name__, False))

    print(f"\n{'='*65}")
    print(f"  Results Summary")
    print(f"{'='*65}")
    for name, ok in results:
        status = "OK" if ok else "FAIL"
        print(f"  [{status:4s}] {name}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\n  {passed}/{len(results)} shapes processed successfully")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
