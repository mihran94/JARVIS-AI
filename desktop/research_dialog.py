"""The research window.

The owner gives an address and a question. The page is read on this machine
and the answer comes from the same provider as the chat, so the key stays in
the Windows vault.

The reading happens on a worker thread, so the window never freezes.
"""
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

from research.research import ResearchError, research


class ResearchWorker(QThread):
    """Reads the page and asks the provider, away from the interface."""

    answered = Signal(str)
    failed = Signal(str)

    def __init__(self, router, url, question, provider, model, key):
        super().__init__()
        self.router = router
        self.url = url
        self.question = question
        self.provider = provider
        self.model = model
        self.key = key

    def run(self):
        try:
            answer = research(self.url, self.question, router=self.router,
                              provider=self.provider, model=self.model, key=self.key)
        except ResearchError as error:
            self.failed.emit(str(error))
            return
        except Exception as error:
            self.failed.emit('The research failed: ' + str(error))
            return
        self.answered.emit(answer)


def open_research(window):
    """Open the research window."""
    dialog = QDialog(window)
    dialog.setWindowTitle('JARVIS research')
    dialog.resize(640, 520)
    layout = QVBoxLayout(dialog)

    note = QLabel(
        'Give an https address and a question about the page. The page is read on '
        'this computer; a page that points inside your own network is refused. '
        'Only the text of the page is sent to the provider.')
    note.setWordWrap(True)
    layout.addWidget(note)

    form = QFormLayout()
    url_field = QLineEdit()
    url_field.setPlaceholderText('https://example.com/page')
    form.addRow('Address', url_field)
    question_field = QLineEdit()
    question_field.setPlaceholderText('What do you want to know about the page?')
    form.addRow('Question', question_field)
    layout.addLayout(form)

    answer = QPlainTextEdit()
    answer.setReadOnly(True)
    answer.setPlaceholderText('The answer appears here.')
    layout.addWidget(answer)

    status = QLabel('')
    status.setWordWrap(True)
    layout.addWidget(status)

    row = QVBoxLayout()
    start = QPushButton('Research')
    close = QPushButton('Close')
    layout.addLayout(row)

    holder = {'worker': None}

    def begin():
        url = url_field.text().strip()
        question = question_field.text().strip()
        if not url or not question:
            status.setText('An address and a question are needed.')
            return
        provider = window.chat_provider.currentText()
        model = window.store.get('model:' + provider,
                                 window.router.spec(provider).default_model)
        key = window.get_key(provider)
        holder['worker'] = ResearchWorker(window.router, url, question, provider, model, key)
        holder['worker'].answered.connect(answer.setPlainText)
        holder['worker'].failed.connect(status.setText)
        holder['worker'].finished.connect(lambda: status.setText('Done.'))
        holder['worker'].start()
        status.setText('Reading the page…')

    start.clicked.connect(begin)
    close.clicked.connect(dialog.close)
    row.addWidget(start)
    row.addWidget(close)
    dialog.show()
    return dialog


__all__ = ['ResearchWorker', 'open_research']
