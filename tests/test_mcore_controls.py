"""Cockpit keyboard controls, without real audio devices or providers."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from desktop.app import Window


@pytest.fixture
def desktop(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    window.show()
    window.activateWindow()
    window.prompt.setFocus()
    app.processEvents()
    try:
        yield window, app
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_f4_uses_the_existing_microphone_button(desktop, monkeypatch):
    window, _ = desktop
    voice = window.voice_panel
    button = window.prime_shell.mic_mute_button
    monkeypatch.setattr(window, 'start_automatic_voice',
                        lambda: pytest.fail('Default unmute must not start Gemini Live'))
    assert not voice.consent.granted
    QTest.keyClick(window.prompt, Qt.Key.Key_F4)
    assert button.isChecked() and voice.microphone_muted
    assert not voice.muted
    QTest.keyClick(window.prompt, Qt.Key.Key_F4)
    assert not button.isChecked() and not voice.microphone_muted
    assert not voice.consent.granted and voice.worker is None


def test_escape_interrupts_live_playback_but_not_an_unrelated_approval(desktop):
    window, _ = desktop
    window.prompt.setPlainText('Open Calculator and calculate: 17 * 23')
    window.send_button.click()
    pending = window.chat_launch
    assert pending is not None
    window.prompt.setFocus()
    calls = []
    live = SimpleNamespace(state='speaking', interrupt=lambda: calls.append('interrupt'))
    window.live_voice = live
    try:
        QTest.keyClick(window.prompt, Qt.Key.Key_Escape)
        assert calls == ['interrupt']
        assert window.chat_launch is pending and not window.policy.stopped
        assert not window.voice_panel.consent.granted
        live.state = 'listening'
        QTest.keyClick(window.prompt, Qt.Key.Key_Escape)
        assert calls == ['interrupt']
    finally:
        window.live_voice = None


def test_escape_preserves_modal_dismissal(desktop):
    window, app = desktop
    voice = window.voice_panel
    voice.pending_speech = 'Still queued'
    dialog = QDialog(window)
    dialog.setModal(True)
    dialog.show()
    app.processEvents()
    try:
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        assert not dialog.isVisible()
        assert voice.pending_speech == 'Still queued'
    finally:
        dialog.close()


def test_interrupt_stops_only_queued_or_playing_local_output(desktop):
    window, _ = desktop
    voice = window.voice_panel
    calls = []
    assert window.hud_interrupt_reply() is False
    voice.pending_speech = 'Queued words'
    voice.pending_sample = 'ta'
    worker = SimpleNamespace(isRunning=lambda: True,
                             requestInterruption=lambda: calls.append('interrupt'))
    voice.speaker_worker = worker
    try:
        assert window.hud_can_interrupt_reply() and window.hud_interrupt_reply()
        assert voice.pending_speech == '' and voice.pending_sample is None
        assert voice.playback_busy and calls == ['interrupt']
        assert not voice.wake_timer.isActive() and not window.voice_rearm_timer.isActive()
    finally:
        voice.speaker_worker = None


def test_f11_keeps_existing_fullscreen_toggle(desktop):
    window, app = desktop
    assert not window.isFullScreen()
    QTest.keyClick(window.prompt, Qt.Key.Key_F11)
    app.processEvents()
    assert window.isFullScreen()
    window.prompt.setFocus()
    QTest.keyClick(window.prompt, Qt.Key.Key_F11)
    app.processEvents()
    assert not window.isFullScreen()
