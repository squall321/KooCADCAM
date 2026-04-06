"""3D viewport widget embedding PyVista in Qt with simulation playback.

Key design:
- Stock/tool/trail actors stored and explicitly removed before re-add
- Single render() call per frame to minimize flicker
- 3-point lighting for depth perception
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import QTimer, Signal

from ..sim.gcode_parser import GcodeParser, PathSegment, PathType
from ..sim.voxel_engine import VoxelEngine, VoxelGrid, ToolShape


class Viewport3D(QWidget):
    """3D viewport with simulation playback."""

    COLORS = {
        PathType.RAPID: "yellow",
        PathType.CUTTING: "red",
        PathType.ARC_CW: "dodgerblue",
        PathType.ARC_CCW: "dodgerblue",
    }

    sim_progress = Signal(int, int)
    sim_stats = Signal(float, float, float)
    sim_finished = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        pv.global_theme.anti_aliasing = "msaa"
        self._plotter = QtInteractor(self)
        self._setup_lighting()
        layout.addWidget(self._plotter.interactor)
        self.setLayout(layout)

        # Sim state
        self._sim_segments: list[PathSegment] = []
        self._sim_grid: VoxelGrid | None = None
        self._sim_engine: VoxelEngine | None = None
        self._sim_idx = 0
        self._sim_playing = False
        self._sim_speed = 5
        self._sim_timer = QTimer()
        self._sim_timer.timeout.connect(self._sim_advance)
        self._trail_pts: list[list[float]] = []

        # Actors (explicit tracking for flicker-free replace)
        self._actor_stock = None
        self._actor_tool = None
        self._actor_trail = None
        self._actor_text = None

    def _setup_lighting(self) -> None:
        self._plotter.set_background("#f0f0f0", top="#d8d8d8")
        self._plotter.remove_all_lights()
        self._plotter.add_light(pv.Light(position=(150, 100, 200), focal_point=(0, 0, 0), intensity=0.9))
        self._plotter.add_light(pv.Light(position=(-120, -60, 100), focal_point=(0, 0, 0), color="#e8e8ff", intensity=0.4))
        self._plotter.add_light(pv.Light(position=(-50, 80, -50), focal_point=(0, 0, 0), color="#ffe8d0", intensity=0.3))
        self._plotter.add_axes()

    # --- Basic display ---

    def clear(self) -> None:
        self._plotter.clear()
        self._actor_stock = None
        self._actor_tool = None
        self._actor_trail = None
        self._actor_text = None
        self._setup_lighting()

    def show_stock(self, lx: float, ly: float, lz: float) -> None:
        box = pv.Box(bounds=(-lx/2, lx/2, -ly/2, ly/2, 0, lz))
        self._plotter.add_mesh(box, color="lightgray", opacity=0.15, style="wireframe", line_width=1)

    def show_target(self, lx: float, ly: float, lz: float) -> None:
        box = pv.Box(bounds=(-lx/2, lx/2, -ly/2, ly/2, 0, lz))
        self._plotter.add_mesh(box, color="steelblue", opacity=0.25, style="surface", smooth_shading=True)

    def show_cad_mesh(self, stl_path: str) -> None:
        mesh = pv.read(stl_path)
        self._plotter.add_mesh(mesh, color="steelblue", opacity=0.4, style="surface",
                               smooth_shading=True, specular=0.5, specular_power=30)

    def show_toolpath(self, segments: list[PathSegment]) -> None:
        grouped: dict[PathType, list[list[float]]] = {pt: [] for pt in PathType}
        for seg in segments:
            grouped[seg.path_type].append([seg.x_start, seg.y_start, seg.z_start])
            grouped[seg.path_type].append([seg.x_end, seg.y_end, seg.z_end])
        for ptype, points in grouped.items():
            if len(points) < 2:
                continue
            pts = np.array(points)
            n_lines = len(pts) // 2
            lines = np.zeros((n_lines, 3), dtype=int)
            lines[:, 0] = 2
            lines[:, 1] = np.arange(0, 2 * n_lines, 2)
            lines[:, 2] = np.arange(1, 2 * n_lines, 2)
            mesh = pv.PolyData(pts, lines=lines.ravel())
            width = 1.0 if ptype == PathType.RAPID else 2.5
            self._plotter.add_mesh(mesh, color=self.COLORS[ptype], line_width=width, label=ptype.value)

    def reset_camera(self) -> None:
        self._plotter.camera_position = "iso"
        self._plotter.reset_camera()
        self._plotter.render()
        self._plotter.update()

    def screenshot(self, path: str) -> None:
        self._plotter.screenshot(path)

    # --- Simulation playback ---

    def sim_setup(self, gcode_text: str, stock_dims: tuple[float, float, float],
                  tool_diameter: float, resolution: float = 2.0,
                  tools: list[dict] | None = None) -> None:
        """Setup simulation with multi-tool support.

        Args:
            tools: List of tool dicts with keys: tool_number, diameter, type.
                   e.g. [{"tool_number": 1, "diameter": 10, "type": "flat"},
                         {"tool_number": 2, "diameter": 6, "type": "ball"}]
        """
        self._sim_timer.stop()
        self._sim_playing = False

        parser = GcodeParser()
        self._sim_segments = parser.parse_text(gcode_text)
        self._sim_idx = 0
        self._trail_pts.clear()

        sx, sy, sz = stock_dims
        self._sim_grid = VoxelGrid.from_stock(-sx/2, sx/2, -sy/2, sy/2, 0, sz, resolution=resolution)
        self._sim_stock_dims = stock_dims
        self._sim_tool_diameter = tool_diameter

        # Multi-tool support: parse tool changes from G-code
        self._sim_tool_table = {}  # tool_number -> (diameter, ToolShape)
        if tools:
            for t in tools:
                tn = t.get("tool_number", 1)
                dia = t.get("diameter", tool_diameter)
                ttype = t.get("type", "flat")
                shape = ToolShape.BALL if "ball" in ttype.lower() else ToolShape.FLAT
                self._sim_tool_table[tn] = (dia, shape)

        # Parse tool change positions from G-code lines
        self._sim_tool_changes = {}  # segment_index -> tool_number
        self._parse_tool_changes(gcode_text)

        # Start with first tool
        first_shape = ToolShape.FLAT
        if self._sim_tool_table:
            first_tn = min(self._sim_tool_table.keys())
            tool_diameter, first_shape = self._sim_tool_table[first_tn]
            self._sim_tool_diameter = tool_diameter

        self._sim_engine = VoxelEngine(self._sim_grid, self._sim_tool_diameter, first_shape)
        self._sim_current_tool_shape = first_shape

        self.clear()
        self._replace_stock()
        self._replace_tool(0, 0, sz + 10)
        self._replace_text("Ready - Press Play")
        self.reset_camera()

        self.sim_progress.emit(0, len(self._sim_segments))
        self.sim_stats.emit(self._sim_grid.volume_total, 0.0, self._sim_grid.volume_total)

    def _parse_tool_changes(self, gcode_text: str) -> None:
        """Find tool change points and map them to segment indices."""
        import re
        lines = gcode_text.splitlines()
        segment_counter = 0
        for line in lines:
            line = line.strip()
            # Count G0/G1 moves to track segment index
            if re.match(r'.*G[01]\s', line) or re.match(r'.*G0[01]\s', line):
                segment_counter += 1
            # Detect tool change: T01 M6, T02 M6, etc.
            t_match = re.search(r'T(\d+)', line)
            if t_match and ('M6' in line or 'M06' in line):
                tn = int(t_match.group(1))
                self._sim_tool_changes[segment_counter] = tn

    def sim_play(self) -> None:
        if not self._sim_segments or self._sim_engine is None:
            return
        self._sim_playing = True
        self._sim_timer.start(80)

    def sim_pause(self) -> None:
        self._sim_playing = False
        self._sim_timer.stop()

    def sim_stop(self) -> None:
        self._sim_timer.stop()
        self._sim_playing = False
        if self._sim_grid is not None:
            sx, sy, sz = self._sim_stock_dims
            self._sim_grid = VoxelGrid.from_stock(
                -sx/2, sx/2, -sy/2, sy/2, 0, sz, resolution=self._sim_grid.resolution)
            self._sim_engine = VoxelEngine(self._sim_grid, self._sim_tool_diameter, ToolShape.FLAT)
            self._sim_idx = 0
            self._trail_pts.clear()
            # Force re-create actors on reset
            self._remove_actor("stock")
            self._remove_actor("tool")
            self._remove_actor("trail")
            self._actor_stock = None
            self._actor_tool = None
            self._actor_trail = None
            self._replace_stock()
            self._replace_tool(0, 0, sz + 10)
            self._replace_text("Stopped - Press Play")
            self._plotter.render()
            self.sim_progress.emit(0, len(self._sim_segments))

    def sim_step(self) -> None:
        self._sim_do_advance()

    def sim_set_speed(self, speed: float) -> None:
        self._sim_speed = max(1, int(speed))

    def _sim_advance(self) -> None:
        if not self._sim_playing:
            return
        if self._sim_idx >= len(self._sim_segments):
            self._sim_timer.stop()
            self._sim_playing = False
            self._replace_text("Complete!")
            self._plotter.render()
            self.sim_finished.emit()
            return
        self._sim_do_advance()

    def _sim_do_advance(self) -> None:
        if self._sim_engine is None or self._sim_grid is None:
            return

        end_idx = min(self._sim_idx + self._sim_speed, len(self._sim_segments))
        for i in range(self._sim_idx, end_idx):
            # Check for tool change at this segment
            if i in self._sim_tool_changes and self._sim_tool_table:
                tn = self._sim_tool_changes[i]
                if tn in self._sim_tool_table:
                    new_dia, new_shape = self._sim_tool_table[tn]
                    self._sim_tool_diameter = new_dia
                    self._sim_current_tool_shape = new_shape
                    # Re-create engine with new tool (grid keeps its state)
                    self._sim_engine = VoxelEngine(
                        self._sim_grid, new_dia, new_shape,
                    )
                    # Force tool actor re-create on shape change
                    self._remove_actor("tool")
                    self._actor_tool = None

            seg = self._sim_segments[i]
            if seg.path_type != PathType.RAPID:
                self._sim_engine.remove_segment(seg, steps_per_mm=1.0)
                self._trail_pts.append([seg.x_start, seg.y_start, seg.z_start])
                self._trail_pts.append([seg.x_end, seg.y_end, seg.z_end])

        last = self._sim_segments[end_idx - 1]
        self._sim_idx = end_idx

        # Update all actors then single render
        self._replace_stock()
        self._replace_tool(last.x_end, last.y_end, last.z_end)
        self._replace_trail()

        pct = 100 * self._sim_idx / len(self._sim_segments)
        status = "Playing" if self._sim_playing else "Paused"
        if self._sim_idx >= len(self._sim_segments):
            status = "Complete"
        self._replace_text(f"[{status}] {pct:.0f}%  ({self._sim_idx}/{len(self._sim_segments)})")

        # Single render for this frame
        self._plotter.render()

        self.sim_progress.emit(self._sim_idx, len(self._sim_segments))
        self.sim_stats.emit(
            self._sim_grid.volume_total,
            self._sim_grid.volume_removed,
            self._sim_grid.volume_remaining,
        )

    # --- Actor management (explicit remove → add to avoid stale mesh) ---

    def _remove_actor(self, which: str) -> None:
        actor = getattr(self, f"_actor_{which}", None)
        if actor is not None:
            try:
                self._plotter.remove_actor(actor)
            except Exception:
                pass
            setattr(self, f"_actor_{which}", None)

    def _replace_stock(self) -> None:
        try:
            mesh = self._sim_engine.to_mesh()
            if mesh is None or mesh.n_cells == 0 or mesh.n_points == 0:
                return

            if self._actor_stock is not None:
                # Update existing actor's mapper data in-place (no flicker)
                mapper = self._actor_stock.GetMapper()
                if mapper is not None:
                    mapper.SetInputData(mesh)
                    mapper.Update()
                    return

            # First time: create actor
            self._actor_stock = self._plotter.add_mesh(
                mesh, color="#4a8db7",
                smooth_shading=True, show_edges=False,
                specular=0.4, specular_power=20,
                diffuse=0.8, ambient=0.15,
                reset_camera=False,
            )
        except Exception:
            pass

    def _replace_tool(self, x: float, y: float, z: float) -> None:
        r = self._sim_tool_diameter / 2 if hasattr(self, '_sim_tool_diameter') else 5
        shape = getattr(self, '_sim_current_tool_shape', ToolShape.FLAT)

        if shape == ToolShape.BALL:
            # Ball endmill: sphere at tip + cylinder shank
            sphere = pv.Sphere(radius=r, center=(x, y, z + r))
            shank = pv.Cylinder(center=(x, y, z + r * 3), direction=(0, 0, 1), radius=r * 0.7, height=r * 4)
            tool_mesh = sphere + shank
            tool_color = "#40c8e8"  # cyan for ball endmill
        else:
            # Flat endmill: cylinder
            tool_mesh = pv.Cylinder(center=(x, y, z + r), direction=(0, 0, 1), radius=r, height=r * 4)
            tool_color = "#e8c840"  # yellow for flat endmill

        if self._actor_tool is not None:
            mapper = self._actor_tool.GetMapper()
            if mapper is not None:
                mapper.SetInputData(tool_mesh)
                mapper.Update()
                # Update color on tool change
                self._actor_tool.GetProperty().SetColor(
                    *pv.Color(tool_color).float_rgb
                )
                return

        self._actor_tool = self._plotter.add_mesh(
            tool_mesh, color=tool_color, opacity=0.8,
            smooth_shading=True, specular=0.6, specular_power=40,
            reset_camera=False,
        )

    def _replace_trail(self) -> None:
        pts_data = self._trail_pts[-600:]
        if len(pts_data) < 4:
            return
        try:
            pts = np.array(pts_data)
            n = len(pts) // 2
            lines = np.zeros((n, 3), dtype=int)
            lines[:, 0] = 2
            lines[:, 1] = np.arange(0, 2 * n, 2)
            lines[:, 2] = np.arange(1, 2 * n, 2)
            trail = pv.PolyData(pts[:2*n], lines=lines.ravel())
            if trail.n_points == 0:
                return

            if self._actor_trail is not None:
                mapper = self._actor_trail.GetMapper()
                if mapper is not None:
                    mapper.SetInputData(trail)
                    mapper.Update()
                    return

            self._actor_trail = self._plotter.add_mesh(
                trail, color="orange", line_width=2,
                reset_camera=False,
            )
        except Exception:
            pass

    def _replace_text(self, text: str) -> None:
        self._remove_actor("text")
        self._actor_text = self._plotter.add_text(
            text, position="upper_left", font_size=11, color="black",
        )
