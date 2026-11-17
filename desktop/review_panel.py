"""The review screen for a prepared change.

WHAT THE OWNER SEES
    One row per prepared change. For each one:

    * what it is — a source revision from GitHub, or an improvement JARVIS
      prepared in its own worktree;
    * the exact revision, shortened;
    * the files it touches;
    * the diff, so it can be read;
    * the test results, and the failure when the tests failed;
    * Approve and Reject.

    Apply stays disabled when the tests failed. A change that did not pass
    its tests can be read, but it cannot be applied, and the button says so
    instead of failing when it is pressed.

THE APPROVAL
    Approving is an action like any other: it goes through the approval
    gateway, it names the exact revision, and it can only be used once. If
    the code changes after the approval, the approval is refused and the
    owner is asked to look again.
"""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core.candidates import Candidate, reject_candidate, stage_candidate
from core.development import Improvement, apply_improvement, reject_improvement
from core.updates import UpdateError
from security.policy import Action


class ReviewPanel(QWidget):
    """The prepared changes, with the diff and the test results."""

    approved = Signal(str)
    rejected = Signal(str)

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.candidate: Candidate | None = None
        self.improvement: Improvement | None = None

        layout = QVBoxLayout(self)
        note = QLabel(
            'A prepared change is only a proposal. Nothing runs until you approve the exact '
            'revision. The version that runs now does not change until you approve, and the '
            'previous version stays available for rollback.')
        note.setWordWrap(True)
        layout.addWidget(note)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Prepared', 'Kind', 'Revision', 'Tests', 'Changed'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self.summary = QLabel('Nothing is waiting for review.')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.diff = QPlainTextEdit()
        self.diff.setReadOnly(True)
        self.diff.setPlaceholderText('The diff of the selected change appears here.')
        layout.addWidget(self.diff, 1)

        self.tests = QPlainTextEdit()
        self.tests.setReadOnly(True)
        self.tests.setMaximumHeight(140)
        self.tests.setPlaceholderText('The test results appear here.')
        layout.addWidget(self.tests)

        row = QHBoxLayout()
        self.approve_button = QPushButton('Approve this exact revision')
        self.approve_button.clicked.connect(self.approve)
        self.reject_button = QPushButton('Reject')
        self.reject_button.clicked.connect(self.reject)
        row.addWidget(self.approve_button)
        row.addWidget(self.reject_button)
        layout.addLayout(row)

        self.keep_running = QCheckBox('Keep JARVIS in the system tray when the window is closed')
        self.keep_running.setChecked(bool(window.store.get('keep_running_in_tray', False)))
        self.keep_running.toggled.connect(
            lambda enabled: window.store.set('keep_running_in_tray', bool(enabled)))
        layout.addWidget(self.keep_running)

        self.refresh()

    # ── the list ────────────────────────────────────────────────────────────

    def refresh(self):
        """Show the prepared changes that are waiting for a decision."""
        from core.candidates import read_candidate

        self.candidate = read_candidate(self.window.installation_root())
        rows = []
        if self.candidate is not None:
            rows.append(('source', self.candidate))
        for improvement in self.window.prepared_improvements():
            rows.append(('improvement', improvement))
        self.table.setRowCount(len(rows))
        for index, (kind, item) in enumerate(rows):
            status = str(item.tests.get('status', 'not run'))
            self.table.setItem(index, 0, QTableWidgetItem(item.prepared_at or '—'))
            self.table.setItem(index, 1, QTableWidgetItem(
                'GitHub source' if kind == 'source' else 'JARVIS improvement'))
            self.table.setItem(index, 2, QTableWidgetItem(item.short))
            self.table.setItem(index, 3, QTableWidgetItem(status))
            self.table.setItem(index, 4, QTableWidgetItem(
                f'{len(item.changed)} file(s)'))
        self.show_item(rows[0][1] if rows else None)

    def show_item(self, item):
        """Show one prepared change."""
        self.diff.clear()
        self.tests.clear()
        if item is None:
            self.summary.setText('Nothing is waiting for review.')
            self.approve_button.setEnabled(False)
            self.reject_button.setEnabled(False)
            return
        if isinstance(item, Candidate):
            self.summary.setText(
                f'Source revision {item.short} from GitHub, prepared {item.prepared_at}. '
                f'The running version is unchanged until you approve it.')
            self.diff.setPlainText(self.window.candidate_diff(item))
        else:
            self.summary.setText(
                f'Improvement for {item.goal}, prepared by {item.provider} in '
                f'{item.worktree} against revision {item.short}.')
            self.diff.setPlainText(item.diff or 'The change did not touch any file.')
        status = str(item.tests.get('status', 'not run'))
        summary = str(item.tests.get('summary', '')).strip()
        text = f'Tests: {status}'
        if summary:
            text += f'\n{summary}'
        if not item.appliable:
            text += ('\nApply is disabled because the tests did not pass. '
                     'Read the failure and prepare the change again.')
        self.tests.setPlainText(text)
        self.approve_button.setEnabled(bool(item.appliable))
        self.reject_button.setEnabled(True)

    # ── the decision ────────────────────────────────────────────────────────

    def approve(self):
        """Approve the exact revision, through the approval gateway."""
        item = self.selected()
        if item is None:
            return
        revision = item.short
        action = Action('activate_prepared_revision', f'{revision} · {item.digest[:16]}')

        def operation():
            if isinstance(item, Candidate):
                return stage_candidate(
                    self.window.installation_root(), self.window.store.path, item,
                    check=lambda: self.window.policy.check(self.window.policy.ticket()),
                    publish=lambda op: self.window.policy.run_if_current(
                        self.window.policy.ticket(), op))
            return apply_improvement(item)

        try:
            message = self.window.gateway.run(action, self.window.confirm, operation)
        except UpdateError as error:
            self.window.statusBar().showMessage(str(error), 15000)
            self.refresh()
            return
        except Exception as error:
            self.window.statusBar().showMessage(str(error), 15000)
            self.refresh()
            return
        self.window.statusBar().showMessage(message, 15000)
        self.approved.emit(revision)
        self.refresh()

    def reject(self):
        """Throw the prepared change away. The running version is untouched."""
        item = self.selected()
        if item is None:
            return
        try:
            if isinstance(item, Candidate):
                message = reject_candidate(self.window.installation_root(), item)
            else:
                message = reject_improvement(item)
        except Exception as error:
            message = str(error)
        self.window.statusBar().showMessage(message, 15000)
        self.rejected.emit(item.short)
        self.refresh()

    def selected(self):
        """The prepared change the owner is looking at."""
        index = self.table.currentRow()
        if index < 0:
            return self.candidate if self.candidate is not None else (
                self.window.prepared_improvements()[0] if self.window.prepared_improvements() else None)
        if index == 0 and self.candidate is not None:
            return self.candidate
        improvements = self.window.prepared_improvements()
        position = index - (1 if self.candidate is not None else 0)
        if 0 <= position < len(improvements):
            return improvements[position]
        return None
