"""Session control grants and the grouped settings use the real controls."""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

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
    assert window.route_interface_command('stop control')
    assert not window.desktop_control_active
    assert cancelled


def test_control_grant_is_session_only_and_does_not_approve_send_or_save(window):
    window.set_desktop_control(True)
    def action(label):
        return Action('mission_tool', 'mouse_click_app_control(name=' + label + ')',
                      arguments=json.dumps({'name': label}))
    assert window.desktop_control_allows(action('View'))
    assert not window.desktop_control_allows(action('Send'))
    assert not window.desktop_control_allows(action('Save'))
    assert not window.desktop_control_allows(Action('apply_code', 'new code'))
    window.stop()
    assert not window.desktop_control_allows(action('View'))
    assert not window.desktop_control_active


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
