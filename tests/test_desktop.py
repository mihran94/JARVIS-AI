import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from desktop.app import Window, STYLE, launch_arguments


def test_desktop_navigation_stop_and_editor(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    window = Window(tmp_path)
    window.show()
    app.processEvents()
    assert window.pages.count() == 12
    assert window.nav.count() == 6
    for index in range(window.nav.count()):
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


def test_packaged_smoke_switch_is_explicit_and_not_forwarded_to_qt():
    args, smoke = launch_arguments(['JarvisAI.exe', '--smoke-test'])
    assert smoke is True
    assert args == ['JarvisAI.exe']
    args, smoke = launch_arguments(['JarvisAI.exe'])
    assert smoke is False
    assert args == ['JarvisAI.exe']


def test_voice_drafts_text_without_network_or_automation(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        assert window.nav.item(0).text() == 'JARVIS Chat'
        assert window.pages.currentIndex() == window.page_indices['JARVIS Chat']
        assert window.voice_panel.consent.granted is False
        window.listen_to_user()
        assert window.pages.currentIndex() == window.page_indices['Voice / Hey Jarvis']
        assert window.store.messages(window.session) == []

        window.voice_panel.allow.setChecked(True)
        window.open_section('JARVIS Chat')
        window.voice_panel.on_transcript('Can you help write a Python test?')
        assert window.prompt.toPlainText() == 'Can you help write a Python test?'
        assert window.store.messages(window.session) == []
        assert window.worker is None
        assert window.gateway is not None

        window.voice_panel.on_wake_call('Hey Jarvis', 'explain this code')
        assert 'explain this code' in window.prompt.toPlainText()
        assert window.store.messages(window.session) == []

        original = window.prompt.toPlainText()
        window.voice_panel.stop_voice()
        window.voice_panel.on_transcript('delete all files')
        assert window.prompt.toPlainText() == original
        window.stop()
        window.on_voice_transcript('launch every program')
        assert window.prompt.toPlainText() == original
    finally:
        window.close()
        app.processEvents()


def test_chat_pc_action_only_runs_exact_allowlisted_command_after_approval(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    launched = []
    monkeypatch.setattr('desktop.app.launch_app',
                        lambda name: launched.append(name) or 'Mock app started')
    # Denial is caught by the UI and reported as a dialog.
    monkeypatch.setattr('desktop.app.QMessageBox.warning', lambda *args: None)
    try:
        window.prompt.setPlainText('open notepad and delete everything')
        window.review_chat_pc_action()
        assert launched == []
        assert 'No action ran' in window.statusBar().currentMessage()

        window.prompt.setPlainText('open notepad')
        window.confirm = lambda action: False
        window.review_chat_pc_action()
        assert launched == []
        assert window.store.tasks()[0]['status'] == 'denied'

        window.confirm = lambda action: (
            action.kind == 'launch_app' and action.target == 'Notepad')
        window.review_chat_pc_action()
        assert launched == ['Notepad']
        assert window.store.tasks()[0]['status'] == 'completed'
        assert window.store.messages(window.session) == []

        window.prompt.setPlainText('கால்குலேட்டர் திற')
        window.confirm = lambda action: action.target == 'Calculator'
        window.review_chat_pc_action()
        assert launched == ['Notepad', 'Calculator']

        window.stop()
        assert not window.review_pc_action_button.isEnabled()
        window.review_chat_pc_action()
        assert launched == ['Notepad', 'Calculator']
        window.resume()
        assert window.review_pc_action_button.isEnabled()
    finally:
        window.close()
        app.processEvents()


def test_hands_free_is_explicit_session_opt_in_and_local_only(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    listens = []
    window.voice_panel.listen = lambda mode='once': listens.append(mode)
    try:
        assert not window.hands_free_voice.isChecked()
        assert not window.voice_panel.consent.listening
        window.hands_free_voice.setChecked(True)
        assert not window.hands_free_voice.isChecked()
        assert listens == []
        window.voice_panel.allow.setChecked(True)
        window.hands_free_voice.setChecked(True)
        assert not window.hands_free_voice.isChecked()
        assert listens == []
        window.chat_provider.setCurrentText('Ollama')
        window.hands_free_voice.setChecked(True)
        assert window.hands_free_voice.isChecked()
        assert window.read_replies.isChecked()
        assert listens == ['dialogue']
        assert window.store.messages(window.session) == []
        window.backup_consent.setChecked(True)
        assert not window.hands_free_voice.isChecked()
        assert not window.local_voice_allowed()
    finally:
        window.close()
        app.processEvents()


def test_local_hands_free_wake_auto_sends_only_to_ollama(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    window.voice_panel.listen = lambda mode='once': None
    sent = []
    window.send = lambda: sent.append((window.chat_provider.currentText(),
                                       window.prompt.toPlainText()))
    try:
        window.voice_panel.allow.setChecked(True)
        window.chat_provider.setCurrentText('Ollama')
        window.hands_free_voice.setChecked(True)
        assert window.local_voice_allowed()

        window.on_wake_detected('Hey Jarvis', 'Explain Python lists')
        assert sent == [('Ollama', 'Explain Python lists')]
        assert window.store.messages(window.session) == []
        # Never accidentally send an existing draft combined with speech.
        window.prompt.setPlainText('An unfinished private draft')
        window.on_wake_detected('Hey Jarvis', 'new question')
        assert len(sent) == 1
        assert 'An unfinished private draft' in window.prompt.toPlainText()

        window.chat_provider.setCurrentText('OpenAI')
        assert not window.hands_free_voice.isChecked()
        window.prompt.clear()
        window.on_wake_detected('Hey Jarvis', 'cloud question')
        assert sent == [('Ollama', 'Explain Python lists')]
        assert window.prompt.toPlainText() == 'cloud question'
    finally:
        window.close()
        app.processEvents()


def test_local_hands_free_rearms_but_emergency_stop_revokes_it(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    listened = []
    window.voice_panel.listen = lambda mode='once': listened.append(mode)
    try:
        window.voice_panel.allow.setChecked(True)
        window.chat_provider.setCurrentText('Ollama')
        window.hands_free_voice.setChecked(True)
        assert listened == ['dialogue']
        window.schedule_local_voice_rearm()
        assert window.voice_rearm_timer.isActive()
        window.voice_rearm_timer.stop()
        window.rearm_local_voice()
        assert listened == ['dialogue', 'dialogue']
        window.stop()
        assert not window.hands_free_voice.isChecked()
        assert not window.voice_rearm_timer.isActive()
        assert not window.voice_panel.consent.granted
        window.rearm_local_voice()
        assert listened == ['dialogue', 'dialogue']
        window.resume()
        assert not window.voice_panel.consent.granted
        assert not window.hands_free_voice.isChecked()
    finally:
        window.close()
        app.processEvents()


def test_hands_free_never_reopens_microphone_during_speech(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    listened = []
    window.voice_panel.listen = lambda mode='once': listened.append(mode)
    try:
        window.voice_panel.allow.setChecked(True)
        window.chat_provider.setCurrentText('Ollama')
        window.hands_free_voice.setChecked(True)
        assert listened == ['dialogue']

        class Speaking:
            running = True

            def isRunning(self):
                return self.running

        speaker = Speaking()
        window.voice_panel.speaker_worker = speaker
        window.schedule_local_voice_rearm()
        assert not window.voice_rearm_timer.isActive()
        window.rearm_local_voice()
        assert listened == ['dialogue']

        # Speech finishing unlocks the next local wake-phrase cycle.
        speaker.running = False
        window.schedule_local_voice_rearm()
        assert window.voice_rearm_timer.isActive()
        window.voice_rearm_timer.stop()
        window.rearm_local_voice()
        assert listened == ['dialogue', 'dialogue']
        window.voice_panel.speaker_worker = None
    finally:
        window.voice_panel.speaker_worker = None
        window.close()
        app.processEvents()
