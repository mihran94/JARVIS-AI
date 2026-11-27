"""Native application identity for source and packaged desktop launches."""
import sys

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


APP_ID = 'JARVIS.M.Desktop'


def set_process_identity():
    """Keep source launches out of Python's taskbar group on Windows."""
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def application_icon():
    """Draw a sharp cyan M at each size used by the native desktop."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 64, size / 64)
        painter.setBrush(QColor('#081b2b'))
        painter.setPen(QPen(QColor('#268da1'), 2))
        painter.drawRoundedRect(3, 3, 58, 58, 8, 8)
        painter.setPen(QPen(QColor('#28e3ee'), 4,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap,
                            Qt.PenJoinStyle.MiterJoin))
        painter.drawPolyline([QPointF(15, 48), QPointF(15, 17), QPointF(32, 34),
                              QPointF(49, 17), QPointF(49, 48)])
        painter.end()
        icon.addPixmap(pixmap)
    return icon
