"""CAD parameters panel - configure stock and target geometry with edge features."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QComboBox, QDoubleSpinBox,
)
from PySide6.QtCore import Signal

from ..widgets.param_editor import ParamEditor


STOCK_SCHEMA = {
    "x": {"type": "float", "min": 1, "max": 2000, "default": 100.0, "unit": "mm"},
    "y": {"type": "float", "min": 1, "max": 2000, "default": 100.0, "unit": "mm"},
    "z": {"type": "float", "min": 1, "max": 500, "default": 20.0, "unit": "mm"},
}

TARGET_SCHEMA = {
    "x": {"type": "float", "min": 1, "max": 2000, "default": 60.0, "unit": "mm"},
    "y": {"type": "float", "min": 1, "max": 2000, "default": 60.0, "unit": "mm"},
    "z": {"type": "float", "min": 1, "max": 500, "default": 15.0, "unit": "mm"},
}

# CadQuery edge selector descriptions
EDGE_LOCATIONS = {
    "Top edges (>Z)": ">Z",
    "Bottom edges (<Z)": "<Z",
    "Vertical edges (|Z)": "|Z",
    "All edges": None,
    "Top + Vertical": ">Z_|Z",   # special: apply to both
    "None (disabled)": "NONE",
}


class CadPanel(QWidget):
    """Panel for editing stock and target geometry parameters."""

    params_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout()

        # Stock
        self.stock_editor = ParamEditor(STOCK_SCHEMA, "Stock Material")
        self.stock_editor.value_changed.connect(lambda *_: self.params_changed.emit())
        layout.addWidget(self.stock_editor)

        # Target
        self.target_editor = ParamEditor(TARGET_SCHEMA, "Target Part")
        self.target_editor.value_changed.connect(lambda *_: self.params_changed.emit())
        layout.addWidget(self.target_editor)

        # Edge features group
        edge_group = QGroupBox("Edge Features")
        edge_layout = QVBoxLayout()

        # Feature type: None / Fillet / Chamfer
        row_type = QHBoxLayout()
        row_type.addWidget(QLabel("Type:"))
        self._edge_type = QComboBox()
        self._edge_type.addItems(["Fillet", "Chamfer", "None"])
        self._edge_type.currentIndexChanged.connect(lambda *_: self.params_changed.emit())
        row_type.addWidget(self._edge_type)
        edge_layout.addLayout(row_type)

        # Size (radius for fillet, distance for chamfer)
        row_size = QHBoxLayout()
        row_size.addWidget(QLabel("Size (mm):"))
        self._edge_size = QDoubleSpinBox()
        self._edge_size.setRange(0.1, 50.0)
        self._edge_size.setValue(3.0)
        self._edge_size.setSingleStep(0.5)
        self._edge_size.valueChanged.connect(lambda *_: self.params_changed.emit())
        row_size.addWidget(self._edge_size)
        edge_layout.addLayout(row_size)

        # Edge location
        row_loc = QHBoxLayout()
        row_loc.addWidget(QLabel("Edges:"))
        self._edge_location = QComboBox()
        for label in EDGE_LOCATIONS:
            self._edge_location.addItem(label)
        self._edge_location.currentIndexChanged.connect(lambda *_: self.params_changed.emit())
        row_loc.addWidget(self._edge_location)
        edge_layout.addLayout(row_loc)

        edge_group.setLayout(edge_layout)
        layout.addWidget(edge_group)

        layout.addStretch()
        self.setLayout(layout)

    def get_stock_params(self) -> dict:
        return self.stock_editor.get_values()

    def get_target_params(self) -> dict:
        params = self.target_editor.get_values()
        # Add edge feature params
        edge_type = self._edge_type.currentText()
        params["edge_type"] = edge_type  # "Fillet", "Chamfer", or "None"
        params["edge_size"] = self._edge_size.value()

        loc_label = self._edge_location.currentText()
        params["edge_selector"] = EDGE_LOCATIONS.get(loc_label, ">Z")

        # Backward compat
        if edge_type == "Fillet":
            params["fillet_radius"] = self._edge_size.value()
        else:
            params["fillet_radius"] = 0
        return params
