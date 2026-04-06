"""G-code viewer panel with syntax highlighting."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QFileDialog,
)
from PySide6.QtGui import QTextCharFormat, QColor, QFont, QSyntaxHighlighter, QTextDocument
from PySide6.QtCore import Signal

import re


class GcodeSyntaxHighlighter(QSyntaxHighlighter):
    """Simple syntax highlighter for G-code."""

    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = []

        # G-codes (green)
        fmt_g = QTextCharFormat()
        fmt_g.setForeground(QColor("#a6e3a1"))
        fmt_g.setFontWeight(QFont.Weight.Bold)
        self._rules.append((re.compile(r"\bG\d+\.?\d*\b"), fmt_g))

        # M-codes (purple)
        fmt_m = QTextCharFormat()
        fmt_m.setForeground(QColor("#cba6f7"))
        fmt_m.setFontWeight(QFont.Weight.Bold)
        self._rules.append((re.compile(r"\bM\d+\b"), fmt_m))

        # Coordinates X Y Z (blue)
        fmt_coord = QTextCharFormat()
        fmt_coord.setForeground(QColor("#89b4fa"))
        self._rules.append((re.compile(r"\b[XYZ]-?\d+\.?\d*\b"), fmt_coord))

        # I J K (cyan)
        fmt_ijk = QTextCharFormat()
        fmt_ijk.setForeground(QColor("#94e2d5"))
        self._rules.append((re.compile(r"\b[IJK]-?\d+\.?\d*\b"), fmt_ijk))

        # Feed/Speed F S (orange)
        fmt_fs = QTextCharFormat()
        fmt_fs.setForeground(QColor("#fab387"))
        self._rules.append((re.compile(r"\b[FS]\d+\.?\d*\b"), fmt_fs))

        # Tool T N (yellow)
        fmt_t = QTextCharFormat()
        fmt_t.setForeground(QColor("#f9e2af"))
        self._rules.append((re.compile(r"\b[TN]\d+\b"), fmt_t))

        # Comments (gray)
        fmt_comment = QTextCharFormat()
        fmt_comment.setForeground(QColor("#6c7086"))
        fmt_comment.setFontItalic(True)
        self._rules.append((re.compile(r"\(.*?\)"), fmt_comment))
        self._rules.append((re.compile(r";.*$"), fmt_comment))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class GcodePanel(QWidget):
    """G-code viewer with syntax highlighting and export."""

    export_requested = Signal(str)  # file path

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout()

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("G-code Output"))
        self._line_count = QLabel("Lines: 0")
        header.addWidget(self._line_count)
        header.addStretch()

        self._export_btn = QPushButton("Export G-code")
        self._export_btn.clicked.connect(self._on_export)
        header.addWidget(self._export_btn)
        layout.addLayout(header)

        # Editor
        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(True)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._highlighter = GcodeSyntaxHighlighter(self._editor.document())
        layout.addWidget(self._editor)

        self.setLayout(layout)

    def set_gcode(self, text: str) -> None:
        self._editor.setPlainText(text)
        lines = text.count("\n") + 1
        self._line_count.setText(f"Lines: {lines}")

    def get_gcode(self) -> str:
        return self._editor.toPlainText()

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export G-code", "", "NC Files (*.nc);;G-code (*.gcode);;All Files (*)"
        )
        if path:
            with open(path, "w") as f:
                f.write(self.get_gcode())
            self.export_requested.emit(path)
