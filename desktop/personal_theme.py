"""Native Qt styling based on the Windows prototype palette."""

PERSONAL_STYLE = """
QWidget { background: #0c0f13; color: #f1f5f9; font-family: 'Segoe UI'; font-size: 14px; }
QLabel#title { color: #34d399; font-size: 24px; font-weight: 750; }
QLabel#subtitle { color: #a8b6c9; }
QPushButton {
    background: #1c222b; border: 1px solid #364150; border-radius: 8px;
    min-height: 30px; padding: 4px 12px; font-weight: 600;
}
QPushButton:hover { background: #232b36; border-color: #34d399; }
QPushButton:disabled { color: #8896a7; background: #161b22; }
QPushButton#primary { background: #34d399; color: #07261c; }
QPushButton#stop { background: #412329; border-color: #d36c78; color: #fff0f2; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: #34d399; }
QLineEdit, QComboBox, QPlainTextEdit, QTableWidget {
    background: #0e1217; border: 1px solid #394555; border-radius: 7px;
    padding: 6px 8px; selection-background-color: #25624d;
}
QLineEdit, QComboBox { min-height: 24px; }
QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #7b8a9e; border-radius: 3px; }
QCheckBox::indicator:checked { background: #34d399; border-color: #34d399; }
QListWidget { background: #11151b; border: 1px solid #27303b; border-radius: 11px; padding: 6px; }
QListWidget::item { padding: 12px 9px; margin: 2px; border-radius: 7px; }
QListWidget::item:hover { background: #232b36; }
QListWidget::item:selected { background: #1d3930; color: #9df9d4; }
QGroupBox {
    border: 1px solid #364150; border-radius: 9px;
    margin-top: 13px; padding: 12px 8px 8px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #cbd5e1; }
QTabWidget::pane { border: 1px solid #364150; border-radius: 8px; }
QTabBar::tab { background: #161b22; padding: 9px 13px; color: #cbd5e1; }
QTabBar::tab:selected { background: #1d3930; color: #9df9d4; }
QHeaderView::section { background: #1c222b; color: #cbd5e1; padding: 7px; border: 0; }
QLabel#systemMetrics { color: #cbd5e1; padding: 6px; }
QStatusBar { border-top: 1px solid #27303b; color: #a8b6c9; }
QScrollArea { border: 0; }
QScrollBar:vertical { background: #11151b; width: 10px; }
QScrollBar::handle:vertical { background: #4b5969; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
