"""Session control grants and the grouped settings use the real controls."""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication, QPushButton
from types import SimpleNamespace

from core.mission_tools import ToolError, build_registry
from desktop.app import Window
from security.policy import Action


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    win.show()
    app.processEvents()
    yield win
    win.close()
    win.deleteLater()
    app.processEvents()


def test_take_control_routes_a_goal_and_release_cancels_the_session(window, monkeypatch):
    goals = []
    cancelled = []
    monkeypatch.setattr(window.mission_controller, 'start', lambda goal, **kwargs: goals.append((goal, kwargs)))
    monkeypatch.setattr(window.mission_controller, 'cancel', lambda: cancelled.append(True))
    assert window.route_interface_command('take control')
    assert window.desktop_control_active
    assert 'CONTROL ACTIVE' in window.prime_shell.footer_status.text()
    assert window.route_interface_command('open Notepad and write hello')
    assert goals == [('open Notepad and write hello', {'from_chat': True})]
    assert window.route_interface_command('Notepad open pannu')
    assert len(goals) == 2
    assert window.route_interface_command('Use the mouse to click View in Notepad')
    assert goals[-1][0] == 'Use the mouse to click View in Notepad'
    assert not window.route_interface_command('open Notepad வேண்டாம்')
    assert not window.route_interface_command('Mouse control')
    assert len(goals) == 3
    assert window.route_interface_command('stop control')
    assert not window.desktop_control_active
    assert cancelled


def test_typed_mic_active_requires_existing_consent(window, monkeypatch):
    monkeypatch.setattr(window, 'start_automatic_voice', lambda: None)
    window.prime_shell.mic_mute_button.setChecked(True)
    window.voice_panel.allow.setChecked(False)
    window.prompt.setPlainText('mic active pannu')
    window.send()
    assert window.voice_panel.microphone_muted

    window.voice_panel.allow.setChecked(True)
    window.prompt.setPlainText('mic active pannu')
    window.send()
    assert not window.voice_panel.microphone_muted
    assert not window.prime_shell.mic_mute_button.isChecked()


def test_typed_remember_stays_local(window, monkeypatch):
    def unexpected_provider(*args, **kwargs):
        pytest.fail('A typed remember command must be handled locally')

    monkeypatch.setattr(window, 'get_key', unexpected_provider)
    window.prompt.setPlainText('நினைவில் வை: I prefer morning meetings')
    window.send()
    assert [note.body for note in window.memory_service.search('meetings')] == [
        'I prefer morning meetings']
    assert not window.prompt.toPlainText()


def test_voice_reconnect_is_bounded_and_mute_cancels_it(window, monkeypatch):
    monkeypatch.setattr(window, 'start_automatic_voice', lambda: None)
    window.voice_panel.allow.setChecked(True)
    window.store.set('voice:auto_gemini', True)
    window.voice_panel.microphone_muted = False
    for delay in (2000, 4000, 8000):
        window.schedule_live_reconnect()
        assert window.live_reconnect_timer.interval() == delay
        window.schedule_live_reconnect()
        assert window.live_reconnect_timer.interval() == delay
        window.live_reconnect_timer.stop()
    window.schedule_live_reconnect()
    assert not window.live_reconnect_timer.isActive()
    window.on_live_voice_state('listening')
    window.schedule_live_reconnect()
    assert window.live_reconnect_timer.isActive()
    window.set_microphone_muted(True)
    assert not window.live_reconnect_timer.isActive()
    window.schedule_live_reconnect()
    assert not window.live_reconnect_timer.isActive()


def test_spoken_take_control_waits_for_a_task_even_with_project_context(window, monkeypatch):
    def unexpected_launch(*args, **kwargs):
        pytest.fail('Taking control must not start a task or open an app')

    window.memory.remember(project='example', editor='VS Code')
    monkeypatch.setattr(window.mission_controller, 'start', unexpected_launch)
    monkeypatch.setattr(window, 'queue_chat_launch', unexpected_launch)
    monkeypatch.setattr(window, 'handle_developer_command', unexpected_launch)
    monkeypatch.setattr('desktop.app.open_project_in_editor', unexpected_launch)

    window.save_live_voice_turn('Take control', '')

    assert window.desktop_control_active
    assert 'CONTROL ACTIVE' in window.prime_shell.footer_status.text()


def test_news_uses_the_existing_gemini_session_and_not_weather(window, monkeypatch):
    requests, sent = [], []
    monkeypatch.setattr(window, 'start_news_briefing', requests.append)
    button = next(b for b in window.prime_chat.terminal.findChildren(QPushButton)
                  if b.text() == 'News')
    button.click()
    assert requests == [window.news_panel.region.currentData()]
    assert window.news_panel.speech.isChecked()
    assert window.route_interface_command('நியூஸ் சொல்லு')
    assert len(requests) == 2
    monkeypatch.setattr(window, 'live_voice', SimpleNamespace(active=True, send=sent.append))
    assert window.read_news_briefing('Verified headline')
    assert 'Verified headline' in sent[0]['realtimeInput']['text']
    window.policy.stop()
    assert not window.read_news_briefing('Must not speak')
    assert len(sent) == 1
    monkeypatch.setattr(window, 'live_voice', None)


def test_control_grant_is_session_only_and_does_not_approve_send_or_save(window):
    window.set_desktop_control(True)
    def action(label):
        return Action('mission_tool', 'mouse_click_app_control(name=' + label + ')',
                      arguments=json.dumps({'name': label}))
    assert window.desktop_control_allows(action('View'))
    assert not window.desktop_control_allows(action('Send'))
    assert not window.desktop_control_allows(action('Save'))
    assert not window.desktop_control_allows(action(''))
    assert not window.desktop_control_allows(action('Envoyer'))
    assert not window.desktop_control_allows(action('அனுப்பு'))
    assert not window.desktop_control_allows(Action('apply_code', 'new code'))
    window.stop()
    assert not window.desktop_control_allows(action('View'))
    assert not window.desktop_control_active


def test_saved_desktop_control_is_restored_and_emergency_stop_revokes_it(window):
    window.store.set('automation:keep_desktop_control', True)
    reopened = Window(window.root)
    try:
        assert not reopened.desktop_control_active
        reopened.start_window_audio()
        assert reopened.desktop_control_active
        reopened.stop()
        assert not reopened.desktop_control_active
        assert not reopened.store.get('automation:keep_desktop_control')
    finally:
        reopened.close()


def test_settings_are_grouped_and_menu_owns_the_settings_entry(window):
    names = {window.settings_categories.itemText(i) for i in range(window.settings_categories.count())}
    assert {'Mouse & Keyboard', 'Desktop Control', 'JARVIS Self Control', 'Remote Control',
            'Wake & Startup', 'Network & Bluetooth', 'Calls', 'Version & Updates', 'Development'} <= names
    assert window.prime_shell.settings_button.isHidden()
    window.prime_shell.menu_button.click()
    window.prime_shell.menu_settings_button.click()
    assert window.prime_shell.settings_dialog.isVisible()
    assert not window.prime_shell.drawer.isVisible()
    window.open_setting_category('Mouse & Keyboard')
    button = next(x for x in window.settings_scroller.findChildren(QPushButton) if x.text() == 'Test mouse click')
    button.click()
    assert window.mouse_test_count == 1
    window.keyboard_test.setText('தமிழ் Tanglish')
    assert window.keyboard_test.text() == 'தமிழ் Tanglish'
    window.input_choices['keyboard'].setChecked(False)
    assert window.store.get('input:keyboard') is False


def test_disabled_keyboard_prevents_the_native_mission_call():
    registry = build_registry(input_allowed=lambda kind: kind != 'keyboard')
    tool = registry.get('type_app_text')
    with pytest.raises(ToolError, match='disabled'):
        tool.run({'process_id': 1, 'title': 'Example', 'name': 'Editor', 'text': 'தமிழ்'}, lambda: None)


def test_main_alignment_groups_time_weather_and_hides_the_separate_wave(window):
    app = QApplication.instance()
    window.resize(1360, 790)
    app.processEvents()
    chat, shell = window.prime_chat, window.prime_shell
    assert shell.clock_label.parentWidget() is chat.weather_detail.parentWidget()
    assert shell.date_label.parentWidget() is chat.weather_detail.parentWidget()
    assert shell.microphone_waveform.isHidden()
    for widget in (chat.weather_refresh, window.send_button, window.camera_toggle):
        point = widget.mapTo(window, widget.rect().bottomRight())
        assert point.x() < window.width()
        assert point.y() < window.height()


def test_colloquial_settings_command_opens_menu_settings_without_a_provider(window):
    assert window.route_interface_command('உன்ன செட்டிங்ஸ் ஓபன் பண்ண சொன்னேன்')
    assert window.prime_shell.settings_dialog.isVisible()
    window.prime_shell.settings_dialog.close()
    assert not window.route_interface_command('செட்டிங்ஸ் ஓபன் பண்ணாதே')
    assert window.route_interface_command('டேக் கண்ட்ரோல்')
    assert window.desktop_control_active
    window.on_live_heard('ஸ்டாப் கண்ட்ரோல்')
    assert not window.desktop_control_active
