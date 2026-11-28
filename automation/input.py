"""Validated input on this Windows computer.

WHAT THIS IS
    The actions that put a key, a click or a scroll into a window, and
    the rule that goes with them: **before every action that depends on
    the focus, the intended window and process are checked again.**

    If the focus moved, the action stops. If the target is ambiguous,
    the action stops. If a dialog appeared that the owner did not
    expect, the action stops. A stop is always a refusal, never a
    guess and never a click through something unexpected.

WHAT THIS IS NOT
    * It is not an arbitrary input layer. The keys are a fixed list,
      the text is bounded, and a click is a position inside a window
      that was named.
    * It is not unattended. Every one of these actions runs inside an
      owner-approved operation.
    * It does not run on anything but Windows.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import sys
import time

#: The largest amount of text one action may type.
MAX_TEXT = 2000

#: How long a click or a key press waits for the window to settle.
SETTLE_SECONDS = 0.05
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1

#: The keys that may be pressed. A key that is not here cannot be
#: pressed, so model text cannot ask for an arbitrary key.
KEY_ALLOWLIST = {
    'enter': 0x0D, 'tab': 0x09, 'escape': 0x1B, 'backspace': 0x08,
    'delete': 0x2E, 'space': 0x20, 'up': 0x26, 'down': 0x28,
    'left': 0x25, 'right': 0x27, 'home': 0x24, 'end': 0x23,
    'pageup': 0x21, 'pagedown': 0x22, 'ctrl+a': 0x41, 'ctrl+c': 0x43,
    'ctrl+v': 0x56, 'ctrl+x': 0x58, 'ctrl+s': 0x53, 'ctrl+z': 0x5A,
    'ctrl+y': 0x59, 'ctrl+e': 0x45, 'ctrl+i': 0x49, 'alt+d': 0x44, 'alt+tab': 0x09,
}

#: The modifiers that may be held with a key.
MODIFIERS = {'ctrl': 0x11, 'alt': 0x12, 'shift': 0x10, 'win': 0x5B}


class InputRefused(RuntimeError):
    """The action was refused before anything was sent."""


class FocusLost(InputRefused):
    """The focus is no longer on the window the action was meant for."""


class AmbiguousTarget(InputRefused):
    """More than one window matches, so the target is not clear."""


class UnexpectedDialog(InputRefused):
    """A dialog appeared that the owner did not expect."""


@dataclass(frozen=True)
class InputTarget:
    """The window an action is meant for.

    The process is what is checked. The title is what the owner named,
    and it is how a wrong window is reported rather than guessed at.
    """

    process_id: int
    title: str = ''

    def describe(self) -> str:
        return self.title or f'process {self.process_id}'


def validate_focus(target: InputTarget, *, foreground=None, dialogs=None) -> None:
    """Check that the action may go ahead.

    `foreground` is the function that reports the process in front, and
    `dialogs` is the function that reports the dialogs that are open.
    Both can be replaced, so the rule itself can be tested without
    Windows.
    """
    if foreground is None:
        from automation.win_controls import foreground_process
        foreground = foreground_process
    current = foreground()
    if not current:
        raise FocusLost('No window is in front, so nothing was sent.')
    if current != target.process_id:
        raise FocusLost(
            f'The window in front is process {current}, not {target.process_id}. '
            'Nothing was sent, because the focus moved.')
    if dialogs is not None:
        from automation.uia import unexpected_dialogs

        found = unexpected_dialogs(dialogs(), expected_titles=(target.title,))
        if found:
            names = ', '.join(element.name or element.control_type for element in found[:3])
            raise UnexpectedDialog(
                f'A dialog is in the way ({names}), so nothing was sent. '
                'Answer it first, or cancel this action.')


def _windows_only():
    if sys.platform != 'win32':
        raise InputRefused('This action is available on Windows only.')


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


def _keyboard_event(character: int, *, key_up: bool, unicode: bool):
    flags = (KEYEVENTF_UNICODE if unicode else 0) | (KEYEVENTF_KEYUP if key_up else 0)
    return _INPUT(INPUT_KEYBOARD, _INPUT_UNION(
        ki=_KEYBDINPUT(0 if unicode else character, character if unicode else 0,
                       flags, 0, 0)))


def send_input(events: list[_INPUT]) -> int:
    """Dispatch a batch of native Windows input events."""
    _windows_only()
    api = ctypes.windll.user32.SendInput
    api.argtypes = [ctypes.c_uint32, ctypes.POINTER(_INPUT), ctypes.c_int]
    api.restype = ctypes.c_uint32
    array = (_INPUT * len(events))(*events)
    return api(len(array), array, ctypes.sizeof(_INPUT))


def _send_keyboard(events):
    if send_input(events) != len(events):
        raise InputRefused('Windows did not accept all keyboard input.')


def _send_unicode(text: str):
    encoded = text.encode('utf-16-le')
    events = []
    for index in range(0, len(encoded), 2):
        unit = int.from_bytes(encoded[index:index + 2], 'little')
        events.extend((_keyboard_event(unit, key_up=False, unicode=True),
                       _keyboard_event(unit, key_up=True, unicode=True)))
    _send_keyboard(events)


def _press_virtual(vk: int, ctrl: bool = False, alt: bool = False, shift: bool = False):
    """Press one key with its modifiers in one native input batch."""
    modifiers = [key for key, held in ((0x11, ctrl), (0x12, alt), (0x10, shift)) if held]
    events = [_keyboard_event(key, key_up=False, unicode=False) for key in (*modifiers, vk)]
    events.extend(_keyboard_event(key, key_up=True, unicode=False)
                  for key in (vk, *reversed(modifiers)))
    _send_keyboard(events)


def type_text(text: str, target: InputTarget, *, foreground=None, dialogs=None) -> str:
    """Type text into the window, after checking the focus again."""
    if not isinstance(text, str) or not text:
        raise InputRefused('There is no text to type.')
    if len(text) > MAX_TEXT:
        raise InputRefused(f'That is more than {MAX_TEXT} characters.')
    validate_focus(target, foreground=foreground, dialogs=dialogs)
    _send_unicode(text)
    time.sleep(SETTLE_SECONDS)
    return f'{len(text)} characters were typed into {target.describe()}.'


def press_key(name: str, target: InputTarget, *, foreground=None, dialogs=None) -> str:
    """Press one of the allowed keys, after checking the focus again."""
    key = (name or '').strip().casefold()
    if key not in KEY_ALLOWLIST:
        raise InputRefused(f'The key {name!r} is not one JARVIS may press.')
    validate_focus(target, foreground=foreground, dialogs=dialogs)
    parts = key.split('+')
    vk = KEY_ALLOWLIST[key]
    _press_virtual(vk, ctrl='ctrl' in parts, alt='alt' in parts, shift='shift' in parts)
    time.sleep(SETTLE_SECONDS)
    return f'{name} was pressed in {target.describe()}.'


def click_at(x: int, y: int, target: InputTarget, *, foreground=None, dialogs=None) -> str:
    """Click at the already-positioned cursor after checking the caller's target."""
    if not isinstance(x, int) or not isinstance(y, int):
        raise InputRefused('The click needs a whole position.')
    if not (0 <= x <= 10000 and 0 <= y <= 10000):
        raise InputRefused('That click is outside the screen.')
    validate_focus(target, foreground=foreground, dialogs=dialogs)
    down = _INPUT(0, _INPUT_UNION(mi=_MOUSEINPUT(0, 0, 0, 0x0002, 0, 0)))
    up = _INPUT(0, _INPUT_UNION(mi=_MOUSEINPUT(0, 0, 0, 0x0004, 0, 0)))
    sent = send_input([down, up])
    if sent != 2:
        if sent == 1:
            send_input([up])
        raise InputRefused('Windows did not accept the complete mouse click.')
    time.sleep(SETTLE_SECONDS)
    return f'The click was sent to {target.describe()} at {x}, {y}.'


def scroll(amount: int, target: InputTarget, *, foreground=None, dialogs=None) -> str:
    """Scroll the validated foreground window and check Windows accepted it.

    A successful request means Windows accepted the input event; it does not
    prove the application actually scrolled. Inspect the window to verify.
    """
    if not isinstance(amount, int) or isinstance(amount, bool) or not (-50 <= amount <= 50):
        raise InputRefused('The scroll must be between 50 steps up and 50 steps down.')
    if amount == 0:
        raise InputRefused('Choose a nonzero scroll amount.')
    validate_focus(target, foreground=foreground, dialogs=dialogs)
    wheel_delta = ctypes.c_uint32(amount * 120).value
    event = _INPUT(0, _INPUT_UNION(
        mi=_MOUSEINPUT(0, 0, wheel_delta, 0x0800, 0, 0)))
    if send_input([event]) != 1:
        raise InputRefused('Windows did not accept the mouse scroll.')
    time.sleep(SETTLE_SECONDS)
    return (f'Windows accepted {amount} scroll steps for {target.describe()}. '
            'Inspect the window to verify its position.')


def activate_window(process_id: int, *, foreground=None, title=None) -> str:
    """Bring a window forward, by the process it belongs to.

    This is the one action that does not need the focus to be already
    on the target, because bringing a window forward is what puts the
    focus there. It is still bounded: the process has to be one that is
    running now.
    """
    if not isinstance(process_id, int) or process_id <= 0:
        raise InputRefused('Which application should come forward?')
    _windows_only()
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    found = []
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == process_id and user32.IsWindowVisible(hwnd):
            if title is not None:
                label = ctypes.create_unicode_buffer(32768)
                user32.GetWindowTextW(hwnd, label, len(label))
                if label.value != title:
                    return True
            found.append(hwnd)
        return True

    user32.EnumWindows(collect, 0)
    if not found:
        raise InputRefused('That application is not running with a visible window.')
    if len(found) > 1:
        raise AmbiguousTarget(
            f'That application has {len(found)} windows, so JARVIS cannot tell '
            'which one to bring forward. Close the extra one and try again.')
    user32.ShowWindow(found[0], 9)  # SW_RESTORE
    user32.SetForegroundWindow(found[0])
    time.sleep(SETTLE_SECONDS)
    return f'Process {process_id} was brought forward.'


__all__ = ['AmbiguousTarget', 'FocusLost', 'InputRefused', 'InputTarget',
           'KEY_ALLOWLIST', 'MAX_TEXT', 'UnexpectedDialog', 'activate_window',
           'click_at', 'press_key', 'scroll', 'type_text', 'validate_focus']
