"""Non-blocking Codex review dialog. No shell, no credential copying."""
from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTextEdit,
                            QPushButton, QHBoxLayout)
from core.codex_bridge import review_command, review_prompt


class CodexReviewDialog(QDialog):
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = root
        self.setWindowTitle('Jarvis-Blue — Codex review')
        self.resize(760, 620)
        self.setFont(QFont('Courier New', 9))
        layout = QVBoxLayout(self)
        note = QLabel('Codex reviews the selected project using its own CLI login. Project content may be sent to OpenAI and usage may be billed.\nRead-only sandbox requested. No edits or builds. Requires a current Codex CLI; provider API settings do not sign Codex in.')
        note.setWordWrap(True)
        layout.addWidget(note)
        folder = QLabel(str(root))
        folder.setWordWrap(True)
        layout.addWidget(folder)
        self.request = QTextEdit()
        self.request.setPlainText('Review the project for correctness bugs and suggest the next improvements.')
        layout.addWidget(self.request, 1)
        row = QHBoxLayout()
        self.run_button = QPushButton('Run Codex review')
        self.run_button.clicked.connect(self._run)
        row.addWidget(self.run_button)
        self.stop_button = QPushButton('Stop')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        row.addWidget(self.stop_button)
        layout.addLayout(row)
        self.status = QLabel('Ready — no request sent')
        layout.addWidget(self.status)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 3)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.started.connect(self._send)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self._stopped = False
        self._bytes = bytearray()

    def _run(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        try:
            command = review_command(self.root)
            self._prompt = review_prompt(self.request.toPlainText())
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        self._stopped = False
        self._bytes.clear()
        self.output.clear()
        self.run_button.setEnabled(False)
        self.request.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText('Starting Codex…')
        self.process.setWorkingDirectory(str(self.root))
        self.process.start(command[0], command[1:])
        self.timer.start(300000)

    def _send(self):
        self.process.write(self._prompt.encode('utf-8'))
        self.process.closeWriteChannel()
        self.status.setText('Review running…')

    def _read(self):
        chunk = bytes(self.process.readAllStandardOutput())
        remaining = 256 * 1024 - len(self._bytes)
        self._bytes.extend(chunk[:max(0, remaining)])
        self.output.setPlainText(self._bytes.decode('utf-8', errors='replace'))
        if len(chunk) > remaining:
            self._stop('Output limit reached; review stopped.')

    def _stop(self, reason=False):
        self._stopped = True
        self.status.setText(reason if isinstance(reason, str) else 'Review stopped.')
        self.process.kill()

    def _timeout(self):
        self._stop('Five-minute limit reached; review stopped.')

    def _idle(self):
        self.timer.stop()
        self.run_button.setEnabled(True)
        self.request.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _finished(self, code, exit_status):
        self._read()
        self._idle()
        if not self._stopped:
            success = code == 0 and exit_status == QProcess.ExitStatus.NormalExit
            self.status.setText('Review completed — inspect the suggestions.' if success else
                                f'Codex failed (exit {code}). Check the output, CLI version and login.')

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._idle()
            self.status.setText('Could not start Codex. Check the CLI installation.')

    def reject(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self._stop()
            self.process.waitForFinished(1000)
        super().reject()

    def closeEvent(self, event):
        self.reject()
        event.accept()
