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
    * an assistant that sits in the middle of an empty conversation and
      steps aside for it once there is something to read;
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

from PySide6.QtCore import (
    QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath,
    QPen, QRadialGradient,
)
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

from desktop.activity_panel import ActivityPanel, STATES


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

    def __init__(self, dark: bool = True):
        self.dark = dark
        if dark:
            self.ground = QColor('#05070c')
            self.ground_far = QColor('#0a1020')
            self.glass = QColor(255, 255, 255, 20)
            self.glass_edge = QColor(255, 255, 255, 34)
            self.ink = QColor('#eef3fb')
            self.muted = QColor('#93a1b8')
            self.accent = QColor('#63e6ff')
            self.accent_deep = QColor('#3a7bff')
            self.good = QColor('#5df2b0')
            self.warn = QColor('#ffcf6b')
            self.danger = QColor('#ff6b81')
            self.bubble_you = QColor(96, 150, 255, 58)
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
    """A rounded surface with a translucent fill and a luminous edge."""

    def __init__(self, palette: PrimePalette, radius: int = 18, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setObjectName('primeGlass')
        self._radius = radius
        self.refresh()

    def refresh(self):
        palette = self.palette_
        self.setStyleSheet(
            f'QFrame {{ background: rgba({palette.glass.red()}, {palette.glass.green()}, '
            f'{palette.glass.blue()}, {palette.glass.alpha()});'
            f' border: 1px solid rgba({palette.glass_edge.red()}, '
            f'{palette.glass_edge.green()}, {palette.glass_edge.blue()}, '
            f'{palette.glass_edge.alpha()});'
            f' border-radius: {self._radius}px; }}')


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
        self._target = 1.0
        self.setMinimumSize(64, 64)
        self.setAccessibleName('JARVIS')
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_state(self, state: str):
        """idle, listening, working or error."""
        if state != self.state:
            self.state = state
            self.update()

    def _tick(self):
        self._phase = (self._phase + 0.012) % (math.pi * 2)
        self.update()

    def _colours(self):
        palette = self.palette_
        if self.state in ('listening', 'speaking'):
            return palette.good, palette.accent
        if self.state == 'working':
            return palette.accent, palette.accent_deep
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
        glow.setColorAt(0.0, _alpha(bright.name(), 90))
        glow.setColorAt(0.45, _alpha(deep.name(), 34))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(centre, radius * 0.98, radius * 0.98)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        ring = radius * 0.70
        rect = QRectF(centre.x() - ring, centre.y() - ring, ring * 2, ring * 2)
        # Three arcs, each a third of the circle apart, each turning at
        # its own speed. The circle is never broken open on one side.
        for index in range(3):
            span = 78 + index * 18
            offset = self._phase * (1 if index % 2 == 0 else -1) + index * 2.094
            pen = QPen(_alpha(bright.name(), 215 if index == 0 else 120),
                       max(1.4, side * 0.017))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, int(math.degrees(offset)) % 360, int(span))
            painter.drawArc(rect, (int(math.degrees(offset)) + 180) % 360, int(span))

        breathing = 1.0 + 0.06 * math.sin(self._phase * 1.6)
        core = radius * 0.30 * breathing
        core_glow = QRadialGradient(centre, core)
        core_glow.setColorAt(0.0, QColor(255, 255, 255, 235))
        core_glow.setColorAt(0.35, _alpha(bright.name(), 220))
        core_glow.setColorAt(1.0, _alpha(deep.name(), 60))
        painter.setBrush(QBrush(core_glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(centre, core, core)

        font = QFont(self.font())
        font.setPointSizeF(max(6.5, side * 0.068))
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(0.4, side * 0.004))
        painter.setFont(font)
        painter.setPen(QPen(QColor('#04121a')))
        painter.drawText(QRectF(centre.x() - core * 1.6, centre.y() - core * 0.44,
                                core * 3.2, core * 0.88),
                         int(Qt.AlignmentFlag.AlignCenter), 'JARVIS')


class PrimeBubble(QFrame):
    """One message: the owner on the right, JARVIS on the left."""

    def __init__(self, role: str, content: str, palette: PrimePalette, parent=None):
        super().__init__(parent)
        # The owner is on the right. The store calls the owner's own
        # messages 'user'.
        you = role.lower() in ('user', 'you') or role.lower().startswith('you')
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
        who = QLabel('You' if you else 'JARVIS')
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
        self.setMinimumWidth(180)
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
        self.setFixedWidth(max(180, min(cap, width)))
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
    """The assistant in the middle of an empty conversation.

    It stands in the centre and it steps aside for the conversation once
    there is something to read, which is the only way an assistant can be
    in the way of nothing.
    """

    def __init__(self, palette: PrimePalette, window, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.window_ref = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addStretch(1)
        self.orb = PrimeOrb(palette)
        self.orb.setFixedSize(176, 176)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignCenter)
        row.addStretch(1)
        layout.addLayout(row)
        self.title = QLabel('How can I help?')
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet(f'color: {palette.ink.name()}; font-size: 20px; font-weight: 600;')
        layout.addWidget(self.title)
        self.hint = QLabel('Ask in Tamil, Tanglish, English or French.')
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet(f'color: {palette.muted.name()}; font-size: 13px;')
        layout.addWidget(self.hint)
        layout.addStretch(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        for child in (self.title, self.hint):
            child.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def refresh_theme(self):
        palette = self.palette_
        self.title.setStyleSheet(
            f'color: {palette.ink.name()}; font-size: 20px; font-weight: 600;')
        self.hint.setStyleSheet(f'color: {palette.muted.name()}; font-size: 13px;')
        self.orb.update()

    def set_busy(self, busy: bool):
        """The conversation is empty or it is not."""
        self.orb.setVisible(not busy)
        self.title.setVisible(not busy)
        self.hint.setVisible(not busy)

    def set_state(self, state: str):
        self.orb.set_state(state)


class PrimeComposer(QFrame):
    """The composer: the prompt and the controls, in one glass card."""

    def __init__(self, palette: PrimePalette, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.setObjectName('primeComposer')
        self.setStyleSheet(
            f'QFrame#primeComposer {{ background: rgba({palette.glass.red()}, '
            f'{palette.glass.green()}, {palette.glass.blue()}, {palette.glass.alpha()});'
            f' border: 1px solid rgba({palette.glass_edge.red()}, '
            f'{palette.glass_edge.green()}, {palette.glass_edge.blue()}, '
            f'{palette.glass_edge.alpha()}); border-radius: 20px; }}')
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
        compact = self.width() < 470
        if not self.buttons or compact == self._compact:
            return
        self._compact = compact
        for index, button in enumerate(self.buttons):
            row, column = divmod(index, 3) if compact else (0, index)
            self.controls.addWidget(button, row, column)
        for column in range(len(self.buttons)):
            self.controls.setColumnStretch(column, int(not compact or column < 3))

    def refresh_theme(self):
        palette = self.palette_
        self.setStyleSheet(
            f'QFrame#primeComposer {{ background: rgba({palette.glass.red()}, '
            f'{palette.glass.green()}, {palette.glass.blue()}, {palette.glass.alpha()});'
            f' border: 1px solid rgba({palette.glass_edge.red()}, '
            f'{palette.glass_edge.green()}, {palette.glass_edge.blue()}, '
            f'{palette.glass_edge.alpha()}); border-radius: 20px; }}')


class PrimeChat(QWidget):
    """The chat surface: the assistant, the conversation, the composer.

    The assistant stands in the middle while the conversation is empty
    and steps aside once there is something to read. The conversation
    moves; the composer stays where it is.
    """

    def __init__(self, window, palette: PrimePalette, parent=None):
        super().__init__(parent)
        self.window_ref = window
        self.palette_ = palette
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 14, 26, 12)
        layout.setSpacing(14)

        # Two states, one room: the assistant standing in the middle of
        # an empty conversation, and the conversation itself.
        self.states = QStackedWidget()
        self.assistant = PrimeAssistant(palette, window)
        self.conversation = PrimeConversation(palette)
        self.states.addWidget(self.assistant)
        self.states.addWidget(self.conversation)
        layout.addWidget(self.states, 1)
        self.task_panels = {}
        self.task_area = QStackedWidget()
        self.task_area.hide()
        self.dismiss_task = QPushButton('Close task details')
        self.dismiss_task.clicked.connect(lambda: window.open_section('JARVIS Chat'))
        self.dismiss_task.hide()
        layout.addWidget(self.dismiss_task)
        layout.addWidget(self.task_area, 2)

        # The approval the owner has to answer, the card of a running
        # job, and the plan of a job with more than one step come with
        # the chat. They are the same cards, moved and not rewritten.
        self.cards = QVBoxLayout()
        self.cards.setSpacing(10)
        layout.addLayout(self.cards)

        self.composer = PrimeComposer(palette)
        layout.addWidget(self.composer)
        self._adopt_composer()

    def _adopt_composer(self):
        """Move the real prompt and the real buttons into the new composer.

        They are the same widgets the old chat used, so nothing about the
        way a message is sent, attached, dictated or researched changes.
        """
        window = self.window_ref
        window.prompt.setMaximumHeight(96)
        window.research_button.setText('Read page')
        window.send_button.setText('Send')
        old_layout = window.composer_bar.layout()
        old_layout.removeWidget(window.prompt)
        self.composer.body.addWidget(window.prompt)

        browser = QPushButton('Browser')
        browser.clicked.connect(window.show_browser_commands)
        buttons = (window.chat_mic, window.attach_button, window.research_button,
                   browser, window.send_button)
        for button in buttons:
            window.composer_actions.removeWidget(button)
            button.setStyleSheet('padding: 7px 7px;')
        self.composer.set_controls(*buttons)

        for card in (window.browser_output, getattr(window, 'chat_approval', None),
                     getattr(window, 'chat_task_card', None),
                     getattr(window, 'plan_card', None)):
            if card is None:
                continue
            old_layout = card.parentWidget().layout() if card.parentWidget() else None
            if old_layout is not None:
                old_layout.removeWidget(card)
            self.cards.addWidget(card)

    def adopt_task_panels(self):
        window = self.window_ref
        names = ('Coding Assistant', 'Video Editor', 'Business', 'PC Control', 'Step Workflows',
                 'Task Queue', 'Command Center')
        # Move existing reviewed controls into the conversation. Keep compatibility
        # indices for shortcuts and settings without leaving another reachable page.
        widgets = {name: window.pages.widget(index) for name, index in window.page_indices.items()}
        for name in names:
            scroller = widgets[name]
            window.pages.removeWidget(scroller)
            self.task_panels[name] = self.task_area.addWidget(scroller)
        for name, widget in widgets.items():
            window.page_indices[name] = window.pages.indexOf(self if name in names else widget)
        for index in range(window.nav.count()):
            item = window.nav.item(index)
            item.setData(Qt.ItemDataRole.UserRole, window.page_indices[item.text()])

    def show_task(self, name):
        active = name in self.task_panels
        if active:
            self.task_area.setCurrentIndex(self.task_panels[name])
        self.task_area.setVisible(active)
        self.dismiss_task.setVisible(active)

    def refresh_theme(self):
        self.assistant.refresh_theme()
        self.conversation.refresh_theme()
        self.composer.refresh_theme()

    def render(self, messages):
        """Show the messages and let the assistant step aside.

        While the conversation is empty the assistant stands in the
        middle of it. Once there is something to read, it steps aside and
        the conversation takes the room.
        """
        self.conversation.render(messages)
        self.states.setCurrentIndex(0 if not messages else 1)

    def set_state(self, state: str):
        self.assistant.set_state(state)


class PrimeShell(QWidget):
    """The whole composition: the top bar, the rail, the content, the line."""

    def __init__(self, window, palette: PrimePalette, parent=None):
        super().__init__(parent)
        self.window_ref = window
        self.palette_ = palette
        self.setObjectName('primeShell')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.build_top_bar())
        self.provider_label = QLabel()
        self.provider_label.setWordWrap(True)
        self.provider_label.setContentsMargins(18, 0, 18, 6)
        outer.addWidget(self.provider_label)

        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(0)
        middle.addWidget(self.build_rail())
        self.content = QVBoxLayout()
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(0)
        middle.addLayout(self.content, 1)
        self.activity = ActivityPanel(palette, self.open_task_history)
        self.activity.hide()
        self.activity.closed.connect(lambda: self.activity_button.setChecked(False))
        self.activity_button.toggled.connect(self.activity.setVisible)
        middle.addWidget(self.activity)
        outer.addLayout(middle, 1)

    # -- the top bar ---------------------------------------------------

    def build_top_bar(self):
        bar = QFrame()
        bar.setObjectName('primeTopBar')
        bar.setFixedHeight(64)
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

        mark = PrimeOrb(palette)
        mark.setFixedSize(30, 30)
        layout.addWidget(mark)
        self.mark = mark

        brand = QLabel('JARVIS AI')
        self.brand = brand
        brand.setStyleSheet(
            f'color: {palette.ink.name()}; font-size: 14px; font-weight: 700;'
            f' letter-spacing: 2.6px;')
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
        layout.addWidget(build)

        layout.addStretch(1)
        self.state_chip = QLabel('READY')
        self.state_chip.setStyleSheet(
            f'color: {palette.good.name()}; font-size: 11px; font-weight: 600;'
            f' letter-spacing: 1.6px; border: 1px solid rgba({palette.good.red()}, '
            f'{palette.good.green()}, {palette.good.blue()}, 90); border-radius: 11px;'
            f' padding: 4px 12px;')
        layout.addWidget(self.state_chip)
        self.activity_button = QPushButton('Activity')
        self.activity_button.setCheckable(True)
        self.activity_button.setToolTip('Show recent actions and their status')
        layout.addWidget(self.activity_button)
        layout.addWidget(self.window_ref.resume_button)
        self.stop_button = QPushButton('Emergency stop')
        self.stop_button.clicked.connect(self.window_ref.stop)
        self.stop_button.setStyleSheet(
            f'QPushButton {{ color: {palette.danger.name()}; font-size: 12px;'
            f' font-weight: 600; border: 1px solid rgba({palette.danger.red()}, '
            f'{palette.danger.green()}, {palette.danger.blue()}, 120); border-radius: 11px;'
            f' padding: 5px 13px; background: rgba({palette.danger.red()}, '
            f'{palette.danger.green()}, {palette.danger.blue()}, 22); }}'
            f'QPushButton:hover {{ background: rgba({palette.danger.red()}, '
            f'{palette.danger.green()}, {palette.danger.blue()}, 48); }}')
        layout.addWidget(self.stop_button)
        return bar

    # -- the rail ------------------------------------------------------

    def build_rail(self):
        rail = QFrame()
        rail.setObjectName('primeRail')
        rail.setFixedWidth(84)
        self.rail = rail
        palette = self.palette_
        rail.setStyleSheet(
            f'QFrame#primeRail {{ background: rgba({palette.glass.red()}, '
            f'{palette.glass.green()}, {palette.glass.blue()}, 12);'
            f' border: none; border-right: 1px solid rgba({palette.glass_edge.red()}, '
            f'{palette.glass_edge.green()}, {palette.glass_edge.blue()}, 46); }}')
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(6)
        self.rail_buttons = {}
        for symbol, title, section in (
            ('◉', 'Chat', 'JARVIS Chat'),
            ('◈', 'Files', 'Files & Folders'),
            ('◐', 'Voice', 'Voice / Hey Jarvis'),
            ('◇', 'Cybersecurity', 'Cybersecurity'),
            ('◎', 'Memory', 'Memory'),
            ('⚙', 'Settings', 'Settings & Safety'),
        ):
            button = QPushButton(symbol)
            button.setToolTip(title)
            button.setAccessibleName(title)
            button.setCheckable(True)
            button.setFixedSize(58, 52)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, name=section: self.open_section(name))
            layout.addWidget(button)
            self.rail_buttons[section] = button
        self.island_button = QPushButton('▱')
        self.island_button.setToolTip('Island')
        self.island_button.setAccessibleName('Island')
        self.island_button.setFixedSize(58, 52)
        self.island_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.island_button.clicked.connect(self.window_ref.open_island)
        layout.addWidget(self.island_button)
        layout.addStretch(1)
        return rail

    def refresh_theme(self):
        """Write the top bar and the rail again, in the new colours."""
        palette = self.palette_
        self.top_bar.setStyleSheet(
            f'QFrame#primeTopBar {{ background: rgba({palette.glass.red()}, '
            f'{palette.glass.green()}, {palette.glass.blue()}, {max(18, palette.glass.alpha())});'
            f' border: none; border-bottom: 1px solid rgba({palette.glass_edge.red()}, '
            f'{palette.glass_edge.green()}, {palette.glass_edge.blue()}, 60); }}')
        self.rail.setStyleSheet(
            f'QFrame#primeRail {{ background: rgba({palette.glass.red()}, '
            f'{palette.glass.green()}, {palette.glass.blue()}, 12);'
            f' border: none; border-right: 1px solid rgba({palette.glass_edge.red()}, '
            f'{palette.glass_edge.green()}, {palette.glass_edge.blue()}, 46); }}')
        self.brand.setStyleSheet(
            f'color: {palette.ink.name()}; font-size: 14px; font-weight: 700;'
            f' letter-spacing: 2.6px;')
        self.build_label.setStyleSheet(f'color: {palette.muted.name()}; font-size: 11px;')
        self.set_state(self.mark.state)
        self.activity.refresh_theme()

    def open_section(self, name: str):
        if name == 'Cybersecurity':
            self.window_ref.open_network_diagnostics()
        else:
            self.window_ref.open_section(name)

    def open_task_history(self):
        self.activity_button.setChecked(False)
        self.window_ref.open_section('Task History')

    def mark_active(self, name: str):
        for section, button in self.rail_buttons.items():
            button.setChecked(section == name)

    def set_state(self, state: str):
        """The state chip and the mark follow what JARVIS is doing."""
        palette = self.palette_
        label, tone = STATES[state]
        colour = getattr(palette, tone)
        self.activity.set_state(state)
        label = label.upper()
        self.state_chip.setText(label)
        self.state_chip.setStyleSheet(
            f'color: {colour.name()}; font-size: 11px; font-weight: 600;'
            f' letter-spacing: 1.6px; border: 1px solid rgba({colour.red()}, '
            f'{colour.green()}, {colour.blue()}, 90); border-radius: 11px;'
            f' padding: 4px 12px;')
        self.mark.set_state(state)

    def set_provider(self, text):
        self.provider_label.setText(text)
