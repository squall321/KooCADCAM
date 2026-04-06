"""Dynamic parameter editor widget - auto-generates UI from param schemas."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit, QGroupBox,
)
from PySide6.QtCore import Signal


class ParamEditor(QWidget):
    """Generates a form UI from a parameter schema dict.

    Schema format:
        {"param_name": {"type": "float", "min": 0, "max": 100, "default": 10, "unit": "mm"}}

    Supported types: float, int, enum, str
    """

    value_changed = Signal(str, object)  # (param_name, new_value)

    def __init__(self, schema: dict[str, dict[str, Any]], title: str = "Parameters", parent: QWidget | None = None):
        super().__init__(parent)
        self._schema = schema
        self._widgets: dict[str, QWidget] = {}
        self._setup_ui(title)

    def _setup_ui(self, title: str) -> None:
        group = QGroupBox(title)
        layout = QVBoxLayout()

        for name, spec in self._schema.items():
            row = QHBoxLayout()
            label_text = name.replace("_", " ").title()
            if "unit" in spec:
                label_text += f" ({spec['unit']})"
            row.addWidget(QLabel(label_text))

            ptype = spec.get("type", "float")
            if ptype == "float":
                w = QDoubleSpinBox()
                w.setRange(spec.get("min", 0), spec.get("max", 99999))
                w.setValue(spec.get("default", 0))
                w.setDecimals(spec.get("decimals", 2))
                w.setSingleStep(spec.get("step", 0.1))
                w.valueChanged.connect(lambda val, n=name: self.value_changed.emit(n, val))
            elif ptype == "int":
                w = QSpinBox()
                w.setRange(spec.get("min", 0), spec.get("max", 99999))
                w.setValue(spec.get("default", 0))
                w.valueChanged.connect(lambda val, n=name: self.value_changed.emit(n, val))
            elif ptype == "enum":
                w = QComboBox()
                w.addItems(spec.get("values", []))
                default = spec.get("default", "")
                idx = w.findText(default)
                if idx >= 0:
                    w.setCurrentIndex(idx)
                w.currentTextChanged.connect(lambda val, n=name: self.value_changed.emit(n, val))
            else:
                w = QLineEdit(str(spec.get("default", "")))
                w.textChanged.connect(lambda val, n=name: self.value_changed.emit(n, val))

            row.addWidget(w)
            layout.addLayout(row)
            self._widgets[name] = w

        layout.addStretch()
        group.setLayout(layout)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(group)
        self.setLayout(main_layout)

    def get_values(self) -> dict[str, Any]:
        """Get all current parameter values."""
        values = {}
        for name, widget in self._widgets.items():
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                values[name] = widget.value()
            elif isinstance(widget, QComboBox):
                values[name] = widget.currentText()
            elif isinstance(widget, QLineEdit):
                values[name] = widget.text()
        return values

    def set_values(self, values: dict[str, Any]) -> None:
        """Set parameter values programmatically."""
        for name, val in values.items():
            widget = self._widgets.get(name)
            if widget is None:
                continue
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                widget.setValue(val)
            elif isinstance(widget, QComboBox):
                idx = widget.findText(str(val))
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            elif isinstance(widget, QLineEdit):
                widget.setText(str(val))
