"""Local, resolution-independent artwork for the Omega desktop."""
from math import pi, sin
from random import Random

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget


DEFAULT_THEME = 'M-Core'
THEMES = {
    DEFAULT_THEME: ('#02070d', '#081b2b', '#23475b', '#e4f5ff', '#90b1c6', '#28e3ee', '#168cbd'),
    'Warm Graphite': ('#141218', '#292230', '#554859', '#fff5ee', '#c5b5c5', '#ffbd93', '#b883d5'),
    'Midnight Blue': ('#060d1a', '#10253d', '#203f57', '#eef9ff', '#9db9cd', '#6ae6ff', '#ffae68'),
    'Apple Silver': ('#dfeaf4', '#f3f8fd', '#a0b9cb', '#132939', '#426176', '#006fa3', '#a6470f'),
    'Dark Titanium': ('#0d1017', '#202834', '#374757', '#f0f5fc', '#a4b5c8', '#82bfed', '#ffc481'),
}
BACKGROUNDS = ('Orbital glass', 'Horizon', 'Quiet')


def tint(color, alpha):
    result = QColor(color)
    result.setAlpha(alpha)
    return result


def theme_sheet(name):
    """The premium stylesheet for one of the Omega palettes.

    The palette is still what the owner chooses in Settings; the sheet it
    produces is the JARVIS PRIME interface system: glass surfaces, rounded
    corners, an accent that matches the palette and one set of states for
    every control.
    """
    from desktop.prime_theme import build

    return build(THEMES[name])


class Backdrop(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        random = Random(57)
        self.stars = [(random.random(), random.random(), random.choice((1, 1, 2)))
                      for _ in range(108)]
        self.theme = 'Midnight Blue'
        self.background = BACKGROUNDS[0]
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg, panel, edge, _, _, cyan, gold = THEMES[self.theme]
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(bg))
        if self.background == 'Quiet':
            return
        for x, y, color, strength in ((.48, .35, cyan, 51), (.94, .11, gold, 29), (.06, .8, cyan, 28)):
            glow = QRadialGradient(w*x, h*y, max(1, w*.68))
            glow.setColorAt(0, tint(color, strength))
            glow.setColorAt(.35, tint(panel, strength))
            glow.setColorAt(1, tint(bg, 0))
            p.fillRect(self.rect(), glow)
        p.setPen(QPen(tint(cyan, 21), 1))
        horizon = h*.63
        for x in range(-w, w*2, 82):
            p.drawLine(QPointF(w*.5, horizon), QPointF(x, h))
        for i in range(7):
            y = horizon + (h-horizon)*(i/6)**2
            p.drawLine(QPointF(0, y), QPointF(w, y))
        if self.background == 'Horizon':
            p.setPen(QPen(tint(gold, 77), 1))
            p.drawLine(QPointF(0, horizon), QPointF(w, horizon))
        else:
            p.setPen(QPen(tint(cyan, 130), 1))
            for x, y, size in self.stars:
                p.drawEllipse(QRectF(x*w, y*h*.76, size, size))


class Reactor(QWidget):
    """A single low-rate painter with no work while hidden or reduced motion is active."""
    def __init__(self, *, compact=False, parent=None):
        super().__init__(parent)
        self.compact = compact
        self.theme = 'Midnight Blue'
        self.activity = 'idle'
        self.level = 0
        self.motion = True
        self.phase = .25
        self.setAccessibleName('Voice activity')
        if compact:
            self.setMinimumSize(42, 42)
        else:
            self.setMinimumHeight(285)
        self.timer = QTimer(self)
        self.timer.setInterval(48)
        self.timer.timeout.connect(self.advance)

    def sizeHint(self):
        return QSize(44, 44) if self.compact else QSize(420, 365)

    def set_motion(self, enabled):
        self.motion = enabled
        self.sync_timer()
        self.update()

    def sync_timer(self):
        if self.motion and self.isVisible() and self.activity != 'stopped':
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()

    def set_activity(self, state):
        if state != self.activity:
            self.activity = state
            self.sync_timer()
            self.update()

    def set_level(self, level):
        self.level = max(0, min(level, 100))

    def advance(self):
        speed = {'idle': .030, 'listening': .045, 'speaking': .075,
                 'thinking': .066, 'coding': .066, 'approval': .020}
        self.phase = (self.phase + speed.get(self.activity, .04)) % (2*pi)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_timer()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        _, _, edge, _, _, accent, secondary = THEMES[self.theme]
        count = 5 if self.compact else 13
        usable_width = self.width() * 0.72
        stride = usable_width / count
        bar_width = stride * 0.55
        energy = self.level / 100 if self.activity == 'listening' else 0.18
        if self.activity in ('speaking', 'thinking', 'coding') and self.motion:
            energy = 0.35 + 0.25 * sin(self.phase * 6)
        for index in range(count):
            spread = 1 - abs((index + 0.5) / count - 0.5)
            height = self.height() * (0.1 + energy * spread * 0.65)
            x = (self.width() - usable_width) / 2 + stride * index
            painter.setBrush(QColor(edge if self.activity == 'stopped' else
                                    accent if index % 2 else secondary))
            painter.drawRoundedRect(QRectF(x, (self.height() - height) / 2, bar_width, height),
                                    bar_width / 2, bar_width / 2)


def dock_icon(symbol, color):
    pixmap = QPixmap(80, 80)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(color))
    font = QFont('Segoe UI Symbol')
    font.setPixelSize(29)
    painter.setFont(font)
    painter.drawText(QRectF(0,0,40,40),Qt.AlignmentFlag.AlignCenter,symbol)
    painter.end()
    return QIcon(pixmap)


class SignalMeter(QWidget):
    """Displays the live input level reported by the active recognizer."""
    def __init__(self):
        super().__init__()
        self.theme = 'Midnight Blue'
        self.level = 0
        self.setFixedSize(73, 30)
        self.setAccessibleName('Microphone input level')

    def set_level(self, value):
        self.level = max(0, min(value, 100))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = THEMES[self.theme][5]
        lit = round(self.level / 10)
        for i in range(10):
            height = 6 + i*2
            p.setPen(QPen(tint(color, 240 if i < lit else 62), 2))
            p.drawLine(5+i*7, 27, 5+i*7, 27-height)
