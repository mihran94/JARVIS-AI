"""Approval-gated desktop tasks: strict parsing, Unicode and stop semantics."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication
from automation.desktop_tasks import DesktopTask, _events, parse_desktop_task, type_into_target
from desktop.app import Window


def test_parser_accepts_explicit_notepad_typing_and_unicode():
    task = parse_desktop_task('Open Notepad and type: வணக்கம் 🌍')
    assert task == DesktopTask('Notepad', 'வணக்கம் 🌍', True)
    assert parse_desktop_task('Type into Notepad: Bonjour') == DesktopTask(
        'Notepad', 'Bonjour', False)
    assert parse_desktop_task('notepad open panni type pannu: Hello') == DesktopTask(
        'Notepad', 'Hello', True)
    assert parse_desktop_task('How do I open Notepad and type?') is None
    assert parse_desktop_task('open notepad and type: hi; run powershell') is not None
    # This is only literal text in Notepad, never a shell command.
    assert parse_desktop_task('open calculator and type: hello') is None
    assert parse_desktop_task('open notepad and delete files') is None
    assert parse_desktop_task(None) is None
    with pytest.raises(ValueError):
        parse_desktop_task('Open Notepad and type: ' + 'x' * 2001)


def test_tamil_emoji_and_newline_make_complete_keyboard_pairs():
    events = _events('அ🙂\n')
    assert len(events) == 8  # Tamil UTF16: 1; emoji: 2; newline: 1
    assert all(events[i].data.ki.dwFlags & 0x0002 == 0 for i in range(0, 8, 2))
    assert all(events[i].data.ki.dwFlags & 0x0002 for i in range(1, 8, 2))


def test_wrong_foreground_never_receives_text(monkeypatch):
    monkeypatch.setattr('automation.desktop_tasks.target_is_foreground', lambda name: False)
    with pytest.raises(RuntimeError, match='not the active'):
        type_into_target('Notepad', 'important text')


def test_chat_executes_previewed_task_only_after_approval(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    typed = []
    launches = []
    monkeypatch.setattr('desktop.app.launch_app', lambda app: launches.append(app))
    monkeypatch.setattr('desktop.app.target_is_foreground', lambda app: True)
    monkeypatch.setattr('desktop.app.type_into_target',
                        lambda app, text: typed.append((app, text)) or 'Input dispatched, not verified')
    try:
        window.prompt.setPlainText('open notepad and type: Hello from JARVIS')
        window.send()
        assert typed == [] and launches == []
        assert window.chat_launch is not None
        assert window.chat_approval.isHidden() is False
        window.finish_chat_launch(False)
        assert typed == [] and launches == []
        window.prompt.setPlainText('open notepad and type: Bonjour')
        window.send()
        window.finish_chat_launch(True)
        assert launches == ['Notepad'] and typed == []
        assert window.desktop_pending is not None
        window.complete_desktop_task()
        assert typed == [('Notepad', 'Bonjour')]
        assert window.desktop_pending is None
        assert window.store.tasks()[0]['status'] == 'completed'
    finally:
        window.close()
        app.processEvents()


def test_emergency_stop_cancels_pending_type_action(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    typed = []
    monkeypatch.setattr('desktop.app.target_is_foreground', lambda app: True)
    monkeypatch.setattr('desktop.app.type_into_target', lambda app, text: typed.append(text))
    try:
        window.prompt.setPlainText('type in notepad: Do not type after STOP')
        window.send()
        window.finish_chat_launch(True)
        assert window.desktop_pending is not None
        window.stop()
        window.complete_desktop_task()
        assert window.desktop_pending is None
        assert typed == []
        window.resume()
        assert typed == []
    finally:
        window.close()
        app.processEvents()
