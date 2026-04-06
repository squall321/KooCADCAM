"""Export CadQuery solids to STEP, STL files."""

from __future__ import annotations

from pathlib import Path

import cadquery as cq


def export_step(solid: cq.Workplane, path: str | Path) -> Path:
    """Export solid to STEP format (AP214).

    Args:
        solid: CadQuery workplane to export.
        path: Output file path.

    Returns:
        Path to the exported file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(solid, str(path), exportType="STEP")
    return path


def export_stl(
    solid: cq.Workplane,
    path: str | Path,
    tolerance: float = 0.01,
    angular_tolerance: float = 0.1,
) -> Path:
    """Export solid to STL format.

    Args:
        solid: CadQuery workplane to export.
        path: Output file path.
        tolerance: Linear tolerance for tessellation.
        angular_tolerance: Angular tolerance for tessellation.

    Returns:
        Path to the exported file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(
        solid,
        str(path),
        exportType="STL",
        tolerance=tolerance,
        angularTolerance=angular_tolerance,
    )
    return path
