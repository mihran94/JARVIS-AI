"""Cancellable single-page research with separate success and failure states."""
from PySide6.QtCore import QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from research.research import ResearchError, research
from security.policy import Stopped


class ResearchWorker(QThread):
    answered = Signal(str)
    failed = Signal(str)

    def __init__(self, router, url, question, provider, model, key, policy=None, ticket=None):
        super().__init__()
        self.router, self.url, self.question = router, url, question
        self.provider, self.model, self.key = provider, model, key
        self.policy, self.ticket = policy, ticket

    def check(self):
        if self.isInterruptionRequested():
            raise Stopped('Research cancelled.')
        if self.policy:
            self.policy.check(self.ticket)

    def run(self):
        try:
            answer = research(self.url, self.question, router=self.router,
                              provider=self.provider, model=self.model, key=self.key, check=self.check)
            self.check()
            self.answered.emit(answer)
        except (ResearchError, Stopped) as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit('Research failed. Check the provider configuration and the page address.')
        finally:
            self.key = ''


class ResearchDialog(QDialog):
    dismissed = Signal()

    def __init__(self, window, *, embedded=False):
        super().__init__(window)
        self.embedded = embedded
        if embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
        self.window = window
        self.worker = None
        self.closing = False
        self.setWindowTitle('JARVIS research')
        self.resize(640, 520)
        layout = QVBoxLayout(self)
        note = QLabel('The selected AI provider receives your question and text from the HTTPS page.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText('https://example.com/page')
        self.question = QLineEdit()
        form.addRow('Address', self.url)
        form.addRow('Question', self.question)
        layout.addLayout(form)
        self.answer = QPlainTextEdit()
        self.answer.setReadOnly(True)
        layout.addWidget(self.answer)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.start_button = QPushButton('Research')
        self.start_button.clicked.connect(self.begin)
        layout.addWidget(self.start_button)
        close = QPushButton('Close')
        close.clicked.connect(self.reject)
        layout.addWidget(close)

    @Slot()
    def begin(self):
        if self.worker:
            return
        url, question = self.url.text().strip(), self.question.text().strip()
        if not url or not question:
            self.status.setText('Enter an address and a question.')
            return
        w = self.window
        try:
            ticket = w.policy.ticket()
            provider = w.chat_provider.currentText()
            model = w.selected_model(provider)
            key = w.get_key(provider)
        except (ValueError, RuntimeError) as error:
            self.status.setText(str(error))
            return
        self.closing = False
        self.worker = ResearchWorker(w.router, url, question, provider, model, key, w.policy, ticket)
        self.worker.answered.connect(self.answered)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finished_worker)
        self.start_button.setEnabled(False)
        self.answer.clear()
        self.status.setText('Reading the page…')
        self.worker.start()

    @Slot(str)
    def answered(self, answer):
        try:
            self.worker.check()
        except Stopped:
            self.status.setText('Research cancelled.')
            return
        self.answer.setPlainText(answer)
        self.status.setText('Answer received.')

    @Slot(str)
    def failed(self, message):
        self.status.setText(message)

    def cancel(self):
        if self.worker:
            self.worker.requestInterruption()
            self.status.setText('Cancelling research…')

    @Slot()
    def finished_worker(self):
        self.worker.deleteLater()
        self.worker = None
        self.start_button.setEnabled(True)
        if self.closing:
            self.reject()
        if getattr(self.window, 'close_when_done', False):
            self.window.close()

    def reject(self):
        if self.worker:
            self.closing = True
            self.cancel()
        elif self.embedded:
            self.dismissed.emit()
        else:
            super().reject()

    def closeEvent(self, event):
        if self.worker:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)


def open_research(window):
    dialog = ResearchDialog(window)
    dialog.show()
    return dialog
