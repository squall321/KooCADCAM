#!/usr/bin/env python3
"""Example 01: Plate → Cuboid with fillet.

Demonstrates the full KooCADCAM pipeline:
1. Generate a 60x60x15mm cuboid with R3 fillets from 100x100x20mm stock
2. Produce STEP file
3. Generate G-code (FANUC)
4. Display toolpath visualization
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.config import Config
from src.pipeline import Pipeline


def main():
    config_path = Path(__file__).parent / "config.yaml"
    config = Config.from_yaml(config_path)

    print("=" * 60)
    print("KooCADCAM - Example 01: Plate Fillet")
    print("=" * 60)
    print(f"  Stock:  {config['stock']['x']} x {config['stock']['y']} x {config['stock']['z']} mm")
    print(f"  Target: {config['target']['x']} x {config['target']['y']} x {config['target']['z']} mm")
    print(f"  Fillet: R{config['target']['fillet_radius']} mm")
    print(f"  Post:   {config['postprocessor']}")
    print()

    pipeline = Pipeline(config)

    # Subscribe to events for progress
    pipeline.bus.on("phase_start", lambda p: print(f"  [{p.upper()}] Starting..."))
    pipeline.bus.on("phase_complete", lambda p: print(f"  [{p.upper()}] Complete!"))

    print("Running pipeline...")
    result = pipeline.run()

    print()
    print("Results:")
    print(f"  STEP file: {result.step_path}")
    print(f"  STL file:  {result.stl_path}")
    print(f"  G-code:    {result.gcode_path}")
    print(f"  G-code lines: {result.gcode_text.count(chr(10))}")
    if result.parsed_paths:
        print(f"  Path segments: {len(result.parsed_paths)}")
        rapid = sum(1 for p in result.parsed_paths if p.path_type.value == "rapid")
        cutting = len(result.parsed_paths) - rapid
        print(f"    Rapid moves:   {rapid}")
        print(f"    Cutting moves: {cutting}")

    # Print first 30 lines of G-code
    print()
    print("G-code preview (first 30 lines):")
    print("-" * 50)
    for line in result.gcode_text.splitlines()[:30]:
        print(f"  {line}")
    print("  ...")

    print()
    print("Done!")


if __name__ == "__main__":
    main()
