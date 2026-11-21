"""Bounded, approval-gated Windows desktop typing for a known target.

This deliberately does not expose arbitrary model-generated mouse clicks,
PowerShell, shell commands, or unattended keyboard shortcuts. The caller must
obtain explicit owner approval for the exact text before invoking this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import re
import sys
import time

import psutil
from automation import win_controls
from core.conversation import addressed_request

MAX_TEXT = 2000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1
VK_RETURN = 0x0D
VK_TAB = 0x09

# Only a trusted app can receive text. App adapters may be added after they
# have dedicated focus and outcome tests.
TARGETS = {'Notepad': 'notepad.exe'}


class VerifiedEdit(str):
    """The foreground editor returned the expected contents after insertion."""


@dataclass(frozen=True)
class DesktopTask:
    app: str
    text: str
    launch: bool = False


def parse_desktop_task(message: str) -> DesktopTask | None:
    """Recognize an *entire* explicit instruction, never a quoted fragment.

    The strict parser prevents a model, document, or incidental mention from
    silently turning into a desktop action.
    """
    if not isinstance(message, str):
        return None
    cleaned = addressed_request(message)
    patterns = (
        (True, r'open\s+notepad\s+and\s+(?:type|write|enter)\s*:\s*([\s\S]+)'),
        (False, r'(?:type|write|enter)\s+in(?:to)?\s+notepad\s*:\s*([\s\S]+)'),
        (True, r'notepad\s+open\s+panni\s+(?:type|write)\s+pannu\s*:\s*([\s\S]+)'),
    )
    for launch, pattern in patterns:
        match = re.fullmatch(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            text = match.group(1).replace('\r\n', '\n').strip()
            if not text or len(text) > MAX_TEXT or '\x00' in text:
                raise ValueError(f'Provide 1 to {MAX_TEXT} characters of text without NUL.')
            return DesktopTask(app='Notepad', text=text, launch=launch)
    return None


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ('wVk', ctypes.c_uint16),
        ('wScan', ctypes.c_uint16),
        ('dwFlags', ctypes.c_uint32),
        ('time', ctypes.c_uint32),
        ('dwExtraInfo', ctypes.c_size_t),
    )


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ('dx', ctypes.c_int32),
        ('dy', ctypes.c_int32),
        ('mouseData', ctypes.c_uint32),
        ('dwFlags', ctypes.c_uint32),
        ('time', ctypes.c_uint32),
        ('dwExtraInfo', ctypes.c_size_t),
    )


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ('uMsg', ctypes.c_uint32),
        ('wParamL', ctypes.c_uint16),
        ('wParamH', ctypes.c_uint16),
    )


class _INPUT_UNION(ctypes.Union):
    _fields_ = (
        ('ki', _KEYBDINPUT),
        ('mi', _MOUSEINPUT),
        ('hi', _HARDWAREINPUT),
    )


class _INPUT(ctypes.Structure):
    _fields_ = (('type', ctypes.c_uint32), ('data', _INPUT_UNION))


def _require_windows():
    if sys.platform != 'win32':
        raise RuntimeError('Desktop keyboard control is only available on Windows.')


def target_is_foreground(app: str) -> bool:
    """Check the focused window's actual process, not its spoofable title."""
    if app not in TARGETS:
        raise ValueError('Unsupported desktop typing target.')
    _require_windows()
    user32 = ctypes.windll.user32
    # Set explicit pointer-sized Win32 signatures; ctypes defaults to c_int
    # and would truncate HWND on 64-bit Windows.
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    user32.GetWindowThreadProcessId.restype = ctypes.c_uint32
    handle = user32.GetForegroundWindow()
    if not handle:
        return False
    pid = ctypes.c_uint32(0)
    user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
    if not pid.value:
        return False
    try:
        return psutil.Process(pid.value).name().casefold() == TARGETS[app]
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False


def _keyboard_event(character: int, *, key_up: bool, unicode: bool):
    flags = (KEYEVENTF_UNICODE if unicode else 0) | (KEYEVENTF_KEYUP if key_up else 0)
    return _INPUT(INPUT_KEYBOARD, _INPUT_UNION(
        ki=_KEYBDINPUT(0 if unicode else character, character if unicode else 0,
                       flags, 0, 0)))


def _events(text: str) -> list[_INPUT]:
    """Build UTF-16 keyboard events; support Tamil and non-BMP characters."""
    events = []
    for character in text:
        if character in ('\n', '\t'):
            key = VK_RETURN if character == '\n' else VK_TAB
            events.extend((_keyboard_event(key, key_up=False, unicode=False),
                           _keyboard_event(key, key_up=True, unicode=False)))
        else:
            payload = character.encode('utf-16-le')
            for i in range(0, len(payload), 2):
                unit = int.from_bytes(payload[i:i+2], 'little')
                events.extend((_keyboard_event(unit, key_up=False, unicode=True),
                               _keyboard_event(unit, key_up=True, unicode=True)))
    return events


def type_into_target(app: str, text: str) -> str:
    """Send literal keystrokes only when the expected app is foreground.

    A successful SendInput result verifies input dispatch, *not* that an editor
    actually saved or retained the text. Never claim more than was observed.
    """
    if app not in TARGETS:
        raise ValueError('Desktop typing target is not allowed.')
    if not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT or '\x00' in text:
        raise ValueError('Desktop typing content is invalid or too large.')
    if not target_is_foreground(app):
        raise RuntimeError(f'{app} is not the active Windows application. No text was sent.')
    hwnd = win_controls.focused_editor()
    if hwnd is None:
        raise RuntimeError('Click inside the document editor and try again. No text was sent.')
    expected = win_controls.expected_edit(hwnd, text)
    # Do not send while a system shortcut modifier is being held down.
    user32 = ctypes.windll.user32
    for key in (0x10, 0x11, 0x12, 0x5B, 0x5C):
        if user32.GetAsyncKeyState(key) & 0x8000:
            raise RuntimeError('Release Shift/Ctrl/Alt/Windows keys before typing.')
    events = _events(text)
    if not target_is_foreground(app) or win_controls.focused_editor() != hwnd:
        raise RuntimeError('The target window changed. No text was sent.')
    array_type = _INPUT * len(events)
    array = array_type(*events)
    user32.SendInput.argtypes = [ctypes.c_uint32, ctypes.POINTER(_INPUT), ctypes.c_int]
    user32.SendInput.restype = ctypes.c_uint32
    sent = user32.SendInput(len(array), array, ctypes.sizeof(_INPUT))
    if sent != len(array):
        if not sent:
            raise RuntimeError('Windows declined the keyboard input.')
        return f'Windows accepted only {sent}/{len(array)} keyboard events. Review the editor before repeating.'
    if expected is not None:
        deadline = time.monotonic() + 0.25
        while time.monotonic() < deadline and target_is_foreground(app) and win_controls.focused_editor() == hwnd:
            observed = win_controls.contents(hwnd)
            if observed is not None and win_controls.normal_text(observed) == expected:
                return VerifiedEdit(f'Verified {len(text)} inserted characters in {app}. The document is still unsaved or its save status is unknown.')
            time.sleep(0.015)
    return (f'{app} received {len(events)} keyboard events. '
            'Text delivery was requested but content and save status are not verified.')
