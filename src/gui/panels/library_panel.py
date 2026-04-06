"""Module library browser panel."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel,
)
from PySide6.QtCore import Signal

from ...cad.library import (
    ThroughHole, CounterboreHole, CountersinkHole, TappedHole,
    RectPocket, CircularPocket, ObroundPocket,
    TSlot, Dovetail, KeySlot,
)


# Registry of available modules
MODULE_REGISTRY = {
    "Holes": {
        "Through Hole": ThroughHole,
        "Counterbore Hole": CounterboreHole,
        "Countersink Hole": CountersinkHole,
        "Tapped Hole": TappedHole,
    },
    "Pockets": {
        "Rectangular Pocket": RectPocket,
        "Circular Pocket": CircularPocket,
        "Obround Pocket": ObroundPocket,
    },
    "Slots": {
        "T-Slot": TSlot,
        "Dovetail": Dovetail,
        "Keyway Slot": KeySlot,
    },
}


class LibraryPanel(QWidget):
    """Browse and select parametric modules from the library."""

    module_selected = Signal(str, str)  # (category, module_name)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Module Library"))

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Module", "Type"])
        self._tree.setColumnCount(2)
        self._populate_tree()
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.expandAll()
        layout.addWidget(self._tree)

        self._info = QLabel("Select a module to view details")
        self._info.setWordWrap(True)
        layout.addWidget(self._info)

        self.setLayout(layout)

    def _populate_tree(self) -> None:
        for category, modules in MODULE_REGISTRY.items():
            cat_item = QTreeWidgetItem([category, ""])
            self._tree.addTopLevelItem(cat_item)
            for name, cls in modules.items():
                child = QTreeWidgetItem([name, cls.__name__])
                cat_item.addChild(child)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        parent = item.parent()
        if parent is None:
            return
        category = parent.text(0)
        module_name = item.text(0)
        cls = MODULE_REGISTRY.get(category, {}).get(module_name)
        if cls:
            schema = cls.get_param_schema()
            info_lines = [f"Module: {module_name}", f"Class: {cls.__name__}", ""]
            if schema:
                info_lines.append("Parameters:")
                for pname, pspec in schema.items():
                    info_lines.append(
                        f"  {pname}: {pspec.get('type', '?')} "
                        f"[{pspec.get('min', '')}-{pspec.get('max', '')}] "
                        f"default={pspec.get('default', '')}"
                    )
            self._info.setText("\n".join(info_lines))
            self.module_selected.emit(category, module_name)
