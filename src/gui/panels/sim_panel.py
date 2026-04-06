"""Simulation control panel with voxel visualization controls."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QSlider, QDoubleSpinBox, QCheckBox, QProgressBar,
)
from PySide6.QtCore import Qt, Signal


class SimPanel(QWidget):
    """Simulation control panel.

    Controls:
    - Play/Pause/Stop/Step simulation
    - Speed factor slider
    - Voxel resolution setting
    - Gouge/overcut highlight toggle
    - Material removal statistics
    """

    play_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    step_clicked = Signal()
    speed_changed = Signal(float)
    resolution_changed = Signal(float)
    show_gouge_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        # --- Playback controls ---
        play_group = QGroupBox("Simulation Playback")
        play_layout = QVBoxLayout()

        btn_row = QHBoxLayout()
        self._btn_play = QPushButton("Play")
        self._btn_play.clicked.connect(self.play_clicked.emit)
        self._btn_pause = QPushButton("Pause")
        self._btn_pause.clicked.connect(self.pause_clicked.emit)
        self._btn_stop = QPushButton("Stop")
        self._btn_stop.clicked.connect(self.stop_clicked.emit)
        self._btn_step = QPushButton("Step")
        self._btn_step.clicked.connect(self.step_clicked.emit)
        btn_row.addWidget(self._btn_play)
        btn_row.addWidget(self._btn_pause)
        btn_row.addWidget(self._btn_stop)
        btn_row.addWidget(self._btn_step)
        play_layout.addLayout(btn_row)

        # Speed slider
        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Speed:"))
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(1, 100)
        self._speed_slider.setValue(10)
        self._speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_row.addWidget(self._speed_slider)
        self._speed_label = QLabel("10x")
        self._speed_label.setFixedWidth(40)
        speed_row.addWidget(self._speed_label)
        play_layout.addLayout(speed_row)

        # Progress
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        play_layout.addWidget(self._progress)
        self._progress_label = QLabel("0 / 0 moves")
        play_layout.addWidget(self._progress_label)

        play_group.setLayout(play_layout)
        layout.addWidget(play_group)

        # --- Voxel settings ---
        voxel_group = QGroupBox("Voxel Simulation")
        voxel_layout = QVBoxLayout()

        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("Resolution (mm):"))
        self._resolution = QDoubleSpinBox()
        self._resolution.setRange(0.1, 5.0)
        self._resolution.setValue(0.5)
        self._resolution.setSingleStep(0.1)
        self._resolution.valueChanged.connect(lambda v: self.resolution_changed.emit(v))
        res_row.addWidget(self._resolution)
        voxel_layout.addLayout(res_row)

        self._show_gouge = QCheckBox("Highlight gouge/overcut")
        self._show_gouge.setChecked(True)
        self._show_gouge.toggled.connect(self.show_gouge_changed.emit)
        voxel_layout.addWidget(self._show_gouge)

        voxel_group.setLayout(voxel_layout)
        layout.addWidget(voxel_group)

        # --- Statistics ---
        stats_group = QGroupBox("Material Removal Statistics")
        stats_layout = QVBoxLayout()
        self._stat_total = QLabel("Total stock volume: --")
        self._stat_removed = QLabel("Material removed: --")
        self._stat_remaining = QLabel("Remaining: --")
        self._stat_gouge = QLabel("Gouge events: 0")
        self._stat_gouge.setStyleSheet("color: #f38ba8;")
        stats_layout.addWidget(self._stat_total)
        stats_layout.addWidget(self._stat_removed)
        stats_layout.addWidget(self._stat_remaining)
        stats_layout.addWidget(self._stat_gouge)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        layout.addStretch()
        self.setLayout(layout)

    def _on_speed_changed(self, value: int) -> None:
        self._speed_label.setText(f"{value}x")
        self.speed_changed.emit(float(value))

    def set_progress(self, current: int, total: int) -> None:
        pct = int(100 * current / max(total, 1))
        self._progress.setValue(pct)
        self._progress_label.setText(f"{current} / {total} moves")

    def set_statistics(
        self,
        total_volume: float,
        removed_volume: float,
        remaining_volume: float,
        gouge_count: int,
    ) -> None:
        self._stat_total.setText(f"Total stock volume: {total_volume:.1f} mm\u00b3")
        self._stat_removed.setText(f"Material removed: {removed_volume:.1f} mm\u00b3")
        self._stat_remaining.setText(f"Remaining: {remaining_volume:.1f} mm\u00b3")
        self._stat_gouge.setText(f"Gouge events: {gouge_count}")
