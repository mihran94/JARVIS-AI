"""The JARVIS PRIME interface — the production surface of the desktop.

WHAT THIS IS
    The application showed the old dashboard with a newer set of colours.
    The chrome, the conversation, the assistant and the island were the
    ones that were written first, and they are the ones the owner was
    looking at. This module is a new composition, built as its own
    widgets and put in place of the old ones.

    It is a real interface, not a skin:

    * a glass shell with its own top bar, a compact rail and a status
      line, drawn as widgets and not as a stylesheet over the old
      layout;
    * a conversation that is a column of messages with the owner on the
      right and JARVIS on the left, and a composer that stays where it
      is while the conversation moves;
    * an assistant hologram that stays visible beside chat and PC activity;
    * an orb that is painted, not assembled, and that shows what JARVIS
      is doing: idle, listening, working;
    * a Dynamic Island that floats above the window and reports the same
      state, so the owner can see that JARVIS heard them while they are
      doing something else.

WHAT IT IS NOT
    It adds no capability. The provider, the memory, the coding flow,
    the voice, the bridge and the permissions are the ones that are
    already in the application, and every control here calls them.
    Nothing is faked, and nothing shows a state that is not real.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import subprocess
import sys
from core.runtime_profile import APP_NAME

from PySide6.QtCore import (
    QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFontMetrics, QKeySequence, QLinearGradient, QPainter, QPainterPath,
    QPen, QRadialGradient, QShortcut,
)
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from desktop.activity_panel import ActivityPanel, STATES
from desktop.prime_theme import MONO_STACK


def build_commit() -> str:
    """Resolve the checkout revision, including detached HEAD and worktrees."""
    if getattr(sys, 'frozen', False):
        try:
            revision = Path(sys.executable).with_name('JARVIS-AI-REVISION.txt').read_text(
                encoding='ascii').strip()
        except (OSError, UnicodeError):
            return ''
        return revision[:7] if re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', revision) else ''
    provided = os.environ.get('JARVIS_BUILD_COMMIT', '').strip()
    if re.fullmatch(r'[0-9a-f]{7,64}', provided):
        return provided[:7]
    root = Path(__file__).resolve().parents[1]
    if not (root / '.git').exists():
        return ''
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--verify', 'HEAD'], cwd=root, capture_output=True,
            text=True, timeout=2, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ''
    revision = result.stdout.strip()
    return revision[:7] if result.returncode == 0 and re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', revision) else ''


def _alpha(color: str, alpha: int) -> QColor:
    """A colour with an alpha, the way Qt paints one."""
    value = QColor(color)
    value.setAlpha(max(0, min(255, alpha)))
    return value


class PrimePalette:
    """The colours of the PRIME surface, in one place."""

    def __init__(self, dark: bool = True, theme=None):
        self.dark = dark
        if dark:
            self.ground = QColor('#141218')
            self.ground_far = QColor('#201b26')
            self.glass = QColor('#292230')
            self.glass_edge = QColor('#554859')
            self.ink = QColor('#fff5ee')
            self.muted = QColor('#c5b5c5')
            self.accent = QColor('#ffbd93')
            self.accent_deep = QColor('#b883d5')
            self.good = QColor('#5df2b0')
            self.warn = QColor('#ffcf6b')
            self.danger = QColor('#ff6b81')
            self.bubble_you = QColor(184, 131, 213, 52)
            self.bubble_jarvis = QColor(255, 255, 255, 16)
        else:
            self.ground = QColor('#f4f6fb')
            self.ground_far = QColor('#e8ecf5')
            self.glass = QColor(255, 255, 255, 210)
            self.glass_edge = QColor(10, 20, 40, 24)
            self.ink = QColor('#0d1420')
            self.muted = QColor('#5a6a80')
            self.accent = QColor('#0a84ff')
            self.accent_deep = QColor('#0060df')
            self.good = QColor('#00a86b')
            self.warn = QColor('#b26a00')
            self.danger = QColor('#d1334a')
            self.bubble_you = QColor(10, 132, 255, 38)
            self.bubble_jarvis = QColor(255, 255, 255, 220)
        if theme is not None:
            ground, panels, edges, ink, muted, accent, secondary = map(QColor, theme)
            self.ground, self.ground_far = ground, ground.lighter(135)
            self.glass, self.glass_edge = panels, edges
            self.ink, self.muted = ink, muted
            self.accent, self.accent_deep = accent, secondary
            self.bubble_you = _alpha(secondary.name(), 52 if dark else 38)


    def adopt(self, other: 'PrimePalette'):
        """Take the colours of another palette, in place.

        The widgets hold a reference to this palette, so changing it
        here changes the whole surface, and each widget that wrote a
        stylesheet is asked to write it again.
        """
        for name in ('ground', 'ground_far', 'glass', 'glass_edge', 'ink', 'muted',
                     'accent', 'accent_deep', 'good', 'warn', 'danger',
                     'bubble_you', 'bubble_jarvis'):
            setattr(self, name, getattr(other, name))
        self.dark = other.dark


class GlassCard(QFrame):
    def __init__(self, palette: PrimePalette, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.setObjectName('primeGlass')
        self.refresh()

    def refresh(self):
        palette = self.palette_
        self.setStyleSheet(
            'QFrame#primeGlass { background: transparent; border: none; }'
            f' QLabel#hudSectionTitle {{ color: {palette.accent.name()};'
            f' font-family: {MONO_STACK}; font-size: 13px; font-weight: 600;'
            f' letter-spacing: 1px; padding: 3px 0 9px;'
            f' border-bottom: 1px solid {palette.glass_edge.name()}; }}')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette_
        width, height = self.width() - 1.5, self.height() - 1.5
        bevel = 9
        panel = QPainterPath(QPointF(0.5, bevel))
        for x, y in ((bevel, 0.5), (width, 0.5), (width, height - bevel),
                     (width - bevel, height), (0.5, height)):
            panel.lineTo(x, y)
        panel.closeSubpath()
        fill = QLinearGradient(0, 0, width, height)
        fill.setColorAt(0, palette.glass)
        fill.setColorAt(1, palette.ground)
        painter.fillPath(panel, QBrush(fill))
        painter.setPen(QPen(_alpha(palette.muted.name(), 105), 1))
        painter.drawPath(panel)
        painter.setPen(QPen(palette.accent, 2))
        painter.drawLine(QPointF(0.5, bevel), QPointF(bevel, 0.5))
        painter.drawLine(QPointF(bevel, 0.5), QPointF(40, 0.5))


class PrimeOrb(QWidget):
    """The assistant, painted rather than assembled.

    The orb is a ring of arcs around a core that breathes. Its colour
    says what JARVIS is doing, and the whole thing is drawn in one
    `paintEvent`, so it is smooth at any size and at any scaling.
    """

    def __init__(self, palette: PrimePalette, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.state = 'idle'
        self._phase = 0.0
        self._motion = True
        self._level = 0
        self._wake_timer = QTimer(self, singleShot=True, interval=900)
        self._wake_timer.timeout.connect(self.end_wake_pulse)
        self.setMinimumSize(64, 64)
        self.setAccessibleName('JARVIS M hologram')
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def showEvent(self, event):
        super().showEvent(event)
        if self._motion:
            self._timer.start()

    def hideEvent(self, event):
        self._wake_timer.stop()
        self._timer.stop()
        super().hideEvent(event)

    def set_motion(self, enabled):
        self._motion = enabled
        if (enabled or self._wake_timer.isActive()) and self.isVisible():
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def set_state(self, state: str):
        """idle, listening, working or error."""
        if state != self.state:
            self.state = state
            self.update()

    def pulse_wake(self):
        self._wake_timer.start()
        self._timer.start()
        self.update()

    def end_wake_pulse(self):
        if not self._motion:
            self._timer.stop()
        self.update()

    def set_level(self, level):
        self._level = max(0, min(100, level))
        if self.state == 'listening':
            self.update()

    def _tick(self):
        speed = 0.15 if self._wake_timer.isActive() else {
            'listening': 0.035, 'thinking': 0.07, 'responding': 0.052,
            'speaking': 0.048, 'working': 0.085, 'approval': 0.022,
            'stopped': 0, 'idle': 0.012,
        }.get(self.state, 0.012)
        self._phase = (self._phase + speed) % (math.pi * 2)
        self.update()

    def _colours(self):
        palette = self.palette_
        if self.state == 'listening':
            return palette.good, palette.accent
        if self.state == 'speaking':
            return palette.accent, palette.good
        if self.state == 'approval':
            return palette.warn, palette.warn.darker(160)
        if self.state in ('thinking', 'responding'):
            return palette.warn, palette.accent_deep
        if self.state == 'working':
            return palette.accent.lighter(130), palette.accent_deep
        if self.state in ('error', 'stopped'):
            return palette.danger, palette.danger
        return palette.accent, palette.accent_deep

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        side = min(self.width(), self.height())
        centre = QPointF(self.width() / 2, self.height() / 2)
        radius = side / 2 - 2
        bright, deep = self._colours()

        glow = QRadialGradient(centre, radius)
        signal = self._level / 100 if self.state == 'listening' else 0
        pulse = signal if not self._motion else max(signal, 0.12 * math.sin(self._phase))
        glow.setColorAt(0.0, _alpha(bright.name(), round(90 + 100 * pulse)))
        glow.setColorAt(0.45, _alpha(deep.name(), 34))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(centre, radius * 0.98, radius * 0.98)

        painter.translate(centre)
        tilt = 0.20 * math.sin(self._phase)
        scale = radius * (1 + 0.10 * pulse)
        painter.scale(scale, scale)

        # Each screen-width stroke is a fibre of the same folded glass ribbon.
        spectrum = QLinearGradient(-0.8, -0.55, 0.8, 0.5)
        spectrum.setColorAt(0.0, deep.lighter(165))
        spectrum.setColorAt(0.28, bright.lighter(145))
        spectrum.setColorAt(0.51, bright.darker(140))
        spectrum.setColorAt(0.73, QColor('#f0fcff') if self.palette_.dark else bright.darker(130))
        spectrum.setColorAt(1.0, bright)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index in range(38):
            t = (index - 18.5) / 18.5
            twist = t * (0.12 + 0.03 * pulse) + tilt * 0.08
            ribbon = QPainterPath(QPointF(-0.74 + twist, 0.49 - t * 0.13))
            ribbon.cubicTo(-0.61 + twist, 0.32, -0.65 - twist, -0.50, -0.60 - twist, -0.60)
            ribbon.cubicTo(-0.53 - twist, -0.73, -0.21 + twist, -0.08, 0.02 + twist, 0.24 + t * 0.12)
            ribbon.cubicTo(0.26 + twist, 0.18, 0.47 - twist, -0.68, 0.65 - twist, -0.60 - t * 0.10)
            ribbon.cubicTo(0.72 - twist, -0.58, 0.58 + twist, 0.30, 0.76 + twist, 0.49 + t * 0.12)
            painter.setOpacity(0.70 if index in (0, 37) else 0.26 + (1 - abs(t)) * 0.24)
            painter.setPen(QPen(QBrush(spectrum), 0.012 if index in (0, 37) else 0.005))
            painter.drawPath(ribbon)

        painter.setOpacity(1)
        projection = QRadialGradient(QPointF(0, 0.82), 0.74)
        projection.setColorAt(0.0, _alpha(bright.name(), round(130 + pulse * 80)))
        projection.setColorAt(0.5, _alpha(bright.name(), 25))
        projection.setColorAt(1.0, _alpha(deep.name(), 0))
        painter.setPen(QPen(_alpha(bright.name(), 62), 0.008))
        painter.setBrush(QBrush(projection))
        painter.drawEllipse(QRectF(-0.82, 0.73, 1.64, 0.18))

        if self.state in ('listening', 'speaking'):
            for index in range(9):
                offset = abs(index - 4)
                level = pulse if self.state == 'listening' else abs(math.sin(self._phase + index * 0.7))
                length = 0.025 + 0.105 * level * (1 - offset / 6)
                x = (index - 4) * 0.07
                painter.setPen(QPen(_alpha(bright.name(), 190), 0.016))
                painter.drawLine(QPointF(x, 0.60 - length), QPointF(x, 0.60 + length))


class PrimeBubble(QFrame):
    """One message: the owner on the right, JARVIS on the left."""

    def __init__(self, role: str, content: str, palette: PrimePalette, parent=None):
        super().__init__(parent)
        # The owner is on the right. The store calls the owner's own
        # messages 'user'.
        you = role.lower() in ('user', 'you', 'local command') or role.lower().startswith('you')
        self.you = you
        self.palette_ = palette
        fill = palette.bubble_you if you else palette.bubble_jarvis
        edge = palette.accent if you else palette.glass_edge
        # The rule names this frame, so the labels inside it are not given
        # a frame of their own.
        self.setObjectName('primeBubble')
        self.setStyleSheet(
            f'QFrame#primeBubble {{ background: rgba({fill.red()}, {fill.green()}, '
            f'{fill.blue()}, {fill.alpha()});'
            f' border: 1px solid rgba({edge.red()}, {edge.green()}, {edge.blue()}, '
            f'{max(40, edge.alpha())}); border-radius: 16px; }}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 11)
        layout.setSpacing(4)
        who = QLabel('You' if you else APP_NAME)
        self.who = who
        who.setObjectName('primeBubbleWho')
        who.setStyleSheet(
            f'QLabel#primeBubbleWho {{ color: {palette.accent.name() if you else palette.muted.name()};'
            f' font-size: 10px; letter-spacing: 1.4px; font-weight: 600;'
            f' background: transparent; border: none; }}')
        layout.addWidget(who)
        body = QLabel(content)
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(f'color: {palette.ink.name()}; font-size: 13px;'
                           f' background: transparent;')
        layout.addWidget(body)
        self.body = body
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def refresh_theme(self):
        palette = self.palette_
        you = self.you
        fill = palette.bubble_you if you else palette.bubble_jarvis
        edge = palette.accent if you else palette.glass_edge
        self.setStyleSheet(
            f'QFrame#primeBubble {{ background: rgba({fill.red()}, {fill.green()}, '
            f'{fill.blue()}, {fill.alpha()});'
            f' border: 1px solid rgba({edge.red()}, {edge.green()}, {edge.blue()}, '
            f'{max(40, edge.alpha())}); border-radius: 16px; }}')
        self.who.setStyleSheet(
            f'QLabel#primeBubbleWho {{ color: {palette.accent.name() if you else palette.muted.name()};'
            f' font-size: 10px; letter-spacing: 1.4px; font-weight: 600;'
            f' background: transparent; border: none; }}')
        self.body.setStyleSheet(f'color: {palette.ink.name()}; font-size: 13px;'
                                f' background: transparent;')

    def fit_to_text(self, cap: int = 660):
        """The bubble is as wide as the words need and no wider."""
        metrics = QFontMetrics(self.body.font())
        width = metrics.horizontalAdvance(self.body.text()) + 34
        self.setFixedWidth(max(1, min(cap, max(135, width))))
        self.setMinimumHeight(0)
        self.updateGeometry()

    def set_content(self, content: str):
        self.body.setText(content)


class PrimeConversation(QScrollArea):
    """The messages, as a column that moves and a composer that does not.

    The owner is on the right, JARVIS on the left, and each message is
    as wide as it needs to be and no wider.
    """

    #: The widest a message may become, so a long answer does not run
    #: the whole width of the window.
    MAX_WIDTH = 660

    def __init__(self, palette: PrimePalette, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._holder = QWidget()
        self._holder.setObjectName('primeConversationHolder')
        self._layout = QVBoxLayout(self._holder)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(12)
        self._layout.addStretch(1)
        self.setWidget(self._holder)
        self._rows = []
        self._messages = []

    @property
    def bubbles(self):
        """The messages that are on screen."""
        found = []
        for row in self._rows:
            for index in range(row.count()):
                widget = row.itemAt(index).widget()
                if isinstance(widget, PrimeBubble):
                    found.append(widget)
        return found

    def refresh_theme(self):
        for bubble in self.bubbles:
            bubble.refresh_theme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for bubble in self.bubbles:
            bubble.fit_to_text(self.bubble_width())

    def bubble_width(self):
        return min(self.MAX_WIDTH, self.viewport().width() - 8)

    def render(self, messages):
        """Update the existing transcript and keep the reader's scroll position."""
        messages = list(messages)
        bar = self.verticalScrollBar()
        position = bar.value()
        append_only = messages[:len(self._messages)] == self._messages
        follow_latest = position >= bar.maximum() - 8 or not append_only
        if not append_only:
            for row in self._rows:
                self._layout.removeItem(row)
                while row.count():
                    widget = row.takeAt(0).widget()
                    if widget is not None:
                        widget.hide()
                        widget.deleteLater()
            self._rows.clear()
        for message in messages[len(self._rows):]:
            bubble = PrimeBubble(message.get('role', 'jarvis'),
                                 message.get('content', ''), self.palette_)
            bubble.fit_to_text(self.bubble_width())
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            if bubble.you:
                row.addStretch(1)
                row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight
                              | Qt.AlignmentFlag.AlignTop)
            else:
                row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft
                              | Qt.AlignmentFlag.AlignTop)
                row.addStretch(1)
            self._layout.insertLayout(self._layout.count() - 1, row)
            self._rows.append(row)
        self._messages = messages
        self._layout.activate()
        if follow_latest:
            QTimer.singleShot(0, self, lambda: bar.setValue(bar.maximum()))
        else:
            bar.setValue(position)


class PrimeAssistant(QWidget):
    """The central hologram and its live interaction status."""

    def __init__(self, palette: PrimePalette, window, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.window_ref = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addStretch(1)
        self.orb = PrimeOrb(palette)
        window.voice_panel.audio_level.connect(self.orb.set_level)
        self.orb.set_motion(not window.store.get('omega:reduced', False))
        self.orb.setFixedSize(200, 200)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignCenter)
        row.addStretch(1)
        layout.addLayout(row)
        self.title = QLabel()
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet(f'color: {palette.ink.name()}; font-size: 20px; font-weight: 600;')
        layout.addWidget(self.title)
        self.hint = QLabel('Speak in Tamil or Tanglish, or type a message below.')
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(f'color: {palette.muted.name()}; font-size: 13px;')
        layout.addWidget(self.hint)
        self.heard = QLabel()
        self.heard.setWordWrap(True)
        self.heard.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.heard.setTextFormat(Qt.TextFormat.PlainText)
        self.heard.setMaximumHeight(54)
        self.heard.hide()
        layout.addWidget(self.heard)
        layout.addStretch(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        for child in (self.title, self.hint):
            child.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.refresh_greeting()
        self.refresh_hologram()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        size = max(64, min(320, event.size().height() - 125, event.size().width() - 14))
        if self.orb.width() != size:
            self.orb.setFixedSize(size, size)

    def paintEvent(self, event):
        if self.orb.isHidden() or not self.palette_.dark:
            return super().paintEvent(event)
        painter = QPainter(self)
        centre = self.orb.geometry().center()
        radius = max(1, self.orb.width() * 1.05)
        glow = QRadialGradient(QPointF(centre), radius)
        glow.setColorAt(0, _alpha(self.palette_.accent.name(), 22))
        glow.setColorAt(1, _alpha(self.palette_.accent.name(), 0))
        painter.fillRect(self.rect(), glow)

    def refresh_greeting(self):
        self.title.setText('What can I help with?')

    def refresh_theme(self):
        palette = self.palette_
        self.title.setStyleSheet(
            f'color: {palette.ink.name()}; font-size: 20px; font-weight: 600;')
        self.hint.setStyleSheet(f'color: {palette.muted.name()}; font-size: 13px;')
        self.orb.update()

    def refresh_hologram(self):
        visible = bool(self.window_ref.store.get('appearance:hologram', True))
        self.orb.setVisible(visible)

    def set_state(self, state: str):
        self.orb.set_state(state)
        if state != 'idle':
            self.title.setText(STATES[state][0])
        else:
            self.refresh_greeting()

    def show_heard(self, text):
        self.heard.setText('Heard  ·  ' + text[:160] + ('…' if len(text) > 160 else ''))
        self.heard.setToolTip(text)
        self.heard.show()


class PrimeComposer(QFrame):
    """The composer: the prompt and the controls, in one glass card."""

    def __init__(self, palette: PrimePalette, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.setObjectName('primeComposer')
        self.setMaximumWidth(900)
        self.setStyleSheet(
            f'QFrame#primeComposer {{ background: rgba({palette.glass.red()}, '
            f'{palette.glass.green()}, {palette.glass.blue()}, {palette.glass.alpha()});'
            f' border: 1px solid rgba({palette.glass_edge.red()}, '
            f'{palette.glass_edge.green()}, {palette.glass_edge.blue()}, '
            f'{palette.glass_edge.alpha()}); border-radius: 5px; }}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 14, 12)
        layout.setSpacing(10)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        layout.addLayout(self.body)
        self.controls = QGridLayout()
        self.controls.setSpacing(8)
        self.buttons = ()
        self._compact = None

    def set_controls(self, *buttons):
        self.buttons = buttons
        self.body.addLayout(self.controls)
        self.layout_controls()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout_controls()

    def layout_controls(self):
        if not self.buttons:
            return
        margins = self.layout().contentsMargins()
        row_width = (sum(button.sizeHint().width() for button in self.buttons)
                     + self.controls.spacing() * (len(self.buttons) - 1)
                     + margins.left() + margins.right())
        compact = self.width() < max(550, row_width)
        if compact == self._compact:
            return
        self._compact = compact
        columns = 4 if compact else len(self.buttons)
        for index, button in enumerate(self.buttons):
            row, column = divmod(index, columns)
            self.controls.addWidget(button, row, column)
        for column in range(len(self.buttons)):
            self.controls.setColumnStretch(column, int(column < columns))

    def refresh_theme(self):
        palette = self.palette_
        self.setStyleSheet(
            f'QFrame#primeComposer {{ background: rgba({palette.glass.red()}, '
            f'{palette.glass.green()}, {palette.glass.blue()}, {palette.glass.alpha()});'
            f' border: 1px solid rgba({palette.glass_edge.red()}, '
            f'{palette.glass_edge.green()}, {palette.glass_edge.blue()}, '
            f'{palette.glass_edge.alpha()}); border-radius: 5px; }}')


class PrimeChat(QWidget):
    """Chat history, the hologram, current PC activity and the composer."""

    def __init__(self, window, palette: PrimePalette, parent=None):
        super().__init__(parent)
        self.window_ref = window
        self.palette_ = palette
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(14)

        self.dashboard = QWidget()
        dashboard = QGridLayout(self.dashboard)
        dashboard.setContentsMargins(0, 0, 0, 0)
        dashboard.setHorizontalSpacing(16)

        self.right_panel = QWidget()
        self.right_panel.setMinimumWidth(266)
        self.right_panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(10)

        self.chat_history = GlassCard(palette)
        history = QVBoxLayout(self.chat_history)
        history.setContentsMargins(14, 13, 14, 13)
        history_title = QLabel('CHAT HISTORY')
        history_title.setObjectName('hudSectionTitle')
        history.addWidget(history_title)
        self.conversation = PrimeConversation(palette)
        history.addWidget(self.conversation, 1)
        self.empty_history = QLabel('Your conversation will appear here.')
        self.empty_history.setWordWrap(True)
        history.addWidget(self.empty_history, 1)
        window.archives.setSizeAdjustPolicy(window.archives.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        window.archives.setMinimumContentsLength(12)
        window.archives.setPlaceholderText('Saved conversations')
        window.archives.setAccessibleName('Saved conversations')
        history.addWidget(window.archives)
        archive_actions = QHBoxLayout()
        for title, button in (('Open', window.archive_button), ('New', window.new_chat_button)):
            button.setText(title)
            archive_actions.addWidget(button)
        history.addLayout(archive_actions)
        self.safety_controls = QGridLayout()
        self.safety_controls.setSpacing(6)
        self._safety_buttons = ()
        self.right_panel.installEventFilter(self)
        history.insertLayout(1, self.safety_controls)
        self.chat_history.setMinimumWidth(150)
        self.chat_history.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.right_layout.addWidget(self.chat_history, 1)
        dashboard.addWidget(self.right_panel, 0, 2)

        display = QWidget()
        display.setMinimumWidth(145)
        display.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        display_layout = QVBoxLayout(display)
        display_layout.setContentsMargins(0, 0, 0, 0)
        display_layout.setSpacing(8)
        display_tabs = QHBoxLayout()
        display_tabs.setSpacing(5)
        self.displays = QStackedWidget()
        self.displays.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.assistant = PrimeAssistant(palette, window)
        self.timeline = ActivityPanel(palette, window.prime_shell.open_task_history)
        self.timeline.setMinimumWidth(0)
        self.timeline.setMaximumWidth(16777215)
        self.timeline.closed.connect(lambda: self.show_display('hologram'))
        self.displays.addWidget(self.assistant)
        self.displays.addWidget(self.timeline)
        self.display_buttons = {}
        for key, label in (('hologram', 'Hologram'), ('timeline', 'Timeline'), ('media', 'Media')):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _checked=False, key=key: self.show_display(key))
            display_tabs.addWidget(button)
            self.display_buttons[key] = button
        self.display_buttons['hologram'].setChecked(True)
        display_layout.addLayout(display_tabs)
        display_layout.addWidget(self.displays, 1)
        dashboard.addWidget(display, 0, 1)

        self.workspace = GlassCard(palette)
        self.workspace.setMinimumWidth(150)
        self.workspace.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        workspace = QVBoxLayout(self.workspace)
        workspace.setContentsMargins(14, 13, 14, 13)
        work_title = QLabel('PC WORK')
        work_title.setObjectName('hudSectionTitle')
        workspace.addWidget(work_title)
        self.work_state = QLabel()
        self.work_state.setWordWrap(True)
        self.work_state.setTextFormat(Qt.TextFormat.PlainText)
        self.work_state.setMinimumHeight(38)
        workspace.addWidget(self.work_state)
        window.mission_mode.show()
        workspace.addWidget(window.mission_mode)
        workspace.addStretch(1)
        for meter in (window.hud.strip.cpu, window.hud.strip.ram):
            meter.setFixedHeight(30)
            meter.setMinimumWidth(0)
            meter.setMaximumWidth(16777215)
            meter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            workspace.addWidget(meter)
        news = QPushButton('Tamil news')
        news.clicked.connect(window.open_news_briefing)
        workspace.addWidget(news)
        dashboard.addWidget(self.workspace, 0, 0)
        for column, stretch in enumerate((2, 5, 3)):
            dashboard.setColumnStretch(column, stretch)
        layout.addWidget(self.dashboard, 1)
        self.task_panels = {}
        self.task_area = QStackedWidget()
        self.task_area.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.displays.addWidget(self.task_area)

        # The approval the owner has to answer, the card of a running
        # job, and the plan of a job with more than one step come with
        # the chat. They are the same cards, moved and not rewritten.
        self.cards = QVBoxLayout()
        self.cards.setSpacing(10)
        layout.addLayout(self.cards)

        self.composer = PrimeComposer(palette)
        self.right_layout.addWidget(self.composer)
        self._adopt_composer()

    def _adopt_composer(self):
        """Move the real prompt and the real buttons into the new composer.

        They are the same widgets the old chat used, so nothing about the
        way a message is sent, attached, dictated or researched changes.
        """
        window = self.window_ref
        window.prompt.setMinimumHeight(56)
        window.prompt.setMaximumHeight(68)
        window.send_button.setText('Send')
        window.prompt.setPlaceholderText('Message JARVIS…')
        old_layout = window.composer_bar.layout()
        old_layout.removeWidget(window.prompt)
        self.composer.body.addWidget(window.prompt)

        window.suggestion_mode.hide()
        buttons = (window.attach_button, window.send_button)
        for button in buttons:
            window.composer_actions.removeWidget(button)
            button.setStyleSheet('padding: 7px 7px;')
        self.composer.set_controls(*buttons)

        for card in (window.browser_output, getattr(window, 'chat_approval', None),
                     getattr(window, 'chat_task_card', None),
                     getattr(window, 'plan_card', None), window.suggestion_card,
                     window.desktop_result_card):
            if card is None:
                continue
            old_layout = card.parentWidget().layout() if card.parentWidget() else None
            if old_layout is not None:
                old_layout.removeWidget(card)
            self.cards.addWidget(card)

    def adopt_task_panels(self):
        window = self.window_ref
        names = ('PC Control', 'Files & Folders', 'Coding Assistant', 'Video Editor',
                 'Business', 'Step Workflows', 'Task Queue', 'Command Center',
                 'Mission Control', 'Task History', 'Review changes', 'System & Usage')
        # Move existing reviewed controls into the conversation. Keep compatibility
        # indices for shortcuts and settings without leaving another reachable page.
        widgets = {name: window.pages.widget(index) for name, index in window.page_indices.items()}
        for name in names:
            scroller = widgets[name]
            window.pages.removeWidget(scroller)
            self.task_panels[name] = self.task_area.addWidget(scroller)
        self.player = widgets['Quantum Visual Player']
        window.pages.removeWidget(self.player)
        self.displays.addWidget(self.player)
        settings_routes = ('Voice / Hey Jarvis', 'AI Providers')
        for name in settings_routes:
            window.pages.removeWidget(widgets[name])
            widgets[name].deleteLater()
        for name, widget in widgets.items():
            window.page_indices[name] = window.pages.indexOf(
                self if name in names or name in settings_routes or widget is self.player else widget)
        for index in range(window.nav.count()):
            item = window.nav.item(index)
            item.setData(Qt.ItemDataRole.UserRole, window.page_indices[item.text()])

    def show_display(self, name):
        widget = {'hologram': self.assistant, 'timeline': self.timeline, 'media': self.player}[name]
        self.displays.setCurrentWidget(widget)
        self.display_buttons[name].setChecked(True)
        self.window_ref.prime_shell.mark_active('JARVIS Chat')
        self.update_workspace_visibility()

    def show_task(self, name):
        if name in self.task_panels:
            self.task_area.setCurrentIndex(self.task_panels[name])
            self.displays.setCurrentWidget(self.task_area)
            for button in self.display_buttons.values():
                button.setAutoExclusive(False)
                button.setChecked(False)
                button.setAutoExclusive(True)
            self.update_workspace_visibility()
        elif name == 'JARVIS Chat':
            self.show_display('hologram')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_workspace_visibility()

    def update_workspace_visibility(self):
        task_open = self.displays.currentWidget() is self.task_area
        show_workspace = not task_open or self.width() >= 1120
        self.workspace.setVisible(show_workspace)
        self.dashboard.layout().setColumnStretch(0, 2 if show_workspace else 0)
        self.window_ref.mission_mode.setVisible(not task_open)

    def eventFilter(self, watched, event):
        if watched is self.right_panel and event.type() == QEvent.Type.Resize:
            self.layout_safety_controls(event.size().width())
        return super().eventFilter(watched, event)

    def place_safety_controls(self, buttons):
        self._safety_buttons = buttons
        self.layout_safety_controls(self.right_panel.width())

    def layout_safety_controls(self, width):
        if not self._safety_buttons or not self._safety_buttons[0].parentWidget():
            return
        compact = width < 350
        for index, button in enumerate(self._safety_buttons):
            if compact and index == 2:
                self.safety_controls.addWidget(button, 1, 0, 1, 2)
            else:
                self.safety_controls.addWidget(button, 0, index)
            button.show()

    def refresh_theme(self):
        self.assistant.refresh_theme()
        self.conversation.refresh_theme()
        self.chat_history.refresh()
        self.workspace.refresh()
        self.timeline.refresh_theme()
        self.composer.refresh_theme()

    def render(self, messages):
        self.conversation.setVisible(bool(messages))
        self.empty_history.setVisible(not messages)
        self.conversation.render(messages)

    def set_state(self, state: str):
        self.assistant.orb.set_motion(not self.window_ref.store.get('omega:reduced', False))
        self.assistant.set_state(state)
        self.timeline.set_state(state)


class PrimeShell(QWidget):
    """The main window's top bar, navigation menu, HUD and content."""

    def __init__(self, window, palette: PrimePalette, parent=None):
        super().__init__(parent)
        self.window_ref = window
        self.palette_ = palette
        self.setObjectName('primeShell')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.build_top_bar())
        self.provider_label = window.hud.strip.provider
        outer.addWidget(window.hud)

        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)
        self.content = QVBoxLayout()
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(0)
        middle.addLayout(self.content, 1)
        self.build_drawer()
        middle.addWidget(self.drawer)
        outer.addLayout(middle, 1)
        self.startup_notice = QLabel()
        self.startup_notice.setObjectName('startupNotice')
        self.startup_notice.setAccessibleName('JARVIS welcome and sharing notice')
        self.startup_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.startup_notice.setWordWrap(True)
        self.startup_notice.setContentsMargins(16, 4, 16, 6)
        self.startup_notice.hide()
        outer.addWidget(self.startup_notice)
        window.pages.currentChanged.connect(self.refresh_mark)

    def pulse_wake(self):
        if self.window_ref.store.get('omega:reduced', False):
            return
        chat = self.window_ref.prime_chat
        if chat.assistant.orb.isVisible():
            chat.assistant.orb.pulse_wake()

    def refresh_mark(self, _index=None):
        chat = getattr(self.window_ref, 'prime_chat', None)
        if chat is not None:
            buttons = (self.mic_mute_button, self.output_mute_button, self.stop_button)
            if self.window_ref.pages.currentWidget() is chat:
                chat.place_safety_controls(buttons)
            else:
                chat.place_safety_controls(())
                for button in buttons:
                    if self.safety_controls.indexOf(button) < 0:
                        self.safety_controls.addWidget(button)
                        button.show()

    # -- the top bar ---------------------------------------------------

    def build_top_bar(self):
        bar = QFrame()
        bar.setObjectName('primeTopBar')
        bar.setFixedHeight(56)
        self.top_bar = bar
        palette = self.palette_
        bar.setStyleSheet(
            f'QFrame#primeTopBar {{ background: rgba({palette.glass.red()}, '
            f'{palette.glass.green()}, {palette.glass.blue()}, {max(18, palette.glass.alpha())});'
            f' border: none; border-bottom: 1px solid rgba({palette.glass_edge.red()}, '
            f'{palette.glass_edge.green()}, {palette.glass_edge.blue()}, 60); }}')
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(14)

        mark = QLabel('M')
        mark.setObjectName('mCoreLogo')
        mark.setAccessibleName('M Core logo')
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(34, 32)
        self.style_core_logo(mark)
        layout.addWidget(mark)
        self.mark = mark

        brand = QLabel(APP_NAME)
        self.brand = brand
        brand.setStyleSheet(
            f'color: {palette.ink.name()}; font-family: {MONO_STACK};'
            ' font-size: 21px; font-weight: 700; letter-spacing: 2px;')
        layout.addWidget(brand)

        commit = build_commit()
        release = os.environ.get('JARVIS_SOURCE_RELEASE', '').strip()
        if commit:
            label = f'Revision {commit}'
        elif re.fullmatch(r'[0-9a-f]{64}', release):
            label = f'Source update {release[:8]}'
        else:
            label = 'Revision unavailable'
        build = QLabel(label)
        self.build_label = build
        build.setStyleSheet(f'color: {palette.muted.name()}; font-size: 11px;')
        build.setVisible(False)
        build.setParent(bar)
        brand.setToolTip(label)

        layout.addStretch(1)
        self.mic_mute_button = QPushButton('Mute mic')
        self.mic_mute_button.setCheckable(True)
        self.mic_mute_button.toggled.connect(self.window_ref.set_microphone_muted)
        self.output_mute_button = self.window_ref.voice_panel.mute_button
        self.state_chip = QLabel('READY')
        self.state_chip.setStyleSheet(
            f'color: {palette.good.name()}; font-size: 11px; font-weight: 600;'
            f' letter-spacing: 1.6px; border: 1px solid rgba({palette.good.red()}, '
            f'{palette.good.green()}, {palette.good.blue()}, 90); border-radius: 11px;'
            f' padding: 4px 12px;')
        layout.addWidget(self.state_chip)
        layout.addStretch(1)
        layout.addWidget(self.window_ref.resume_button)
        self.safety_controls = QHBoxLayout()
        self.safety_controls.setSpacing(6)
        self.safety_controls.addWidget(self.mic_mute_button)
        self.safety_controls.addWidget(self.output_mute_button)
        self.stop_button = self.window_ref.hud.strip.stop_button
        self.stop_button.setStyleSheet(
            f'QPushButton {{ color: {palette.danger.name()}; font-size: 12px;'
            f' font-weight: 600; border: 1px solid rgba({palette.danger.red()}, '
            f'{palette.danger.green()}, {palette.danger.blue()}, 120); border-radius: 11px;'
            f' padding: 5px 13px; background: rgba({palette.danger.red()}, '
            f'{palette.danger.green()}, {palette.danger.blue()}, 22); }}'
            f'QPushButton:hover {{ background: rgba({palette.danger.red()}, '
            f'{palette.danger.green()}, {palette.danger.blue()}, 48); }}')
        self.safety_controls.addWidget(self.stop_button)
        layout.addLayout(self.safety_controls)
        self.settings_button = QPushButton('Settings')
        self.settings_button.setCheckable(True)
        self.settings_button.clicked.connect(lambda checked: (
            self.open_section('Settings & Safety') if checked else self.close_drawer()))
        layout.addWidget(self.settings_button)

        self.menu_button = QPushButton('Menu')
        self.menu_button.setCheckable(True)
        self.menu_button.setAccessibleName('JARVIS menu')
        self.menu_button.clicked.connect(lambda checked: (
            self.show_drawer('menu') if checked else self.close_drawer()))
        layout.addWidget(self.menu_button)
        return bar

    def build_drawer(self):
        self.drawer = QFrame()
        self.drawer.setObjectName('primeDrawer')
        layout = QVBoxLayout(self.drawer)
        layout.setContentsMargins(18, 14, 14, 14)
        header = QHBoxLayout()
        self.drawer_title = QLabel()
        self.drawer_title.setObjectName('pageTitle')
        header.addWidget(self.drawer_title, 1)
        self.drawer_close = QPushButton('Close')
        self.drawer_close.setAccessibleName('Close side panel')
        self.drawer_close.clicked.connect(self.close_drawer)
        header.addWidget(self.drawer_close)
        layout.addLayout(header)

        self.drawer_content = QStackedWidget()
        self.drawer_content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        menu = QWidget()
        menu_layout = QVBoxLayout(menu)
        menu_layout.setContentsMargins(0, 6, 0, 0)
        menu_layout.setSpacing(12)
        self.menu_items = {}
        for title, section in (
            ('Chat', 'JARVIS Chat'),
            ('Automation', 'PC Control'),
        ):
            button = QPushButton(title)
            button.setAccessibleName(title)
            if section == 'PC Control':
                button.setObjectName('primary')
            button.clicked.connect(lambda _checked=False, name=section: self.open_section(name))
            menu_layout.addWidget(button)
            self.menu_items[section] = button
        controls = QGridLayout()
        for index, (title, action) in enumerate((
            ('Talk once', self.talk_once),
            ('Fullscreen', self.window_ref.toggle_fullscreen),
        )):
            button = QPushButton(title)
            button.clicked.connect(action)
            controls.addWidget(button, *divmod(index, 2))
        menu_layout.addLayout(controls)
        self.mini_view_button = QPushButton('Mini view')
        self.mini_view_button.clicked.connect(self.open_mini_view)
        menu_layout.addWidget(self.mini_view_button)
        menu_layout.addStretch(1)
        self.drawer_content.addWidget(menu)
        self.drawer_content.addWidget(self.window_ref.settings_scroller)
        self.drawer_content.addWidget(self.window_ref.news_panel)
        layout.addWidget(self.drawer_content, 1)
        close = QShortcut(QKeySequence('Escape'), self.drawer)
        close.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        close.activated.connect(self.close_drawer)
        self.drawer.hide()
        self.style_drawer()

    def show_drawer(self, name):
        title, index = {
            'menu': ('JARVIS Menu', 0),
            'settings': ('Settings & Safety', 1),
            'news': ('Tamil news', 2),
        }[name]
        self.drawer_title.setText(title)
        self.drawer_content.setCurrentIndex(index)
        self.settings_button.setChecked(name == 'settings')
        self.menu_button.setChecked(name == 'menu')
        self.resize_drawer()
        self.drawer.show()
        self.drawer_close.setFocus()

    def talk_once(self):
        self.close_drawer()
        self.window_ref.listen_to_user()

    def open_mini_view(self):
        self.close_drawer()
        self.window_ref.open_island()

    def close_drawer(self):
        was_open = not self.drawer.isHidden()
        return_focus = self.settings_button if self.settings_button.isChecked() else self.menu_button
        self.drawer.hide()
        self.settings_button.setChecked(False)
        self.menu_button.setChecked(False)
        if was_open:
            return_focus.setFocus()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'drawer'):
            self.resize_drawer()

    def resize_drawer(self):
        self.drawer.setFixedWidth(max(330, min(540, round(self.width() * 0.39))))

    def style_drawer(self):
        palette = self.palette_
        self.drawer.setStyleSheet(
            f'QFrame#primeDrawer {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,'
            f' stop:0 {palette.glass.name()}, stop:1 {palette.ground.name()});'
            f' border: 1px solid {palette.glass_edge.name()};'
            f' border-left: 2px solid {palette.accent.name()}; }}'
            'QFrame#primeDrawer QWidget#pageRoot { background: transparent; }')

    def style_core_logo(self, mark):
        palette = self.palette_
        mark.setStyleSheet(
            f'QLabel#mCoreLogo {{ color: {palette.accent.name()};'
            f' background: {palette.ground.name()}; border: 1px solid {palette.glass_edge.name()};'
            f' border-radius: 6px; font-family: {MONO_STACK}; font-size: 19px; font-weight: 700; }}')

    def refresh_theme(self):
        """Apply the selected theme to the top bar."""
        palette = self.palette_
        self.top_bar.setStyleSheet(
            f'QFrame#primeTopBar {{ background: rgba({palette.glass.red()}, '
            f'{palette.glass.green()}, {palette.glass.blue()}, {max(18, palette.glass.alpha())});'
            f' border: none; border-bottom: 1px solid rgba({palette.glass_edge.red()}, '
            f'{palette.glass_edge.green()}, {palette.glass_edge.blue()}, 60); }}')
        self.brand.setStyleSheet(
            f'color: {palette.ink.name()}; font-size: 21px; font-weight: 700;')
        self.build_label.setStyleSheet(f'color: {palette.muted.name()}; font-size: 11px;')
        self.style_core_logo(self.mark)
        self.set_state(self.window_ref.prime_state())
        self.style_drawer()

    def open_section(self, name: str):
        self.window_ref.open_section(name)

    def open_task_history(self):
        self.window_ref.open_section('Task History')

    def mark_active(self, name: str):
        for section, button in self.menu_items.items():
            button.setEnabled(section != name)

    def set_state(self, state: str):
        """Show what JARVIS is doing in the title bar and Activity."""
        palette = self.palette_
        label, tone = STATES[state]
        colour = getattr(palette, tone)
        label = label.upper()
        self.state_chip.setText(label)
        self.state_chip.setStyleSheet(
            f'color: {colour.name()}; font-size: 11px; font-weight: 600;'
            f' letter-spacing: 1.6px; border: 1px solid rgba({colour.red()}, '
            f'{colour.green()}, {colour.blue()}, 90); border-radius: 11px;'
            f' padding: 4px 12px;')

    def set_provider(self, text):
        provider = 'Chat · ' + text.removeprefix('Active brain: ')
        self.provider_label.setText(provider)
        self.provider_label.setToolTip(provider)
