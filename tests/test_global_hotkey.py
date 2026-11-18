"""The rules for the key that brings JARVIS up.

The written shortcut, the keys Windows keeps for itself and the keys
other applications usually take are plain rules, and they are checked
here on any machine.

The registration itself is a Windows feature, so the test that actually
takes a key from the operating system runs only on Windows. The Windows
runner of the workflow runs it.
"""
import sys

import pytest

from desktop.global_hotkey import (
    COMMONLY_TAKEN,
    DEFAULT_SHORTCUT,
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    WINDOWS_RESERVED,
    GlobalHotkey,
    Shortcut,
    ShortcutError,
    commonly_taken,
    parse_shortcut,
    shortcut_status,
)


def test_a_shortcut_is_read():
    shortcut = parse_shortcut('Ctrl+Alt+J')
    assert shortcut.modifiers == MOD_CONTROL | MOD_ALT
    assert shortcut.virtual_key == ord('J')


def test_the_modifiers_are_read_in_any_order():
    first = parse_shortcut('Ctrl+Alt+Shift+K')
    second = parse_shortcut('Shift+Ctrl+Alt+K')
    assert first == second


def test_the_same_modifier_written_twice_is_still_one():
    assert parse_shortcut('Ctrl+Ctrl+J') == parse_shortcut('Ctrl+J')


def test_a_letter_is_not_case_sensitive():
    assert parse_shortcut('ctrl+alt+j') == parse_shortcut('Ctrl+Alt+J')


def test_a_digit_is_read():
    assert parse_shortcut('Ctrl+Alt+7').virtual_key == ord('7')


def test_a_function_key_alone_is_allowed():
    # The function keys are not typed, so they are safe on their own.
    assert parse_shortcut('F5').virtual_key == 0x74


def test_a_function_key_is_read():
    assert parse_shortcut('Ctrl+Shift+F5').virtual_key == 0x74


def test_a_named_key_is_read():
    assert parse_shortcut('Ctrl+Alt+Space').virtual_key == 0x20


def test_a_shortcut_is_written_back_the_way_a_person_says_it():
    assert parse_shortcut('ctrl+alt+j').describe() == 'Ctrl+Alt+J'
    assert parse_shortcut('Ctrl+Alt+Space').describe() == 'Ctrl+Alt+Space'


def test_an_empty_shortcut_is_refused_with_a_reason():
    with pytest.raises(ShortcutError) as error:
        parse_shortcut('')
    assert 'Type the key' in str(error.value)


def test_a_key_without_a_modifier_is_refused():
    # A bare key would be taken while the owner types.
    with pytest.raises(ShortcutError) as error:
        parse_shortcut('J')
    assert 'modifier' in str(error.value)


def test_two_keys_are_refused():
    with pytest.raises(ShortcutError) as error:
        parse_shortcut('Ctrl+J+K')
    assert 'second one' in str(error.value)


def test_a_key_that_does_not_exist_is_refused():
    with pytest.raises(ShortcutError) as error:
        parse_shortcut('Ctrl+Alt+Shout')
    assert 'not a key' in str(error.value)


def test_the_windows_keys_are_refused():
    for name, _modifiers, _key in WINDOWS_RESERVED:
        with pytest.raises(ShortcutError) as error:
            parse_shortcut(name)
        assert 'belongs to Windows' in str(error.value)


def test_ctrl_alt_delete_is_refused():
    with pytest.raises(ShortcutError) as error:
        parse_shortcut('Ctrl+Alt+Del')
    assert 'belongs to Windows' in str(error.value)


def test_the_keys_other_applications_take_are_only_a_warning():
    for name, _modifiers, _key in COMMONLY_TAKEN:
        shortcut = parse_shortcut(name)
        assert commonly_taken(shortcut) == name
        assert 'other applications' in shortcut_status(name)


def test_a_free_key_has_no_warning():
    shortcut = parse_shortcut('Ctrl+Alt+Space')
    assert commonly_taken(shortcut) == ''
    assert shortcut_status('Ctrl+Alt+Space') == 'Ctrl+Alt+Space is ready.'


def test_a_broken_shortcut_is_explained_and_not_raised():
    assert 'Ctrl+Alt+Del' in shortcut_status('Ctrl+Alt+Del')
    assert 'not a key' in shortcut_status('Ctrl+Alt+Shout')


def test_the_default_shortcut_can_be_used():
    assert parse_shortcut(DEFAULT_SHORTCUT).describe() == 'Ctrl+Alt+Space'


def test_the_shortcut_survives_a_round_trip():
    shortcut = parse_shortcut('Ctrl+Alt+Shift+Space')
    assert parse_shortcut(shortcut.describe()) == shortcut


def test_two_different_shortcuts_are_not_equal():
    assert parse_shortcut('Ctrl+Alt+J') != parse_shortcut('Ctrl+Alt+K')


def test_the_modifier_flags_are_the_ones_windows_uses():
    assert MOD_ALT == 1
    assert MOD_CONTROL == 2
    assert MOD_SHIFT == 4
    assert MOD_WIN == 8


def test_a_shortcut_can_be_equal_to_a_made_one():
    assert Shortcut(MOD_CONTROL | MOD_ALT, ord('J')) == parse_shortcut('Ctrl+Alt+J')


@pytest.mark.skipif(sys.platform != 'win32', reason='the key is a Windows feature')
def test_a_key_is_taken_from_windows_and_given_back():
    """The real thing: Windows is asked for a key, and then gives it back."""
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    pressed = []
    hotkey = GlobalHotkey(lambda: pressed.append(True))
    message = hotkey.register('Ctrl+Alt+Shift+F9')
    try:
        assert 'now brings JARVIS up' in message, message
        assert hotkey.registered
        assert hotkey.shortcut.describe() == 'Ctrl+Alt+Shift+F9'
    finally:
        hotkey.unregister()
    assert not hotkey.registered


@pytest.mark.skipif(sys.platform != 'win32', reason='the key is a Windows feature')
def test_windows_says_when_another_program_holds_the_key():
    """Taking the same key twice must be refused, not silently ignored."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    first = GlobalHotkey(lambda: None)
    second = GlobalHotkey(lambda: None)
    try:
        first.register('Ctrl+Alt+Shift+F10')
        message = second.register('Ctrl+Alt+Shift+F10')
        assert 'already holds this key' in message, message
        assert not second.registered
    finally:
        first.unregister()
        second.unregister()


@pytest.mark.skipif(sys.platform == 'win32', reason='Windows is the supported system')
def test_on_another_system_the_shortcut_is_saved_and_says_it_does_nothing():
    hotkey = GlobalHotkey(lambda: None)
    message = hotkey.register('Ctrl+Alt+Space')
    assert 'does nothing here' in message, message
    assert not hotkey.registered
    assert hotkey.shortcut is not None


def test_a_broken_shortcut_is_not_registered():
    hotkey = GlobalHotkey(lambda: None)
    message = hotkey.register('Ctrl+Alt+Del')
    assert 'belongs to Windows' in message
    assert not hotkey.registered
