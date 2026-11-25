"""M-CORE is a view of the real CMD desktop, not a second runtime."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from desktop.app import Window
from desktop.prime_ui import core_colour


@pytest.fixture
def desktop(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        window.show()
        app.processEvents()
        yield window, app
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_hud_palette_and_conversation_preserve_real_chat(desktop):
    window, app = desktop
    shell, chat = window.prime_shell, window.prime_chat
    palette = window.prime_palette
    assert core_colour(palette, 'idle') == palette.accent
    assert core_colour(palette, 'thinking') == palette.warn
    assert core_colour(palette, 'working') == palette.good
    assert core_colour(palette, 'stopped') == palette.danger
    assert chat.states.currentWidget() is chat.assistant
    assert shell.mark.isHidden()
    window.show_local_system_reply('/time', 'Local reply')
    app.processEvents()
    assert chat.states.currentWidget() is chat.conversation
    assert shell.mark.isVisible()
    shell.work_actions['Coding Assistant'].trigger()
    assert chat.task_area.currentIndex() == chat.task_panels['Coding Assistant']


def test_mcore_typed_summon_never_starts_mic_or_provider(desktop, monkeypatch):
    window, _ = desktop

    def unexpected(*args, **kwargs):
        pytest.fail('A typed summon only changes the view.')

    monkeypatch.setattr(window, 'send_chat_reply', unexpected)
    monkeypatch.setattr(window.voice_panel, 'listen', unexpected)
    window.prompt.setPlainText('Hey Jarvis!')
    window.send_button.click()
    assert not window.prompt.toPlainText()
    assert 'JARVIS is ready' in window.statusBar().currentMessage()
    assert not window.voice_panel.consent.listening


def test_mcore_revokes_mic_and_does_not_auto_grant(desktop):
    window, _ = desktop
    shell = window.prime_shell
    assert shell.mic_button.text() == 'Mic: off'
    shell.mic_button.click()
    assert window.pages.currentWidget() is window.pages.widget(window.page_indices['Voice / Hey Jarvis'])
    assert not window.voice_panel.consent.listening
    window.voice_panel.allow.setChecked(True)
    assert shell.mic_button.text() == 'Mic: ready'
    window.voice_panel.mute_button.setChecked(True)
    assert shell.mic_button.text() == 'Mic: ready'  # Reply mute is not microphone consent.
    shell.mic_button.click()
    assert not window.voice_panel.consent.listening
    assert shell.mic_button.text() == 'Mic: off'


def test_mcore_stop_cancels_approval_and_stops_audio(desktop, monkeypatch):
    window, _ = desktop
    calls = []
    monkeypatch.setattr(window.audio_test, 'stop', lambda: calls.append('audio stopped'))
    monkeypatch.setattr('desktop.app.launch_app', lambda *_: pytest.fail('No action may run'))
    window.prompt.setPlainText('Open Calculator and calculate: 17 * 23')
    window.send_button.click()
    assert window.prime_shell.state_chip.text() == 'APPROVAL REQUIRED'
    assert window.chat_launch is not None
    window.prime_shell.stop_button.click()
    assert window.policy.stopped
    assert not window.voice_panel.consent.listening
    assert window.chat_launch is None
    assert window.prime_shell.state_chip.text() == 'STOPPED'
    assert not window.prime_shell.mic_button.isEnabled()
    assert calls == ['audio stopped']


def test_mcore_route_does_not_claim_connected_live_voice(desktop):
    window, _ = desktop
    window.live_voice = SimpleNamespace(active=True, state='connecting')
    try:
        window.refresh_prime_state()
        assert window.prime_shell.mic_button.text() == 'Mic: connecting'
        assert window.prime_shell.provider_label.text() == 'Connecting to Gemini Live'
        window.live_voice.state = 'listening'
        window.refresh_prime_state()
        assert window.prime_shell.mic_button.text() == 'Mic: Gemini Live'
        assert 'Active route: Gemini Live' in window.prime_shell.provider_label.text()
    finally:
        window.live_voice = None
