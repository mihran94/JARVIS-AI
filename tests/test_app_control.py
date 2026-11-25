from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from automation import app_control
from automation.input import InputRefused
from security.policy import Stopped


def item(name, kind, *, automation_id='', password=False, pid=42):
    return SimpleNamespace(Current=SimpleNamespace(
        Name=name, AutomationId=automation_id, ProcessId=pid, IsEnabled=True,
        IsOffscreen=False, IsPassword=password,
        ControlType=SimpleNamespace(ProgrammaticName=f'ControlType.{kind}'),
    ))


@pytest.fixture
def published(monkeypatch):
    controls = []
    check = Mock()
    pattern = Mock()

    @contextmanager
    def app(pid, title):
        assert (pid, title) == (42, 'Test window')
        yield controls, check

    monkeypatch.setattr(app_control, '_foreground_app', app)
    monkeypatch.setattr(app_control.win_controls, 'foreground_process', lambda: 42)
    monkeypatch.setattr(app_control, '_control_pattern', lambda *_args, **_options: pattern)
    return controls, check, pattern


def test_inspection_excludes_passwords_and_other_processes(published):
    controls, _, _ = published
    controls.extend([item('Draft', 'Edit'), item('Password', 'Edit', password=True),
                     item('Wrong window', 'Button', pid=84)])
    result = app_control.see_controls(42, 'Test window')
    assert 'Draft' in result
    assert 'Password' not in result
    assert 'Wrong window' not in result


def test_click_refuses_ambiguity_and_honours_cancellation(published):
    controls, check, pattern = published
    controls.extend([item('Review', 'Button', automation_id='one'),
                     item('Review', 'Button', automation_id='two')])
    with pytest.raises(InputRefused, match='ambiguous'):
        app_control.use_control(42, 'Test window', 'Review')
    with pytest.raises(Stopped):
        app_control.use_control(42, 'Test window', 'Review', 'one',
                                checkpoint=Mock(side_effect=Stopped('Stopped')))
    pattern.Invoke.assert_not_called()
    assert 'invoked' in app_control.use_control(42, 'Test window', 'Review', 'one')
    check.assert_called()
    pattern.Invoke.assert_called_once_with()


def test_field_edit_checks_the_actual_value(published):
    controls, _, pattern = published
    controls.append(item('Draft', 'Edit'))
    pattern.Current.IsReadOnly = False
    value = 'வணக்கம், ready'
    pattern.Current.Value = value
    assert 'verified' in app_control.use_control(42, 'Test window', 'Draft', text=value)
    pattern.SetValue.assert_called_once_with(value)
    pattern.Current.Value = 'unchanged'
    with pytest.raises(InputRefused, match='did not verify'):
        app_control.use_control(42, 'Test window', 'Draft', text=value)


def test_keyboard_refuses_to_type_into_an_unfocused_field(published, monkeypatch):
    controls, _, _ = published
    field = item('Draft', 'Edit')
    field.Current.HasKeyboardFocus = False
    controls.append(field)
    send = Mock()
    monkeypatch.setattr(app_control.desktop_input, 'type_text', send)
    with pytest.raises(InputRefused, match='Focus the selected field'):
        app_control.keyboard_input(42, 'Test window', 'Draft', text='draft')
    send.assert_not_called()


def test_mouse_refuses_a_covered_control_before_moving(published, monkeypatch):
    controls, _, _ = published
    button = item('Review', 'Button')
    button.GetClickablePoint = lambda: SimpleNamespace(X=30, Y=40)
    controls.append(button)
    monkeypatch.setattr(app_control, '_point_hits', lambda *_: False)
    send = Mock()
    mouse = SimpleNamespace(SetCursorPos=Mock())
    monkeypatch.setattr(app_control.ctypes, 'windll', SimpleNamespace(user32=mouse), raising=False)
    monkeypatch.setattr(app_control.desktop_input, 'click_at', send)
    with pytest.raises(InputRefused, match='covered or has moved'):
        app_control.mouse_click(42, 'Test window', 'Review')
    mouse.SetCursorPos.assert_not_called()
    send.assert_not_called()
