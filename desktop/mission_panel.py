"""The JARVIS mission console — the Command Deck.

WHAT THIS IS
    A page in the desktop application that shows one mission while it
    runs, with the computer it is running on around it. The owner types
    a goal, JARVIS works towards it, and every step is shown as it
    happens: what JARVIS decided, which tool it called, when the owner's
    approval was needed, what came back, and what the evidence was.

    The layout is three columns:

    * on the left, the real readings of this computer — the CPU and the
      memory as rings, the last readings as a line, and the owner's own
      notes;
    * in the middle, the mission: its goal, its rail of steps, the
      approval it is waiting for and the answer it produced;
    * on the right, the evidence — the calls that really ran, what they
      returned, and the final answer.

    The rail is painted rather than assembled from list rows, because the
    rail is the point: one marker per step, coloured by kind, and the
    newest step glows.

WHAT THIS IS NOT
    * It does not run anything. It shows what `core.mission` did, and the
      window that owns it starts and stops the mission.
    * It does not invent progress. There is no percentage and no
      estimate. The counter says which step of how many, and only the
      steps that really ran are on the rail.
    * It does not show a tool as successful unless the tool returned.
    * A reading that cannot be taken is shown as unavailable. The rings
      never carry a made-up number.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget, QComboBox,
)

from core.mission import BUDGET_SECONDS, MAX_STEPS
from desktop.prime_theme import MONO_STACK
from security.policy import Stopped

#: How each kind of step is coloured on the rail.
KIND_COLOURS = {
    'goal': 'accent',
    'thought': 'muted',
    'tool': 'accent',
    'approval': 'warn',
    'result': 'good',
    'answer': 'good',
    'error': 'danger',
    'cancelled': 'warn',
}

#: The words the status pill uses.
STATUS_WORDS = {
    'idle': 'Ready',
    'running': 'Working',
    'approval': 'Approval needed',
    'completed': 'Complete',
    'failed': 'Failed',
    'cancelled': 'Cancelled',
}

#: The colour of the status pill.
STATUS_COLOURS = {
    'idle': 'muted',
    'running': 'accent',
    'approval': 'warn',
    'completed': 'good',
    'failed': 'danger',
    'cancelled': 'warn',
}

#: How many readings the little line chart keeps.
SAMPLE_HISTORY = 24

#: How often the readings are taken, in milliseconds.
REFRESH_MS = 2000


def _mono(size: int, weight: int = 500) -> QFont:
    """The technical face of the interface."""
    font = QFont()
    font.setFamilies([family.strip().strip("'") for family in MONO_STACK.split(',')])
    font.setPointSize(size)
    font.setWeight(QFont.Weight(weight))
    return font


def _glass(palette, alpha=12, edge=26):
    """The translucent fill and the luminous edge of a surface."""
    fill = QColor(255, 255, 255, alpha)
    edge_colour = QColor(255, 255, 255, edge)
    return fill, edge_colour


class GaugeRing(QWidget):
    """One real reading, drawn as a ring.

    The ring shows a share of a whole: the CPU load, the memory in use.
    A reading that is not available draws an empty ring and says so,
    because a guessed number on a gauge is worse than no gauge.
    """

    def __init__(self, palette, caption, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.caption = caption
        self.value = None
        self.text = '—'
        self.setFixedSize(112, 112)
        self.setAccessibleName(caption)

    def set_reading(self, percent, text):
        """Show a reading. `percent` is None when it is not available."""
        self.value = percent
        self.text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette_
        centre = self.rect().center()
        radius = 36
        box = QRectF(centre.x() - radius, centre.y() - radius - 6, radius * 2, radius * 2)

        painter.setPen(QPen(QColor(255, 255, 255, 30), 7))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(box, 0, 360 * 16)

        if self.value is not None:
            colour = getattr(palette, 'accent')
            painter.setPen(QPen(QColor(colour), 7))
            painter.drawArc(box, int(-90 * 16), int(360 * max(0.0, min(1.0, self.value)) * 16))

        painter.setPen(QPen(QColor(palette.ink)))
        painter.setFont(_mono(11, 600))
        metrics = QFontMetrics(painter.font())
        text = self.text
        painter.drawText(QRectF(centre.x() - radius, centre.y() - 10, radius * 2, 20),
                         Qt.AlignmentFlag.AlignCenter, text)

        painter.setPen(QPen(QColor(palette.muted)))
        painter.setFont(_mono(8, 600))
        painter.drawText(QRectF(0, self.height() - 20, self.width(), 16),
                         Qt.AlignmentFlag.AlignCenter, self.caption.upper())


class SampleLine(QWidget):
    """The last readings of one measurement, drawn as a line.

    The line is scaled to the readings it holds, so the shape is the
    truth and the height is not a promise about a scale.
    """

    def __init__(self, palette, colour='accent', parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.colour_name = colour
        self.values = []
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def push(self, value):
        """Add a reading. None is ignored, because it is not a reading."""
        if value is None:
            return
        self.values.append(float(value))
        if len(self.values) > SAMPLE_HISTORY:
            del self.values[:-SAMPLE_HISTORY]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colour = getattr(self.palette_, self.colour_name)
        if len(self.values) < 2:
            return
        low = min(self.values)
        high = max(self.values)
        span = max(1e-6, high - low)
        width = self.width()
        height = self.height()
        points = []
        for index, value in enumerate(self.values):
            x = width * index / (len(self.values) - 1)
            y = height - 3 - (height - 6) * (value - low) / span
            points.append((x, y))
        painter.setPen(QPen(QColor(colour), 1.8))
        for index in range(1, len(points)):
            painter.drawLine(int(points[index - 1][0]), int(points[index - 1][1]),
                             int(points[index][0]), int(points[index][1]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colour))
        painter.drawEllipse(int(points[-1][0]) - 2, int(points[-1][1]) - 2, 5, 5)


class TelemetryColumn(QWidget):
    """The left column: what this computer is doing right now.

    Every number here is a real reading taken from this machine. A
    reading that cannot be taken says so.
    """

    def __init__(self, palette, *, root=None, memory=None, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.root = root
        self.memory = memory
        self.setFixedWidth(250)

        from desktop.system_metrics import CpuSampler

        self.sampler = CpuSampler()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = self._card(layout)
        head = QHBoxLayout()
        eyebrow = QLabel('PC TELEMETRY')
        eyebrow.setStyleSheet('color: #63e6ff; font-size: 10px; font-weight: 700; '
                              'letter-spacing: 2.2px;')
        head.addWidget(eyebrow)
        head.addStretch(1)
        card.layout().addLayout(head)

        rings = QHBoxLayout()
        rings.setSpacing(8)
        self.cpu = GaugeRing(palette, 'CPU')
        self.ram = GaugeRing(palette, 'RAM')
        rings.addWidget(self.cpu)
        rings.addWidget(self.ram)
        card.layout().addLayout(rings)

        self.line = SampleLine(palette, 'accent')
        card.layout().addWidget(self.line)
        self.extra = QLabel('GPU —    TEMP —    DISK —')
        self.extra.setStyleSheet('color: #93a1b8; font-size: 10px;')
        self.extra.setAccessibleName('GPU, temperature and disk')
        card.layout().addWidget(self.extra)

        memory_card = self._card(layout)
        head = QHBoxLayout()
        eyebrow = QLabel('MEMORY')
        eyebrow.setStyleSheet('color: #63e6ff; font-size: 10px; font-weight: 700; '
                              'letter-spacing: 2.2px;')
        head.addWidget(eyebrow)
        head.addStretch(1)
        memory_card.layout().addLayout(head)
        self.memory_count = QLabel('notes —')
        self.memory_count.setStyleSheet('font-size: 15px; font-weight: 600;')
        self.memory_count.setAccessibleName('Saved notes')
        memory_card.layout().addWidget(self.memory_count)
        self.memory_last = QLabel('')
        self.memory_last.setStyleSheet('color: #93a1b8; font-size: 10px;')
        memory_card.layout().addWidget(self.memory_last)
        layout.addStretch(1)

        self.timer = QTimer(self)
        self.timer.setInterval(REFRESH_MS)
        self.timer.timeout.connect(self.refresh)

    def _card(self, layout):
        """One glass surface."""
        card = QFrame()
        card.setObjectName('deckCard')
        card.setStyleSheet(
            f'QFrame#deckCard {{ background: rgba(255, 255, 255, 12); '
            f'border: 1px solid rgba(255, 255, 255, 26); border-radius: 18px; }}')
        inner = QVBoxLayout(card)
        inner.setContentsMargins(18, 16, 18, 16)
        inner.setSpacing(10)
        layout.addWidget(card)
        return card

    def start(self):
        """Begin taking readings."""
        self.refresh()
        self.timer.start()

    def stop(self):
        """Stop taking readings."""
        self.timer.stop()

    def refresh(self):
        """Take one real reading and show it."""
        from desktop.system_metrics import snapshot

        try:
            data = snapshot(self.root, self.sampler)
        except Exception:
            data = {}
        cpu = data.get('cpu_usage_percent')
        ram = data.get('ram_usage_percent')
        self.cpu.set_reading(None if cpu is None else cpu / 100.0,
                              '—' if cpu is None else f'{cpu:.0f}%')
        self.ram.set_reading(None if ram is None else ram / 100.0,
                              '—' if ram is None else f'{ram:.0f}%')
        if cpu is not None:
            self.line.push(cpu)

        def part(name, value, unit=''):
            return '—' if value is None else f'{value:.0f}{unit}' if isinstance(value, (int, float)) else '—'

        self.extra.setText(
            f"GPU {part('gpu', data.get('gpu_usage_percent'), '%')}    "
            f"TEMP {part('temp', data.get('cpu_temperature_c'), '°C')}    "
            f"DISK {part('disk', data.get('disk_used_gib'), ' GiB')}")

        if self.memory is not None:
            try:
                count = self.memory.count()
            except Exception:
                count = None
            self.memory_count.setText('notes —' if count is None else f'{count} notes')
            self.memory_last.setText('the notes you keep on this computer'
                                     if count is None else 'saved on this computer')


class EvidenceColumn(QWidget):
    """The right column: what really ran, and what came of it."""

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.setFixedWidth(252)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.eyebrow = QLabel('EVIDENCE')
        self.eyebrow.setStyleSheet('color: #63e6ff; font-size: 10px; font-weight: 700; '
                                   'letter-spacing: 2.6px;')
        layout.addWidget(self.eyebrow)
        self.count = QLabel('no tool ran')
        self.count.setStyleSheet('color: #93a1b8; font-size: 11px;')
        layout.addWidget(self.count)

        self.cards = QVBoxLayout()
        self.cards.setSpacing(10)
        layout.addLayout(self.cards)

        self.answer_eyebrow = QLabel('ANSWER')
        self.answer_eyebrow.setStyleSheet('color: #63e6ff; font-size: 10px; font-weight: 700; '
                                          'letter-spacing: 2.6px;')
        layout.addWidget(self.answer_eyebrow)
        self.answer = QLabel('No mission has run yet.')
        self.answer.setWordWrap(True)
        self.answer.setAccessibleName('Mission answer')
        self.answer.setStyleSheet('font-size: 13px;')
        layout.addWidget(self.answer)
        layout.addStretch(1)

    def clear(self):
        """Empty the column."""
        while self.cards.count():
            item = self.cards.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.count.setText('no tool ran')
        self.answer.setText('No mission has run yet.')

    def show_evidence(self, tools_used):
        """Show the calls that really ran."""
        while self.cards.count():
            item = self.cards.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not tools_used:
            self.count.setText('no tool ran')
            return
        self.count.setText(f'{len(tools_used)} tool result(s)')
        for entry in tools_used:
            card = QFrame()
            card.setObjectName('evidenceCard')
            card.setStyleSheet(
                f'QFrame#evidenceCard {{ background: rgba(255, 255, 255, 10); '
                f'border: 1px solid rgba(255, 255, 255, 22); border-radius: 12px; }}')
            inner = QVBoxLayout(card)
            inner.setContentsMargins(14, 12, 14, 12)
            inner.setSpacing(5)
            name = QLabel(str(entry.get('tool', '')))
            name.setStyleSheet('font-size: 11px; font-weight: 600;')
            name.setAccessibleName('Tool that ran')
            inner.addWidget(name)
            summary = QLabel(str(entry.get('summary', '')))
            summary.setWordWrap(True)
            summary.setStyleSheet('color: #5d6b80; font-size: 10px;')
            inner.addWidget(summary)
            result = QLabel(str(entry.get('result', ''))[:220])
            result.setWordWrap(True)
            result.setStyleSheet('color: #5df2b0; font-size: 11px;')
            result.setAccessibleName('Tool result')
            inner.addWidget(result)
            self.cards.addWidget(card)

    def show_answer(self, text):
        """Show the answer, or say that there is not one."""
        self.answer.setText(text or 'No mission has run yet.')


class MissionTimeline(QWidget):
    """The rail of a mission: one marker for every step that happened."""

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self._entries = []
        self._heights = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setAccessibleName('Mission timeline')

    def entries(self) -> list:
        """The steps on the rail, oldest first."""
        return list(self._entries)

    def clear(self):
        """Empty the rail."""
        self._entries = []
        self._heights = []
        self.updateGeometry()
        self.update()

    def add(self, kind: str, label: str, detail: str = ''):
        """Put one step on the rail."""
        self._entries.append({'kind': kind, 'label': label, 'detail': detail})
        self._heights.append(self._measure(label, detail))
        self.updateGeometry()
        self.update()

    def _colour(self, kind: str) -> QColor:
        return getattr(self.palette_, KIND_COLOURS.get(kind, 'muted'))

    def _measure(self, label: str, detail: str) -> int:
        """How tall one row is, so the widget can be given a real height."""
        label_font = _mono(9, 600)
        body_font = QFont(self.font())
        metrics = QFontMetrics(label_font)
        height = metrics.height()
        if detail:
            body = QFontMetrics(body_font)
            width = max(120, self.width() - 74)
            height += body.boundingRect(0, 0, width, 0,
                                        Qt.TextFlag.TextWordWrap, detail).height() + 6
        return height + 20

    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize

        return QSize(320, max(80, sum(self._heights)))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        label_font = _mono(9, 600)
        body_font = QFont(self.font())
        palette = self.palette_
        left = 22
        top = 10

        if self._entries:
            rail = QPen(QColor(palette.muted.red(), palette.muted.green(),
                               palette.muted.blue(), 70))
            rail.setWidth(1)
            painter.setPen(rail)
            painter.drawLine(int(left), int(top + 6),
                             int(left), int(top + sum(self._heights[:-1]) + 6))

        for index, entry in enumerate(self._entries):
            height = self._heights[index]
            colour = self._colour(entry['kind'])
            y = top + sum(self._heights[:index])
            centre_y = y + 7

            if index == len(self._entries) - 1:
                glow = QColor(colour)
                glow.setAlpha(46)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(glow)
                painter.drawEllipse(QRectF(left - 9, centre_y - 9, 18, 18))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawEllipse(QRectF(left - 4.5, centre_y - 4.5, 9, 9))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(palette.ground.red(), palette.ground.green(),
                                       palette.ground.blue(), 200)))
            painter.drawEllipse(QRectF(left - 2, centre_y - 2, 4, 4))

            painter.setFont(label_font)
            painter.setPen(QColor(palette.ink))
            metrics = QFontMetrics(label_font)
            text = metrics.elidedText(str(entry['label']).upper(), Qt.TextElideMode.ElideRight,
                                       max(80, self.width() - left - 26))
            painter.drawText(left + 18, centre_y + 4, text)

            if entry['detail']:
                painter.setFont(body_font)
                painter.setPen(QColor(palette.muted))
                width = max(120, self.width() - left - 26)
                painter.drawText(QRectF(left + 18, centre_y + 12, width, height - 26),
                                 Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft,
                                 str(entry['detail']))


class MissionPanel(QWidget):
    """The Command Deck: the computer, the mission and the evidence."""

    run_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, palette, *, root=None, memory=None, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self._status = 'idle'
        self._goal = ''

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(14)

        columns = QHBoxLayout()
        columns.setSpacing(14)

        self.telemetry = TelemetryColumn(palette, root=root, memory=memory)
        columns.addWidget(self.telemetry)

        middle = QVBoxLayout()
        middle.setSpacing(10)
        header = QHBoxLayout()
        eyebrow = QLabel('MISSION CONTROL')
        eyebrow.setStyleSheet('color: #63e6ff; font-size: 10px; font-weight: 700; '
                              'letter-spacing: 2.6px;')
        header.addWidget(eyebrow)
        header.addStretch(1)
        self.counter = QLabel('')
        self.counter.setAccessibleName('Mission step counter')
        self.counter.setStyleSheet('font-size: 11px; font-weight: 600;')
        header.addWidget(self.counter)
        self.status = QLabel('READY')
        self.status.setAccessibleName('Mission status')
        header.addWidget(self.status)
        middle.addLayout(header)

        self.title = QLabel('Give JARVIS a goal and watch it work')
        self.title.setWordWrap(True)
        self.title.setStyleSheet('font-size: 19px; font-weight: 600;')
        self.title.setAccessibleName('Mission goal')
        middle.addWidget(self.title)

        self.scroller = QScrollArea()
        self.scroller.setWidgetResizable(True)
        self.scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.timeline = MissionTimeline(palette)
        self.scroller.setWidget(self.timeline)
        middle.addWidget(self.scroller, 1)

        self.approval = QFrame()
        self.approval.setObjectName('approvalBanner')
        self.approval.setStyleSheet(
            'QFrame#approvalBanner { background: rgba(255, 207, 107, 26); '
            'border: 1px solid rgba(255, 207, 107, 110); border-radius: 14px; }')
        approval_layout = QVBoxLayout(self.approval)
        approval_layout.setContentsMargins(16, 12, 16, 12)
        approval_layout.setSpacing(4)
        self.approval_title = QLabel('APPROVAL NEEDED')
        self.approval_title.setStyleSheet('color: #ffcf6b; font-size: 10px; '
                                           'font-weight: 700; letter-spacing: 2.0px;')
        approval_layout.addWidget(self.approval_title)
        self.approval_detail = QLabel('')
        self.approval_detail.setStyleSheet('color: #93a1b8; font-size: 11px;')
        self.approval_detail.setWordWrap(True)
        approval_layout.addWidget(self.approval_detail)
        self.approval.setVisible(False)
        middle.addWidget(self.approval)

        columns.addLayout(middle, 1)

        self.evidence_column = EvidenceColumn(palette)
        columns.addWidget(self.evidence_column)
        outer.addLayout(columns, 1)

        # ── the composer
        command = QHBoxLayout()
        command.setSpacing(8)
        self.goal = QLineEdit()
        self.goal.setPlaceholderText('Give JARVIS a goal and watch it work')
        self.goal.setAccessibleName('Mission goal')
        self.goal.returnPressed.connect(self.request_run)
        command.addWidget(self.goal, 1)
        self.run_limit = QComboBox()
        self.run_limit.setAccessibleName('Mission execution limits')
        self.run_limit.addItem('6 steps · 3 min', (MAX_STEPS, BUDGET_SECONDS))
        self.run_limit.addItem('12 steps · 6 min', (12, 360))
        self.run_limit.addItem('24 steps · 12 min', (24, 720))
        self.run_limit.setToolTip('Maximum planner steps and elapsed time for this mission')
        command.addWidget(self.run_limit)
        self.run_button = QPushButton('Start mission')
        self.run_button.setAccessibleName('Start mission')
        self.run_button.clicked.connect(self.request_run)
        command.addWidget(self.run_button)
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.setAccessibleName('Cancel mission')
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        self.cancel_button.setEnabled(False)
        command.addWidget(self.cancel_button)
        outer.addLayout(command)

        self.refresh_theme()

    # ------------------------------------------------------------------

    def request_run(self):
        """Ask the window to start a mission with what the owner typed."""
        goal = self.goal.text().strip()
        if not goal:
            return
        self.run_requested.emit(goal)

    def set_goal(self, goal: str):
        """The goal of the mission that is running."""
        self._goal = goal
        self.title.setText(goal or 'Give JARVIS a goal and watch it work')

    def set_running(self, running: bool):
        """Show that a mission is running, or that it is not."""
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.goal.setEnabled(not running)
        self.run_limit.setEnabled(not running)
        if running:
            self.set_status('running')
            self.timeline.clear()
            self.approval.setVisible(False)
            self.evidence_column.clear()

    def set_status(self, status: str):
        """The state pill."""
        self._status = status
        word = STATUS_WORDS.get(status, 'Ready')
        colour = getattr(self.palette_, STATUS_COLOURS.get(status, 'muted')).name()
        self.status.setText(word.upper())
        self.status.setStyleSheet(
            f'color: {colour}; font-size: 11px; font-weight: 700; letter-spacing: 1.6px; '
            f'border: 1px solid {colour}; border-radius: 8px; padding: 4px 8px;')

    def current_status(self) -> str:
        """What the pill is showing, as a name."""
        return self._status

    def append_event(self, event):
        """Put one step of a running mission on the rail."""
        self.timeline.add(event.kind, event.label, event.detail)
        if event.kind == 'approval':
            self.approval_detail.setText(event.detail)
            self.approval.setVisible(True)
        elif event.kind in ('tool', 'result', 'answer', 'error', 'cancelled'):
            self.approval.setVisible(False)
        self._scroll_to_end()

    def set_counter(self, used: int, total: int):
        """Which step of how many. No percentage, because none is known."""
        self.counter.setText(f'Step {used} of {total}' if total else '')

    def show_result(self, mission):
        """Show the finished mission: its answer, its status and its evidence."""
        self.set_status(mission.status)
        self.set_counter(mission.steps, getattr(self, 'max_steps', 0) or mission.steps)
        self.evidence_column.show_evidence(mission.tools_used)
        if mission.answer:
            self.evidence_column.show_answer(mission.answer)
        elif mission.status != 'completed':
            self.evidence_column.show_answer(
                'The mission did not finish. The steps that ran are on the rail.')

    def _scroll_to_end(self):
        """Keep the newest step in view."""
        bar = self.scroller.verticalScrollBar()
        bar.setValue(bar.maximum())

    def showEvent(self, event):
        super().showEvent(event)
        self.telemetry.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.telemetry.stop()

    def refresh_theme(self):
        """Apply the chosen palette."""
        palette = self.palette_
        self.setStyleSheet(
            f'QWidget {{ color: {palette.ink.name()}; }}'
            f'QLineEdit {{ background: {palette.ground_far.name()}; '
            f'color: {palette.ink.name()}; border: 1px solid {palette.muted.name()}; '
            'border-radius: 10px; padding: 9px 12px; }')
        self.set_status(self._status)


class MissionWorker(QThread):
    """Runs one mission away from the interface thread.

    The worker owns the cancellation, because only the thread that runs
    the mission can say that it stopped. It reports every step as it
    happens, so the console shows the mission while it works rather than
    after it finishes.
    """

    event = Signal(object)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, runtime, goal: str, confirm=None, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.goal = goal
        self.confirm = confirm
        self._cancelled = False

    def cancel(self):
        """Ask the mission to stop at the next step."""
        self._cancelled = True
        self.requestInterruption()

    def check(self):
        """The cancellation check the runtime uses during this mission."""
        if self._cancelled or self.isInterruptionRequested():
            raise Stopped('Mission cancelled by the owner.')
        if self.runtime.check is not None:
            self.runtime.check()

    def run(self):
        try:
            mission = self.runtime.run(self.goal, confirm=self.confirm, check=self.check)
        except Stopped:
            self.failed.emit('Mission cancelled by the owner.')
            return
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.result.emit(mission)


__all__ = ['KIND_COLOURS', 'STATUS_COLOURS', 'STATUS_WORDS',
           'EvidenceColumn', 'GaugeRing', 'MissionPanel', 'MissionTimeline',
           'MissionWorker', 'SampleLine', 'TelemetryColumn']
