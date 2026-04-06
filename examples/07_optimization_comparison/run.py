#!/usr/bin/env python3
"""Example 07: Parameter optimization comparison.

Shows how parameter changes affect cycle time.
Core digital twin feature: 'what-if' analysis before real cutting.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.cam.stock import Stock
from src.cam.tools import TOOL_LIBRARY
from src.cam.toolpath import FacingStrategy, PocketStrategy
from src.cam.gcode_writer import GcodeWriter
from src.cam.postprocessor import get_postprocessor
from src.cam.optimizer import optimize_all
from src.sim.gcode_parser import GcodeParser
from src.sim.time_estimator import TimeEstimator, MachineParams, estimate_distances


def run_scenario(name, stepover_ratio, depth_per_pass, feed_rate, spindle_rpm):
    """Run one parameter scenario and return timing."""
    stock = Stock(100, 100, 20)
    tool = TOOL_LIBRARY["flat_10mm"]
    tb = {"x_min": -30, "x_max": 30, "y_min": -30, "y_max": 30}

    segs = []
    segs.extend(FacingStrategy().generate(
        tool=tool, stock_bounds=stock.bounds,
        target_z=15, depth_per_pass=depth_per_pass,
        stepover_ratio=stepover_ratio,
        feed_rate=feed_rate, plunge_rate=200, spindle_rpm=spindle_rpm,
    ))
    segs.extend(PocketStrategy().generate(
        tool=tool, stock_bounds=stock.bounds, target_bounds=tb,
        z_top=15, z_bottom=0,
        depth_per_pass=depth_per_pass, stepover_ratio=stepover_ratio,
        feed_rate=feed_rate, plunge_rate=200, spindle_rpm=spindle_rpm,
    ))
    segs, _ = optimize_all(segs, base_feed=feed_rate)

    gcode = GcodeWriter(get_postprocessor("fanuc")).generate(segs)
    parsed = GcodeParser().parse_text(gcode)

    time_est = TimeEstimator().estimate(parsed)
    dist = estimate_distances(parsed)

    return {
        "name": name,
        "time": time_est.total_time,
        "cutting_time": time_est.cutting_time,
        "cutting_pct": time_est.cutting_pct,
        "total_moves": len(parsed),
        "cutting_dist": dist.total_cutting_distance,
        "rapid_dist": dist.total_rapid_distance,
    }


def format_time(sec):
    if sec < 60:
        return f"{sec:.0f}s"
    m, s = divmod(sec, 60)
    return f"{int(m)}m {int(s)}s"


def main():
    print("=" * 75)
    print("  KooCADCAM - Parameter Optimization Comparison")
    print("  Same part, different cutting parameters -> different cycle times")
    print("=" * 75)

    # Test scenarios
    scenarios = [
        # name,                stepover, DOC, feed, RPM
        ("Conservative",       0.30,     1.0,  400,  6000),
        ("Default",            0.40,     2.5,  600,  8000),
        ("Aggressive",         0.55,     4.0,  1000, 10000),
        ("HSM (High Speed)",   0.15,     0.5,  2500, 18000),
    ]

    results = []
    for params in scenarios:
        name = params[0]
        print(f"\n  [{name}]  stepover={params[1]*100:.0f}%  DOC={params[2]}mm  "
              f"feed={params[3]}mm/min  rpm={params[4]}")
        result = run_scenario(*params)
        results.append(result)
        print(f"    -> {format_time(result['time']):>10}  "
              f"({result['total_moves']} moves, "
              f"{result['cutting_dist']:.0f}mm cut)")

    # Comparison table
    print("\n" + "=" * 75)
    print("  Comparison Summary")
    print("=" * 75)
    print(f"  {'Scenario':<22} {'Total Time':>12} {'Cutting':>10} {'Moves':>8}  {'vs Default':>12}")
    print("  " + "-" * 73)

    baseline = results[1]["time"]  # Default as baseline
    for r in results:
        delta = r["time"] - baseline
        delta_pct = 100 * delta / baseline
        delta_str = f"{delta_pct:+.1f}%" if r["name"] != "Default" else "---"
        print(f"  {r['name']:<22} {format_time(r['time']):>12} "
              f"{format_time(r['cutting_time']):>10} {r['total_moves']:>8}  "
              f"{delta_str:>12}")

    # Best scenario
    best = min(results, key=lambda x: x["time"])
    worst = max(results, key=lambda x: x["time"])
    saving_pct = 100 * (worst["time"] - best["time"]) / worst["time"]

    print("\n" + "=" * 75)
    print(f"  Best:  {best['name']:<20} -> {format_time(best['time'])}")
    print(f"  Worst: {worst['name']:<20} -> {format_time(worst['time'])}")
    print(f"  Potential time saving: {saving_pct:.0f}% "
          f"({format_time(worst['time'] - best['time'])})")
    print("=" * 75)
    print("\nDigital twin insight: parameter changes can save minutes per part")
    print("Multiply by production volume: 1000 parts x 5min = 83 hours saved")


if __name__ == "__main__":
    main()
