"""Application entry point for KooCADCAM GUI."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def run() -> None:
    """Launch the KooCADCAM GUI application."""
    app = QApplication(sys.argv)
    app.setApplicationName("KooCADCAM")
    app.setOrganizationName("KooCADCAM")
    app.setApplicationVersion("0.1.0")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run()
