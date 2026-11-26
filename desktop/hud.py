"""Live desktop telemetry, task status, microphone and emergency controls."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from desktop.prime_theme import MONO_STACK

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


class HudDial(QWidget):
    """One real CPU or memory reading, with a compact progress bar."""

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setObjectName('hudDial')
        self.caption = caption
        self.value = None
        self.text = '—'
        self.setFixedSize(70, 30)
        self.setAccessibleName(caption)

    def set_reading(self, percent, text: str):
        """Show a reading. `percent` is None when it is not available."""
        self.value = None if percent is None else float(percent)
        self.text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(_font(MONO_STACK, 8, 600))
        painter.setPen(QColor(MUTED))
        painter.drawText(QRectF(0, 3, self.width(), 14), Qt.AlignmentFlag.AlignLeft, self.caption)
        painter.setPen(QColor(INK))
        painter.drawText(QRectF(0, 3, self.width(), 14), Qt.AlignmentFlag.AlignRight, self.text)

        track = QRectF(0, 23, self.width(), 3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(EDGE))
        painter.drawRoundedRect(track, 1.5, 1.5)
        if self.value is not None:
            painter.setBrush(QColor(CYAN))
            track.setWidth(track.width() * max(0.0, min(1.0, self.value)))
            painter.drawRoundedRect(track, 1.5, 1.5)


class HudStrip(QWidget):
    """The line of readings that is always in sight.

    It shows the engine that answered, the CPU and the memory,
    the step of the task, the approvals that are waiting, the state of
    the microphone, and the Emergency Stop.
    """

    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('hudStrip')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(66)
        self.setStyleSheet(
            'QWidget#hudStrip, QWidget#hudDial, '
            'QWidget#hudStrip QLabel { background: transparent; }')
        self.engine_name = 'Local'
        self.engine_reason = ''
        self.step = 0
        self.total = 0
        self.approval_text = ''
        self.mic_text = 'Microphone closed'
        self.muted = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 6, 20, 6)
        layout.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(3)

        self.engine_chip = QLabel('Local')
        self.engine_chip.setFont(_font(MONO_STACK, 11, 700))
        self.engine_chip.setAccessibleName('Automation engine')
        # The chip is a chip: it is as wide as the word and no wider.
        self.engine_chip.setSizePolicy(QSizePolicy.Policy.Fixed,
                                       QSizePolicy.Policy.Fixed)
        self.engine_chip.setMinimumWidth(96)
        left.addWidget(self.engine_chip, 0, Qt.AlignmentFlag.AlignLeft)

        self.provider = QLabel()
        self.provider.setFont(_font(TAMIL_STACK, 10, 600))
        self.provider.setStyleSheet(f'color: {INK};')
        self.provider.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        left.addWidget(self.provider)

        self.engine_note = QLabel('')
        self.engine_note.setFont(_font(TAMIL_STACK, 10))
        self.engine_note.setWordWrap(True)
        self.engine_note.setStyleSheet(f'color: {MUTED};')
        self.engine_note.setMaximumHeight(24)
        left.addWidget(self.engine_note)
        layout.addLayout(left, 2)

        self.cpu = HudDial('CPU')
        layout.addWidget(self.cpu)
        self.ram = HudDial('RAM')
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
        self.progress.hide()
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
        self.mic.setWordWrap(True)
        self.mic.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
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
        self.engine_chip.setToolTip(self.engine_reason or 'Automation tries the local engine first.')
        self.engine_note.setToolTip(self.engine_reason)
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
        self.progress.setVisible(bool(self.total))

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
        state = self.mic_text.lower()
        allowed = 'allowed' in state and 'not been allowed' not in state
        summary = 'Mic listening' if 'listening' in state else (
            'Mic muted' if 'muted' in state else 'Mic allowed' if allowed else 'Mic closed')
        self.mic.setText(summary)
        self.mic.setToolTip(self.mic_text)
        self.mic.setStyleSheet(f'color: {GOOD if allowed or "listening" in state else MUTED};')
        self.mute.setText('Replies muted' if self.muted else 'Replies on')
        self.mute.setStyleSheet(f'color: {GOLD if self.muted else MUTED};')

    def summary(self) -> str:
        """One line about the HUD, for a test or a log."""
        return (f'{self.engine_name} | CPU {self.cpu.text} | RAM {self.ram.text} | '
                f'step {self.step} of {self.total} | {self.mic_text} | '
                f'{"muted" if self.muted else "replies on"}')


class HudFrame(QWidget):
    """Compact status strip for the active desktop window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('hudFrame')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.strip = HudStrip()
        layout.addWidget(self.strip)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(GROUND))
        painter.setPen(QPen(_alpha(CYAN, 65), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

__all__ = ['CYAN', 'CYAN_DEEP', 'DANGER', 'EDGE', 'GOOD', 'GOLD', 'GROUND', 'INK',
           'MUTED', 'PANEL', 'TAMIL_STACK', 'HudDial',
           'HudFrame', 'HudStrip']
