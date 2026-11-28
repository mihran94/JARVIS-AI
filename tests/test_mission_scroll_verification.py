"""Mouse-wheel regression tests without sending native input to Windows."""
import ctypes

import pytest

from automation import input as desktop_input
from automation.input import FocusLost, InputRefused, InputTarget


def test_scroll_requires_verified_foreground_before_sending(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_input, 'send_input', lambda events: called.append(events) or 1)
    with pytest.raises(FocusLost):
        desktop_input.scroll(2, InputTarget(42, 'Editor'), foreground=lambda: 99)
    assert called == []


@pytest.mark.parametrize('amount', [-51, 51, True, 0, '5'])
def test_scroll_rejects_invalid_or_noop_amounts(monkeypatch, amount):
    called = []
    monkeypatch.setattr(desktop_input, 'send_input', lambda events: called.append(events) or 1)
    with pytest.raises(InputRefused):
        desktop_input.scroll(amount, InputTarget(42, 'Editor'), foreground=lambda: 42)
    assert called == []


def test_scroll_reports_unaccepted_native_event(monkeypatch):
    monkeypatch.setattr(desktop_input, 'send_input', lambda events: 0)
    with pytest.raises(InputRefused, match='did not accept'):
        desktop_input.scroll(1, InputTarget(42, 'Editor'), foreground=lambda: 42)


@pytest.mark.parametrize('amount', [3, -2])
def test_scroll_dispatches_one_signed_wheel_event(monkeypatch, amount):
    captured = []
    monkeypatch.setattr(desktop_input, 'send_input',
                        lambda events: captured.extend(events) or len(events))
    monkeypatch.setattr(desktop_input.time, 'sleep', lambda seconds: None)
    answer = desktop_input.scroll(
        amount, InputTarget(42, 'Editor'), foreground=lambda: 42)
    assert len(captured) == 1
    assert captured[0].type == 0
    assert captured[0].data.mi.dwFlags == 0x0800
    assert captured[0].data.mi.mouseData == ctypes.c_uint32(amount * 120).value
    assert 'Inspect the window' in answer
