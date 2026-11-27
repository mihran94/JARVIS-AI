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
import platform
import time
from datetime import datetime
from pathlib import Path
import re
import subprocess
import sys
from core.runtime_profile import APP_NAME, APP_VERSION
from shiboken6 import isValid

from PySide6.QtCore import (
    QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFontMetrics, QKeySequence, QLinearGradient, QPainter, QPainterPath,
    QPen, QRadialGradient, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QMenu, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
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
            self.ground = QColor('#02070d')
            self.ground_far = QColor('#061321')
            self.glass = QColor('#081b2b')
            self.glass_edge = QColor('#23475b')
            self.ink = QColor('#e4f5ff')
            self.muted = QColor('#90b1c6')
            self.accent = QColor('#28e3ee')
            self.accent_deep = QColor('#168cbd')
            self.good = QColor('#5df2b0')
            self.warn = QColor('#ffcf6b')
            self.danger = QColor('#ff6b81')
            self.bubble_you = QColor(22, 140, 189, 52)
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
            f' padding-left: 8px; border-left: 2px solid {palette.warn.name()};'
            f' border-bottom: 1px solid {palette.glass_edge.name()}; }}')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette_
        width, height = self.width() - 1.5, self.height() - 1.5
        bevel = 12
        panel = QPainterPath(QPointF(0.5, bevel))
        for x, y in ((bevel, 0.5), (width, 0.5), (width, height - bevel),
                     (width - bevel, height), (0.5, height)):
            panel.lineTo(x, y)
        panel.closeSubpath()
        fill = QLinearGradient(0, 0, width, height)
        fill.setColorAt(0, palette.glass)
        fill.setColorAt(1, palette.ground)
        painter.fillPath(panel, QBrush(fill))
        painter.setPen(QPen(_alpha(palette.accent.name(), 105), 1))
        painter.drawPath(panel)
        painter.setPen(QPen(palette.accent, 1.5))
        painter.drawLine(QPointF(0.5, bevel), QPointF(bevel, 0.5))
        painter.drawLine(QPointF(bevel, 0.5), QPointF(min(64, width - 12), 0.5))
        painter.drawLine(QPointF(width - bevel, height), QPointF(width, height - bevel))


class CoreMark(QLabel):
    """A vector M monogram using the active HUD palette."""

    def __init__(self, palette, parent=None):
        super().__init__('M', parent)
        self.palette_ = palette

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width() / 40, self.height() / 40)
        frame = QPainterPath(QPointF(1, 9))
        for x, y in ((9, 1), (39, 1), (39, 31), (31, 39), (1, 39)):
            frame.lineTo(x, y)
        frame.closeSubpath()
        p.fillPath(frame, self.palette_.glass)
        p.setPen(QPen(_alpha(self.palette_.accent.name(), 150), 1))
        p.drawPath(frame)
        mark = QPainterPath(QPointF(10, 29))
        for x, y in ((10, 11), (20, 23), (30, 11), (30, 29)):
            mark.lineTo(x, y)
        p.setPen(QPen(_alpha(self.palette_.accent.name(), 45), 6))
        p.drawPath(mark)
        p.setPen(QPen(self.palette_.accent, 2))
        p.drawPath(mark)


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
        if self.state in ('listening', 'speaking'):
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
        signal = self._level / 100 if self.state in ('listening', 'speaking') else 0
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
                level = signal * (0.65 + 0.35 * abs(math.sin(self._phase + index * 0.7)))
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
        self.ensurePolished()
        self.body.ensurePolished()
        self.who.ensurePolished()
        metrics = QFontMetrics(self.body.font())
        width = max(1, min(cap, max(135, metrics.horizontalAdvance(self.body.text()) + 34)))
        layout = self.layout()
        margins = layout.contentsMargins()
        body_width = max(1, width - margins.left() - margins.right())
        body_height = max(self.body.fontMetrics().height(), self.body.heightForWidth(body_width))
        height = margins.top() + self.who.sizeHint().height() + layout.spacing() + body_height + margins.bottom()
        self.setFixedSize(width, height)

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
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.setWidget(self._holder)
        self._rows = []
        self._messages = []
        self._follow_latest = True
        self.verticalScrollBar().valueChanged.connect(self.track_scroll_position)
        self.verticalScrollBar().rangeChanged.connect(self.follow_new_range)

    def track_scroll_position(self, value):
        self._follow_latest = value >= self.verticalScrollBar().maximum() - 8

    def follow_new_range(self, _minimum, maximum):
        if self._follow_latest:
            self.verticalScrollBar().setValue(maximum)

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
        bar = self.verticalScrollBar()
        follow_latest = bar.value() >= bar.maximum() - 8
        self._follow_latest = follow_latest
        super().resizeEvent(event)
        for bubble in self.bubbles:
            bubble.fit_to_text(self.bubble_width())
        if follow_latest:
            QTimer.singleShot(0, self, lambda: bar.setValue(bar.maximum()))

    def bubble_width(self):
        return min(self.MAX_WIDTH, self.viewport().width() - 8)

    def render(self, messages):
        """Update the existing transcript and keep the reader's scroll position."""
        messages = list(messages)
        bar = self.verticalScrollBar()
        position = bar.value()
        append_only = messages[:len(self._messages)] == self._messages
        follow_latest = position >= bar.maximum() - 8 or not append_only
        self._follow_latest = follow_latest
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
            self._layout.addLayout(row)
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
        window.voice_panel.audio_level.connect(self.set_microphone_level)
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
        self.caption = QLabel()
        self.caption.setAccessibleName('Hologram captions')
        self.caption.setWordWrap(True)
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.hide()
        layout.addWidget(self.caption)
        self.heard = QPlainTextEdit()
        self.heard.setReadOnly(True)
        self.heard.setAccessibleName('Heard')
        self.heard.setFixedHeight(70)
        self.heard.hide()
        layout.addWidget(self.heard)
        layout.addStretch(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        for child in (self.title, self.hint):
            child.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.refresh_greeting()
        self.refresh_hologram()

    def set_microphone_level(self, level):
        if self.orb.state == 'listening':
            self.orb.set_level(level)

    def set_output_level(self, level):
        if self.orb.state == 'speaking':
            self.orb.set_level(level)

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
        self.heard.setPlainText('Heard  ·  ' + text)
        self.heard.show()
        self.caption.setText(text)
        self.refresh_caption()

    def refresh_caption(self):
        window = self.window_ref
        self.caption.setVisible(bool(self.caption.text()) and not window.voice_panel.microphone_muted
                                and window.hologram_captions.isChecked())


class PrimeComposer(QWidget):
    """The prompt and controls at the bottom of the chat panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('primeComposer')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
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
        compact = self.width() < row_width
        if compact == self._compact:
            return
        self._compact = compact
        columns = min(3, len(self.buttons)) if compact else len(self.buttons)
        for index, button in enumerate(self.buttons):
            row, column = divmod(index, columns)
            self.controls.addWidget(button, row, column)
        for column in range(len(self.buttons)):
            self.controls.setColumnStretch(column, int(column < columns))


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

        self.chat_history = GlassCard(palette)
        self.chat_history.setMinimumWidth(266)
        self.chat_history.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        history = QVBoxLayout(self.chat_history)
        history.setContentsMargins(14, 13, 14, 13)
        history.setSpacing(8)
        history_title = QLabel('COMMUNICATIONS')
        history_title.setObjectName('hudSectionTitle')
        chat_header = QHBoxLayout()
        chat_header.addWidget(history_title, 1)
        history.addLayout(chat_header)
        self.safety_controls = QGridLayout()
        self.safety_controls.setSpacing(6)
        self._safety_buttons = ()
        self.chat_history.installEventFilter(self)
        self.conversation = PrimeConversation(palette)
        history.addWidget(self.conversation, 1)
        self.empty_history = QLabel('Your conversation will appear here.')
        self.empty_history.setWordWrap(True)
        history.addWidget(self.empty_history, 1)
        self.chat_column = QWidget()
        chat_column = QVBoxLayout(self.chat_column)
        chat_column.setContentsMargins(0, 0, 0, 0)
        chat_column.setSpacing(12)
        chat_column.addWidget(self.chat_history, 1)
        dashboard.addWidget(self.chat_column, 0, 2)

        self.display = display = QWidget()
        display.setMinimumWidth(145)
        display.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        display_layout = QVBoxLayout(display)
        display_layout.setContentsMargins(0, 0, 0, 0)
        display_layout.setSpacing(8)
        display_tabs = QHBoxLayout()
        display_tabs.setSpacing(5)
        self.displays = QStackedWidget()
        self.displays.setMinimumHeight(150)
        self.displays.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.assistant = PrimeAssistant(palette, window)
        self.timeline = ActivityPanel(palette, window.prime_shell.open_task_history)
        self.timeline.setMinimumWidth(0)
        self.timeline.setMaximumWidth(16777215)
        self.timeline.closed.connect(lambda: self.show_display('hologram'))
        self.displays.addWidget(self.assistant)
        self.displays.addWidget(self.timeline)
        self.camera_preview = window.camera_panel.preview
        self.camera_preview.setMinimumHeight(0)
        self.camera_preview.setMaximumHeight(16777215)
        self.camera_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.displays.addWidget(self.camera_preview)
        window.camera_toggle.toggled.connect(
            lambda enabled: self.show_camera_preview(enabled and window.camera_preview_choice.isChecked()))
        window.camera_preview_choice.toggled.connect(
            lambda visible: self.show_camera_preview(visible and window.camera_toggle.isChecked()))
        from desktop.youtube_panel import YouTubePanel
        self.youtube = YouTubePanel()
        self.displays.addWidget(self.youtube)
        from desktop.web_panel import BrowserWindow
        self.web_panel = BrowserWindow(window)
        self.display_buttons = {}
        for key, label in (('hologram', 'Hologram'), ('media', 'Media')):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _checked=False, key=key: self.show_display(key))
            button.setParent(display)
            button.hide()
            self.display_buttons[key] = button
        self.display_buttons['hologram'].setChecked(True)
        self.voice_display = GlassCard(palette)
        voice_layout = QVBoxLayout(self.voice_display)
        voice_layout.setContentsMargins(12, 10, 12, 8)
        voice_title = QLabel('VOICE INTERFACE')
        voice_title.setObjectName('hudSectionTitle')
        voice_layout.addWidget(voice_title)
        voice_layout.addWidget(self.displays, 1)
        window.prime_shell.microphone_waveform.hide()
        display_layout.addWidget(self.voice_display, 1)
        self.terminal = GlassCard(palette)
        terminal_layout = QVBoxLayout(self.terminal)
        terminal_layout.setContentsMargins(10, 6, 10, 8)
        terminal_header = QHBoxLayout()
        terminal_heading = QLabel('TERMINAL / NEWS')
        terminal_heading.setObjectName('hudSectionTitle')
        terminal_header.addWidget(terminal_heading, 1)
        news_button = QPushButton('News')
        news_button.clicked.connect(window.request_news_briefing)
        terminal_header.addWidget(news_button)
        history_button = QPushButton('Task history')
        history_button.setCheckable(True)
        history_button.toggled.connect(self.switch_terminal)
        terminal_header.addWidget(history_button)
        terminal_header.addWidget(window.mission_mode)
        terminal_layout.addLayout(terminal_header)
        self.work_state = QLabel()
        self.work_state.setWordWrap(True)
        self.work_state.setTextFormat(Qt.TextFormat.PlainText)
        self.work_state.hide()
        terminal_layout.addWidget(self.work_state)
        self.terminal_output = QPlainTextEdit()
        self.terminal_output.setAccessibleName('Terminal output')
        self.terminal_output.setReadOnly(True)
        self.terminal_output.setPlaceholderText('Coding and news activity appears here.')
        self.terminal_output.document().setMaximumBlockCount(400)
        self.terminal_output.setFixedHeight(82)
        terminal_layout.addWidget(self.terminal_output)
        self.terminal_history = QPlainTextEdit()
        self.terminal_history.setAccessibleName('Task history')
        self.terminal_history.setReadOnly(True)
        self.terminal_history.setFixedHeight(82)
        self.terminal_history.hide()
        terminal_layout.addWidget(self.terminal_history)
        self.terminal.setVisible(bool(window.store.get('appearance:terminal', True)))
        display_layout.addWidget(self.terminal)
        dashboard.addWidget(display, 0, 1)

        self.workspace = GlassCard(palette)
        self.workspace.setMinimumWidth(150)
        self.workspace.setMaximumWidth(230)
        self.workspace.setMaximumHeight(245)
        self.workspace.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        workspace = QVBoxLayout(self.workspace)
        workspace.setContentsMargins(14, 13, 14, 13)
        system_title = QLabel('SYSTEM')
        system_title.setObjectName('hudSectionTitle')
        workspace.addWidget(system_title)
        from desktop.hud import HudDial
        self.gpu_dial, self.temperature_dial = HudDial('GPU'), HudDial('TEMP')
        gauges = QGridLayout()
        for index, meter in enumerate((window.hud.strip.cpu, window.hud.strip.ram,
                                       self.gpu_dial, self.temperature_dial)):
            meter.setFixedHeight(82)
            meter.setMinimumWidth(0)
            meter.setMaximumWidth(16777215)
            meter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            gauges.addWidget(meter, index // 2, index % 2)
        workspace.addLayout(gauges)
        self.system_rail = QWidget()
        self.system_rail.setMaximumWidth(230)
        rail = QVBoxLayout(self.system_rail)
        rail.setContentsMargins(0, 0, 0, 0)
        rail.setSpacing(12)
        rail.addWidget(self.workspace)
        self.reference_cards = []
        for title, attr in (('STATUS', 'status_detail'), ('WEATHER', 'weather_detail')):
            card = GlassCard(palette)
            body = QVBoxLayout(card)
            body.setContentsMargins(12, 10, 12, 10)
            heading = QLabel(title)
            heading.setObjectName('hudSectionTitle')
            body.addWidget(heading)
            detail = QLabel()
            detail.setWordWrap(True)
            detail.setTextFormat(Qt.TextFormat.PlainText)
            detail.setStyleSheet(f'color: {palette.muted.name()}; font-size: 12px;')
            setattr(self, attr, detail)
            body.addWidget(detail)
            if title == 'WEATHER':
                from desktop.weather_visual import WeatherVisual
                heading.setText('TIME / WEATHER')
                self.weather_visual = WeatherVisual()
                self.weather_visual.set_motion(not window.reduce_motion.isChecked())
                window.reduce_motion.toggled.connect(
                    lambda reduced: self.weather_visual.set_motion(not reduced))
                body.insertWidget(1, self.weather_visual)
                clock = window.prime_shell.clock_label
                date = window.prime_shell.date_label
                clock.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
                clock.setAlignment(Qt.AlignmentFlag.AlignLeft)
                body.insertWidget(1, clock)
                body.insertWidget(2, date)
                clock.show()
                date.show()
                self.weather_refresh = QPushButton('Refresh weather')
                self.weather_refresh.clicked.connect(self.refresh_weather)
                body.addWidget(self.weather_refresh)
            self.reference_cards.append(card)
            rail.addWidget(card)
        self.weather_detail.setText('Paris, France\nRefresh to load · Open-Meteo')
        self.weather_timer = QTimer(self, interval=15 * 60 * 1000)
        self.weather_timer.timeout.connect(self.refresh_weather)
        self.weather_timer.start()
        rail.addStretch(1)
        dashboard.addWidget(self.system_rail, 0, 0)
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

        self.composer = PrimeComposer()
        self.composer_rule = QFrame()
        self.composer_rule.setFixedHeight(1)
        self.composer_rule.setStyleSheet(f'background: {palette.glass_edge.name()};')
        history.addWidget(self.assistant.heard)
        self.command_panel = GlassCard(palette)
        command = QVBoxLayout(self.command_panel)
        command.setContentsMargins(12, 10, 12, 12)
        command_heading = QLabel('COMMAND')
        command_heading.setObjectName('hudSectionTitle')
        command.addWidget(command_heading)
        command.addWidget(self.composer)
        command.addLayout(self.safety_controls)
        chat_column.addWidget(self.command_panel)
        self.voice_button = QPushButton('Start voice')
        self.voice_button.setAccessibleName('Start Gemini voice conversation')
        self.voice_button.setToolTip('Start a continuous Tamil or Tanglish conversation with Gemini.')
        self.voice_button.clicked.connect(window.toggle_live_voice)
        self.suggestions_button = QPushButton('💡')
        self.suggestions_button.setAccessibleName('Suggestions')
        self.suggestions_button.setToolTip('Show suggestions for the current chat')
        self.suggestions_menu = QMenu(self.suggestions_button)
        self.suggestions_button.setMenu(self.suggestions_menu)
        self.suggestions_menu.aboutToShow.connect(self.populate_suggestions)
        self._adopt_composer()
        self.refresh_reference_panels()

    def refresh_weather(self):
        ui = self.window_ref.omega
        if ui is not None:
            if self.window_ref.policy.stopped:
                return
            ui.feeds.refresh(weather_only=True)
            self.weather_detail.setText((ui.location.text().strip() or 'Selected coordinates')
                                        + '\nFetching weather…')

    def refresh_reference_panels(self, data=None):
        import psutil
        window = self.window_ref
        try:
            elapsed = max(0, int(time.time() - psutil.boot_time()))
            uptime = f'{elapsed // 3600:02}:{elapsed % 3600 // 60:02}'
            processes = str(len(psutil.pids()))
        except (OSError, psutil.Error):
            uptime = processes = 'Unavailable'
        engine = 'Gemini Live' if window.live_voice is not None else window.provider.currentText()
        network = (data or {}).get('network_status', 'Not measured')
        self.status_detail.setText(f'UPTIME   {uptime}\nPROCESSES   {processes}\n'
                                   f'NETWORK   {network}\nPLATFORM   {platform.system()}\nENGINE   {engine}')
        gpu, temperature = (data or {}).get('gpu_usage_percent'), (data or {}).get('cpu_temperature_c')
        self.gpu_dial.set_reading(None if gpu is None else gpu / 100, 'N/A' if gpu is None else f'{gpu:.0f}%')
        self.temperature_dial.set_reading(None if temperature is None else temperature / 100,
                                          'N/A' if temperature is None else f'{temperature:.0f}°C')
        ui = window.omega
        if ui is not None and ui.weather_value.text() not in ('—', ''):
            from desktop.weather_visual import weather_kind
            code = getattr(ui, 'weather_code', None)
            condition = weather_kind(code)
            self.weather_visual.set_weather(code, getattr(ui, 'weather_day', True))
            self.weather_detail.setText(ui.weather_value.text() + ' · ' + condition
                                        + '\n' + ui.weather_detail.text())
        if ui is not None:
            headlines = ui.news_value.text()
            if ('  ·  ' in headlines and headlines != getattr(self, '_last_feed_news', '')):
                self._last_feed_news = headlines
                self.terminal_output.appendPlainText('NEWS\n' + headlines)

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
        self.composer.body.addWidget(window.attach_button)
        window.attach_button.setMinimumHeight(42)
        window.attach_button.setStyleSheet('border: 1px dashed #28e3ee; padding: 8px;')
        entry = QHBoxLayout()
        entry.addWidget(window.prompt, 1)
        entry.addWidget(window.send_button)
        self.composer.body.addLayout(entry)

        window.suggestion_mode.hide()
        for button in (window.attach_button, window.send_button):
            window.composer_actions.removeWidget(button)
            button.setStyleSheet('padding: 7px 7px;')
        self.voice_button.hide()
        self.suggestions_button.hide()
        self.composer.set_controls(window.prime_shell.mic_mute_button, window.camera_toggle)

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

    def set_live_voice_status(self, state, *, enabled):
        if state == 'idle':
            label, description = 'Start voice', 'Start Gemini voice conversation'
        elif state == 'connecting':
            label, description = 'Cancel', 'Cancel the Gemini voice connection'
        else:
            label, description = 'End voice', 'End Gemini voice conversation'
        self.voice_button.setText(label)
        self.voice_button.setAccessibleName(description)
        self.voice_button.setToolTip(description)
        self.voice_button.setEnabled(enabled or state != 'idle')
        self.composer.layout_controls()

    def populate_suggestions(self):
        window = self.window_ref
        menu = self.suggestions_menu
        menu.clear()
        if window.suggested_steps:
            menu.addAction('Review suggested steps', window.review_suggested_plan)
        if window.prompt.toPlainText().strip():
            action = menu.addAction('Suggest with Gemini', window.suggest_chat_draft)
            action.setEnabled(window.worker is None and not window.voice_panel.live_voice_active
                              and not window.policy.stopped)
        else:
            menu.addAction('Suggest next steps', lambda: self.draft_suggestion('/suggest '))

    def draft_suggestion(self, text):
        prompt = self.window_ref.prompt
        if not prompt.toPlainText().strip():
            prompt.insertPlainText(text)
        prompt.setFocus()

    def switch_terminal(self, history):
        self.terminal_history.setVisible(history)
        self.terminal_output.setVisible(not history)
        if history:
            rows = self.window_ref.store.tasks()
            self.terminal_history.setPlainText('\n\n'.join(
                f"{row['kind']} · {row['status']}\n{row['detail'] or ''}" for row in rows
            ) or 'No actions recorded yet.')

    def write_terminal(self, label, text):
        if text:
            self.terminal_output.appendPlainText(f'{label}\n{text}')

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
        widget = {'hologram': self.assistant, 'timeline': self.timeline, 'media': self.youtube,
                  'local_media': self.player}[name]
        self.displays.setCurrentWidget(widget)
        button = self.display_buttons.get('media' if name == 'local_media' else name)
        if button is not None:
            button.setChecked(True)
        self.window_ref.prime_shell.mark_active('JARVIS Chat')
        self.update_workspace_visibility()

    def open_browser(self, url=''):
        self.window_ref.prime_shell.close_drawer()
        self.window_ref.open_section('JARVIS Chat')
        self.web_panel.open_url(url)

    def play_youtube(self, url):
        self.displays.setCurrentWidget(self.youtube)
        self.display_buttons['media'].setChecked(True)
        self.update_workspace_visibility()
        self.youtube.open_url(url)

    def show_camera_preview(self, enabled):
        if enabled:
            self.displays.setCurrentWidget(self.camera_preview)
        elif self.displays.currentWidget() is self.camera_preview:
            self.show_display('hologram')

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
        self.system_rail.setVisible(show_workspace and self.width() >= 850)
        grid = self.dashboard.layout()
        stacked = task_open and self.width() < 900
        self.display.setMinimumHeight(260 if stacked else 0)
        self.terminal.setVisible(not stacked and bool(self.window_ref.store.get('appearance:terminal', True)))
        if getattr(self, '_stacked_task', False) != stacked:
            self._stacked_task = stacked
            grid.removeWidget(self.display)
            grid.removeWidget(self.chat_column)
            if stacked:
                grid.addWidget(self.display, 0, 1, 1, 2)
                grid.addWidget(self.chat_column, 1, 1, 1, 2)
            else:
                grid.addWidget(self.display, 0, 1)
                grid.addWidget(self.chat_column, 0, 2)
            grid.setRowStretch(0, 1)
            grid.setRowStretch(1, 1 if stacked else 0)
        grid.setColumnStretch(0, 2 if show_workspace else 0)
        self.window_ref.mission_mode.setVisible(not task_open)

    def eventFilter(self, watched, event):
        if watched is self.chat_history and event.type() == QEvent.Type.Resize:
            self.layout_safety_controls(event.size().width())
        return False

    def place_safety_controls(self, buttons):
        self._safety_buttons = buttons
        self.layout_safety_controls(self.chat_history.width())

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
        self.command_panel.refresh()
        self.voice_display.refresh()
        for card in self.reference_cards:
            card.refresh()
        self.terminal.refresh()
        self.timeline.refresh_theme()
        self.composer_rule.setStyleSheet(f'background: {self.palette_.glass_edge.name()};')

    def render(self, messages):
        self.conversation.setVisible(bool(messages))
        self.empty_history.setVisible(not messages)
        self.conversation.render(messages)

    def set_state(self, state: str):
        self.assistant.set_state(state)
        self.timeline.set_state(state)


class MicrophoneWaveform(QWidget):
    """A scrolling history of the measured microphone input."""

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.level = 0
        self.samples = [0] * 90
        self.setFixedHeight(38)
        self.setAccessibleName('Microphone waveform')
        self.timer = QTimer(self, interval=60)
        self.timer.timeout.connect(self.advance)

    def showEvent(self, event):
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def set_level(self, value):
        self.level = max(0, min(100, value))

    def advance(self):
        self.samples = self.samples[1:] + [self.level]
        self.level = 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette_.accent, 2))
        spacing = self.width() / len(self.samples)
        center = self.height() / 2
        for index, value in enumerate(self.samples):
            half = max(0.5, value / 100 * (center - 3))
            x = spacing * (index + 0.5)
            painter.drawLine(QPointF(x, center - half), QPointF(x, center + half))


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
        window.hud.setParent(self)
        window.hud.hide()

        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)
        self.content = QVBoxLayout()
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(0)
        middle.addLayout(self.content, 1)
        self.build_drawer()
        self.build_settings_dialog()
        outer.addLayout(middle, 1)
        self.startup_notice = QLabel()
        self.startup_notice.setObjectName('startupNotice')
        self.startup_notice.setAccessibleName('JARVIS welcome and sharing notice')
        self.startup_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.startup_notice.setWordWrap(True)
        self.startup_notice.setContentsMargins(16, 4, 16, 6)
        self.startup_notice.hide()
        self.microphone_waveform = MicrophoneWaveform(palette, self)
        footer = QHBoxLayout()
        footer.setContentsMargins(16, 0, 16, 5)
        self.footer_status = QLabel()
        self.footer_status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.footer_status.setStyleSheet(f'color: {palette.accent.name()}; font-size: 10px;')
        footer.addWidget(self.footer_status, 1)
        self.footer_shortcuts = QLabel('F4  MUTE   ·   F11  FULLSCREEN   ·   ESC  INTERRUPT')
        self.footer_shortcuts.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.footer_shortcuts.setAlignment(Qt.AlignmentFlag.AlignRight)
        footer.addWidget(self.footer_shortcuts, 1)
        window.hud.strip.mic.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        window.hud.strip.mic.setMinimumWidth(110)
        window.hud.strip.mic.hide()
        window.hud.strip.mute.hide()
        self.output_mute_button.hide()
        outer.addLayout(footer)
        self.clock_timer = QTimer(self, interval=1000)
        self.clock_timer.timeout.connect(self.refresh_clock)
        self.clock_timer.start()
        self.refresh_clock()
        self.mute_shortcut = QShortcut(QKeySequence('F4'), self.window_ref)
        self.mute_shortcut.activated.connect(lambda: self.window_ref.set_microphone_muted(
            not self.window_ref.voice_panel.microphone_muted))
        self.interrupt_shortcut = QShortcut(QKeySequence('Escape'), self.window_ref)
        self.interrupt_shortcut.activated.connect(self.interrupt_or_close)
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
            buttons = (self.stop_button,)
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

        mark = CoreMark(palette)
        mark.setObjectName('mCoreLogo')
        mark.setAccessibleName('M Core logo')
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(40, 40)
        self.style_core_logo(mark)
        layout.addWidget(mark)
        self.mark = mark

        brand = QLabel(APP_NAME)
        self.brand = brand
        brand.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        brand.setMinimumWidth(0)
        brand.setStyleSheet(
            f'color: {palette.ink.name()}; font-family: {MONO_STACK};'
            ' font-size: 21px; font-weight: 700; letter-spacing: 2px;')
        layout.addWidget(brand, 2)

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
        self.mic_mute_button = QPushButton('🎙')
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
        self.clock_label = QLabel()
        self.clock_label.setAccessibleName('Current time and date')
        self.clock_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.clock_label.setMaximumWidth(190)
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.clock_label.setStyleSheet(f'color: {palette.accent.name()}; font-family: {MONO_STACK}; font-size: 22px;')
        self.clock_label.setParent(bar)
        self.clock_label.hide()
        self.date_label = QLabel(bar)
        self.date_label.setAccessibleName('Current date')
        self.date_label.setStyleSheet(f'color: {palette.muted.name()}; font-size: 11px;')
        self.date_label.hide()
        layout.addWidget(self.window_ref.resume_button)
        self.safety_controls = QHBoxLayout()
        self.safety_controls.setSpacing(6)
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
        self.settings_button = QPushButton('⚙')
        self.settings_button.setAccessibleName('Settings')
        self.settings_button.setToolTip('Settings')
        self.settings_button.setFixedWidth(42)
        self.settings_button.setCheckable(True)
        self.settings_button.clicked.connect(lambda checked: (
            self.open_section('Settings & Safety') if checked else self.settings_dialog.close()))
        layout.addWidget(self.settings_button)
        self.settings_button.hide()

        self.menu_button = QPushButton('☷')
        self.menu_button.setFixedWidth(42)
        self.menu_button.setToolTip('Menu')
        self.menu_button.setCheckable(True)
        self.menu_button.setAccessibleName('JARVIS menu')
        self.menu_button.clicked.connect(lambda checked: (
            self.show_drawer('menu') if checked else self.close_drawer()))
        layout.addWidget(self.menu_button)
        self.fullscreen_button = QPushButton('⛶')
        self.fullscreen_button.setFixedWidth(42)
        self.fullscreen_button.setAccessibleName('Toggle fullscreen')
        self.fullscreen_button.setToolTip('Fullscreen (F11)')
        self.fullscreen_button.clicked.connect(self.window_ref.toggle_fullscreen)
        layout.addWidget(self.fullscreen_button)
        return bar

    def interrupt_or_close(self):
        if self.settings_dialog.isVisible():
            self.settings_dialog.close()
        elif self.drawer.isVisible():
            self.close_drawer()
        else:
            self.window_ref.stop()

    def refresh_clock(self):
        now = datetime.now().astimezone()
        self.clock_label.setText(now.strftime('%H:%M:%S'))
        self.date_label.setText(now.strftime('%A, %d %b %Y'))
        live = getattr(self.window_ref, 'live_voice', None)
        engine = 'GEMINI LIVE' if live is not None else self.window_ref.provider.currentText().upper()
        mic = 'MUTED' if self.window_ref.voice_panel.microphone_muted else (
            'LIVE' if live is not None else 'READY')
        control = 'CONTROL ACTIVE' if self.window_ref.desktop_control_active else 'M-CORE'
        self.footer_status.setText(f'● ENGINE · {engine}     ● MIC · {mic}     ● {control}')

    def build_drawer(self):
        self.drawer = QFrame(self)
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
        menu_layout.setSpacing(8)
        self.menu_items = {}
        self.menu_settings_button = QPushButton('Settings')
        self.menu_settings_button.clicked.connect(lambda: self.open_section('Settings & Safety'))
        menu_layout.addWidget(self.menu_settings_button)
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
            button.hide()
        plugins = QPushButton('Plugins')
        plugins.clicked.connect(self.window_ref.open_plugins)
        menu_layout.addWidget(plugins)
        for title, action in (
            ('Browser', lambda: self.window_ref.prime_chat.open_browser()),
            ('Desktop Control', lambda: self.window_ref.open_setting_category('Desktop Control')),
            ('Files & Folders', lambda: self.open_section('Files & Folders')),
            ('Remote Control', lambda: self.window_ref.open_setting_category('Remote Control')),
            ('Saved Projects', self.window_ref.open_saved_projects),
            ('Task History', self.open_task_history),
            ('Version & Updates', lambda: self.window_ref.open_setting_category('Version & Updates')),
            ('Help', lambda: self.window_ref.show_local_system_reply('Help',
                'Speak in Tamil or Tanglish, or type and press Enter. Use /suggest for ideas. '
                'F4 toggles the mic; F11 toggles fullscreen; Esc interrupts.')),
        ):
            button = QPushButton(title)
            button.clicked.connect(self.close_drawer)
            button.clicked.connect(action)
            menu_layout.addWidget(button)
        archives = self.window_ref.archives
        archives.setSizeAdjustPolicy(archives.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        archives.setMinimumContentsLength(10)
        archives.setAccessibleName('Saved conversations')
        archives.setPlaceholderText('Saved conversations')
        archives.setParent(menu)
        archives.hide()
        for title, button in (('Open chat', self.window_ref.archive_button),
                              ('New chat', self.window_ref.new_chat_button)):
            button.setText(title)
            button.clicked.connect(self.close_drawer)
        for button in (self.window_ref.archive_button, self.window_ref.new_chat_button):
            button.setParent(menu)
            button.hide()
        self.mini_view_button = QPushButton('Mini view', menu)
        self.mini_view_button.clicked.connect(self.open_mini_view)
        self.mini_view_button.hide()
        menu_layout.addStretch(1)
        version = QLabel(f'{APP_NAME} {APP_VERSION}')
        version.setToolTip(self.build_label.text())
        menu_layout.addWidget(version)
        self.menu_scroller = QScrollArea()
        self.menu_scroller.setAccessibleName('JARVIS menu options')
        self.menu_scroller.setFrameShape(QFrame.Shape.NoFrame)
        self.menu_scroller.setWidgetResizable(True)
        self.menu_scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.menu_scroller.setWidget(menu)
        self.drawer_content.addWidget(self.menu_scroller)
        self.drawer_content.addWidget(self.window_ref.news_panel)
        layout.addWidget(self.drawer_content, 1)
        close = QShortcut(QKeySequence('Escape'), self.drawer)
        close.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        close.activated.connect(self.close_drawer)
        self.drawer.hide()
        self.style_drawer()

    def build_settings_dialog(self):
        self.settings_dialog = QDialog(self, Qt.WindowType.Tool)
        self.settings_dialog.setWindowTitle('Settings & Safety')
        self.settings_dialog.setObjectName('primeDrawer')
        available = self.screen().availableGeometry()
        self.settings_dialog.resize(min(820, max(360, available.width() - 12)),
                                    min(690, max(400, available.height() - 80)))
        self.settings_dialog.setMinimumSize(360, 400)
        self.settings_dialog.finished.connect(lambda: self.settings_button.setChecked(False))
        layout = QVBoxLayout(self.settings_dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(self.window_ref.settings_scroller)
        self.settings_dialog.setStyleSheet(self.drawer.styleSheet())
        self.settings_dialog.finished.connect(
            lambda: QApplication.instance().removeEventFilter(self))

    def eventFilter(self, watched, event):
        dialog = getattr(self, 'settings_dialog', None)
        if (event.type() == QEvent.Type.MouseButtonPress and self.drawer.isVisible()
                and watched is not self.menu_button and QApplication.activePopupWidget() is None
                and not self.drawer.rect().contains(self.drawer.mapFromGlobal(event.globalPosition().toPoint()))):
            self.close_drawer()
        if (event.type() == QEvent.Type.MouseButtonPress and dialog is not None
                and isValid(dialog) and dialog.isVisible()):
            popup = QApplication.activePopupWidget()
            inside_popup = popup is not None and isinstance(watched, QWidget) and (
                popup is watched or popup.isAncestorOf(watched))
            if not inside_popup and not dialog.frameGeometry().contains(event.globalPosition().toPoint()):
                dialog.close()
        # Application filters also receive teardown events for objects whose
        # native Qt wrapper has already been released. We never consume an
        # event, so avoid forwarding those wrappers through the C++ base call.
        return False

    def show_drawer(self, name):
        if name == 'settings':
            self.close_drawer()
            self.settings_button.setChecked(True)
            self.settings_dialog.show()
            QApplication.instance().installEventFilter(self)
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        title, index = {
            'menu': ('JARVIS Menu', 0),
            'news': ('Tamil news', 1),
        }[name]
        self.settings_dialog.close()
        self.drawer_title.setText(title)
        self.drawer_content.setCurrentIndex(index)
        if name == 'menu':
            self.menu_scroller.verticalScrollBar().setValue(0)
        self.menu_button.setChecked(name == 'menu')
        self.resize_drawer()
        self.drawer.show()
        self.drawer.raise_()
        QApplication.instance().installEventFilter(self)
        self.drawer_close.setFocus()

    def talk_once(self):
        self.close_drawer()
        self.window_ref.listen_to_user()

    def open_mini_view(self):
        self.close_drawer()
        self.window_ref.open_island()

    def close_drawer(self):
        dialog = getattr(self, 'settings_dialog', None)
        if dialog is not None and isValid(dialog):
            dialog.close()
        was_open = not self.drawer.isHidden()
        self.drawer.hide()
        QApplication.instance().removeEventFilter(self)
        self.menu_button.setChecked(False)
        if was_open:
            self.menu_button.setFocus()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'drawer'):
            self.resize_drawer()

    def resize_drawer(self):
        news = self.drawer_content.currentIndex() == 1
        width = min(540 if news else 360, max(280, self.width() - 24))
        height = min(560 if news else 520, max(240, self.height() - self.top_bar.height() - 24))
        self.drawer.setGeometry(max(12, self.width() - width - 16), self.top_bar.height() + 8, width, height)

    def style_drawer(self):
        palette = self.palette_
        self.drawer.setStyleSheet(
            f'QFrame#primeDrawer, QDialog#primeDrawer {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,'
            f' stop:0 {palette.glass.name()}, stop:1 {palette.ground.name()});'
            f' border: 1px solid {palette.glass_edge.name()};'
            f' border-radius: 10px; border-top: 2px solid {palette.accent.name()}; }}'
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
        self.settings_dialog.setStyleSheet(self.drawer.styleSheet())

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
