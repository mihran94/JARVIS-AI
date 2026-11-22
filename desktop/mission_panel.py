"""The JARVIS mission console — the HUD for a running agent.

WHAT THIS IS
    A page in the desktop application that shows one mission while it
    runs. The owner types a goal, JARVIS works towards it, and every
    step is shown as it happens: what JARVIS decided, which tool it
    called, when the owner's approval was needed, what came back, and
    what the evidence was.

    The console paints its own timeline rather than using a list widget,
    because the timeline is the point: one rail, one marker per step,
    and the marker says at a glance whether a step was a thought, a
    call, an approval, a result or a failure. The newest step glows.

WHAT THIS IS NOT
    * It does not run anything. It shows what `core.mission` did, and
      the window that owns it starts and stops the mission.
    * It does not invent progress. There is no percentage and no
      estimate. The counter says which step of how many, and only the
      steps that really ran are on the rail.
    * It does not show a tool as successful unless the tool returned.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

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


def _mono(size: int, weight: int = 500) -> QFont:
    """The technical face of the interface."""
    font = QFont()
    font.setFamilies([family.strip().strip("'") for family in MONO_STACK.split(',')])
    font.setPointSize(size)
    font.setWeight(QFont.Weight(weight))
    return font


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
    """The mission console: a goal, a rail of steps and the evidence."""

    run_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self._status = 'idle'
        self._answer = ''

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        eyebrow = QLabel('MISSION CONTROL')
        eyebrow.setStyleSheet('color: #63e6ff; font-size: 11px; font-weight: 700; '
                              'letter-spacing: 2.6px;')
        outer.addWidget(eyebrow)

        title = QLabel('Give JARVIS a goal and watch it work')
        title.setStyleSheet('font-size: 22px; font-weight: 600;')
        outer.addWidget(title)

        note = QLabel('JARVIS may read, calculate, search your memory and read a public page '
                      'on its own. Anything that changes your computer asks you first.')
        note.setWordWrap(True)
        note.setStyleSheet('color: #93a1b8; font-size: 12px;')
        outer.addWidget(note)

        command = QHBoxLayout()
        command.setSpacing(8)
        self.goal = QLineEdit()
        self.goal.setPlaceholderText('What should JARVIS do?')
        self.goal.setAccessibleName('Mission goal')
        self.goal.returnPressed.connect(self.request_run)
        command.addWidget(self.goal, 1)
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

        status_row = QHBoxLayout()
        self.status = QLabel('Ready')
        self.status.setAccessibleName('Mission status')
        status_row.addWidget(self.status)
        self.counter = QLabel('')
        self.counter.setAccessibleName('Mission step counter')
        status_row.addWidget(self.counter)
        status_row.addStretch(1)
        outer.addLayout(status_row)

        self.scroller = QScrollArea()
        self.scroller.setWidgetResizable(True)
        self.scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.timeline = MissionTimeline(palette)
        self.scroller.setWidget(self.timeline)
        outer.addWidget(self.scroller, 1)

        self.answer_card = QFrame()
        self.answer_card.setObjectName('missionAnswer')
        answer_layout = QVBoxLayout(self.answer_card)
        answer_layout.setContentsMargins(14, 12, 14, 12)
        answer_head = QLabel('RESULT')
        answer_head.setStyleSheet('color: #93a1b8; font-size: 10px; font-weight: 700; '
                                  'letter-spacing: 1.6px;')
        answer_layout.addWidget(answer_head)
        self.answer = QLabel('No mission has run yet.')
        self.answer.setWordWrap(True)
        self.answer.setAccessibleName('Mission result')
        answer_layout.addWidget(self.answer)
        self.answer_card.setVisible(False)
        outer.addWidget(self.answer_card)

        self.evidence = QLabel('')
        self.evidence.setAccessibleName('Mission evidence')
        self.evidence.setStyleSheet('color: #93a1b8; font-size: 11px;')
        outer.addWidget(self.evidence)

        self.refresh_theme()

    # ------------------------------------------------------------------

    def request_run(self):
        """Ask the window to start a mission with what the owner typed."""
        goal = self.goal.text().strip()
        if not goal:
            return
        self.run_requested.emit(goal)

    def set_running(self, running: bool):
        """Show that a mission is running, or that it is not."""
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.goal.setEnabled(not running)
        if running:
            self.set_status('running')
            self.timeline.clear()
            self.answer_card.setVisible(False)
            self.answer.setText('')
            self._answer = ''
            self.evidence.setText('')

    def set_status(self, status: str):
        """The state pill."""
        self._status = status
        word = STATUS_WORDS.get(status, 'Ready')
        colour = getattr(self.palette_, STATUS_COLOURS.get(status, 'muted')).name()
        self.status.setText(word.upper())
        self.status.setStyleSheet(f'color: {colour}; font-size: 11px; font-weight: 700; '
                                  f'letter-spacing: 1.6px; border: 1px solid {colour}; '
                                  'border-radius: 8px; padding: 4px 8px;')

    def current_status(self) -> str:
        """What the pill is showing, as a name."""
        return self._status

    def append_event(self, event):
        """Put one step of a running mission on the rail."""
        self.timeline.add(event.kind, event.label, event.detail)
        self._scroll_to_end()

    def set_counter(self, used: int, total: int):
        """Which step of how many. No percentage, because none is known."""
        self.counter.setText(f'Step {used} of {total}' if total else '')

    def show_result(self, mission):
        """Show the finished mission: its answer, its status and its evidence."""
        self.set_status(mission.status)
        self.set_counter(mission.steps, getattr(self, 'max_steps', 0) or mission.steps)
        if mission.answer:
            self.answer.setText(mission.answer)
            self.answer_card.setVisible(True)
        elif mission.status != 'completed':
            self.answer.setText('The mission did not finish. The steps that ran are on the rail.')
            self.answer_card.setVisible(True)
        if mission.tools_used:
            names = ', '.join(item['tool'] for item in mission.tools_used)
            self.evidence.setText(f'Evidence: {len(mission.tools_used)} tool result(s) — {names}')
        else:
            self.evidence.setText('Evidence: no tool ran for this mission.')
        self._scroll_to_end()

    def _scroll_to_end(self):
        """Keep the newest step in view."""
        bar = self.scroller.verticalScrollBar()
        bar.setValue(bar.maximum())

    def refresh_theme(self):
        """Apply the chosen palette."""
        palette = self.palette_
        self.setStyleSheet(
            f'QWidget {{ color: {palette.ink.name()}; }}'
            f'QLineEdit {{ background: {palette.ground_far.name()}; '
            f'color: {palette.ink.name()}; border: 1px solid {palette.muted.name()}; '
            'border-radius: 10px; padding: 9px 12px; }'
            f'QFrame#missionAnswer {{ background: {palette.ground_far.name()}; '
            f'border: 1px solid {palette.muted.name()}; border-radius: 12px; }}')
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
           'MissionPanel', 'MissionTimeline', 'MissionWorker']
