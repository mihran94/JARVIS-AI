"""The Cybersecurity interface: a separate, defensive page.

WHAT THIS IS
    A page of its own, away from the Main Assistant. It offers a fixed
    list of read-only checks about this computer. The owner approves the
    check before it runs, the findings are shown with how serious each
    one is, and the report can be saved to a file the owner chooses.

WHAT THIS IS NOT
    * It is not a tool the assistant can call. Nothing in the mission
      runtime reaches this page, and no model text turns into a check.
    * It does not change the computer. Every check here only reads.
    * It does not gather credentials. What a check sees is redacted
      before it becomes a finding.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from cybersecurity.diagnostics import CHECKS, CheckUnavailable, run_check
from cybersecurity.report import SEVERITIES, SecurityReport
from security.policy import Action


class CybersecurityPanel(QWidget):
    """Run the scoped checks and read what they found."""

    def __init__(self, *, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.report = SecurityReport(scope='Local device')
        self._build()

    # ------------------------------------------------------------------ build

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 10, 10)
        layout.setSpacing(10)

        title = QLabel('Cybersecurity')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        note = QLabel(
            'Defensive checks about this computer. Each one only reads, and each one '
            'asks your approval before it runs. Nothing here is sent to the AI '
            'provider, and no check can change your computer.')
        note.setObjectName('pageSubtitle')
        note.setWordWrap(True)
        layout.addWidget(note)

        self.checks = QListWidget()
        self.checks.setAccessibleName('The available checks')
        self.checks.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for name, (title, description, _) in CHECKS.items():
            item = QListWidgetItem(f'{title}\n{description}')
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setToolTip(description)
            self.checks.addItem(item)
        layout.addWidget(self.checks, 1)

        row = QHBoxLayout()
        self.run_button = QPushButton('Run the selected check')
        self.run_button.setAccessibleName('Run the selected check')
        self.run_button.clicked.connect(self.run_selected)
        row.addWidget(self.run_button)
        self.run_all_button = QPushButton('Run every check this computer allows')
        self.run_all_button.clicked.connect(self.run_everything)
        row.addWidget(self.run_all_button)
        row.addStretch(1)
        self.save_button = QPushButton('Save the report')
        self.save_button.clicked.connect(self.save_report)
        row.addWidget(self.save_button)
        layout.addLayout(row)

        self.summary = QLabel('No check has run yet.')
        self.summary.setWordWrap(True)
        self.summary.setAccessibleName('The findings summary')
        layout.addWidget(self.summary)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setAccessibleName('The findings')
        layout.addWidget(self.output, 2)

    # ------------------------------------------------------------------ checks

    def run_selected(self):
        """Run the check the owner selected, after they approve it."""
        item = self.checks.currentItem()
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        label = CHECKS[name][0]

        def operation():
            findings = run_check(name, store=self.window.store)
            self.report.checks_run.append(label)
            self.report.extend(findings)
            self.show_report()

        try:
            self.window.gateway.run(Action('security_check', label), self.window.confirm,
                                    operation)
        except CheckUnavailable as error:
            self.report.notes.append(f'{label}: not run. {error}')
            self.show_report()
        except Exception as error:
            self.report.notes.append(f'{label}: not run. {error}')
            self.show_report()

    def run_everything(self):
        """Run every check this computer allows, after the owner approves it."""
        def operation():
            for name, (label, _, _) in CHECKS.items():
                try:
                    self.report.extend(run_check(name, store=self.window.store))
                    self.report.checks_run.append(label)
                except CheckUnavailable as error:
                    self.report.notes.append(f'{label}: not run. {error}')
            self.show_report()

        try:
            self.window.gateway.run(Action('security_check', 'Every check on this computer'),
                                    self.window.confirm, operation)
        except Exception as error:
            self.report.notes.append(f'The checks were not run. {error}')
            self.show_report()

    # ------------------------------------------------------------------ report

    def show_report(self):
        """Show the findings, most serious first."""
        self.summary.setText(self.report.summary())
        self.output.setPlainText(self.report.as_text())

    def save_report(self):
        """Write the report to a file the owner chooses."""
        if not self.report.findings and not self.report.checks_run:
            self.summary.setText('There is no report to save yet. Run a check first.')
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save the cybersecurity report', 'jarvis-cybersecurity-report.txt',
            'Text file (*.txt);;All files (*)')
        if not path:
            return
        try:
            Path(path).write_text(self.report.as_text(), encoding='utf-8')
        except OSError as error:
            self.summary.setText(f'The report was not saved. {error}')
            return
        self.summary.setText(f'The report was saved to {path}. {self.report.summary()}')


__all__ = ['CybersecurityPanel']
