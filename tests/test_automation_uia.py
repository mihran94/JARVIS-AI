"""UI Automation and the validated input layer.

WHAT IS COVERED
    * A control is found by the name the owner can see, by its type or
      by its automation id, and an unknown type is refused.
    * A dialog the owner did not expect is found, and the action stops.
    * Before every input the focus is checked again: when the focus
      moved, nothing is sent.
    * A key that is not on the allowlist cannot be pressed.
    * Text is bounded, and a scroll is bounded.
    * The input layer refuses to run on anything that is not Windows.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest

from automation.input import (
    AmbiguousTarget, FocusLost, InputRefused, InputTarget, KEY_ALLOWLIST,
    UnexpectedDialog, activate_window, click_at, press_key, scroll, type_text,
    validate_focus,
)
from automation.uia import (
    CONTROL_TYPES, UiaElement, UiaUnavailable, describe, find, flatten,
    load_client, read_tree, unexpected_dialogs,
)


def tree():
    """A small control tree, as Windows would publish it."""
    window = UiaElement(name='Notepad', control_type='Window', process_id=42,
                         automation_id='notepad-window')
    window.children.append(UiaElement(name='File', control_type='MenuItem',
                                      process_id=42, enabled=True))
    window.children.append(UiaElement(name='Edit', control_type='Edit',
                                      process_id=42, value='hello'))
    window.children.append(UiaElement(name='Save', control_type='Button',
                                      process_id=42, enabled=True))
    window.children.append(UiaElement(name='Hidden', control_type='Button',
                                      process_id=42, offscreen=True))
    return [window]


# ── the control tree ───────────────────────────────────────────────────────

def test_a_control_is_found_by_its_name():
    matches = find(tree(), name='Save')
    assert len(matches) == 1
    assert matches[0].control_type == 'Button'


def test_a_control_is_found_by_its_type():
    matches = find(tree(), control_type='Edit')
    assert len(matches) == 1
    assert matches[0].value == 'hello'


def test_a_control_is_found_by_its_automation_id():
    matches = find(tree(), automation_id='notepad-window')
    assert len(matches) == 1
    assert matches[0].name == 'Notepad'


def test_the_search_is_not_case_sensitive():
    assert find(tree(), name='save')


def test_a_control_that_is_off_screen_can_be_left_out():
    assert len(find(tree(), name='Hidden')) == 1
    assert find(tree(), name='Hidden', visible_only=True) == []


def test_an_unknown_control_type_is_refused():
    with pytest.raises(ValueError):
        find(tree(), control_type='Wombat')


def test_the_tree_is_flattened():
    assert len(flatten(tree())) == 5


def test_the_tree_reads_as_words():
    text = describe(tree())
    assert 'Button "Save"' in text
    assert 'Edit "Edit"' in text


def test_a_dialog_that_was_not_expected_is_found():
    dialog = UiaElement(name='Save changes?', control_type='Dialog', process_id=42)
    assert unexpected_dialogs([dialog]) == [dialog]


def test_the_dialog_that_was_expected_is_not_a_problem():
    dialog = UiaElement(name='Notepad', control_type='Dialog', process_id=42)
    assert unexpected_dialogs([dialog], expected_titles=('Notepad',)) == []


def test_the_tree_cannot_be_read_off_windows():
    if os.name != 'nt':
        with pytest.raises(UiaUnavailable):
            load_client()
        with pytest.raises(UiaUnavailable):
            read_tree(process_id=1)


def test_a_control_type_that_does_not_exist_is_not_on_the_list():
    assert 'Button' in CONTROL_TYPES
    assert 'Wombat' not in CONTROL_TYPES


# ── the focus rule ─────────────────────────────────────────────────────────

def test_the_focus_is_checked_before_anything_is_sent():
    target = InputTarget(process_id=42, title='Notepad')
    validate_focus(target, foreground=lambda: 42)


def test_a_moved_focus_stops_the_action():
    target = InputTarget(process_id=42, title='Notepad')
    with pytest.raises(FocusLost) as error:
        validate_focus(target, foreground=lambda: 99)
    assert 'focus moved' in str(error.value)


def test_no_window_in_front_stops_the_action():
    target = InputTarget(process_id=42)
    with pytest.raises(FocusLost):
        validate_focus(target, foreground=lambda: None)


def test_an_unexpected_dialog_stops_the_action():
    target = InputTarget(process_id=42, title='Notepad')
    dialog = UiaElement(name='Save changes?', control_type='Dialog', process_id=42)
    with pytest.raises(UnexpectedDialog):
        validate_focus(target, foreground=lambda: 42, dialogs=lambda: [dialog])


def test_the_expected_dialog_does_not_stop_the_action():
    target = InputTarget(process_id=42, title='Notepad')
    dialog = UiaElement(name='Notepad', control_type='Dialog', process_id=42)
    validate_focus(target, foreground=lambda: 42, dialogs=lambda: [dialog])


# ── the actions ────────────────────────────────────────────────────────────

def test_typing_needs_a_window_in_front():
    target = InputTarget(process_id=42)
    with pytest.raises(FocusLost):
        type_text('hello', target, foreground=lambda: 7)


def test_the_text_is_bounded():
    target = InputTarget(process_id=42)
    with pytest.raises(InputRefused):
        type_text('x' * 5000, target, foreground=lambda: 42)


def test_empty_text_is_refused():
    target = InputTarget(process_id=42)
    with pytest.raises(InputRefused):
        type_text('', target, foreground=lambda: 42)


def test_only_the_allowed_keys_may_be_pressed():
    target = InputTarget(process_id=42)
    with pytest.raises(InputRefused) as error:
        press_key('win+r', target, foreground=lambda: 42)
    assert 'not one JARVIS may press' in str(error.value)


def test_the_allowed_keys_are_a_fixed_list():
    assert 'enter' in KEY_ALLOWLIST
    assert 'ctrl+s' in KEY_ALLOWLIST
    assert 'f12' not in KEY_ALLOWLIST


def test_a_scroll_is_bounded():
    target = InputTarget(process_id=42)
    with pytest.raises(InputRefused):
        scroll(500, target, foreground=lambda: 42)


def test_a_click_needs_a_whole_position():
    target = InputTarget(process_id=42)
    with pytest.raises(InputRefused):
        click_at(10.5, 20, target, foreground=lambda: 42)


def test_a_click_outside_the_screen_is_refused():
    target = InputTarget(process_id=42)
    with pytest.raises(InputRefused):
        click_at(99999, 20, target, foreground=lambda: 42)


def test_the_actions_stop_before_windows_is_reached():
    # The focus rule is checked first, so a wrong focus is reported before
    # the operating system is asked to do anything.
    target = InputTarget(process_id=42)
    for action in (lambda: type_text('x', target, foreground=lambda: 1),
                   lambda: press_key('enter', target, foreground=lambda: 1),
                   lambda: scroll(1, target, foreground=lambda: 1),
                   lambda: click_at(1, 1, target, foreground=lambda: 1)):
        with pytest.raises(FocusLost):
            action()


def test_bringing_a_window_forward_needs_a_process():
    with pytest.raises(InputRefused):
        activate_window(0)


def test_the_target_describes_itself():
    assert InputTarget(process_id=42, title='Notepad').describe() == 'Notepad'
    assert InputTarget(process_id=42).describe() == 'process 42'
