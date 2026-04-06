"""Tool selection widget with preset library."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QGroupBox, QDoubleSpinBox,
)
from PySide6.QtCore import Signal

from ...cam.tools import TOOL_LIBRARY, CuttingTool


class ToolSelector(QWidget):
    """Widget for selecting CNC cutting tools from the preset library."""

    tool_changed = Signal(str)  # tool key

    def __init__(self, label: str = "Select Tool", parent: QWidget | None = None):
        super().__init__(parent)
        self._current_key: str = ""
        self._setup_ui(label)

    def _setup_ui(self, label: str) -> None:
        group = QGroupBox(label)
        layout = QVBoxLayout()

        # Combo box for presets
        row = QHBoxLayout()
        row.addWidget(QLabel("Preset:"))
        self._combo = QComboBox()
        for key, tool in TOOL_LIBRARY.items():
            self._combo.addItem(f"{tool.name} (D{tool.diameter})", key)
        self._combo.currentIndexChanged.connect(self._on_selection_changed)
        row.addWidget(self._combo)
        layout.addLayout(row)

        # Info display
        self._info_label = QLabel("")
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        layout.addStretch()
        group.setLayout(layout)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(group)
        self.setLayout(main_layout)

        # Trigger initial selection
        if self._combo.count() > 0:
            self._on_selection_changed(0)

    def _on_selection_changed(self, index: int) -> None:
        key = self._combo.itemData(index)
        if key and key in TOOL_LIBRARY:
            self._current_key = key
            tool = TOOL_LIBRARY[key]
            self._info_label.setText(
                f"Type: {tool.tool_type.value}\n"
                f"Diameter: {tool.diameter} mm\n"
                f"Flute Length: {tool.flute_length} mm\n"
                f"Flutes: {tool.flutes}\n"
                f"Tool #: T{tool.tool_number:02d}"
            )
            self.tool_changed.emit(key)

    def get_selected_tool(self) -> CuttingTool | None:
        if self._current_key in TOOL_LIBRARY:
            return TOOL_LIBRARY[self._current_key]
        return None
