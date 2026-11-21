"""Local, resolution-independent artwork for the Omega desktop."""
from math import cos, pi, radians, sin
from random import Random

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from desktop.omega_geography import LAND_ROWS


DEFAULT_THEME = 'Quantum Dark'
THEMES = {
    DEFAULT_THEME: ('#050910', '#101d2b', '#315568', '#eafaff', '#96b7c9', '#45e6ff', '#efae67'),
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


GLOBE = tuple(
    (cos(radians(lat))*sin(radians(lon)), sin(radians(lat)),
     cos(radians(lat))*cos(radians(lon)), land == '1')
    for lat, row in zip(range(-88, 89, 4), LAND_ROWS)
    for lon, land in zip(range(-180, 180, 4), row)
    if land == '1' or (lat % 12 == 0 and lon % 12 == 0)
)


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
        self.setAccessibleName('JARVIS AI core')
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
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        _, _, edge, ink, _, cyan, gold = THEMES[self.theme]
        accent = gold if self.activity in ('approval', 'coding') else cyan
        if self.activity == 'stopped':
            accent = '#ed7287'
        w, h = self.width(), self.height()
        radius = min(w*.43, h*.43) if self.compact else min(w*.255, h*.295)
        x, y = w*.5, h*(.5 if self.compact else .385)
        phase = self.phase if self.motion else .25
        strength = self.level/100 if self.activity == 'listening' else 0
        if self.activity == 'speaking':
            strength = .35 + .23*sin(phase*5)
        glow = QRadialGradient(x, y, max(1, radius*1.45))
        glow.setColorAt(0, tint(accent, 140))
        glow.setColorAt(.25, tint(accent, 68))
        glow.setColorAt(.7, tint(accent, 20))
        glow.setColorAt(1, tint(accent, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(x,y), radius*1.45, radius*1.45)
        if not self.compact:
            lens = QRadialGradient(x, y, max(1, radius))
            lens.setColorAt(0, tint(accent, 30))
            lens.setColorAt(.45, tint(accent, 12))
            lens.setColorAt(.62, tint(accent, 65))
            lens.setColorAt(.72, tint(edge, 218))
            lens.setColorAt(.85, tint(edge, 73))
            lens.setColorAt(1, tint(edge, 1))
            p.setBrush(lens)
            p.drawEllipse(QPointF(x, y), radius, radius)
            p.setPen(QPen(tint(accent, 64), max(1, radius*.015)))
            for i in range(8):
                angle = i*pi/4 - phase*.31
                p.drawLine(QPointF(x+radius*.52*cos(angle), y+radius*.52*sin(angle)),
                           QPointF(x+radius*.75*cos(angle), y+radius*.75*sin(angle)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, scale in enumerate((.48, .68, .82, .96, 1.10, 1.23)):
            r = radius*scale
            ring = QRectF(x-r,y-r,r*2,r*2)
            p.setPen(QPen(tint(accent, 75 if i >= 4 else 105), max(1, radius*.012)))
            p.drawEllipse(ring)
            p.setPen(QPen(tint(gold if i in (2,4) else accent, 226),
                          max(1, radius*(.017+i*.003+strength*.025))))
            direction = -1 if i%2 else 1
            for sector in (0,120,240):
                p.drawArc(ring, int((sector + phase*52*direction + i*18)*16), (26+i*4)*16)
        for i in range(36):
            angle = i*pi/18
            step = .045 if i%3 == 0 else .022
            p.setPen(QPen(tint(accent, 120 if step > .03 else 52), 1))
            a = radius*1.15
            b = radius*(1.15-step)
            p.drawLine(QPointF(x+a*cos(angle), y+a*sin(angle)),
                       QPointF(x+b*cos(angle), y+b*sin(angle)))
        points = 8 if self.compact else 18
        p.setBrush(QColor(accent))
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(points):
            angle = i*2*pi/points + phase*.38
            r = radius*(.76 + .26*sin(i*2.3+phase))
            p.drawEllipse(QPointF(x+r*cos(angle),y+r*sin(angle)),1.2,1.2)
        if self.compact:
            p.drawEllipse(QPointF(x,y),max(2,radius*.20),max(2,radius*.20))
            return
        p.setPen(QColor(ink))
        font = QFont('Segoe UI')
        font.setPixelSize(max(12, int(radius*.22)))
        font.setWeight(QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, radius*.043)
        p.setFont(font)
        p.drawText(QRectF(x-radius,y-radius*.24,radius*2,radius*.48),
                   Qt.AlignmentFlag.AlignCenter,'JARVIS')
        self.draw_globe(p, x, h*.795, min(w*.155,h*.17), phase, cyan, edge)

    @staticmethod
    def draw_globe(p, x, y, r, phase, cyan, edge):
        p.setPen(QPen(tint(cyan,145),1.2))
        halo = QRadialGradient(x, y, max(1, r))
        halo.setColorAt(0, tint(cyan, 9))
        halo.setColorAt(.82, tint(cyan, 23))
        halo.setColorAt(1, tint(cyan, 75))
        p.setBrush(halo)
        p.drawEllipse(QPointF(x,y),r,r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(tint(cyan, 52),1))
        p.drawEllipse(QRectF(x-r*1.42,y+r*.68,r*2.84,r*.52))
        angle = phase+ .30
        c, s = cos(angle), sin(angle)
        tilt_c, tilt_s = cos(.32), sin(.32)
        for gx, gy, gz, land in GLOBE:
            depth = gz*c - gx*s
            front = gy*tilt_s + depth*tilt_c
            if front <= 0:
                continue
            p.setPen(QPen(tint(cyan if land else edge, int(50+160*front)), 2.2 if land else 1.4))
            p.drawPoint(QPointF(x+r*(gx*c+gz*s), y-r*(gy*tilt_c-depth*tilt_s)))


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
