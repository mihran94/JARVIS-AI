"""Recovery and session-boundary regressions; no hardware/provider calls."""
import json
import os
import time
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtMultimedia import QAudioFormat
from PySide6.QtWidgets import QApplication, QPushButton

from core import coding_tasks
from core.store import Store
from desktop import camera, live_voice
from security.policy import Policy


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('state', ['pending', 'running'])
def test_restart_keeps_interrupted_coding_task_explicitly_retryable(tmp_path, state):
    store = Store(tmp_path / 'history.sqlite3')
    task = coding_tasks.create(store, 'Improve greeting', 'OpenAI')
    coding_tasks.set_state(store, task, state)
    reopened = Store(tmp_path / 'history.sqlite3')
    recovered = coding_tasks.load(reopened, task.ident)
    assert recovered.state == 'interrupted'
    assert recovered.goal == task.goal and recovered.provider == task.provider
    assert [item.ident for item in coding_tasks.resumable(reopened)] == [task.ident]
    assert recovered.resumable
    assert not recovered.appliable
    # Reopening must not start or automatically approve the saved operation.
    assert reopened.tasks()[0]['status'] == 'interrupted'


@pytest.mark.parametrize('saved', ['not-hex', 'abc', 42, ['camera']])
def test_corrupt_camera_preference_does_not_prevent_startup(app, tmp_path, monkeypatch, saved):
    store = Store(tmp_path / 'history.sqlite3')
    store.set('camera:device', saved)
    monkeypatch.setattr(camera, 'QCamera', None)
    toggle = QPushButton()
    toggle.setCheckable(True)
    panel = camera.CameraPanel(store, Policy(), toggle)
    try:
        assert panel.choice.currentIndex() == 0
        assert not toggle.isChecked()
        assert store.get('camera:device') == saved
    finally:
        panel.close()
        panel.deleteLater()


class Socket(QObject):
    connected = Signal()
    disconnected = Signal()
    errorOccurred = Signal(object)
    textMessageReceived = Signal(str)
    binaryMessageReceived = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

    def open(self, url):
        pass

    def abort(self):
        self.disconnected.emit()


class Audio(QObject):
    stateChanged = Signal(object)

    def __init__(self, *args):
        super().__init__()

    def setVolume(self, value):
        pass

    def stop(self):
        pass

    def reset(self):
        pass


def test_late_packets_from_old_socket_cannot_stop_replacement_session(app, monkeypatch):
    monkeypatch.setattr(live_voice, 'QWebSocket', Socket)
    monkeypatch.setattr(live_voice, 'QAudioSource', Audio)
    monkeypatch.setattr(live_voice, 'QAudioSink', Audio)
    fmt = SimpleNamespace(sampleFormat=lambda: QAudioFormat.SampleFormat.Int16)
    device = SimpleNamespace(preferredFormat=lambda: fmt, isNull=lambda: False,
                             isFormatSupported=lambda value: True)
    monkeypatch.setattr(live_voice.AudioTest, 'pcm_format', lambda value: fmt)
    live = live_voice.LiveVoice()
    live.start('test-key', 'test', microphone=device, output_device=device)
    old = live.socket
    live.stop()
    live.start('test-key', 'test', microphone=device, output_device=device)
    current = live.socket
    try:
        old.textMessageReceived.emit(json.dumps({'error': {'message': 'old session'}}))
        old.binaryMessageReceived.emit(b'{"error":{"message":"old binary"}}')
        assert live.socket is current and live.state == 'connecting'
    finally:
        live.stop()


def test_stop_during_speaker_reset_does_not_reopen_audio(app):
    live = live_voice.LiveVoice()
    live.socket = Socket()
    resets, starts = [], []

    class Speaker(Audio):
        def reset(self):
            resets.append(True)
            if len(resets) == 1:
                live.stop()

        def start(self):
            starts.append(True)
            return object()

    live.player = Speaker()
    live.output = object()
    live.set_state('speaking')
    live.interrupt()
    assert live.state == 'idle' and live.output is None
    assert starts == []


def test_completed_turn_callback_preserves_reentrant_next_turn(app):
    live = live_voice.LiveVoice()
    live.set_state('listening')
    live.transcript = ['first question', 'first reply']
    heard = []

    def next_turn(question, reply):
        heard.append((question, reply))
        live.transcript = ['next question', '']

    live.turn_finished.connect(next_turn)
    live.receive('{"serverContent":{"turnComplete":true}}')
    assert heard == [('first question', 'first reply')]
    assert live.transcript == ['next question', '']


def test_heard_callback_replacing_session_discards_rest_of_old_packet(app):
    live = live_voice.LiveVoice()
    live.socket = object()
    live.set_state('listening')
    replacement = object()

    def replace(text):
        live.socket = replacement
        live.transcript = ['new session', '']

    live.heard_changed.connect(replace)
    live.receive(json.dumps({'serverContent': {
        'inputTranscription': {'text': 'old input'},
        'outputTranscription': {'text': 'old reply'}, 'turnComplete': True,
    }}))
    assert live.socket is replacement
    assert live.transcript == ['new session', '']


def test_retry_after_restart_still_requires_new_approval(app, tmp_path, monkeypatch):
    from desktop.app import QMessageBox, Window

    store = Store(tmp_path / 'history.sqlite3')
    task = coding_tasks.create(store, 'Change the greeting', 'OpenAI')
    coding_tasks.set_state(store, task, 'running')
    window = Window(tmp_path)
    monkeypatch.setattr(QMessageBox, 'warning', staticmethod(lambda *args: None))
    called, approvals = [], []
    monkeypatch.setattr(window, 'run_improvement',
                        lambda *args, **kwargs: called.append((args, kwargs)))
    window.confirm = lambda action: approvals.append(action) or False
    try:
        window.retry_improvement()
        assert [action.kind for action in approvals] == ['retry_saved_improvement']
        assert called == []
        window.confirm = lambda action: True
        window.retry_improvement()
        assert len(called) == 1
        assert called[0][0][0] == task.goal
        assert called[0][1]['task'].ident == task.ident
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_window_defers_close_without_blocking_until_voice_worker_exits(app, tmp_path, monkeypatch):
    from desktop.app import Window

    window = Window(tmp_path)
    busy = [True]
    stopped, waited, cancelled = [], [], []
    window.voice_panel.worker = SimpleNamespace(isRunning=lambda: busy[0],
                                                isInterruptionRequested=lambda: True)
    monkeypatch.setattr(window, 'stop', lambda: stopped.append(True))
    monkeypatch.setattr(window.voice_panel, 'stop_voice', lambda: cancelled.append(True))
    monkeypatch.setattr(window.voice_panel, 'wait_for_workers', lambda: waited.append(True))
    try:
        window.show()
        app.processEvents()
        window.close()
        assert window.isVisible()
        assert window.close_when_done
        assert stopped == []
        assert cancelled == [True]
        assert window.policy.stopped
        assert waited == []
        busy[0] = False
        deadline = time.monotonic() + 2
        while window.isVisible() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert not window.isVisible()
        assert waited == [True]
        assert stopped == []
    finally:
        window.voice_panel.worker = None
        window.close()
        window.deleteLater()
        app.processEvents()
