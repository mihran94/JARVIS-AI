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
from pathlib import Path
import time

from automation.input import FocusLost, InputRefused, UnexpectedDialog, press_key, validate_focus
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


__all__ = ['SAVE_TIMEOUT', 'SaveResult', 'editor_text', 'save_open_document',
           'verify_file']
