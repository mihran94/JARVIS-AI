from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agents.gateway import Gateway
from automation import named_apps
from automation.input import InputRefused
from core.store import Store
from security.policy import Denied, Policy


def test_tanglish_and_literal_field_text():
    assert named_apps.parse('Jarvis, CapCut-la Export click pannu') == named_apps.Request('click', 'CapCut', 'Export')
    assert named_apps.parse('in app Editor, set Name = வணக்கம் ABC').value == 'வணக்கம் ABC'
    assert named_apps.parse('How do I open installed app CapCut?') is None


def test_catalog_launch_is_approved_and_resolved_again(tmp_path, monkeypatch):
    item = SimpleNamespace(Name='Video Editor', Path='test-id', InvokeVerb=Mock())
    catalog = [item]
    monkeypatch.setattr(named_apps, 'installed_items', lambda: catalog)
    gateway = Gateway(Policy(), Store(tmp_path / 'history.db'))
    request = named_apps.parse('installed app Video Editor open pannu')
    with pytest.raises(Denied):
        named_apps.run(request, gateway, lambda _: False, lambda: None)
    item.InvokeVerb.assert_not_called()
    named_apps.run(request, gateway, lambda _: True, lambda: None)
    item.InvokeVerb.assert_called_once()
    def replace(_):
        item.Path = 'replacement'
        return True
    with pytest.raises(InputRefused):
        named_apps.run(request, gateway, replace, lambda: None)
    item.InvokeVerb.assert_called_once()


def test_window_name_requires_one_match_and_checks_process_identity(tmp_path, monkeypatch):
    rows = [dict(pid=42, title='First'), dict(pid=43, title='Second')]
    monkeypatch.setattr(named_apps, 'inspect_windows', lambda: rows)
    monkeypatch.setattr(named_apps.app_control, '_application', lambda pid: 'Editor.exe')
    started = [123]
    monkeypatch.setattr(named_apps.psutil, 'Process', lambda pid: SimpleNamespace(create_time=lambda: started[0]))
    with pytest.raises(InputRefused):
        named_apps.resolve_window('Editor')
    assert named_apps.resolve_window('Second') == (43, 'Second', 123)
    focus = Mock()
    monkeypatch.setattr(named_apps.app_control, 'focus_selected', focus)
    def restart(_):
        started[0] += 1
        return True
    with pytest.raises(InputRefused, match='restarted'):
        named_apps.run(named_apps.Request('click', 'Second', 'Export'),
                       Gateway(Policy(), Store(tmp_path / 'history.db')), restart, lambda: None)
    focus.assert_not_called()


def test_typed_and_spoken_requests_reach_local_catalog(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from desktop.app import Window
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    item = SimpleNamespace(Name='Video Editor', Path='test-id', InvokeVerb=Mock())
    monkeypatch.setattr(named_apps, 'installed_items', lambda: [item])
    monkeypatch.setattr(window, 'confirm', lambda _: True)
    try:
        window.prompt.setPlainText('list installed apps')
        window.send()
        assert window.store.messages(window.session)[-1]['content'] == 'Video Editor'
        window.save_live_voice_turn('Jarvis, installed app Video Editor open pannu', '')
        item.InvokeVerb.assert_called_once()
        assert window.store.tasks()[0]['status'] == 'dispatched'
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_selected_app_followups_verify_original_handle(tmp_path, monkeypatch):
    gateway = Gateway(Policy(), Store(tmp_path / 'history.db'))
    current = [41]
    monkeypatch.setattr(named_apps, 'resolve_window', lambda _: (7, 'My edit', 123))
    monkeypatch.setattr(named_apps.psutil, 'Process', lambda _: SimpleNamespace(create_time=lambda: 123))
    monkeypatch.setattr(named_apps.app_control, 'focus_selected', lambda *_: None)
    monkeypatch.setattr(named_apps.app_control.win_controls, 'foreground_window', lambda: current[0])
    monkeypatch.setattr(named_apps.app_control, 'see_controls', lambda *_: "Button 'Export'")
    invoke = Mock(return_value='Windows invoked Export')
    monkeypatch.setattr(named_apps.app_control, 'use_control', invoke)
    target, detail = named_apps.select('CapCut', gateway, lambda _: True, lambda: None)
    assert target == named_apps.SelectedWindow(7, 'My edit', 123, 41)
    assert 'Export' in detail
    assert named_apps.parse('Export click pannu') is None
    request = named_apps.parse('Export click pannu', has_selection=True)
    named_apps.run(request, gateway, lambda _: True, lambda: None, selected=target)
    assert invoke.call_args.args[:3] == (7, 'My edit', 'Export')
    current[0] = 42
    with pytest.raises(InputRefused, match='window changed'):
        named_apps.run(request, gateway, lambda _: True, lambda: None, selected=target)
    assert invoke.call_count == 1


def test_selected_app_survives_voice_turn_and_releases_on_stop(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from desktop.app import Window
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    target = named_apps.SelectedWindow(7, 'My edit', 123, 41)
    monkeypatch.setattr(named_apps, 'select', lambda *args: (target, 'Selected My edit'))
    run = Mock(return_value='Field verified')
    monkeypatch.setattr(named_apps, 'run', run)
    try:
        window.prompt.setPlainText('CapCut app select pannu')
        window.send()
        window.save_live_voice_turn('set Project name = KAAVALAN AI', '')
        assert run.call_args.kwargs['selected'] == target
        assert run.call_args.args[0].value == 'KAAVALAN AI'
        window.stop()
        assert window.selected_app_window is None
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_physical_mouse_and_keyboard_commands_bind_selected_window(tmp_path, monkeypatch):
    selected = named_apps.SelectedWindow(7, 'My edit', 123, 41)
    monkeypatch.setattr(named_apps.psutil, 'Process', lambda _: SimpleNamespace(create_time=lambda: 123))
    monkeypatch.setattr(named_apps.app_control, 'focus_selected', lambda *_: None)
    foreground = [41]
    monkeypatch.setattr(named_apps.app_control.win_controls, 'foreground_window', lambda: foreground[0])
    mouse = Mock(return_value='Clicked')
    keyboard = Mock(return_value='Typed')
    monkeypatch.setattr(named_apps.app_control, 'mouse_click', mouse)
    monkeypatch.setattr(named_apps.app_control, 'keyboard_input', keyboard)
    gateway = Gateway(Policy(), Store(tmp_path / 'history.db'))

    assert named_apps.parse('Notepad app open pannu').app == 'Notepad'
    assert named_apps.parse('mouse click Editor') is None
    assert named_apps.parse('in app Notepad, keyboard press tab in Editor').value == 'tab'
    for command in ('mouse click Editor', 'keyboard type in Editor = வணக்கம்'):
        request = named_apps.parse(command, has_selection=True)
        named_apps.run(request, gateway, lambda _: True, lambda: None, selected=selected)
    assert mouse.call_args.args[:3] == (7, 'My edit', 'Editor')
    assert keyboard.call_args.kwargs['text'] == 'வணக்கம்'
    foreground[0] = 42
    with pytest.raises(InputRefused, match='window changed'):
        named_apps.run(request, gateway, lambda _: True, lambda: None, selected=selected)
    assert keyboard.call_count == 1


@pytest.mark.parametrize(('command', 'control'), [
    ('Hey Jarvis, Play pannu.', 'Play'),
    ('டைம்லைன் ஓபன் பண்ணு', 'Timeline'),
    ('split at playhead', 'Split'),
])
def test_short_editor_commands_require_an_app_context(command, control):
    assert named_apps.parse(command) is None
    assert named_apps.parse(command, has_selection=True) == named_apps.Request(
        'mouse_click', control=control)


def test_clip_selection_requires_a_named_control():
    assert named_apps.parse('Select Clip 3', has_selection=True) == named_apps.Request(
        'select_control', control='Clip 3')
    assert named_apps.parse('select this', has_selection=True) is None


@pytest.mark.parametrize(('command', 'verb', 'selecting', 'status'), [
    ('Jarvis, இதை செலக்ட் பண்ணு', 'select_control', True, 'verified'),
    ('itha select pannu', 'select_control', True, 'verified'),
    ('click here', 'mouse_click', False, 'dispatched'),
])
def test_pointed_voice_command_keeps_original_target(tmp_path, monkeypatch, command, verb, selecting, status):
    from PySide6.QtWidgets import QApplication
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    target = named_apps.SelectedWindow(7, 'My edit', 123, 41)
    window.selected_app_window = target
    monkeypatch.setattr(named_apps.psutil, 'Process', lambda _: SimpleNamespace(create_time=lambda: 123))
    monkeypatch.setattr(named_apps.app_control, 'focus_selected', lambda *_: None)
    monkeypatch.setattr(named_apps.app_control.win_controls, 'foreground_window', lambda: 41)
    capture = Mock(return_value=('Clip A', '', (2, 9)))
    monkeypatch.setattr(named_apps.app_control, 'pointed_control', capture)
    action = Mock(return_value='Windows response')
    monkeypatch.setattr(named_apps.app_control, verb, action)

    def approve(proposal):
        assert 'Clip A' in proposal.target
        capture.return_value = ('Clip B', '', (2, 10))
        return True

    monkeypatch.setattr(window, 'confirm', approve)
    try:
        window.save_live_voice_turn(command, '')
        capture.assert_called_once_with(7, 'My edit', selecting=selecting)
        assert action.call_args.args == (7, 'My edit', 'Clip A', '')
        assert action.call_args.kwargs['runtime_id'] == (2, 9)
        assert window.store.tasks()[0]['status'] == status
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_selected_window_drag_shows_both_targets_and_requires_approval(tmp_path, monkeypatch):
    store = Store(tmp_path / 'history.db')
    gateway = Gateway(Policy(), store)
    current = named_apps.SelectedWindow(7, 'My edit', 123, 41)
    monkeypatch.setattr(named_apps.psutil, 'Process', lambda _: SimpleNamespace(create_time=lambda: 123))
    monkeypatch.setattr(named_apps.app_control, 'focus_selected', lambda *_: None)
    monkeypatch.setattr(named_apps.app_control.win_controls, 'foreground_window', lambda: 41)
    drag = Mock(return_value='Verified')
    monkeypatch.setattr(named_apps.app_control, 'drag_control', drag)
    request = named_apps.parse('Clip A to Project bin drag pannu', has_selection=True)
    assert named_apps.parse('drag Clip A into Project bin', has_selection=True) == request
    assert named_apps.parse('Clip A-ஐ Project bin-க்கு டிராக் பண்ணு', has_selection=True) == request

    def approve(action, answer):
        assert action.target.endswith('Clip A → Project bin')
        return answer

    with pytest.raises(Denied):
        named_apps.run(request, gateway, lambda a: approve(a, False), lambda: None, selected=current)
    drag.assert_not_called()
    named_apps.run(request, gateway, lambda a: approve(a, True), lambda: None, selected=current)
    assert drag.call_args.args == (7, 'My edit', 'Clip A', '')
    assert drag.call_args.kwargs['destination'] == 'Project bin'
    assert store.tasks()[0]['status'] == 'verified'
