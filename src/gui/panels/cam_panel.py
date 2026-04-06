"""CAM settings panel - cutting parameters and post-processor selection."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QGroupBox,
)
from PySide6.QtCore import Signal

from ..widgets.param_editor import ParamEditor
from ..widgets.tool_selector import ToolSelector
from ...cam.postprocessor import POSTPROCESSORS


CUTTING_SCHEMA = {
    "spindle_rpm": {"type": "int", "min": 100, "max": 30000, "default": 8000, "unit": "rpm"},
    "feed_rate": {"type": "float", "min": 10, "max": 10000, "default": 500.0, "unit": "mm/min"},
    "plunge_rate": {"type": "float", "min": 10, "max": 5000, "default": 200.0, "unit": "mm/min"},
    "depth_per_pass": {"type": "float", "min": 0.1, "max": 50, "default": 2.0, "unit": "mm"},
    "stepover_ratio": {"type": "float", "min": 0.05, "max": 1.0, "default": 0.4, "step": 0.05},
}


class CamPanel(QWidget):
    """Panel for CAM settings: tools, cutting params, post-processor."""

    params_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout()

        # Roughing tool selector
        self.roughing_tool = ToolSelector("Roughing Tool")
        self.roughing_tool.tool_changed.connect(lambda *_: self.params_changed.emit())
        layout.addWidget(self.roughing_tool)

        # Finishing tool selector
        self.finishing_tool = ToolSelector("Finishing Tool")
        self.finishing_tool.tool_changed.connect(lambda *_: self.params_changed.emit())
        layout.addWidget(self.finishing_tool)

        # Cutting parameters
        self.cutting_editor = ParamEditor(CUTTING_SCHEMA, "Cutting Parameters")
        self.cutting_editor.value_changed.connect(lambda *_: self.params_changed.emit())
        layout.addWidget(self.cutting_editor)

        # Post-processor selection
        post_group = QGroupBox("Post-Processor")
        post_layout = QHBoxLayout()
        post_layout.addWidget(QLabel("Controller:"))
        self._post_combo = QComboBox()
        for key in POSTPROCESSORS:
            self._post_combo.addItem(key.upper(), key)
        self._post_combo.currentIndexChanged.connect(lambda *_: self.params_changed.emit())
        post_layout.addWidget(self._post_combo)
        post_group.setLayout(post_layout)
        layout.addWidget(post_group)

        layout.addStretch()
        self.setLayout(layout)

    def get_cutting_params(self) -> dict:
        return self.cutting_editor.get_values()

    def get_postprocessor_name(self) -> str:
        return self._post_combo.currentData() or "fanuc"
