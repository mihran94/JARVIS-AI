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
from automation.input import _INPUT, _keyboard_event, send_input
from core.conversation import addressed_request

MAX_TEXT = 2000
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
    calculation = re.fullmatch(r'open\s+calculator\s+and\s+calculate\s*:\s*([\s\S]*)',
                               cleaned, flags=re.IGNORECASE)
    if calculation:
        from automation.calculator import parse_expression

        expression = ' '.join(parse_expression(calculation.group(1)))
        return DesktopTask(app='Calculator', text=expression, launch=True)
    patterns = (
        (True, r'open\s+notepad\s+and\s+(?:type|write|enter)\s*:\s*([\s\S]+)'),
        (False, r'(?:type|write|enter)\s+in(?:to)?\s+notepad\s*:\s*([\s\S]+)'),
        (True, r'notepad\s+open\s+panni\s+(?:type|write)\s+pannu\s*:\s*([\s\S]+)'),
        (True, r'notepad\s+open\s+(?:panni|பண்ணி)\s+(?:ezhuthu|எழுது|type\s+(?:pannu|பண்ணு))(?:\s*[:,]\s*|\s+)([\s\S]+)'),
        (True, r'(?:நோட்பேட்|நோட்பேடை|notepad)\s+திறந்து\s+எழுது(?:\s*[:,]\s*|\s+)([\s\S]+)'),
        (True, r'ouvre\s+(?:le\s+)?(?:bloc-notes|notepad)\s+et\s+(?:écris|saisis)\s*:\s*([\s\S]+)'),
        (False, r'(?:écris|saisis)\s+dans\s+(?:le\s+)?(?:bloc-notes|notepad)\s*:\s*([\s\S]+)'),
        (False, r'(?:நோட்பேடில்|notepad[ -]?ல்)\s+எழுது\s*:\s*([\s\S]+)'),
    )
    for launch, pattern in patterns:
        match = re.fullmatch(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            text = match.group(1).replace('\r\n', '\n').strip()
            if not text or len(text) > MAX_TEXT or '\x00' in text:
                raise ValueError(f'Provide 1 to {MAX_TEXT} characters of text without NUL.')
            return DesktopTask(app='Notepad', text=text, launch=launch)
    return None


def _require_windows():
    if sys.platform != 'win32':
        raise RuntimeError('Desktop keyboard control is only available on Windows.')


def target_is_foreground(app: str) -> bool:
    """Check the focused window's actual process, not its spoofable title."""
    if app not in TARGETS:
        raise ValueError('Unsupported desktop typing target.')
    _require_windows()
    pid = win_controls.foreground_process()
    if pid is None:
        return False
    try:
        return psutil.Process(pid).name().casefold() == TARGETS[app]
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False


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
    sent = send_input(events)
    if sent != len(events):
        if not sent:
            raise RuntimeError('Windows declined the keyboard input.')
        return f'Windows accepted only {sent}/{len(events)} keyboard events. Review the editor before repeating.'
    if expected is not None:
        deadline = time.monotonic() + 0.25
        while time.monotonic() < deadline and target_is_foreground(app) and win_controls.focused_editor() == hwnd:
            observed = win_controls.contents(hwnd)
            if observed is not None and win_controls.normal_text(observed) == expected:
                return VerifiedEdit(f'Verified {len(text)} inserted characters in {app}. The document is still unsaved or its save status is unknown.')
            time.sleep(0.015)
    return (f'{app} received {len(events)} keyboard events. '
            'Text delivery was requested but content and save status are not verified.')
