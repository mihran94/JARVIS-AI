"""The JARVIS holographic HUD — one window, everything visible.

WHAT THIS IS
    The whole assistant is one window, and this is the part of it that
    always answers the same four questions: what is this computer doing,
    what is JARVIS doing, which engine answered, and how do I stop it.

    It is drawn rather than assembled from boxes, because a HUD is a
    picture: an arc-reactor core, two dials for the real CPU and memory
    readings, a progress line for the task, a badge when an approval is
    waiting, and the words of the last thing that was said.

THE RULES
    * Every reading is real. A reading that cannot be taken is drawn as
      unavailable, because a made-up number on a dial is worse than an
      empty dial.
    * The motion is subtle. The sweep moves slowly, and it stops when
      the owner has asked for less motion.
    * The Tamil is real Tamil. The type stack names the Tamil font of
      Windows, so the Tamil the owner reads is measured and drawn with
      the same font, not with a fallback that has no Tamil glyphs.
    * One window. Emergency Stop is always in sight, and the shortcut
      behind it is the same one.

WHAT THIS IS NOT
    * It is not a control panel. It reports; the actions live in the
      pages it sits above.
    * It does not run anything and it does not decide anything.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from desktop.prime_theme import FONT_STACK, MONO_STACK

#: The font stack for Tamil. Nirmala UI is the Tamil font of Windows, and
#: it has to be named: a font with no Tamil glyphs measures the Latin
#: letters, and the Tamil is drawn from another font on top of them.
TAMIL_STACK = "'Nirmala UI', 'Noto Sans Tamil', 'Latha', 'Segoe UI', sans-serif"

#: The colours of the HUD.
GROUND = '#05080e'
PANEL = '#0b1220'
EDGE = '#1d3b57'
CYAN = '#63dcff'
CYAN_DEEP = '#1f6f9c'
GOLD = '#efae67'
INK = '#e9f3fc'
MUTED = '#8ba3bd'
DANGER = '#ff7286'
GOOD = '#5df2b0'

#: How often the sweep moves, in milliseconds.
SWEEP_MS = 60

#: How many readings the little history keeps.
SAMPLE_HISTORY = 24


def _font(families: str, size: int, weight: int = 500) -> QFont:
    """A font from a stack, with a weight Qt understands."""
    font = QFont()
    font.setFamilies([family.strip().strip("'") for family in families.split(',')])
    font.setPointSize(size)
    font.setWeight(QFont.Weight(weight))
    return font


def _alpha(color: str, alpha: int) -> QColor:
    """The same colour with an alpha."""
    value = QColor(color)
    value.setAlpha(max(0, min(255, int(alpha))))
    return value


class HudCore(QWidget):
    """The arc-reactor core: a ring, a sweep and a pulse.

    The sweep is the only motion in the HUD. It is slow enough to read as
    a display and not as an animation, and it stops when the owner has
    asked for less motion.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 64)
        self.setAccessibleName('JARVIS core')
        self.phase = 0.0
        self.pulse = 0.0
        self.motion = True
        self._timer = QTimer(self)
        self._timer.setInterval(SWEEP_MS)
        self._timer.timeout.connect(self._tick)

    def set_motion(self, enabled: bool):
        """Turn the motion on or off."""
        self.motion = bool(enabled)
        if not self.motion:
            self.phase = 0.0
        self.update()

    def _tick(self):
        if not self.motion:
            return
        self.phase = (self.phase + 0.6) % 360.0
        self.pulse = (self.pulse + 0.4) % 360.0
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        # The sweep only runs while the core is on the screen. A core
        # that is not visible must not keep the machine busy.
        if self.motion:
            self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        centre = self.rect().center()
        radius = 22

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(_alpha(EDGE, 220), 2))
        painter.drawArc(QRectF(centre.x() - radius, centre.y() - radius,
                               radius * 2, radius * 2), 0, 360 * 16)

        painter.setPen(QPen(_alpha(CYAN, 40), 6))
        painter.drawArc(QRectF(centre.x() - radius + 4, centre.y() - radius + 4,
                               (radius - 4) * 2, (radius - 4) * 2), 0, 360 * 16)

        if self.motion:
            painter.setPen(QPen(QColor(CYAN), 3))
            painter.drawArc(QRectF(centre.x() - radius + 4, centre.y() - radius + 4,
                                   (radius - 4) * 2, (radius - 4) * 2),
                            int(self.phase * 16), int(60 * 16))

        painter.setPen(QPen(QColor(CYAN), 1))
        painter.setBrush(QBrush(QColor(CYAN)))
        painter.drawEllipse(centre, 3, 3)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(_alpha(CYAN, 90), 1))
        painter.drawEllipse(centre, 13, 13)


class HudDial(QWidget):
    """One real reading, drawn as a dial.

    The dial shows a share of a whole: the CPU load, the memory in use.
    A reading that is not available draws an empty dial and says so.
    """

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.caption = caption
        self.value = None
        self.text = '—'
        self.setFixedSize(88, 104)
        self.setAccessibleName(caption)

    def set_reading(self, percent, text: str):
        """Show a reading. `percent` is None when it is not available."""
        self.value = None if percent is None else float(percent)
        self.text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        centre = self.rect().center()
        radius = 30
        top = centre.y() - radius - 6
        box = QRectF(centre.x() - radius, top, radius * 2, radius * 2)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(_alpha(EDGE, 200), 6))
        painter.drawArc(box, 0, 360 * 16)

        if self.value is not None:
            painter.setPen(QPen(QColor(CYAN), 6))
            painter.drawArc(box, int(-90 * 16),
                            int(360 * max(0.0, min(1.0, self.value)) * 16))
            painter.setPen(QPen(_alpha(CYAN, 120), 1))
            painter.drawLine(int(centre.x()), int(top),
                             int(centre.x() + radius * 0.6 * _cos(self.value)),
                             int(top + radius * 0.6 * _sin(self.value)))
        else:
            painter.setPen(QPen(_alpha(DANGER, 90), 2))
            painter.drawArc(box, int(-90 * 16), int(18 * 16))

        painter.setPen(QPen(QColor(INK)))
        painter.setFont(_font(MONO_STACK, 12, 600))
        painter.drawText(QRectF(centre.x() - radius, centre.y() - 12, radius * 2, 22),
                         Qt.AlignmentFlag.AlignCenter, self.text)

        painter.setPen(QPen(QColor(MUTED)))
        painter.setFont(_font(MONO_STACK, 8, 600))
        painter.drawText(QRectF(0, self.height() - 20, self.width(), 16),
                         Qt.AlignmentFlag.AlignCenter, self.caption.upper())


def _cos(value: float) -> float:
    """The cosine of an angle in degrees, without importing the module."""
    import math
    return math.cos(math.radians(value * 360.0 - 90.0))


def _sin(value: float) -> float:
    """The sine of an angle in degrees, without importing the module."""
    import math
    return math.sin(math.radians(value * 360.0 - 90.0))


class HudStrip(QWidget):
    """The line of readings that is always in sight.

    It shows the core, the engine that answered, the CPU and the memory,
    the step of the task, the approvals that are waiting, the state of
    the microphone, and the Emergency Stop.
    """

    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('hudStrip')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(126)
        self.engine_name = 'Local'
        self.engine_reason = ''
        self.step = 0
        self.total = 0
        self.approval_text = ''
        self.mic_text = 'Microphone closed'
        self.muted = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(20)

        self.core = HudCore()
        layout.addWidget(self.core)

        left = QVBoxLayout()
        left.setSpacing(6)
        title = QLabel('JARVIS')
        title.setFont(_font(FONT_STACK, 20, 700))
        title.setStyleSheet(f'color: {INK}; letter-spacing: 4px;')
        left.addWidget(title)

        self.engine_chip = QLabel('Local')
        self.engine_chip.setFont(_font(MONO_STACK, 11, 700))
        self.engine_chip.setAccessibleName('Engine that answered')
        # The chip is a chip: it is as wide as the word and no wider.
        self.engine_chip.setSizePolicy(QSizePolicy.Policy.Fixed,
                                       QSizePolicy.Policy.Fixed)
        self.engine_chip.setMinimumWidth(96)
        left.addWidget(self.engine_chip, 0, Qt.AlignmentFlag.AlignLeft)

        self.engine_note = QLabel('')
        self.engine_note.setFont(_font(TAMIL_STACK, 10))
        self.engine_note.setWordWrap(True)
        self.engine_note.setStyleSheet(f'color: {MUTED};')
        self.engine_note.setMaximumHeight(34)
        left.addWidget(self.engine_note)
        layout.addLayout(left, 2)

        self.cpu = HudDial('CPU')
        layout.addWidget(self.cpu)
        self.ram = HudDial('Memory')
        layout.addWidget(self.ram)

        task = QVBoxLayout()
        task.setSpacing(5)
        self.task_label = QLabel('No task running')
        self.task_label.setFont(_font(MONO_STACK, 10, 600))
        self.task_label.setStyleSheet(f'color: {MUTED};')
        task.addWidget(self.task_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setAccessibleName('Task progress')
        task.addWidget(self.progress)
        self.approval = QLabel('')
        self.approval.setFont(_font(MONO_STACK, 10, 600))
        self.approval.setWordWrap(True)
        self.approval.setStyleSheet(f'color: {GOLD};')
        self.approval.setMaximumHeight(34)
        task.addWidget(self.approval)
        layout.addLayout(task, 2)

        voice = QVBoxLayout()
        voice.setSpacing(5)
        self.mic = QLabel('Microphone closed')
        self.mic.setFont(_font(MONO_STACK, 10, 600))
        self.mic.setAccessibleName('Microphone status')
        self.mic.setStyleSheet(f'color: {MUTED};')
        voice.addWidget(self.mic)
        self.mute = QLabel('Replies on')
        self.mute.setFont(_font(MONO_STACK, 10, 600))
        self.mute.setStyleSheet(f'color: {MUTED};')
        voice.addWidget(self.mute)
        layout.addLayout(voice, 1)

        self.stop_button = QPushButton('Emergency stop')
        self.stop_button.setObjectName('stop')
        self.stop_button.setAccessibleName('Emergency stop')
        self.stop_button.setFixedHeight(38)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        layout.addWidget(self.stop_button)

    # ------------------------------------------------------------------

    def set_engine(self, engine: str, reason: str = ''):
        """Say which engine answered, and why."""
        self.engine_name = engine or 'Local'
        self.engine_reason = reason or ''
        self.engine_chip.setText(self.engine_name)
        colour = GOLD if self.engine_name != 'Local' else CYAN
        self.engine_chip.setStyleSheet(
            f'color: {colour}; border: 1px solid {colour}; border-radius: 9px;'
            ' padding: 3px 9px;')
        self.engine_note.setText(self.engine_reason)
        self.engine_note.setVisible(bool(self.engine_reason))

    def set_reading(self, name: str, percent, text: str):
        """Show one real reading. `percent` is None when it is missing."""
        dial = self.cpu if name == 'cpu' else self.ram
        dial.set_reading(percent, text)

    def set_progress(self, step: int, total: int = 0):
        """Show the step of the task. There is no invented percentage."""
        self.step = int(step or 0)
        self.total = int(total or 0)
        if self.total:
            self.task_label.setText(f'Step {self.step} of {self.total}')
            self.progress.setValue(int(100 * min(1.0, self.step / self.total)))
        else:
            self.task_label.setText('No task running')
            self.progress.setValue(0)

    def set_approval(self, text: str):
        """Show that an approval is waiting."""
        self.approval_text = text or ''
        self.approval.setText(self.approval_text)
        self.approval.setVisible(bool(self.approval_text))

    def clear_approval(self):
        """There is no approval waiting any more."""
        self.set_approval('')

    def set_mic(self, text: str, muted: bool = False):
        """Show the state of the microphone and the mute."""
        self.mic_text = text or ''
        self.muted = bool(muted)
        self.mic.setText(self.mic_text)
        self.mic.setStyleSheet(f'color: {GOOD if "allowed" in self.mic_text.lower() else MUTED};')
        self.mute.setText('Replies muted' if self.muted else 'Replies on')
        self.mute.setStyleSheet(f'color: {GOLD if self.muted else MUTED};')

    def set_motion(self, enabled: bool):
        """Turn the motion on or off."""
        self.core.set_motion(enabled)

    def summary(self) -> str:
        """One line about the HUD, for a test or a log."""
        return (f'{self.engine_name} | CPU {self.cpu.text} | RAM {self.ram.text} | '
                f'step {self.step} of {self.total} | {self.mic_text} | '
                f'{"muted" if self.muted else "replies on"}')


class HudFrame(QWidget):
    """The chassis the strip sits on.

    It paints the faint grid, the soft corner light and the slow scan
    line that make the surface read as a projection rather than a form.

    The grid is drawn once into a picture and kept, because the HUD is
    repainted every time the scan line moves, and drawing thirty lines
    again every time is work the machine does not need to do. The scan
    line is the only thing that changes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('hudFrame')
        self.phase = 0.0
        self.motion = True
        self._grid = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.strip = HudStrip()
        layout.addWidget(self.strip)
        self._timer = QTimer(self)
        self._timer.setInterval(SWEEP_MS)
        self._timer.timeout.connect(self._tick)

    def _grid_picture(self):
        """The grid, drawn once and kept until the size changes."""
        if self._grid is None or self._grid.size() != self.size():
            picture = QPixmap(self.size())
            picture.fill(QColor(GROUND))
            painter = QPainter(picture)
            painter.setPen(QPen(_alpha(EDGE, 46), 1))
            step = 46
            x = 0
            while x < picture.width():
                painter.drawLine(x, 0, x, picture.height())
                x += step
            y = 0
            while y < picture.height():
                painter.drawLine(0, y, picture.width(), y)
                y += step
            painter.end()
            self._grid = picture
        return self._grid

    def set_motion(self, enabled: bool):
        """Turn the motion on or off."""
        self.motion = bool(enabled)
        self.strip.set_motion(enabled)
        if not self.motion:
            self.phase = 0.0
        self.update()

    def _tick(self):
        if not self.motion:
            return
        old = int(self.rect().height() * (self.phase / 360.0))
        self.phase = (self.phase + 0.35) % 360.0
        new = int(self.rect().height() * (self.phase / 360.0))
        # Only the two lines are repainted. The rest of the chassis is
        # the picture that was drawn once, and it does not change.
        top = min(old, new)
        height = abs(new - old) + 2
        self.update(0, top, self.rect().width(), height)

    def showEvent(self, event):
        super().showEvent(event)
        # The scan line only runs while the HUD is on the screen. A HUD
        # that is not visible must not keep the machine busy.
        if self.motion:
            self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._grid = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._grid_picture())
        # The slow scan line. It is the only movement on the chassis.
        if self.motion:
            painter.setPen(QPen(_alpha(CYAN, 26), 2))
            position = int(self.rect().height() * (self.phase / 360.0))
            painter.drawLine(0, position, self.rect().width(), position)
        painter.setPen(QPen(_alpha(CYAN, 70), 1))
        painter.drawLine(0, self.rect().height() - 1,
                         self.rect().width(), self.rect().height() - 1)

__all__ = ['CYAN', 'CYAN_DEEP', 'DANGER', 'EDGE', 'GOOD', 'GOLD', 'GROUND', 'INK',
           'MUTED', 'PANEL', 'SWEEP_MS', 'TAMIL_STACK', 'HudCore', 'HudDial',
           'HudFrame', 'HudStrip']
