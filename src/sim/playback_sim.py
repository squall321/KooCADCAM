"""Playback-style material removal simulation.

Uses PyVista's add_on_render_event callback for smooth frame-by-frame
animation of the cutting process. Each frame:
1. Advance N segments
2. Remove voxels along those segments
3. Re-render the stock mesh + tool position
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pyvista as pv

from .gcode_parser import GcodeParser, PathSegment, PathType
from .voxel_engine import VoxelEngine, VoxelGrid, ToolShape


class PlaybackSimulator:
    """Frame-by-frame animated material removal.

    Opens a 3D window and plays the cutting process like a video:
    - Stock material visibly shrinks as the tool moves
    - Tool (yellow) tracks along the toolpath
    - Progress bar and stats update in real-time

    Usage:
        sim = PlaybackSimulator(
            gcode_path="output/gcode/plate_fillet.nc",
            stock_dims=(100, 100, 20),
            tool_diameter=10.0,
        )
        sim.play()
    """

    def __init__(
        self,
        gcode_text: str,
        stock_dims: tuple[float, float, float],
        tool_diameter: float,
        tool_shape: ToolShape = ToolShape.FLAT,
        voxel_resolution: float = 2.0,
        segments_per_frame: int = 5,
    ):
        self.stock_dims = stock_dims
        self.tool_diameter = tool_diameter
        self.tool_shape = tool_shape
        self.voxel_resolution = voxel_resolution
        self.segments_per_frame = segments_per_frame

        # Parse G-code
        parser = GcodeParser()
        self.segments = parser.parse_text(gcode_text)
        self.total_segments = len(self.segments)

        # Voxel grid
        sx, sy, sz = stock_dims
        self.grid = VoxelGrid.from_stock(
            -sx / 2, sx / 2, -sy / 2, sy / 2, 0, sz,
            resolution=voxel_resolution,
        )
        self.engine = VoxelEngine(self.grid, tool_diameter, tool_shape)

        # State
        self._current_idx = 0
        self._playing = False
        self._plotter = None
        self._stock_actor = None
        self._tool_actor = None
        self._text_actor = None
        self._trail_actor = None
        self._trail_pts: list[list[float]] = []
        self._timer_id = None

    def play(self):
        """Open window and start playback."""
        self._plotter = pv.Plotter(
            title="KooCADCAM - Cutting Simulation (Space=pause, R=restart, Q=quit)",
            window_size=(1400, 900),
        )
        self._plotter.set_background("white")
        self._plotter.add_axes()

        # Initial stock
        self._render_stock()

        # Initial tool at origin
        self._render_tool(0, 0, self.stock_dims[2] + 5)

        # Info text
        self._text_actor = self._plotter.add_text(
            "Press SPACE to start", position="upper_left",
            font_size=12, color="black", name="info",
        )

        # Key bindings
        self._plotter.add_key_event("space", self._toggle_play)
        self._plotter.add_key_event("r", self._restart)
        self._plotter.add_key_event("Right", self._step_forward)

        self._plotter.camera_position = "iso"
        self._plotter.reset_camera()

        # Timer callback for animation
        self._playing = True
        self._plotter.add_callback(self._advance_frame, interval=50)

        self._plotter.show()

    def _toggle_play(self):
        self._playing = not self._playing

    def _restart(self):
        """Reset simulation to beginning."""
        sx, sy, sz = self.stock_dims
        self.grid = VoxelGrid.from_stock(
            -sx / 2, sx / 2, -sy / 2, sy / 2, 0, sz,
            resolution=self.voxel_resolution,
        )
        self.engine = VoxelEngine(self.grid, self.tool_diameter, self.tool_shape)
        self._current_idx = 0
        self._trail_pts.clear()
        self._playing = True

    def _step_forward(self):
        """Advance one frame manually."""
        if not self._playing:
            self._do_advance()

    def _advance_frame(self):
        """Timer callback - advance simulation by N segments."""
        if not self._playing:
            return
        if self._current_idx >= self.total_segments:
            self._playing = False
            return
        self._do_advance()

    def _do_advance(self):
        """Process next batch of segments."""
        end_idx = min(self._current_idx + self.segments_per_frame, self.total_segments)

        for i in range(self._current_idx, end_idx):
            seg = self.segments[i]
            if seg.path_type != PathType.RAPID:
                self.engine.remove_segment(seg, steps_per_mm=1.0)
                self._trail_pts.append([seg.x_start, seg.y_start, seg.z_start])
                self._trail_pts.append([seg.x_end, seg.y_end, seg.z_end])

        last_seg = self.segments[end_idx - 1]
        self._current_idx = end_idx

        # Update visuals
        self._render_stock()
        self._render_tool(last_seg.x_end, last_seg.y_end, last_seg.z_end)
        self._render_trail()

        # Update text
        pct = 100 * self._current_idx / self.total_segments
        vol_removed = self.grid.volume_removed
        vol_remain = self.grid.volume_remaining

        status = "PLAYING" if self._playing else "PAUSED"
        if self._current_idx >= self.total_segments:
            status = "COMPLETE"

        info = (
            f"[{status}]  {pct:.0f}%  ({self._current_idx}/{self.total_segments})\n"
            f"Removed: {vol_removed:.0f} mm3  |  Remaining: {vol_remain:.0f} mm3\n"
            f"Space=play/pause  R=restart  Right=step  Q=quit"
        )
        if self._text_actor is not None:
            self._plotter.remove_actor(self._text_actor)
        self._text_actor = self._plotter.add_text(
            info, position="upper_left",
            font_size=11, color="black", name="info",
        )

    def _render_stock(self):
        """Re-render voxel stock mesh."""
        if self._stock_actor is not None:
            self._plotter.remove_actor(self._stock_actor)
            self._stock_actor = None

        try:
            mesh = self.engine.to_mesh()
            if mesh.n_cells > 0:
                self._stock_actor = self._plotter.add_mesh(
                    mesh, color="steelblue", opacity=1.0,
                    smooth_shading=True, show_edges=False,
                    name="stock",
                )
        except Exception:
            pass

    def _render_tool(self, x: float, y: float, z: float):
        """Move tool indicator."""
        if self._tool_actor is not None:
            self._plotter.remove_actor(self._tool_actor)
            self._tool_actor = None

        r = self.tool_diameter / 2
        if self.tool_shape == ToolShape.BALL:
            tool_mesh = pv.Sphere(radius=r, center=(x, y, z))
        else:
            tool_mesh = pv.Cylinder(
                center=(x, y, z + r), direction=(0, 0, 1),
                radius=r, height=r * 4,
            )
        self._tool_actor = self._plotter.add_mesh(
            tool_mesh, color="yellow", opacity=0.7, name="tool",
        )

    def _render_trail(self):
        """Render recent cutting trail."""
        if self._trail_actor is not None:
            self._plotter.remove_actor(self._trail_actor)
            self._trail_actor = None

        # Show last 300 trail points for performance
        pts_data = self._trail_pts[-300:]
        if len(pts_data) < 4:
            return

        pts = np.array(pts_data)
        n = len(pts) // 2
        lines = np.zeros((n, 3), dtype=int)
        lines[:, 0] = 2
        lines[:, 1] = np.arange(0, 2 * n, 2)
        lines[:, 2] = np.arange(1, 2 * n, 2)
        trail_mesh = pv.PolyData(pts[:2 * n], lines=lines.ravel())
        self._trail_actor = self._plotter.add_mesh(
            trail_mesh, color="orange", line_width=2, name="trail",
        )


def play_simulation(
    gcode_file: str = "output/gcode/plate_fillet.nc",
    stock_dims: tuple[float, float, float] = (100, 100, 20),
    tool_diameter: float = 10.0,
    resolution: float = 2.0,
    speed: int = 5,
):
    """Quick-launch cutting simulation playback.

    Args:
        gcode_file: Path to G-code file.
        stock_dims: Stock dimensions (x, y, z).
        tool_diameter: Tool diameter in mm.
        resolution: Voxel size in mm (smaller=finer, slower).
        speed: Segments per frame (higher=faster playback).
    """
    gcode = Path(gcode_file).read_text()
    sim = PlaybackSimulator(
        gcode_text=gcode,
        stock_dims=stock_dims,
        tool_diameter=tool_diameter,
        voxel_resolution=resolution,
        segments_per_frame=speed,
    )
    sim.play()
