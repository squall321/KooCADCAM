"""Machine connection and real-time status dashboard panel."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QGroupBox, QComboBox, QPushButton, QLineEdit,
    QProgressBar, QFrame,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont

from ...cnc.base import CncConnection, ConnectionState, MachineStatus


class StatusLED(QFrame):
    """Small colored LED indicator widget."""

    def __init__(self, size: int = 14, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = "gray"
        self._update_style()

    def set_color(self, color: str) -> None:
        self._color = color
        self._update_style()

    def _update_style(self) -> None:
        r = self.width() // 2
        self.setStyleSheet(
            f"background-color: {self._color}; "
            f"border-radius: {r}px; "
            f"border: 1px solid #45475a;"
        )


class DROWidget(QWidget):
    """Digital Readout widget for a single axis."""

    def __init__(self, axis: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)

        label = QLabel(axis)
        label.setFixedWidth(20)
        label.setStyleSheet("color: #89b4fa; font-weight: bold; font-size: 14px;")
        layout.addWidget(label)

        self._value = QLabel("0.000")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._value.setStyleSheet(
            "font-family: 'JetBrains Mono', 'Consolas', monospace; "
            "font-size: 18px; color: #a6e3a1; "
            "background-color: #11111b; padding: 4px 8px; "
            "border: 1px solid #313244; border-radius: 3px;"
        )
        layout.addWidget(self._value)
        self.setLayout(layout)

    def set_value(self, val: float) -> None:
        self._value.setText(f"{val:+10.3f}")


class MachinePanel(QWidget):
    """Real-time machine status dashboard.

    Shows:
    - Connection status and controls
    - DRO (Digital Readout) for X/Y/Z/A/B
    - Spindle RPM and feed rate
    - Program progress
    - Override percentages
    """

    connection_requested = Signal(str, str)  # (type, address)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._connection: CncConnection | None = None
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll_status)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        # --- Connection group ---
        conn_group = QGroupBox("Connection")
        conn_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        self._led = StatusLED()
        row1.addWidget(self._led)
        self._status_label = QLabel("Disconnected")
        row1.addWidget(self._status_label)
        row1.addStretch()
        conn_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self._type_combo = QComboBox()
        self._type_combo.addItems(["Simulator", "GRBL Serial", "LinuxCNC", "OPC UA", "MTConnect"])
        row2.addWidget(self._type_combo)
        self._addr_edit = QLineEdit("/dev/ttyUSB0")
        self._addr_edit.setPlaceholderText("Address / Port")
        row2.addWidget(self._addr_edit)
        conn_layout.addLayout(row2)

        row3 = QHBoxLayout()
        self._btn_connect = QPushButton("Connect")
        self._btn_connect.clicked.connect(self._on_connect)
        row3.addWidget(self._btn_connect)
        self._btn_disconnect = QPushButton("Disconnect")
        self._btn_disconnect.clicked.connect(self._on_disconnect)
        self._btn_disconnect.setEnabled(False)
        row3.addWidget(self._btn_disconnect)
        conn_layout.addLayout(row3)

        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # --- DRO group ---
        dro_group = QGroupBox("Position (DRO)")
        dro_layout = QVBoxLayout()
        self._dro_x = DROWidget("X")
        self._dro_y = DROWidget("Y")
        self._dro_z = DROWidget("Z")
        self._dro_a = DROWidget("A")
        self._dro_b = DROWidget("B")
        dro_layout.addWidget(self._dro_x)
        dro_layout.addWidget(self._dro_y)
        dro_layout.addWidget(self._dro_z)
        dro_layout.addWidget(self._dro_a)
        dro_layout.addWidget(self._dro_b)
        dro_group.setLayout(dro_layout)
        layout.addWidget(dro_group)

        # --- Spindle / Feed ---
        sf_group = QGroupBox("Spindle / Feed")
        sf_layout = QGridLayout()
        sf_layout.addWidget(QLabel("Spindle:"), 0, 0)
        self._spindle_label = QLabel("0 rpm")
        self._spindle_label.setStyleSheet("font-size: 14px; color: #f9e2af; font-weight: bold;")
        sf_layout.addWidget(self._spindle_label, 0, 1)
        sf_layout.addWidget(QLabel("Override:"), 0, 2)
        self._spindle_ovr = QLabel("100%")
        sf_layout.addWidget(self._spindle_ovr, 0, 3)

        sf_layout.addWidget(QLabel("Feed:"), 1, 0)
        self._feed_label = QLabel("0 mm/min")
        self._feed_label.setStyleSheet("font-size: 14px; color: #fab387; font-weight: bold;")
        sf_layout.addWidget(self._feed_label, 1, 1)
        sf_layout.addWidget(QLabel("Override:"), 1, 2)
        self._feed_ovr = QLabel("100%")
        sf_layout.addWidget(self._feed_ovr, 1, 3)
        sf_group.setLayout(sf_layout)
        layout.addWidget(sf_group)

        # --- Program progress ---
        prog_group = QGroupBox("Program")
        prog_layout = QVBoxLayout()
        self._prog_name = QLabel("No program")
        prog_layout.addWidget(self._prog_name)
        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 100)
        prog_layout.addWidget(self._prog_bar)
        self._prog_line = QLabel("Line: 0 / 0")
        prog_layout.addWidget(self._prog_line)
        prog_group.setLayout(prog_layout)
        layout.addWidget(prog_group)

        # --- Control buttons ---
        ctrl_group = QGroupBox("Control")
        ctrl_layout = QHBoxLayout()
        self._btn_start = QPushButton("Start")
        self._btn_start.clicked.connect(self._on_start)
        self._btn_pause = QPushButton("Pause")
        self._btn_pause.clicked.connect(self._on_pause)
        self._btn_stop = QPushButton("Stop")
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.setStyleSheet("background-color: #f38ba8; color: #1e1e2e;")
        ctrl_layout.addWidget(self._btn_start)
        ctrl_layout.addWidget(self._btn_pause)
        ctrl_layout.addWidget(self._btn_stop)
        ctrl_group.setLayout(ctrl_layout)
        layout.addWidget(ctrl_group)

        layout.addStretch()
        self.setLayout(layout)

    def set_connection(self, connection: CncConnection) -> None:
        self._connection = connection

    def _on_connect(self) -> None:
        conn_type = self._type_combo.currentText()
        addr = self._addr_edit.text()
        self.connection_requested.emit(conn_type, addr)

        if conn_type == "Simulator":
            from ...cnc.simulator import SoftSimulator
            self._connection = SoftSimulator(speed_factor=10.0)
            self._connection.connect()

        if self._connection and self._connection.state == ConnectionState.CONNECTED:
            self._led.set_color("#a6e3a1")
            self._status_label.setText("Connected")
            self._btn_connect.setEnabled(False)
            self._btn_disconnect.setEnabled(True)
            self._poll_timer.start(100)  # 10Hz updates

    def _on_disconnect(self) -> None:
        self._poll_timer.stop()
        if self._connection:
            self._connection.disconnect()
        self._led.set_color("gray")
        self._status_label.setText("Disconnected")
        self._btn_connect.setEnabled(True)
        self._btn_disconnect.setEnabled(False)

    def _on_start(self) -> None:
        if self._connection:
            self._connection.start()

    def _on_pause(self) -> None:
        if self._connection:
            if self._connection.state == ConnectionState.PAUSED:
                self._connection.resume()
            else:
                self._connection.pause()

    def _on_stop(self) -> None:
        if self._connection:
            self._connection.stop()

    def _poll_status(self) -> None:
        if not self._connection:
            return

        status = self._connection.get_status()
        self._update_display(status)

    def _update_display(self, status: MachineStatus) -> None:
        # LED color
        color_map = {
            ConnectionState.CONNECTED: "#a6e3a1",
            ConnectionState.RUNNING: "#89b4fa",
            ConnectionState.PAUSED: "#f9e2af",
            ConnectionState.ALARM: "#f38ba8",
            ConnectionState.ERROR: "#f38ba8",
            ConnectionState.DISCONNECTED: "gray",
        }
        self._led.set_color(color_map.get(status.state, "gray"))
        self._status_label.setText(status.state.value.title())

        # DRO
        self._dro_x.set_value(status.work_position.x)
        self._dro_y.set_value(status.work_position.y)
        self._dro_z.set_value(status.work_position.z)
        self._dro_a.set_value(status.work_position.a)
        self._dro_b.set_value(status.work_position.b)

        # Spindle / Feed
        self._spindle_label.setText(f"{status.spindle_rpm:.0f} rpm")
        self._spindle_ovr.setText(f"{status.spindle_override:.0f}%")
        self._feed_label.setText(f"{status.feed_rate:.0f} mm/min")
        self._feed_ovr.setText(f"{status.feed_override:.0f}%")

        # Progress
        self._prog_name.setText(status.program_name or "No program")
        self._prog_bar.setValue(int(status.progress_pct))
        self._prog_line.setText(f"Line: {status.current_line} / {status.total_lines}")
