"""The Automation page: everything JARVIS can do to this computer.

WHAT THIS IS
    One page holds the whole of the automation surface: the browser, the
    suggestion mode, the work-on-this mission, the control of any app on
    the desktop, the task activity, and the proposed actions that are
    waiting for the owner.

    A proposed action is a card with three answers: Run it as it is, Edit
    it and run that, or Dismiss it. All three go through the same
    approval gateway as every other action in JARVIS, so there is exactly
    one place where an action can be allowed, and the owner sees the same
    card whichever engine proposed it.

WHAT THIS IS NOT
    * It does not run anything itself. It shows what was proposed and
      asks the owner; the runner that is handed to it goes through the
      gateway and decides.
    * It does not keep its own approval rules, and it does not keep a
      key.
    * It does not read the screen, the microphone or a file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from desktop.hud import CYAN, DANGER, EDGE, GOLD, INK, MUTED

#: The name of the page this panel is the content of.
PAGE_NAME = 'Automation'


@dataclass
class ProposedAction:
    """One action JARVIS would like to do, and the owner has not allowed yet.

    `editable` holds the fields the owner may change before the action
    runs. An action with no editable fields can still be run or
    dismissed, but not edited, and the card says so.
    """

    kind: str
    target: str
    detail: str = ''
    digest: str = ''
    run: object = None
    editable: dict = field(default_factory=dict)
    approval_scope: str = 'always'
    ident: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def summary(self) -> str:
        """One line that says what this action is about."""
        if self.detail:
            return self.detail
        return f'{self.kind}: {self.target}'


class ProposedActionCard(QFrame):
    """One proposed action, and the three answers the owner has."""

    run_requested = Signal(str, dict)
    dismiss_requested = Signal(str)
    edit_requested = Signal(str)

    def __init__(self, action: ProposedAction, parent=None):
        super().__init__(parent)
        self.action = action
        self.setObjectName('proposedAction')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel(action.kind.replace('_', ' ').upper())
        title.setStyleSheet(f'color: {GOLD}; font-size: 10px; font-weight: 700;'
                            ' letter-spacing: 2px;')
        layout.addWidget(title)

        self.summary = QLabel(action.summary())
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(f'color: {INK};')
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)

        self.digest = QLabel(('Content SHA-256: ' + action.digest) if action.digest else '')
        self.digest.setStyleSheet(f'color: {MUTED}; font-size: 10px;')
        self.digest.setWordWrap(True)
        self.digest.setVisible(bool(action.digest))
        layout.addWidget(self.digest)

        self.editor = QWidget()
        editor_layout = QFormLayout(self.editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        self.fields = {}
        for name, value in action.editable.items():
            field_box = QLineEdit(str(value))
            field_box.setAccessibleName(f'{name} of the proposed action')
            self.fields[name] = field_box
            editor_layout.addRow(name, field_box)
        self.editor.setVisible(False)
        layout.addWidget(self.editor)

        buttons = QHBoxLayout()
        self.run_button = QPushButton('Run')
        self.run_button.setObjectName('primary')
        self.run_button.setAccessibleName('Run this proposed action')
        self.run_button.clicked.connect(self._run)
        buttons.addWidget(self.run_button)

        self.edit_button = QPushButton('Edit')
        self.edit_button.setAccessibleName('Edit this proposed action')
        self.edit_button.setEnabled(bool(action.editable))
        self.edit_button.clicked.connect(self._edit)
        buttons.addWidget(self.edit_button)

        self.dismiss_button = QPushButton('Dismiss')
        self.dismiss_button.setAccessibleName('Dismiss this proposed action')
        self.dismiss_button.clicked.connect(
            lambda: self.dismiss_requested.emit(self.action.ident))
        buttons.addWidget(self.dismiss_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        if not action.editable:
            self.edit_button.setToolTip('This action has nothing the owner can change.')

    # ------------------------------------------------------------------

    def _run(self):
        values = {name: box.text() for name, box in self.fields.items()}
        self.run_requested.emit(self.action.ident, values)

    def _edit(self):
        # `isHidden` is used and not `isVisible`, because the card is
        # often not on screen yet when the owner presses Edit.
        showing = not self.editor.isHidden()
        self.editor.setVisible(not showing)
        self.edit_button.setText('Done editing' if not showing else 'Edit')
        self.edit_requested.emit(self.action.ident)

    def edited_values(self) -> dict:
        """What the owner changed."""
        return {name: box.text() for name, box in self.fields.items()}


class AutomationPanel(QWidget):
    """The one page that holds the whole automation surface."""

    #: A proposed action was run, with the values the owner chose.
    action_run = Signal(object, dict)
    #: A proposed action was dismissed.
    action_dismissed = Signal(object)
    #: The owner wants the browser section.
    browser_requested = Signal(str)
    research_requested = Signal()
    #: The owner wants a mission started.
    mission_requested = Signal(str)
    suggestion_requested = Signal(str)
    #: The owner wants the list of open applications.
    refresh_requested = Signal()
    #: The owner wants the controls of the selected application.
    inspect_requested = Signal(str)

    def __init__(self, *, runner=None, parent=None):
        super().__init__(parent)
        self.setObjectName('automationPanel')
        self._runner = runner
        self._cards = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(self._build_modes())
        self.suggestion_results = QVBoxLayout()
        layout.addLayout(self.suggestion_results)
        layout.addWidget(self._build_proposals())
        layout.addWidget(self._build_browser())
        layout.addWidget(self._build_app_control())
        layout.addWidget(self._build_activity())

    # ------------------------------------------------------------------

    def _build_browser(self) -> QWidget:
        box = QGroupBox('Browser')
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self.browser_command = QLineEdit()
        self.browser_command.setPlaceholderText(
            'open https://…  ·  inspect  ·  fill Field label  ·  click Button name')
        self.browser_command.setAccessibleName('Browser command')
        row.addWidget(self.browser_command, 1)
        self.browser_button = QPushButton('Run in the browser')
        self.browser_button.setObjectName('primary')
        self.browser_button.setAccessibleName('Run the browser command')
        self.browser_button.clicked.connect(self._request_browser)
        row.addWidget(self.browser_button)
        self.research_button = QPushButton('Read page with AI')
        self.research_button.clicked.connect(self.research_requested.emit)
        row.addWidget(self.research_button)
        layout.addLayout(row)
        self.browser_status = QLabel('The browser is closed. A draft stays here until you approve it, '
                                     'and nothing is submitted for you.')
        self.browser_status.setTextFormat(Qt.TextFormat.PlainText)
        self.browser_status.setWordWrap(True)
        self.browser_status.setStyleSheet(f'color: {MUTED};')
        layout.addWidget(self.browser_status)
        return box

    def _request_browser(self):
        command = self.browser_command.text().strip()
        if command:
            self.browser_requested.emit(command)

    def _build_modes(self) -> QWidget:
        box = QGroupBox('Task')
        layout = QVBoxLayout(box)
        self.suggestion_mode = QCheckBox('Suggestion Mode')
        self.suggestion_mode.setAccessibleName('Suggestion Mode')
        self.suggestion_mode.setToolTip(
            'Get a plan in chat instead of an action. Nothing starts until you approve it.')
        layout.addWidget(self.suggestion_mode)

        row = QHBoxLayout()
        self.goal = QLineEdit()
        self.goal.setPlaceholderText('What should JARVIS work on?')
        self.goal.setAccessibleName('Goal for a mission')
        row.addWidget(self.goal, 1)
        self.work_button = QPushButton('Work on this')
        self.work_button.setObjectName('primary')
        self.work_button.setAccessibleName('Work on this')
        self.work_button.clicked.connect(self._request_mission)
        self.suggestion_mode.toggled.connect(lambda enabled: self.work_button.setText(
            'Get suggestions' if enabled else 'Work on this'))
        row.addWidget(self.work_button)
        layout.addLayout(row)
        return box

    def _build_app_control(self) -> QWidget:
        box = QGroupBox('Any App Control')
        layout = QVBoxLayout(box)
        note = QLabel('JARVIS inspects the app in front, proposes one exact action, '
                      'and checks the result before it says it worked.')
        note.setWordWrap(True)
        note.setStyleSheet(f'color: {MUTED};')
        layout.addWidget(note)

        row = QHBoxLayout()
        self.windows = QPlainTextEdit()
        self.windows.setReadOnly(True)
        self.windows.setMaximumHeight(120)
        self.windows.setAccessibleName('Open applications')
        self.windows.setPlaceholderText('No application has been listed yet.')
        row.addWidget(self.windows, 1)
        column = QVBoxLayout()
        self.refresh_button = QPushButton('Refresh windows')
        self.refresh_button.setAccessibleName('Refresh the list of open applications')
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        column.addWidget(self.refresh_button)
        self.inspect_button = QPushButton('Inspect the app in front')
        self.inspect_button.setAccessibleName('Inspect the application in front')
        self.inspect_button.clicked.connect(
            lambda: self.inspect_requested.emit(self.windows.toPlainText()))
        column.addWidget(self.inspect_button)
        row.addLayout(column)
        layout.addLayout(row)

        self.controls = QPlainTextEdit()
        self.controls.setReadOnly(True)
        self.controls.setMaximumHeight(110)
        self.controls.setAccessibleName('Controls of the inspected application')
        self.controls.setPlaceholderText('The controls of an inspected application appear here.')
        layout.addWidget(self.controls)
        return box

    def _build_proposals(self) -> QWidget:
        self.proposals = QGroupBox('Proposed actions')
        self.proposal_layout = QVBoxLayout(self.proposals)
        self.proposal_layout.setSpacing(10)
        self.proposal_layout.addStretch()
        self.proposals.hide()
        return self.proposals

    def _build_activity(self) -> QWidget:
        box = QGroupBox('Task activity')
        layout = QVBoxLayout(box)
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumHeight(150)
        self.activity.setAccessibleName('Task activity')
        self.activity.setPlaceholderText('No task has run yet.')
        layout.addWidget(self.activity)
        return box

    # ------------------------------------------------------------------

    def _request_mission(self):
        goal = self.goal.text().strip()
        if goal:
            if self.suggestion_mode.isChecked():
                self.suggestion_requested.emit(goal)
            else:
                self.mission_requested.emit(goal)

    def set_runner(self, runner):
        """Give the panel the way to run an action."""
        self._runner = runner

    def set_browser_status(self, text: str):
        """Say what the browser is doing."""
        self.browser_status.setText(text or 'The browser is closed.')

    def set_windows(self, text: str):
        """Show the applications that are open."""
        self.windows.setPlainText(text or '')

    def set_controls(self, text: str):
        """Show the controls of the application that was inspected."""
        self.controls.setPlainText(text or '')

    def set_activity(self, text: str):
        """Show what has been happening."""
        self.activity.setPlainText(text or '')

    def set_suggestion_mode(self, enabled: bool):
        """Show the state of Suggestion Mode."""
        self.suggestion_mode.setChecked(bool(enabled))

    # ------------------------------------------------------------------

    def propose(self, action: ProposedAction):
        """Show one action that is waiting for the owner."""
        card = ProposedActionCard(action)
        card.run_requested.connect(self._run)
        card.dismiss_requested.connect(self._dismiss)
        self.proposal_layout.insertWidget(self.proposal_layout.count() - 1, card)
        self._cards[action.ident] = card
        self.proposals.show()
        return card

    def cards(self) -> list:
        """The cards that are waiting, in the order they were proposed."""
        return list(self._cards.values())

    def _run(self, ident: str, values: dict):
        card = self._cards.get(ident)
        if card is None:
            return
        self.action_run.emit(card.action, values)

    def _dismiss(self, ident: str):
        card = self._cards.pop(ident, None)
        if card is None:
            return
        self.action_dismissed.emit(card.action)
        card.setParent(None)
        card.deleteLater()
        self.proposals.setVisible(bool(self._cards))

    def remove(self, ident: str):
        """Take one card away, without recording a dismissal."""
        card = self._cards.pop(ident, None)
        if card is None:
            return
        card.setParent(None)
        card.deleteLater()
        self.proposals.setVisible(bool(self._cards))

    def clear_proposals(self):
        """Nothing is waiting any more."""
        for ident in list(self._cards):
            self.remove(ident)


__all__ = ['AutomationPanel', 'PAGE_NAME', 'ProposedAction', 'ProposedActionCard']
