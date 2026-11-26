"""Keyboard/HUD controls exercise the real Window without opening audio devices."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from desktop.app import Window
from voice.consent import VoiceConsent, VoiceError


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


def test_session_mute_preserves_consent_but_blocks_the_capture_gate():
    consent = VoiceConsent()
    consent.set_muted(True)
    consent.grant()
    assert consent.granted and consent.muted and not consent.listening
    with pytest.raises(VoiceError, match='Unmute'):
        consent.require_listening()
    consent.revoke()
    consent.set_muted(False)
    assert not consent.listening
    with pytest.raises(VoiceError, match='Allow'):
        consent.require_listening()


def test_f4_mutes_input_and_unmute_never_opens_the_microphone(desktop, monkeypatch):
    window, app = desktop
    voice = window.voice_panel
    starts = []

    def no_capture(*_):
        starts.append('capture')
        pytest.fail('No capture should start from F4 or while muted.')

    monkeypatch.setattr(voice, '_recognizer_factory', no_capture)
    voice.allow.setChecked(True)
    assert voice.consent.listening
    QTest.keyClick(window.prompt, Qt.Key.Key_F4)
    assert voice.consent.granted and voice.microphone_muted
    assert not voice.consent.listening
    assert window.hud_mic_state() == 'Mic: muted'
    assert not voice.muted  # Reply mute remains a separate control.
    voice.listen('continuous')
    assert voice.worker is None and not voice.continuous
    QTest.keyClick(window.prompt, Qt.Key.Key_F4)
    app.processEvents()
    assert voice.consent.listening and not voice.microphone_muted
    assert voice.worker is None and not starts
    assert window.hud_mic_state() == 'Mic: ready'
    assert not window.voice_rearm_timer.isActive()


def test_mute_stops_existing_live_session_without_restarting_it(desktop):
    window, _ = desktop
    voice = window.voice_panel
    voice.allow.setChecked(True)
    live = SimpleNamespace(active=True, state='listening')
    messages = []

    def stop(message):
        messages.append(message)
        live.active = False
        live.state = 'idle'

    live.stop = stop
    window.live_voice = live
    try:
        window.hud_toggle_microphone()
        assert not live.active and messages == ['Microphone muted. Live Voice ended.']
        assert voice.consent.granted and not voice.consent.listening
        window.hud_toggle_microphone()
        assert not live.active and len(messages) == 1
    finally:
        window.live_voice = None


def test_escape_interrupts_only_the_existing_speaker_and_not_pc_approval(desktop):
    window, _ = desktop
    voice = window.voice_panel
    calls = []

    class Speaker:
        def isRunning(self):
            return True

        def requestInterruption(self):
            calls.append('interrupt')

    # An unrelated routing approval remains neither granted nor declined.
    window.prompt.setPlainText('Open Calculator and calculate: 17 * 23')
    window.send_button.click()
    pending = window.chat_launch
    assert pending is not None
    window.prompt.setFocus()
    voice.speaker_worker = Speaker()
    voice.speaking = True
    voice.refresh()
    try:
        assert window.hud_can_interrupt_reply()
        QTest.keyClick(window.prompt, Qt.Key.Key_Escape)
        assert calls == ['interrupt']
        assert voice.playback_busy
        assert not voice.wake_timer.isActive() and not window.voice_rearm_timer.isActive()
        assert window.chat_launch is pending and not window.policy.stopped
        assert not voice.consent.granted
    finally:
        voice.speaker_worker = None
        voice.speaking = False


def test_escape_on_modal_dialog_keeps_normal_dismissal(desktop):
    window, app = desktop
    voice = window.voice_panel
    voice.pending_speech = 'Still queued'
    voice.refresh()
    assert window.hud_can_interrupt_reply()
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


def test_interrupt_button_callback_drops_only_queued_reply_or_interrupts_active_live_output(desktop):
    window, _ = desktop
    voice = window.voice_panel
    assert window.hud_interrupt_reply() is False
    voice.pending_speech = 'Queued words'
    voice.pending_sample = 'ta'
    voice.refresh()
    assert window.hud_interrupt_reply() is True
    assert voice.pending_speech == '' and voice.pending_sample is None
    assert not window.hud_can_interrupt_reply()

    calls = []
    live = SimpleNamespace(active=True, state='speaking', interrupt=lambda: calls.append('interrupt'))
    window.live_voice = live
    try:
        assert window.hud_interrupt_reply() is True
        assert calls == ['interrupt']
        live.state = 'listening'
        assert window.hud_interrupt_reply() is False
        assert calls == ['interrupt']
    finally:
        window.live_voice = None


def test_f11_uses_existing_fullscreen_toggle(desktop):
    window, app = desktop
    assert not window.isFullScreen()
    QTest.keyClick(window.prompt, Qt.Key.Key_F11)
    app.processEvents()
    assert window.isFullScreen()
    window.prompt.setFocus()
    QTest.keyClick(window.prompt, Qt.Key.Key_F11)
    app.processEvents()
    assert not window.isFullScreen()
