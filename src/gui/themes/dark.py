"""Dark theme stylesheet for KooCADCAM GUI."""

DARK_STYLESHEET = """
QMainWindow {
    background-color: #1e1e2e;
}

QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Ubuntu", "Noto Sans", sans-serif;
    font-size: 13px;
}

QMenuBar {
    background-color: #181825;
    color: #cdd6f4;
    border-bottom: 1px solid #313244;
}

QMenuBar::item:selected {
    background-color: #45475a;
}

QMenu {
    background-color: #1e1e2e;
    border: 1px solid #45475a;
}

QMenu::item:selected {
    background-color: #45475a;
}

QToolBar {
    background-color: #181825;
    border-bottom: 1px solid #313244;
    spacing: 6px;
    padding: 4px;
}

QToolButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 6px 12px;
    min-width: 60px;
}

QToolButton:hover {
    background-color: #45475a;
    border-color: #89b4fa;
}

QToolButton:pressed {
    background-color: #585b70;
}

QTabWidget::pane {
    border: 1px solid #313244;
    background-color: #1e1e2e;
}

QTabBar::tab {
    background-color: #181825;
    color: #a6adc8;
    border: 1px solid #313244;
    padding: 8px 16px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #1e1e2e;
    color: #89b4fa;
    border-bottom-color: #1e1e2e;
}

QTabBar::tab:hover {
    background-color: #313244;
}

QGroupBox {
    border: 1px solid #313244;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 14px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: #89b4fa;
}

QLabel {
    color: #cdd6f4;
}

QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #89b4fa;
}

QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
}

QComboBox::drop-down {
    border: none;
}

QComboBox QAbstractItemView {
    background-color: #1e1e2e;
    color: #cdd6f4;
    selection-background-color: #45475a;
}

QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #b4d0fb;
}

QPushButton:pressed {
    background-color: #74c7ec;
}

QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}

QTextEdit, QPlainTextEdit {
    background-color: #11111b;
    color: #a6e3a1;
    font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
    font-size: 12px;
    border: 1px solid #313244;
    border-radius: 4px;
}

QScrollBar:vertical {
    background: #181825;
    width: 10px;
    border: none;
}

QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 5px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #585b70;
}

QScrollBar:horizontal {
    background: #181825;
    height: 10px;
    border: none;
}

QScrollBar::handle:horizontal {
    background: #45475a;
    border-radius: 5px;
    min-width: 20px;
}

QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    border-top: 1px solid #313244;
}

QSplitter::handle {
    background-color: #313244;
}

QSplitter::handle:hover {
    background-color: #89b4fa;
}

QTreeWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 4px;
}

QTreeWidget::item:selected {
    background-color: #45475a;
}

QTreeWidget::item:hover {
    background-color: #313244;
}

QHeaderView::section {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #313244;
    padding: 4px;
}

QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 4px;
}
"""
