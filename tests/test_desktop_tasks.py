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


def test_calculator_chat_command_requires_approval_and_foreground(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    actions = []
    target = object()
    monkeypatch.setattr('desktop.app.launch_app', lambda name: actions.append(name))
    monkeypatch.setattr('automation.calculator.foreground_calculator', lambda: None)

    def calculate(expression, window_target, *, check):
        check()
        assert window_target is target
        actions.append(expression)
        return '888'

    monkeypatch.setattr('automation.calculator.calculate_in_window', calculate)
    monkeypatch.setattr(window, 'send_chat_reply', lambda *_args, **_kwargs: pytest.fail(
        'The local calculation must stay on the PC'))
    try:
        command = 'Open Calculator and calculate: 37 × 24'
        window.prompt.setPlainText(command)
        window.send()
        assert '37 * 24' in window.chat_approval_label.text()
        assert actions == []
        window.finish_chat_launch(False)
        assert actions == []

        window.prompt.setPlainText(command)
        window.send()
        window.finish_chat_launch(True)
        window.complete_desktop_task()
        assert actions == ['Calculator']
        monkeypatch.setattr('automation.calculator.foreground_calculator', lambda: target)
        window.complete_desktop_task()
        assert actions == ['Calculator', '37 * 24']
        assert window.desktop_result_label.text() == 'Calculator display verified: 37 * 24 = 888'
        assert window.store.tasks()[0]['status'] == 'verified'
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


@pytest.mark.parametrize('expression', ['37 * 24 and open Notepad', '1 / 3', '1 * 1234567'])
def test_calculator_rejects_inputs_outside_the_arithmetic_grammar(expression):
    with pytest.raises(ValueError, match='two integers'):
        parse_desktop_task('Open Calculator and calculate: ' + expression)


def test_windows_sendinput_structure_and_mock_dispatch(monkeypatch):
    """The 32/64-bit INPUT struct must match Win32, even on Linux CI."""
    import ctypes
    from types import SimpleNamespace
    import automation.desktop_tasks as desktop_tasks
    import automation.input as input_backend

    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(desktop_tasks._INPUT) == expected

    class FakeSendInput:
        def __init__(self):
            self.calls = []

        def __call__(self, count, events, stride):
            self.calls.append((count, stride))
            return count

    class FakeUser32:
        def __init__(self):
            self.SendInput = FakeSendInput()

        def GetAsyncKeyState(self, _key):
            return 0

    api = FakeUser32()
    # Run the real dispatch code against the fake Win32 API on either OS.
    monkeypatch.setattr(input_backend, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(desktop_tasks.ctypes, 'windll',
                        SimpleNamespace(user32=api), raising=False)
    monkeypatch.setattr(desktop_tasks, 'target_is_foreground',
                        lambda app: app == 'Notepad')
    monkeypatch.setattr(desktop_tasks.win_controls, 'focused_editor', lambda: 42)
    monkeypatch.setattr(desktop_tasks.win_controls, 'expected_edit', lambda *_: None)
    result = desktop_tasks.type_into_target('Notepad', 'வணக்கம்')
    assert api.SendInput.calls
    assert api.SendInput.calls[0][1] == expected
    assert 'not verified' in result


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
        assert window.store.tasks()[0]['status'] == 'unverified'
    finally:
        window.close()
        window.deleteLater()
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
        window.deleteLater()
        app.processEvents()
def test_capcut_shortcut_uses_one_native_keyboard_batch(monkeypatch):
    from automation import input as windows_input

    batches = []

    def send(events):
        batches.append(events)
        return len(events)

    monkeypatch.setattr(windows_input, 'send_input', send)
    windows_input.press_key('ctrl+e', windows_input.InputTarget(1), foreground=lambda: 1)
    assert len(batches) == 1
    assert [(event.data.ki.wVk, event.data.ki.dwFlags) for event in batches[0]] == [
        (0x11, 0), (0x45, 0), (0x45, 2), (0x11, 2),
    ]
