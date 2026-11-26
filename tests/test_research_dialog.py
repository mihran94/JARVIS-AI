"""The research window in the desktop."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QPushButton

from desktop.research_dialog import ResearchWorker, open_research
from research.research import ResearchError


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


class FakeWindow:
    """The little bit of the window that the research dialog uses."""

    class _Provider:
        default_model = 'a-model'

    class _Router:
        def spec(self, name):
            return FakeWindow._Provider()

    def __init__(self):
        from core.store import Store
        import tempfile
        self.router = FakeWindow._Router()
        self.store = Store(tempfile.mkdtemp() + '/history.sqlite3')
        self.chat_provider = type('Box', (), {'currentText': lambda self: 'Gemini'})()
        self.get_key = lambda provider: 'key'


def test_the_window_opens(app):
    from PySide6.QtWidgets import QWidget
    window = FakeWindow()
    dialog = open_research(QWidget())
    assert dialog is not None
    assert dialog.windowTitle() == 'JARVIS research'


def test_the_worker_reports_a_refused_address():
    class Router:
        def spec(self, name):
            class Spec:
                default_model = 'a-model'
            return Spec()

    worker = ResearchWorker(Router(), 'http://insecure.example', 'Why?', 'Gemini', 'a-model', '')
    messages = []
    worker.failed.connect(messages.append)
    worker.run()
    assert messages
    assert 'https' in messages[0].lower()


def test_the_worker_reports_a_question_that_is_not_there():
    class Router:
        def spec(self, name):
            class Spec:
                default_model = 'a-model'
            return Spec()

    worker = ResearchWorker(Router(), 'https://example.com', '', 'Gemini', 'a-model', '')
    messages = []
    worker.failed.connect(messages.append)
    worker.run()
    assert messages


def test_the_automation_page_offers_the_research_window(tmp_path):
    """The owner names a page and a question, and gets an answer from it."""
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        window.open_section('PC Control')
        assert window.automation_panel.research_button.text() == 'Read page with AI'
        window.automation_panel.research_button.click()
        dialog = window.research_dialog
        assert dialog is not None
        assert dialog.windowTitle() == 'JARVIS research'
        assert not dialog.isWindow()
        assert window.prime_chat.task_area.isAncestorOf(dialog)
        dialog.reject()
        assert window.prime_chat.task_area.currentIndex() == window.prime_chat.task_panels['PC Control']
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
