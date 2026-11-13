"""Futuristic blue theme for the existing PySide6 Windows desktop.

Visual-only styling: no new permissions, listeners, or background processes.
"""

FUTURISTIC_BLUE = """
QWidget {
    background-color: #07111f;
    color: #e4f5ff;
    font-family: 'Segoe UI';
    font-size: 14px;
}
QMainWindow { background-color: #050c18; }
QLabel#title {
    color: #64e8ff;
    font-size: 30px;
    font-weight: 800;
    letter-spacing: 2px;
}
QLabel#subtitle {
    color: #8faac5;
    font-size: 12px;
    padding: 4px 0 12px 0;
}
QPushButton {
    background-color: #10304a;
    color: #e5f7ff;
    border: 1px solid #1c668b;
    border-radius: 9px;
    padding: 10px 16px;
    font-weight: 600;
}
QPushButton:hover { background-color: #17496b; border-color: #47dfff; }
QPushButton:pressed { background-color: #0b263e; }
QPushButton:disabled { color: #6b8498; background-color: #0c1c2c; border-color: #203a50; }
QPushButton#stop {
    background-color: #541e35;
    border: 1px solid #ed6685;
    color: #fff2f4;
}
QPushButton#stop:hover { background-color: #7a2946; }
QPlainTextEdit, QLineEdit, QComboBox, QTableWidget {
    background-color: #0a1b30;
    color: #e4f5ff;
    border: 1px solid #254f6d;
    border-radius: 8px;
    padding: 8px;
    selection-background-color: #17648b;
}
QListWidget {
    background-color: #09182a;
    border: 1px solid #173b55;
    border-radius: 12px;
    padding: 8px;
    min-width: 210px;
}
QListWidget::item { padding: 15px 10px; margin: 3px 0; border-radius: 7px; }
QListWidget::item:hover { background-color: #12344e; }
QListWidget::item:selected { background-color: #124b71; color: #70eaff; }
QHeaderView::section { background-color: #12304a; color: #b7e8ff; padding: 9px; border: 0; }
QTableWidget { gridline-color: #1c405a; }
QLabel#systemMetrics {
    background-color: #0b253b;
    border: 1px solid #23617f;
    border-radius: 10px;
    color: #b6edff;
    padding: 14px;
    font-family: 'Consolas';
    font-size: 13px;
}
QStatusBar { background-color: #071625; color: #91b8d2; border-top: 1px solid #173d59; }
QScrollBar:vertical { background-color: #09192a; width: 10px; }
QScrollBar::handle:vertical { background-color: #255575; border-radius: 4px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
