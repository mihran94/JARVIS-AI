"""Read local network diagnostics without blocking the desktop UI."""
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from quantum_core.local_diagnostics import DiagnosticError, REPORTS, read_network_report


class ReportWorker(QThread):
    result = Signal(str)

    def __init__(self, report, parent):
        super().__init__(parent)
        self.report = report

    def run(self):
        try:
            text = read_network_report(self.report)
        except DiagnosticError as error:
            text = str(error)
        self.result.emit(text)


class NetworkDiagnostics(QDialog):
    """A local-only view for on-demand OS inventory reports."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('JARVIS Cybersecurity · Local diagnostics')
        self.resize(620, 390)
        self.worker = None

        layout = QVBoxLayout(self)
        description = QLabel('Read the operating system’s local network tables. Results stay in this window.')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.report_type = QComboBox()
        for key, label in REPORTS.items():
            self.report_type.addItem(label, key)
        layout.addWidget(self.report_type)
        self.read_button = QPushButton('Read report')
        self.read_button.clicked.connect(self.read_report)
        layout.addWidget(self.read_button)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
        self.close_button = QPushButton('Close')
        self.close_button.clicked.connect(self.reject)
        layout.addWidget(self.close_button)

    def read_report(self):
        if self.worker is not None:
            return
        self.read_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.output.setPlainText('Reading the operating system…')
        self.worker = ReportWorker(self.report_type.currentData(), self)
        self.worker.result.connect(self.output.setPlainText)
        self.worker.finished.connect(self.report_finished)
        self.worker.start()

    def report_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.read_button.setEnabled(True)
        self.close_button.setEnabled(True)

    def reject(self):
        if self.worker is None:
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            event.ignore()
        else:
            super().closeEvent(event)
