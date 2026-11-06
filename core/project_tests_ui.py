"""Non-blocking Project tests dialog. No shell, no credential copying."""
from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTextEdit,
                            QPushButton, QHBoxLayout)
from core.project_tests import test_command
from PyQt6.QtCore import QProcessEnvironment
from PyQt6.QtWidgets import QMessageBox


class ProjectTestsDialog(QDialog):
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = root
        self.setWindowTitle('Jarvis-Blue — Project tests')
        self.resize(760, 620)
        self.setFont(QFont('Courier New', 9))
        layout = QVBoxLayout(self)
        note = QLabel('Runs Python unittest discovery in the working copy tests folder. This executes project code with your user permissions; it is not a sandbox. Use trusted projects only. No dependencies are installed. The app Python environment is used.')
        note.setWordWrap(True)
        layout.addWidget(note)
        folder = QLabel(str(root))
        folder.setWordWrap(True)
        layout.addWidget(folder)
        self.request = QTextEdit()
        self.request.setPlainText('Python unittest: tests/test*.py')
        self.request.setReadOnly(True)
        self.request.setMaximumHeight(45)
        layout.addWidget(self.request, 1)
        row = QHBoxLayout()
        self.run_button = QPushButton('Run Project tests')
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
            command = test_command(self.root)
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return
        if QMessageBox.question(self, 'Run trusted project tests',
            'These tests execute code and can access your files and network. Run this trusted project?') != QMessageBox.StandardButton.Yes:
            return
        environment = QProcessEnvironment()
        system = QProcessEnvironment.systemEnvironment()
        for key in ('PATH', 'SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'HOME', 'USERPROFILE', 'LANG'):
            if system.contains(key): environment.insert(key, system.value(key))
        self.process.setProcessEnvironment(environment)
        self._stopped = False
        self._bytes.clear()
        self.output.clear()
        self.run_button.setEnabled(False)
        self.request.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText('Starting tests…')
        self.process.setWorkingDirectory(str(self.root))
        self.process.start(command[0], command[1:])
        self.timer.start(300000)

    def _send(self):
        self.process.closeWriteChannel()
        self.status.setText('Tests running…')

    def _read(self):
        chunk = bytes(self.process.readAllStandardOutput())
        remaining = 256 * 1024 - len(self._bytes)
        self._bytes.extend(chunk[:max(0, remaining)])
        self.output.setPlainText(self._bytes.decode('utf-8', errors='replace'))
        if len(chunk) > remaining:
            self._stop('Output limit reached; tests stopped.')

    def _stop(self, reason=False):
        self._stopped = True
        self.status.setText(reason if isinstance(reason, str) else 'Tests stopped.')
        self.process.kill()

    def _timeout(self):
        self._stop('Five-minute limit reached; tests stopped.')

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
            self.status.setText('Tests passed — inspect the output.' if success else
                                ('No tests discovered.' if code == 5 else f'Tests failed (exit {code}). Inspect the output.'))

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._idle()
            self.status.setText('Could not start Python. Check the app installation.')

    def reject(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self._stop()
            self.process.waitForFinished(1000)
        super().reject()

    def closeEvent(self, event):
        self.reject()
        event.accept()
