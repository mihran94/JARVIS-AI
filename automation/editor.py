"""Saving a document that is open in a Windows editor.

WHAT THIS IS
    Notepad and the other editors can be told to save. This does that,
    with three checks around it:

    * the window that is in front is the one the owner named, checked
      again immediately before the key is sent;
    * the save is given a moment to finish, and a **Save As** dialog
      that appeared instead is reported rather than clicked through;
    * the file on the disk is read back and compared with what the
      editor shows, so "saved" means the bytes are really there.

WHAT THIS IS NOT
    * It does not type a path into a dialog. A file that has never been
      saved needs the owner to say where it goes.
    * It does not report a save it did not see. If the file cannot be
      read back with the expected contents, the answer says so.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time

import psutil

from automation.input import (
    FocusLost, InputRefused, InputTarget, UnexpectedDialog, activate_window, click_at, press_key,
    validate_focus,
)
from automation import win_controls
from automation.win_controls import contents as editor_contents, focused_editor

#: How long the save is given to finish, in seconds.
SAVE_TIMEOUT = 12


@dataclass
class SaveResult:
    """What the save actually did."""

    saved: bool = False
    path: str = ''
    message: str = ''
    verified: bool = False

    def as_dict(self) -> dict:
        return {'saved': self.saved, 'path': self.path, 'message': self.message,
                'verified': self.verified}


def verify_file(path, expected: str = '') -> tuple:
    """Whether the file on the disk holds what the editor shows.

    The comparison ignores the line endings, because Windows writes
    CRLF and the editor shows LF.
    """
    source = Path(path)
    if not source.is_file():
        return False, f'The file {source.name} is not there.'
    try:
        written = source.read_text('utf-8', errors='replace')
    except OSError as error:
        return False, f'The file could not be read back: {error}'
    if not expected:
        return True, f'{source.name} was written ({len(written):,} characters).'
    if written.replace('\r\n', '\n') == expected.replace('\r\n', '\n'):
        return True, f'{source.name} was written and read back unchanged.'
    return False, (f'{source.name} was written, but what is in the file is not what the '
                   'editor showed.')


def save_open_document(target, *, path=None, timeout: int = SAVE_TIMEOUT,
                        foreground=None, dialogs=None) -> SaveResult:
    """Save the document in the window the owner named.

    `path` is the file the editor has open. When it is not given, the
    save is still sent, but nothing can be verified afterwards.
    """
    if foreground is None:
        def foreground():
            from automation.win_controls import foreground_process

            return foreground_process()

    try:
        validate_focus(target, foreground=foreground, dialogs=dialogs)
    except FocusLost as error:
        return SaveResult(message=str(error))
    except UnexpectedDialog as error:
        return SaveResult(message=str(error))
    except InputRefused as error:
        return SaveResult(message=str(error))

    try:
        press_key('ctrl+s', target, foreground=foreground, dialogs=dialogs)
    except InputRefused as error:
        return SaveResult(message=str(error))

    if path is None:
        return SaveResult(saved=True,
                          message='The save was sent. No file was named, so it could not '
                                  'be read back.')

    # What the editor is showing is what the file has to hold.
    expected = ''
    try:
        expected = editor_text()
    except Exception:
        expected = ''

    deadline = time.monotonic() + max(1, int(timeout))
    while time.monotonic() < deadline:
        verified, message = verify_file(path, expected)
        if verified:
            return SaveResult(saved=True, path=str(path), message=message, verified=True)
        time.sleep(0.2)
    verified, message = verify_file(path, expected)
    return SaveResult(saved=verified, path=str(path), message=message, verified=verified)


def editor_text() -> str:
    """What the editor that is in front is showing."""
    handle = focused_editor()
    if handle is None:
        return ''
    return editor_contents(handle) or ''


def save_notepad_with_mouse(path, checkpoint):
    """Click File and Save in the one Notepad window matching an existing file."""
    from automation.inspection import inspect_windows

    if sys.platform != 'win32':
        raise InputRefused('Mouse Save is available in Windows Notepad.')
    source = Path(path)
    if not source.is_absolute() or not source.is_file() or source.is_symlink():
        raise InputRefused('Choose an existing local file open in Notepad.')
    titles = {f'{label} - Notepad' for label in
              (source.name, source.stem, '*' + source.name, '*' + source.stem)}
    windows = [row for row in inspect_windows() if row['title'] in titles]
    if len(windows) != 1:
        raise InputRefused('Open exactly one Notepad window with the named file.')
    pid = windows[0]['pid']
    process = psutil.Process(pid)
    if process.name().casefold() != 'notepad.exe':
        raise InputRefused('The window did not belong to Windows Notepad.')
    if not any(Path(arg).is_absolute() and Path(arg).resolve() == source.resolve()
               for arg in process.cmdline()[1:]):
        raise InputRefused('Open the named file directly in Notepad so its full path can be verified.')
    checkpoint()
    activate_window(pid)
    hwnd = win_controls.foreground_window()
    if not hwnd or win_controls.window_process(hwnd) != pid:
        raise InputRefused('Windows did not bring the named Notepad window forward.')

    user = ctypes.WinDLL('user32', use_last_error=True)
    hmenu = wintypes.HMENU
    signatures = {
        'GetWindowTextW': ([wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
        'GetMenu': ([wintypes.HWND], hmenu),
        'GetSubMenu': ([hmenu, ctypes.c_int], hmenu),
        'GetMenuItemCount': ([hmenu], ctypes.c_int),
        'GetMenuStringW': ([hmenu, wintypes.UINT, wintypes.LPWSTR, ctypes.c_int, wintypes.UINT], ctypes.c_int),
        'GetMenuItemRect': ([wintypes.HWND, hmenu, wintypes.UINT, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
        'SetCursorPos': ([ctypes.c_int, ctypes.c_int], wintypes.BOOL),
        'GetCursorPos': ([ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
        'WindowFromPoint': ([wintypes.POINT], wintypes.HWND),
    }
    for name, (args, result) in signatures.items():
        function = getattr(user, name)
        function.argtypes, function.restype = args, result

    def guard():
        checkpoint()
        title = ctypes.create_unicode_buffer(260)
        user.GetWindowTextW(hwnd, title, len(title))
        if win_controls.foreground_window() != hwnd or title.value not in titles:
            raise InputRefused('The named Notepad window lost focus. No further input was sent.')
        return pid

    def item_at(menu, label):
        matches = []
        for index in range(user.GetMenuItemCount(menu)):
            text = ctypes.create_unicode_buffer(128)
            user.GetMenuStringW(menu, index, text, len(text), 0x0400)  # MF_BYPOSITION
            if text.value.partition('\t')[0].replace('&', '').casefold() == label:
                matches.append(index)
        if len(matches) != 1:
            raise InputRefused(f'Notepad did not expose one {label.title()} menu item.')
        return matches[0]

    def click_item(owner, menu, index):
        guard()
        rect = wintypes.RECT()
        if not user.GetMenuItemRect(owner, menu, index, ctypes.byref(rect)):
            raise InputRefused('Notepad did not expose the menu item location.')
        x, y = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
        if not user.SetCursorPos(x, y):
            raise InputRefused('Windows could not move the mouse to the menu item.')

        def checked_point():
            guard()
            cursor = wintypes.POINT()
            hit = user.WindowFromPoint(wintypes.POINT(x, y))
            if (not user.GetCursorPos(ctypes.byref(cursor)) or (cursor.x, cursor.y) != (x, y)
                    or not hit or win_controls.window_process(hit) != pid):
                raise InputRefused('The Notepad menu is covered or the pointer moved.')
            return pid

        click_at(x, y, InputTarget(pid), foreground=checked_point)

    guard()
    expected = editor_text()
    if not expected:
        raise InputRefused('The current Notepad text could not be read for verification.')
    menu = user.GetMenu(hwnd)
    file_item = item_at(menu, 'file')
    submenu = user.GetSubMenu(menu, file_item)
    save_item = item_at(submenu, 'save')
    click_item(hwnd, menu, file_item)
    click_item(None, submenu, save_item)
    deadline = time.monotonic() + SAVE_TIMEOUT
    while time.monotonic() < deadline:
        checkpoint()
        verified, message = verify_file(source, expected)
        if verified:
            return 'Notepad File → Save was clicked. ' + message
        time.sleep(0.1)
    raise RuntimeError(message)


__all__ = ['SAVE_TIMEOUT', 'SaveResult', 'editor_text', 'save_open_document',
           'verify_file']
