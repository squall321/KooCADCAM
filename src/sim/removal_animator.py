"""Animated material removal simulation with real-time 3D rendering.

Shows the stock being cut away step-by-step as the tool follows
the G-code toolpath. Uses PyVista for interactive 3D visualization.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pyvista as pv

from .gcode_parser import GcodeParser, PathSegment, PathType
from .voxel_engine import VoxelEngine, VoxelGrid, ToolShape


@dataclass
class AnimatorConfig:
    """Configuration for the removal animation."""
    voxel_resolution: float = 1.0       # mm per voxel
    update_interval: int = 5            # update display every N segments
    tool_color: str = "yellow"
    stock_color: str = "lightgray"
    cut_surface_color: str = "steelblue"
    gouge_color: str = "red"
    tool_opacity: float = 0.6
    stock_opacity: float = 1.0
    background: str = "white"
    window_size: tuple[int, int] = (1400, 900)
    show_toolpath_trail: bool = True
    trail_color: str = "orange"
    save_frames: bool = False
    frame_dir: str = "output/images/frames"


class RemovalAnimator:
    """Animated material removal simulation.

    Creates a real-time 3D animation showing:
    - Stock material being removed voxel by voxel
    - Tool position moving along the toolpath
    - Cut surface coloring
    - Optional toolpath trail
    - Progress statistics overlay

    Usage:
        animator = RemovalAnimator(
            stock_dims=(100, 100, 20),
            tool_diameter=10.0,
            tool_shape=ToolShape.FLAT,
        )
        animator.run(gcode_text)  # Interactive window
        # or
        animator.run(gcode_text, save_gif="output/images/cutting.gif")
    """

    def __init__(
        self,
        stock_dims: tuple[float, float, float],
        tool_diameter: float,
        tool_shape: ToolShape = ToolShape.FLAT,
        config: AnimatorConfig | None = None,
    ) -> None:
        self.stock_dims = stock_dims
        self.tool_diameter = tool_diameter
        self.tool_shape = tool_shape
        self.config = config or AnimatorConfig()

        self._plotter: pv.Plotter | None = None
        self._grid: VoxelGrid | None = None
        self._engine: VoxelEngine | None = None
        self._stock_actor = None
        self._tool_actor = None
        self._trail_points: list[list[float]] = []

    def run(
        self,
        gcode_text: str,
        save_gif: str | None = None,
        on_progress: Callable[[int, int, dict], None] | None = None,
    ) -> dict[str, Any]:
        """Run the animated simulation.

        Args:
            gcode_text: G-code program text.
            save_gif: If set, save animation as GIF to this path.
            on_progress: Callback(current_step, total_steps, stats).

        Returns:
            Final simulation statistics.
        """
        cfg = self.config
        sx, sy, sz = self.stock_dims

        # Parse G-code
        parser = GcodeParser()
        segments = parser.parse_text(gcode_text)
        if not segments:
            return {"error": "No segments parsed from G-code"}

        # Create voxel grid
        self._grid = VoxelGrid.from_stock(
            -sx / 2, sx / 2, -sy / 2, sy / 2, 0, sz,
            resolution=cfg.voxel_resolution,
        )
        self._engine = VoxelEngine(
            self._grid, self.tool_diameter, self.tool_shape,
        )

        # Setup plotter
        self._plotter = pv.Plotter(
            title="KooCADCAM - Material Removal Simulation",
            window_size=cfg.window_size,
            off_screen=save_gif is not None,
        )
        self._plotter.set_background(cfg.background)
        self._plotter.add_axes()

        if save_gif:
            Path(save_gif).parent.mkdir(parents=True, exist_ok=True)
            self._plotter.open_gif(save_gif)

        # Initial stock display
        self._render_stock()
        self._plotter.camera_position = "iso"
        self._plotter.reset_camera()

        # Add text overlay - store the actor for updates
        self._text_actor = None

        # Animate through segments
        total = len(segments)
        total_removed = 0
        cutting_segments = [s for s in segments if s.path_type != PathType.RAPID]

        for i, seg in enumerate(segments):
            # Remove material
            if seg.path_type != PathType.RAPID:
                result = self._engine.remove_segment(seg, steps_per_mm=1.0)
                total_removed += result.voxels_removed

            # Update tool position
            self._update_tool(seg.x_end, seg.y_end, seg.z_end)

            # Collect trail
            if cfg.show_toolpath_trail and seg.path_type != PathType.RAPID:
                self._trail_points.append([seg.x_start, seg.y_start, seg.z_start])
                self._trail_points.append([seg.x_end, seg.y_end, seg.z_end])

            # Update display at intervals
            if i % cfg.update_interval == 0 or i == total - 1:
                self._render_stock()
                self._render_trail()

                pct = 100 * (i + 1) / total
                vol_removed = self._grid.volume_removed
                vol_remaining = self._grid.volume_remaining
                stats_text = (
                    f"Progress: {pct:.0f}%  ({i + 1}/{total} moves)\n"
                    f"Removed: {vol_removed:.0f} mm3\n"
                    f"Remaining: {vol_remaining:.0f} mm3"
                )

                # Update text overlay
                if self._text_actor is not None:
                    self._plotter.remove_actor(self._text_actor)
                self._text_actor = self._plotter.add_text(
                    stats_text, position="upper_left",
                    font_size=10, color="black", name="stats_text",
                )

                if save_gif:
                    self._plotter.write_frame()
                else:
                    self._plotter.render()

                if on_progress:
                    on_progress(i + 1, total, {
                        "volume_removed": vol_removed,
                        "volume_remaining": vol_remaining,
                    })

        # Final frame hold
        if save_gif:
            for _ in range(10):
                self._plotter.write_frame()
            self._plotter.close()
        else:
            # Keep window open for interaction
            self._plotter.show()

        return {
            "total_segments": total,
            "cutting_segments": len(cutting_segments),
            "volume_total": self._grid.volume_total,
            "volume_removed": self._grid.volume_removed,
            "volume_remaining": self._grid.volume_remaining,
            "removal_pct": 100 * self._grid.volume_removed / max(self._grid.volume_total, 1),
        }

    def _render_stock(self) -> None:
        """Re-render the voxel stock mesh."""
        if self._stock_actor is not None:
            self._plotter.remove_actor(self._stock_actor)

        # Convert filled voxels to mesh
        try:
            mesh = self._engine.to_mesh()
            if mesh.n_cells > 0:
                self._stock_actor = self._plotter.add_mesh(
                    mesh,
                    color=self.config.cut_surface_color,
                    opacity=self.config.stock_opacity,
                    show_edges=False,
                    smooth_shading=True,
                    name="stock",
                )
        except Exception:
            pass

    def _update_tool(self, x: float, y: float, z: float) -> None:
        """Move the tool indicator to new position."""
        if self._tool_actor is not None:
            self._plotter.remove_actor(self._tool_actor)

        r = self.tool_diameter / 2
        if self.tool_shape == ToolShape.BALL:
            tool_mesh = pv.Sphere(radius=r, center=(x, y, z))
        else:
            tool_mesh = pv.Cylinder(
                center=(x, y, z + r),
                direction=(0, 0, 1),
                radius=r,
                height=r * 2,
            )

        self._tool_actor = self._plotter.add_mesh(
            tool_mesh,
            color=self.config.tool_color,
            opacity=self.config.tool_opacity,
            name="tool",
        )

    def _render_trail(self) -> None:
        """Render the toolpath trail."""
        if not self.config.show_toolpath_trail or len(self._trail_points) < 2:
            return

        pts = np.array(self._trail_points[-500:])  # Last 500 points for performance
        n = len(pts) // 2
        if n < 1:
            return

        lines = np.zeros((n, 3), dtype=int)
        lines[:, 0] = 2
        lines[:, 1] = np.arange(0, 2 * n, 2)
        lines[:, 2] = np.arange(1, 2 * n, 2)

        trail_mesh = pv.PolyData(pts[:2 * n], lines=lines.ravel())
        self._plotter.add_mesh(
            trail_mesh,
            color=self.config.trail_color,
            line_width=1.5,
            name="trail",
        )


def run_removal_simulation(
    gcode_text: str,
    stock_dims: tuple[float, float, float] = (100, 100, 20),
    tool_diameter: float = 10.0,
    tool_shape: ToolShape = ToolShape.FLAT,
    resolution: float = 1.0,
    update_interval: int = 5,
    save_gif: str | None = None,
) -> dict[str, Any]:
    """Convenience function to run a removal simulation.

    Args:
        gcode_text: G-code program.
        stock_dims: (lx, ly, lz) of stock material.
        tool_diameter: Cutting tool diameter.
        tool_shape: FLAT, BALL, or BULL.
        resolution: Voxel size in mm (smaller = finer but slower).
        update_interval: Frames between display updates.
        save_gif: Path to save as animated GIF. None = interactive window.

    Returns:
        Statistics dict.
    """
    config = AnimatorConfig(
        voxel_resolution=resolution,
        update_interval=update_interval,
    )
    animator = RemovalAnimator(stock_dims, tool_diameter, tool_shape, config)
    return animator.run(gcode_text, save_gif=save_gif)
