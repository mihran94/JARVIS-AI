import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from desktop.app import Window, STYLE


def test_desktop_navigation_stop_and_editor(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    window = Window(tmp_path)
    window.show()
    app.processEvents()
    assert window.pages.count() == 12
    for index in range(11):
        window.nav.setCurrentRow(index)
        app.processEvents()
        assert window.pages.currentIndex() == index
    window.confirm = lambda _: True
    window.editor.setPlainText('print("tested")')
    window.save_file()
    assert window.workspace.read('hello.py') == 'print("tested")'
    assert window.store.tasks()[0]['status'] == 'completed'
    window.stop()
    assert window.policy.stopped and not window.send_button.isEnabled()
    window.resume()
    assert not window.policy.stopped and window.send_button.isEnabled()
    window.close()
    app.processEvents()


def test_chat_worker_to_ui_persists_result(tmp_path):
    import time
    import httpx
    from providers.router import ProviderRouter
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    class TestVault:
        def get(self, provider):
            return 'test-key-not-real'
    window.vault = TestVault()
    body = 'data: {"choices":[{"delta":{"content":"Hello from transport test"}}]}\n\ndata: [DONE]\n\n'
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=body))
    window.router = ProviderRouter(transport=transport)
    window.prompt.setPlainText('Hello')
    window.send()
    deadline = time.monotonic() + 5
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert window.worker is None
    assert window.store.messages(window.session)[-1] == {
        'role': 'assistant', 'content': 'Hello from transport test'}
    assert window.store.tasks()[0]['status'] == 'completed'
    assert window.send_button.isEnabled()
    window.close()


def test_late_output_ignored_after_stop_resume(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    window.chat_ticket = window.policy.ticket()
    window.chat_task = window.store.task('chat', 'test')
    window.stop()
    window.resume()
    window.on_chunk('must not appear')
    window.on_result('completed', 'must not be stored')
    assert 'must not' not in window.transcript.toPlainText()
    assert window.store.messages(window.session) == []
    rows = {x['id']: x for x in window.store.tasks()}
    assert rows[window.chat_task]['status'] == 'cancelled'
    window.close()


def test_saved_chat_reopens(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    old = window.session
    window.store.message(old, 'user', 'Earlier conversation')
    window.new_chat()
    window.archives.setCurrentIndex(window.archives.findData(old))
    window.open_chat()
    assert window.session == old
    assert 'Earlier conversation' in window.transcript.toPlainText()
    window.close()


def test_provider_check_records_health_without_chat(tmp_path):
    import time
    import httpx
    from providers.router import ProviderRouter
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    class TestVault:
        def get(self, provider):
            return 'fake-test-key'
    window.vault = TestVault()
    window.confirm = lambda _: True
    body = ('data: {"choices":[{"delta":{"content":"OK"}}]}\n\n'
            'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":1,"total_tokens":6}}\n\n'
            'data: [DONE]\n\n')
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=body))
    window.router = ProviderRouter(transport=transport)
    window.test_connection()
    deadline = time.monotonic() + 5
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert window.worker is None
    assert window.store.messages(window.session) == []
    assert window.store.tasks()[0]['kind'] == 'provider_check'
    assert window.store.tasks()[0]['status'] == 'completed'
    assert window.store.usage_rows()[0]['total_tokens'] == 6
    assert 'completed' in window.provider_health.text()
    window.close()


def test_stop_cancels_desktop_queue(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    window.enqueue()
    assert window.queue.rows()[0]['status'] == 'queued'
    window.stop()
    window.resume()
    assert window.queue.rows()[0]['status'] == 'cancelled'
    window.close()

def test_workflow_desktop_create_and_emergency_cancel(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    window.workflow_apps.setText('Notepad, Calculator')
    window.add_workflow()
    assert window.workflows.rows()[0]['status'] == 'queued'
    assert [step['app'] for step in window.workflows.steps(window.workflows.rows()[0]['id'])] == [
        'Notepad', 'Calculator']
    window.stop()
    assert window.workflows.rows()[0]['status'] == 'cancelled'
    window.resume()
    window.close()
