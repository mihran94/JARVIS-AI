"""The Calculator display and the saved document.

WHAT IS COVERED
    * The value the Calculator is showing is read out of the control
      tree, and the number is taken from the known display element
      rather than from any text that happens to be there.
    * A display that shows something which is not a number is not
      treated as a result.
    * The separators a Calculator shows are removed from the value.
    * A file that is read back with the contents the editor showed is
      verified; a file that differs is not.
    * A save that cannot be verified is reported as a failure, and the
      focus that moved stops the save before anything is sent.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

from automation.calculator import (
    find_display, is_a_display_value, normalise_value, read_display,
)
from automation.editor import SaveResult, save_open_document, verify_file
from automation.input import FocusLost, InputTarget
from automation.uia import UiaElement


def tree(display='42', control_type='Text', automation_id='calculatorResults'):
    """A tree shaped like the one the Calculator publishes."""
    window = UiaElement(name='Calculator', control_type='Window', process_id=42)
    window.children.append(UiaElement(name='Seven', control_type='Button',
                                      process_id=42))
    window.children.append(UiaElement(name=display, control_type=control_type,
                                      automation_id=automation_id, process_id=42))
    return [window]


# ── the calculator ─────────────────────────────────────────────────────────

def test_the_display_is_read():
    assert find_display(tree()) == '42'


def test_the_known_display_element_is_preferred():
    elements = tree(display='7', control_type='Text', automation_id='someOther')
    elements[0].children.append(UiaElement(name='99', control_type='Text',
                                            automation_id='calculatorResults',
                                            process_id=42))
    assert find_display(elements) == '99'


def test_a_text_element_with_a_number_is_used_when_there_is_no_id():
    elements = tree(display='1,234.5', control_type='Text', automation_id='')
    assert find_display(elements) == '1,234.5'


def test_a_display_that_is_not_a_number_is_not_a_result():
    assert is_a_display_value('42') is True
    assert is_a_display_value('-3.5') is True
    assert is_a_display_value('1,000') is True
    assert is_a_display_value('') is False
    assert is_a_display_value('Error') is False
    assert is_a_display_value('Memory') is False


def test_the_separators_are_removed():
    assert normalise_value('1,234.50') == '1234.50'
    assert normalise_value(' 42 ') == '42'


def test_a_display_that_cannot_be_read_is_empty():
    assert read_display(42) == ''


# ── the saved file ─────────────────────────────────────────────────────────

def test_a_file_with_the_expected_contents_is_verified(tmp_path):
    path = tmp_path / 'note.txt'
    path.write_text('the note\n', encoding='utf-8')
    verified, message = verify_file(path, 'the note\n')
    assert verified is True
    assert 'read back unchanged' in message


def test_a_file_with_different_contents_is_not_verified(tmp_path):
    path = tmp_path / 'note.txt'
    path.write_text('something else\n', encoding='utf-8')
    verified, message = verify_file(path, 'the note\n')
    assert verified is False
    assert 'not what the editor showed' in message


def test_the_line_endings_do_not_matter(tmp_path):
    path = tmp_path / 'note.txt'
    path.write_bytes(b'the note\r\nsecond line\r\n')
    verified, _ = verify_file(path, 'the note\nsecond line\n')
    assert verified is True


def test_a_file_that_is_not_there_is_not_verified(tmp_path):
    verified, message = verify_file(tmp_path / 'nothing.txt')
    assert verified is False
    assert 'not there' in message


def test_a_save_that_cannot_be_verified_is_a_failure(tmp_path):
    """The focus moved, so nothing was sent and nothing is claimed."""
    target = InputTarget(process_id=42, title='Notepad')
    result = save_open_document(target, path=tmp_path / 'note.txt',
                                foreground=lambda: 99)
    assert isinstance(result, SaveResult)
    assert result.saved is False
    assert result.verified is False
    assert 'focus moved' in result.message


def test_a_save_that_is_verified_is_reported(tmp_path, monkeypatch):
    """With the focus right and the file written, the save is real."""
    path = tmp_path / 'note.txt'
    path.write_text('the note\n', encoding='utf-8')
    target = InputTarget(process_id=42, title='Notepad')

    import automation.editor as editor

    monkeypatch.setattr(editor, 'press_key',
                        lambda *args, **kwargs: 'Ctrl+S was sent.')
    # The editor shows this, so the file has to hold this.
    monkeypatch.setattr(editor, 'editor_text', lambda: 'the note\n')
    result = save_open_document(target, path=path, foreground=lambda: 42)
    assert result.saved is True
    assert result.verified is True
    assert 'read back unchanged' in result.message


def test_a_save_that_writes_something_else_is_not_verified(tmp_path, monkeypatch):
    """The file exists, but it does not hold what the editor shows."""
    path = tmp_path / 'note.txt'
    path.write_text('something else\n', encoding='utf-8')
    target = InputTarget(process_id=42, title='Notepad')

    import automation.editor as editor

    monkeypatch.setattr(editor, 'press_key',
                        lambda *args, **kwargs: 'Ctrl+S was sent.')
    monkeypatch.setattr(editor, 'editor_text', lambda: 'the note\n')
    result = save_open_document(target, path=path, foreground=lambda: 42, timeout=1)
    assert result.verified is False
    assert 'not what the editor showed' in result.message
