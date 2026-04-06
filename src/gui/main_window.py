"""Main application window for KooCADCAM."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTabWidget, QSplitter, QToolBar, QStatusBar,
    QMessageBox, QFileDialog, QLabel,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QIcon

from .viewport_3d import Viewport3D
from .panels.cad_panel import CadPanel
from .panels.cam_panel import CamPanel
from .panels.library_panel import LibraryPanel
from .panels.gcode_panel import GcodePanel
from .panels.machine_panel import MachinePanel
from .panels.sim_panel import SimPanel
from .themes.dark import DARK_STYLESHEET

from ..core.events import EventBus
from ..cad.primitives import create_box
from ..cad.operations import apply_fillet, apply_chamfer
from ..cad.exporter import export_step, export_stl
from ..cam.stock import Stock
from ..cam.tools import CuttingTool, TOOL_LIBRARY
from ..cam.toolpath import (
    FacingStrategy, PocketStrategy, ProfileStrategy, FilletStrategy,
)
from ..cam.gcode_writer import GcodeWriter
from ..cam.postprocessor import get_postprocessor
from ..cam.optimizer import optimize_all
from ..cam.collision import check_all
from ..sim.gcode_parser import GcodeParser


class MainWindow(QMainWindow):
    """KooCADCAM main application window.

    Layout:
    ┌─────────────────────────────────────────────────┐
    │  Toolbar                                        │
    ├──────────┬──────────────────────┬───────────────┤
    │          │                      │               │
    │  Left    │   3D Viewport        │               │
    │  Panel   │   (center)           │               │
    │  Tabs    │                      │               │
    │          ├──────────────────────┘               │
    │          │   G-code Panel (bottom)              │
    ├──────────┴──────────────────────────────────────┤
    │  Status Bar                                      │
    └─────���───────────────────────────────────────────┘
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("KooCADCAM - Parametric CAD/CAM Automation")
        self.setMinimumSize(1400, 900)
        self.setStyleSheet(DARK_STYLESHEET)

        self._bus = EventBus()
        self._output_dir = Path("output")

        self._setup_toolbar()
        self._setup_central()
        self._setup_statusbar()
        self._setup_menu()

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Open Config...", self._on_open_config)
        file_menu.addSeparator()
        file_menu.addAction("Export STEP...", self._on_export_step)
        file_menu.addAction("Export G-code...", lambda: self._gcode_panel._on_export())
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # View menu
        view_menu = menubar.addMenu("View")
        view_menu.addAction("Reset Camera", lambda: self._viewport.reset_camera())
        view_menu.addAction("Screenshot...", self._on_screenshot)

        # Help menu
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self._on_about)

    def _setup_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._btn_generate_cad = toolbar.addAction("Generate CAD")
        self._btn_generate_cad.triggered.connect(self._on_generate_cad)

        self._btn_generate_gcode = toolbar.addAction("Generate G-code")
        self._btn_generate_gcode.triggered.connect(self._on_generate_gcode)

        toolbar.addSeparator()

        self._btn_run_all = toolbar.addAction("Run All")
        self._btn_run_all.triggered.connect(self._on_run_all)

        toolbar.addSeparator()

        self._btn_simulate = toolbar.addAction("Simulate")
        self._btn_simulate.triggered.connect(self._on_sim_play)

        toolbar.addSeparator()

        self._btn_export_step = toolbar.addAction("Export STEP")
        self._btn_export_step.triggered.connect(self._on_export_step)

    def _setup_central(self) -> None:
        # Main splitter: left panel | center+bottom
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel tabs
        self._left_tabs = QTabWidget()
        self._cad_panel = CadPanel()
        self._cam_panel = CamPanel()
        self._library_panel = LibraryPanel()
        self._machine_panel = MachinePanel()
        self._sim_panel = SimPanel()
        self._left_tabs.addTab(self._cad_panel, "CAD")
        self._left_tabs.addTab(self._cam_panel, "CAM")
        self._left_tabs.addTab(self._library_panel, "Library")
        self._left_tabs.addTab(self._machine_panel, "Machine")
        self._left_tabs.addTab(self._sim_panel, "Simulate")
        self._left_tabs.setMinimumWidth(320)
        self._left_tabs.setMaximumWidth(420)

        # Right area: viewport on top, gcode on bottom
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        self._viewport = Viewport3D()
        self._gcode_panel = GcodePanel()
        self._gcode_panel.setMaximumHeight(250)
        right_splitter.addWidget(self._viewport)
        right_splitter.addWidget(self._gcode_panel)
        right_splitter.setSizes([700, 200])

        main_splitter.addWidget(self._left_tabs)
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([350, 1050])

        self.setCentralWidget(main_splitter)

        # Connect simulation panel signals to viewport
        self._sim_panel.play_clicked.connect(self._on_sim_play)
        self._sim_panel.pause_clicked.connect(self._viewport.sim_pause)
        self._sim_panel.stop_clicked.connect(self._viewport.sim_stop)
        self._sim_panel.step_clicked.connect(self._viewport.sim_step)
        self._sim_panel.speed_changed.connect(self._viewport.sim_set_speed)
        self._viewport.sim_progress.connect(self._sim_panel.set_progress)
        self._viewport.sim_stats.connect(
            lambda t, r, rem: self._sim_panel.set_statistics(t, r, rem, 0)
        )
        self._viewport.sim_finished.connect(
            lambda: self._statusbar.showMessage("Simulation complete!")
        )

    def _setup_statusbar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Ready")

    # --- Actions ---

    def _on_generate_cad(self) -> None:
        try:
            self._statusbar.showMessage("Generating CAD model...")
            target = self._cad_panel.get_target_params()
            stock_p = self._cad_panel.get_stock_params()

            # Create target solid with edge features
            solid = create_box(target["x"], target["y"], target["z"])
            edge_type = target.get("edge_type", "None")
            edge_size = target.get("edge_size", 0)
            edge_sel = target.get("edge_selector", ">Z")

            if edge_type != "None" and edge_size > 0 and edge_sel != "NONE":
                if edge_sel == ">Z_|Z":
                    # Apply to both top and vertical edges
                    if edge_type == "Fillet":
                        solid = apply_fillet(solid, edge_size, ">Z")
                        solid = apply_fillet(solid, edge_size, "|Z")
                    else:
                        solid = apply_chamfer(solid, edge_size, ">Z")
                        solid = apply_chamfer(solid, edge_size, "|Z")
                else:
                    if edge_type == "Fillet":
                        solid = apply_fillet(solid, edge_size, edge_sel)
                    else:
                        solid = apply_chamfer(solid, edge_size, edge_sel)

            # Export
            step_path = self._output_dir / "step" / "part.step"
            stl_path = self._output_dir / "step" / "part.stl"
            export_step(solid, step_path)
            export_stl(solid, stl_path)

            # Update viewport
            self._viewport.clear()
            self._viewport.show_stock(stock_p["x"], stock_p["y"], stock_p["z"])
            self._viewport.show_cad_mesh(str(stl_path))
            self._viewport.reset_camera()

            self._statusbar.showMessage(f"CAD generated: {step_path}")
        except Exception as e:
            self._show_error("CAD Generation Error", e)

    def _on_generate_gcode(self) -> None:
        try:
            self._statusbar.showMessage("Generating G-code...")
            stock_p = self._cad_panel.get_stock_params()
            target_p = self._cad_panel.get_target_params()
            cutting = self._cam_panel.get_cutting_params()
            post_name = self._cam_panel.get_postprocessor_name()

            stock = Stock(stock_p["x"], stock_p["y"], stock_p["z"])
            target_bounds = {
                "x_min": -target_p["x"] / 2, "x_max": target_p["x"] / 2,
                "y_min": -target_p["y"] / 2, "y_max": target_p["y"] / 2,
            }

            # Get tools
            roughing = self._cam_panel.roughing_tool.get_selected_tool()
            finishing = self._cam_panel.finishing_tool.get_selected_tool()
            if not roughing:
                roughing = TOOL_LIBRARY["flat_10mm"]
            if not finishing:
                finishing = TOOL_LIBRARY["ball_6mm"]

            # Generate toolpaths
            segments = []

            # 1. Facing
            facing = FacingStrategy()
            segments.extend(facing.generate(
                tool=roughing,
                stock_bounds=stock.bounds,
                target_z=target_p["z"],
                depth_per_pass=cutting["depth_per_pass"],
                stepover_ratio=cutting["stepover_ratio"],
                feed_rate=cutting["feed_rate"],
                plunge_rate=cutting["plunge_rate"],
                spindle_rpm=int(cutting["spindle_rpm"]),
            ))

            # 2. Pocket (remove material around target)
            pocket = PocketStrategy()
            segments.extend(pocket.generate(
                tool=roughing,
                stock_bounds=stock.bounds,
                target_bounds=target_bounds,
                z_top=target_p["z"],
                z_bottom=0,
                depth_per_pass=cutting["depth_per_pass"],
                stepover_ratio=cutting["stepover_ratio"],
                feed_rate=cutting["feed_rate"],
                plunge_rate=cutting["plunge_rate"],
                spindle_rpm=int(cutting["spindle_rpm"]),
            ))

            # 3. Fillet
            fillet_r = target_p.get("fillet_radius", 0)
            if fillet_r > 0:
                fillet = FilletStrategy()
                segments.extend(fillet.generate(
                    tool=finishing,
                    target_bounds=target_bounds,
                    target_z=target_p["z"],
                    fillet_radius=fillet_r,
                    feed_rate=cutting["feed_rate"] * 0.6,
                    spindle_rpm=int(cutting["spindle_rpm"]),
                ))

            # Optimize toolpaths
            segments, opt_report = optimize_all(segments, base_feed=cutting["feed_rate"])

            # Collision check
            col_report = check_all(segments, stock.bounds, target_z_min=0.0)
            if col_report.has_errors:
                self._statusbar.showMessage(f"Warning: {col_report.error_count} collision errors detected!")

            # Write G-code
            post = get_postprocessor(post_name)
            writer = GcodeWriter(post)
            gcode_path = self._output_dir / "gcode" / f"part{post.file_extension}"
            gcode_text = writer.generate(segments)
            writer.save(segments, gcode_path)

            # Update panels
            self._gcode_panel.set_gcode(gcode_text)

            # Parse and visualize
            parser = GcodeParser()
            parsed = parser.parse_text(gcode_text)

            self._viewport.clear()
            self._viewport.show_stock(stock_p["x"], stock_p["y"], stock_p["z"])
            self._viewport.show_target(target_p["x"], target_p["y"], target_p["z"])
            self._viewport.show_toolpath(parsed)
            self._viewport.reset_camera()

            self._statusbar.showMessage(f"G-code generated: {gcode_path} ({len(parsed)} moves)")
        except Exception as e:
            self._show_error("G-code Generation Error", e)

    def _on_run_all(self) -> None:
        self._on_generate_cad()
        self._on_generate_gcode()

    def _on_sim_play(self) -> None:
        """Start cutting simulation in the 3D viewport."""
        try:
            gcode = self._gcode_panel.get_gcode()
            if not gcode.strip():
                self._on_generate_gcode()
                gcode = self._gcode_panel.get_gcode()
            if not gcode.strip():
                self._statusbar.showMessage("Generate G-code first!")
                return

            stock_p = self._cad_panel.get_stock_params()
            resolution = self._sim_panel._resolution.value()
            speed = self._sim_panel._speed_slider.value()

            roughing = self._cam_panel.roughing_tool.get_selected_tool()
            finishing = self._cam_panel.finishing_tool.get_selected_tool()
            tool_dia = roughing.diameter if roughing else 10.0

            # Build tool table for multi-tool simulation
            tools = []
            if roughing:
                tools.append({
                    "tool_number": roughing.tool_number,
                    "diameter": roughing.diameter,
                    "type": roughing.tool_type.value,
                })
            if finishing:
                tools.append({
                    "tool_number": finishing.tool_number,
                    "diameter": finishing.diameter,
                    "type": finishing.tool_type.value,
                })

            self._viewport.sim_setup(
                gcode_text=gcode,
                stock_dims=(stock_p["x"], stock_p["y"], stock_p["z"]),
                tool_diameter=tool_dia,
                resolution=resolution,
                tools=tools,
            )
            self._viewport.sim_set_speed(speed)
            self._viewport.sim_play()

            self._left_tabs.setCurrentWidget(self._sim_panel)
            self._statusbar.showMessage("Simulation playing...")
        except Exception as e:
            self._show_error("Simulation Error", e)

    def _on_export_step(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export STEP", "", "STEP Files (*.step *.stp);;All Files (*)"
        )
        if path:
            try:
                target = self._cad_panel.get_target_params()
                solid = create_box(target["x"], target["y"], target["z"])
                fillet_r = target.get("fillet_radius", 0)
                if fillet_r > 0:
                    solid = apply_fillet(solid, fillet_r, ">Z")
                export_step(solid, path)
                self._statusbar.showMessage(f"STEP exported: {path}")
            except Exception as e:
                self._show_error("Export Error", e)

    def _on_open_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Config", "", "YAML Files (*.yaml *.yml);;All Files (*)"
        )
        if path:
            self._statusbar.showMessage(f"Config loaded: {path}")

    def _on_screenshot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Screenshot", "", "PNG Images (*.png);;All Files (*)"
        )
        if path:
            self._viewport.screenshot(path)
            self._statusbar.showMessage(f"Screenshot saved: {path}")

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About KooCADCAM",
            "KooCADCAM v0.1.0\n\n"
            "Parametric CAD/CAM Automation System\n\n"
            "Features:\n"
            "- CadQuery parametric modeling\n"
            "- Module library (holes, pockets, slots)\n"
            "- Multi-strategy toolpath generation\n"
            "- 4 CNC post-processors (FANUC, Siemens, Haas, GRBL)\n"
            "- 3D visualization with PyVista\n\n"
            "Cross-platform: Linux / macOS / Windows"
        )

    def _show_error(self, title: str, error: Exception) -> None:
        self._statusbar.showMessage(f"Error: {error}")
        QMessageBox.critical(
            self, title,
            f"{error}\n\n{traceback.format_exc()}"
        )
