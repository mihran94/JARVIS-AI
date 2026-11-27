"""Compact, low-frequency weather animation driven by measured weather codes."""
import math
import time

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


def weather_kind(code):
    if code in (0, 1):
        return 'Clear'
    if code in (2, 3):
        return 'Cloudy'
    if code in (45, 48):
        return 'Fog'
    if code in (71, 73, 75, 77, 85, 86):
        return 'Snow'
    if code in (95, 96, 99):
        return 'Thunderstorm'
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return 'Rain'
    return 'Unavailable'


class WeatherVisual(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.code, self.day = None, True
        self.motion = True
        self.setFixedHeight(44)
        self.setAccessibleName('Current weather conditions')
        self.timer = QTimer(self, interval=80)
        self.timer.timeout.connect(self.update)

    def set_weather(self, code, day=True):
        self.code, self.day = code, day
        self.setAccessibleDescription(weather_kind(code))
        self.sync_motion()
        self.update()

    def set_motion(self, enabled):
        self.motion = enabled
        self.sync_motion()
        self.update()

    def sync_motion(self):
        if self.motion and self.isVisible() and weather_kind(self.code) != 'Unavailable':
            self.timer.start()
        else:
            self.timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_motion()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, 0)
        phase = time.monotonic() if self.motion else 0
        kind = weather_kind(self.code)
        painter.setPen(QPen(QColor('#28e3ee'), 1.5))
        if kind == 'Unavailable':
            painter.drawText(self.rect().translated(-self.width() // 2, 0),
                             Qt.AlignmentFlag.AlignCenter, '—')
            return
        if kind == 'Clear':
            painter.drawEllipse(QPointF(0, 22), 9, 9)
            if self.day:
                for index in range(8):
                    angle = index * math.pi / 4 + phase * .15
                    painter.drawLine(QPointF(math.cos(angle) * 13, 22 + math.sin(angle) * 13),
                                     QPointF(math.cos(angle) * 18, 22 + math.sin(angle) * 18))
            else:
                painter.setBrush(QColor('#081b2b'))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(5, 18), 8, 8)
            return
        shift = math.sin(phase * .6) * 3
        painter.setBrush(QColor('#153d50'))
        for x, y, radius in ((-13, 20, 8), (-2, 15, 11), (12, 21, 8)):
            painter.drawEllipse(QPointF(x + shift, y), radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if kind in ('Rain', 'Thunderstorm', 'Snow'):
            for index in range(5):
                x = -16 + index * 8
                y = 30 + ((phase * 15 + index * 3) % 12)
                if kind == 'Snow':
                    painter.drawEllipse(QPointF(x, y), 1.3, 1.3)
                else:
                    painter.drawLine(QPointF(x, y), QPointF(x - 2, y + 4))
        if kind == 'Thunderstorm':
            painter.setPen(QPen(QColor('#ffd45a'), 2))
            painter.drawPolyline([QPointF(1, 24), QPointF(-3, 31),
                                  QPointF(3, 31), QPointF(-1, 38)])
        if kind == 'Fog':
            for y in (32, 37, 42):
                painter.drawLine(QPointF(-21 + shift, y), QPointF(21 + shift, y))
