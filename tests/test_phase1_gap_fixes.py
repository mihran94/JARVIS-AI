"""The gaps this cycle closed in the Personal Codex Assistant tree.

Each test here exists because something was wrong on the branch:

1. The Video Editor buttons opened a browser and put a prompt on the
   clipboard with no approval, while the same action asked for approval when
   it was typed in the chat. The same action must be approved either way.
2. The AI Studio project link opened a browser with no approval.
3. Closing the window during a coding task left the Codex CLI and the test
   process running behind the owner's back. The Emergency Stop has to reach
   them before the window goes away.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

import desktop.app as desktop
from security.policy import Action


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = desktop.Window(tmp_path)
    monkeypatch.setattr(win, 'get_key', lambda provider: 'fake-key')
    monkeypatch.setattr(desktop.QMessageBox, 'warning',
                        staticmethod(lambda *args, **kwargs: None))
    yield win, app
    win.close()
    win.deleteLater()
    app.processEvents()


def test_the_video_tool_handoff_is_preserved(tmp_path, monkeypatch):
    """The Video Studio one-click handoff still opens the tool.

    The accepted Video Studio section made this a single click on purpose,
    and that behaviour is preserved. The chat command for the same tool
    still asks for approval, because a chat command can be anything the
    owner typed.
    """
    app = QApplication.instance() or QApplication([])
    win = desktop.Window(tmp_path)
    opened = []
    monkeypatch.setattr('desktop.app.QDesktopServices.openUrl',
                        staticmethod(lambda url: opened.append(str(url)) or True))
    monkeypatch.setattr(desktop.QMessageBox, 'warning',
                        staticmethod(lambda *args, **kwargs: None))
    try:
        win.open_video_tool('Google Flow')
        assert len(opened) == 1
        assert 'flow.google.com' in opened[0]
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_the_chat_command_for_the_same_tool_still_asks(tmp_path, monkeypatch):
    """The chat path keeps its approval; only the button is one click."""
    app = QApplication.instance() or QApplication([])
    win = desktop.Window(tmp_path)
    opened = []
    monkeypatch.setattr('desktop.app.QDesktopServices.openUrl',
                        staticmethod(lambda url: opened.append(str(url)) or True))
    monkeypatch.setattr(desktop.QMessageBox, 'warning',
                        staticmethod(lambda *args, **kwargs: None))
    try:
        win.queue_chat_launch('/video', 'Google Flow')
        assert win.chat_launch is not None
        assert win.chat_launch[2].kind == 'open_video_tool'
        assert opened == [], 'the browser opened before the owner approved'
        win.finish_chat_launch(True)
        assert len(opened) == 1
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_the_website_project_link_needs_the_approval(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    win = desktop.Window(tmp_path)
    opened = []
    monkeypatch.setattr('desktop.app.QDesktopServices.openUrl',
                        staticmethod(lambda url: opened.append(str(url)) or True))
    monkeypatch.setattr(desktop.QMessageBox, 'warning',
                        staticmethod(lambda *args, **kwargs: None))
    win.website_project_url.setText('https://ai.studio/apps/test-project')
    try:
        win.confirm = lambda action: False
        win.open_website_project()
        assert opened == [], 'the browser opened without an approval'
        win.confirm = lambda action: True
        win.open_website_project()
        assert len(opened) == 1
        kinds = [row['kind'] for row in win.store.tasks()]
        assert 'open_website_project' in kinds
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_closing_the_window_during_a_task_stops_the_workers(window, monkeypatch):
    """The window waits, and the Emergency Stop reaches the task."""
    win, app = window
    stopped = []
    monkeypatch.setattr(win, 'stop', lambda: stopped.append(True))
    win.test_worker = object()
    win.coding_worker = None
    win.editor.document().setModified(False)
    win.show()
    app.processEvents()
    win.close()
    win.deleteLater()
    app.processEvents()
    # The window did not go away while a task was running.
    assert win.isVisible()
    assert stopped == [True], 'the task was not stopped'
    assert win.close_when_done is True
    win.test_worker = None
    win.close()
    win.deleteLater()
    app.processEvents()


def test_the_window_closes_when_the_last_worker_is_gone(window):
    win, app = window
    win.close_when_done = True
    win.coding_worker = None
    win.test_worker = None
    win.editor.document().setModified(False)
    win.show()
    app.processEvents()
    win.on_test_finished()
    app.processEvents()
    assert win.isVisible() is False


def test_the_test_command_runs_off_the_interface_thread(window, monkeypatch, tmp_path):
    """The test command runs in a worker thread, and the window stays usable."""
    import threading
    import time
    win, app = window
    seen = []

    def fake_run_local_tests(folder, command, timeout=1800, cancel=None, observer=None):
        seen.append(threading.current_thread())
        return 'passed', '1 passed'

    monkeypatch.setattr('developer_studio.codex_task.run_local_tests', fake_run_local_tests)
    from developer_studio.intents import parse_coding_request
    from developer_studio.projects import SavedProject
    project = SavedProject('project-a', str(tmp_path), 'VS Code', 'pytest -q')
    request = parse_coding_request('run the tests of project-a', [project],
                                   lambda text: 'VS Code')
    win.coding = {'project': project, 'request': request, 'editor': 'VS Code',
                  'editor_status': {'installed': False, 'setup': '', 'path': None},
                  'steps': [], 'index': 0, 'outcome': None, 'text': 'run the tests'}
    win.start_test_run(win.coding['project'], tmp_path, 'pytest -q')
    deadline = time.monotonic() + 10
    while win.test_worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert seen, 'the test command did not run'
    assert all(thread is not threading.main_thread() for thread in seen), \
        'the test command ran on the interface thread'
