"""Lightweight animated, decorative AI orb for the JARVIS BLUE command center.

The orb represents UI activity only; it does not imply microphone access or AI readiness.
"""
import math
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


class BlueOrb(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(240, 200)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        if not self.isVisible():
            return
        self._phase = (self._phase + 0.035) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        w, h = self.width(), self.height()
        x, y = w / 2, h / 2
        radius = min(w * 0.30, h * 0.36)
        glow = QRadialGradient(x, y, radius * 1.6)
        glow.setColorAt(0, QColor(22, 158, 227, 115))
        glow.setColorAt(0.5, QColor(0, 117, 200, 45))
        glow.setColorAt(1, QColor(0, 40, 100, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(int(x - radius * 1.6), int(y - radius * 1.6),
                            int(radius * 3.2), int(radius * 3.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for ring in range(3):
            offset = math.sin(self._phase + ring) * 3
            r = radius * (0.58 + ring * 0.18) + offset
            pen = QPen(QColor(50 + ring * 25, 210, 255, 205 - ring * 45))
            pen.setWidthF(2.5 if ring == 0 else 1.5)
            painter.setPen(pen)
            painter.drawEllipse(int(x - r), int(y - r), int(2 * r), int(2 * r))
        painter.setPen(QPen(QColor(114, 237, 255), 3))
        for i in range(12):
            angle = i * math.pi / 6 + self._phase * 0.35
            inner = radius * 0.85
            outer = inner + (8 if i % 3 == 0 else 4)
            painter.drawLine(int(x + math.cos(angle) * inner),
                             int(y + math.sin(angle) * inner),
                             int(x + math.cos(angle) * outer),
                             int(y + math.sin(angle) * outer))
        painter.end()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        self._timer.start()
        super().showEvent(event)
