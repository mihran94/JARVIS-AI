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
