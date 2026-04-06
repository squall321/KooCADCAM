"""3D visualization of CAD models and G-code toolpaths using PyVista."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pyvista as pv

from .gcode_parser import PathSegment, PathType


class PathVisualizer:
    """Visualize G-code toolpaths in 3D.

    Color coding:
    - Rapid moves (G0): yellow dashed
    - Cutting moves (G1): red solid
    - Arc moves (G2/G3): blue solid
    """

    COLORS = {
        PathType.RAPID: "yellow",
        PathType.CUTTING: "red",
        PathType.ARC_CW: "dodgerblue",
        PathType.ARC_CCW: "dodgerblue",
    }
    LINE_WIDTHS = {
        PathType.RAPID: 1.0,
        PathType.CUTTING: 2.5,
        PathType.ARC_CW: 2.5,
        PathType.ARC_CCW: 2.5,
    }

    def __init__(self) -> None:
        self._plotter: pv.Plotter | None = None

    def create_path_mesh(self, segments: list[PathSegment]) -> dict[PathType, pv.PolyData]:
        """Convert path segments into PyVista line meshes grouped by type."""
        grouped: dict[PathType, list[list[float]]] = {pt: [] for pt in PathType}

        for seg in segments:
            grouped[seg.path_type].append([seg.x_start, seg.y_start, seg.z_start])
            grouped[seg.path_type].append([seg.x_end, seg.y_end, seg.z_end])

        meshes = {}
        for ptype, points in grouped.items():
            if len(points) < 2:
                continue
            pts = np.array(points)
            n_lines = len(pts) // 2
            lines = np.zeros((n_lines, 3), dtype=int)
            lines[:, 0] = 2  # each line has 2 points
            lines[:, 1] = np.arange(0, 2 * n_lines, 2)
            lines[:, 2] = np.arange(1, 2 * n_lines, 2)
            mesh = pv.PolyData(pts, lines=lines.ravel())
            meshes[ptype] = mesh

        return meshes

    def create_stock_mesh(
        self, lx: float, ly: float, lz: float, opacity: float = 0.15,
    ) -> pv.PolyData:
        """Create a translucent stock bounding box."""
        return pv.Box(bounds=(
            -lx / 2, lx / 2, -ly / 2, ly / 2, 0, lz,
        ))

    def create_target_mesh(
        self, lx: float, ly: float, lz: float,
    ) -> pv.PolyData:
        """Create the target part bounding box."""
        return pv.Box(bounds=(
            -lx / 2, lx / 2, -ly / 2, ly / 2, 0, lz,
        ))

    def plot(
        self,
        segments: list[PathSegment],
        stock_dims: tuple[float, float, float] | None = None,
        target_dims: tuple[float, float, float] | None = None,
        cad_mesh: Any = None,
        title: str = "KooCADCAM - Toolpath Visualization",
        save_path: str | Path | None = None,
        show: bool = True,
    ) -> pv.Plotter:
        """Render the complete visualization.

        Args:
            segments: Parsed G-code path segments.
            stock_dims: (lx, ly, lz) of stock material.
            target_dims: (lx, ly, lz) of target part.
            cad_mesh: Optional PyVista mesh of CAD model.
            title: Window title.
            save_path: If set, save screenshot to this path.
            show: Whether to display interactive window.
        """
        plotter = pv.Plotter(title=title, window_size=(1400, 900))
        plotter.set_background("white")

        # Stock (translucent)
        if stock_dims:
            stock = self.create_stock_mesh(*stock_dims)
            plotter.add_mesh(stock, color="lightgray", opacity=0.12, style="wireframe", line_width=1)

        # Target part (translucent solid)
        if target_dims:
            target = self.create_target_mesh(*target_dims)
            plotter.add_mesh(target, color="steelblue", opacity=0.25, style="surface")

        # CAD mesh if provided
        if cad_mesh is not None:
            plotter.add_mesh(cad_mesh, color="steelblue", opacity=0.3, style="surface")

        # Toolpath lines
        path_meshes = self.create_path_mesh(segments)
        for ptype, mesh in path_meshes.items():
            plotter.add_mesh(
                mesh,
                color=self.COLORS[ptype],
                line_width=self.LINE_WIDTHS[ptype],
                label=ptype.value,
            )

        plotter.add_legend(bcolor="white", border=True)
        plotter.add_axes()
        plotter.camera_position = "iso"

        if save_path:
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            plotter.screenshot(str(save_path))

        if show:
            plotter.show()

        self._plotter = plotter
        return plotter
