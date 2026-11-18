"""The key that brings JARVIS up, wired into the application.

The rules for the shortcut are in tests/test_global_hotkey.py. What is
checked here is that the application takes the key, keeps it, and does
the right thing when it is pressed.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from desktop.app import Window
from desktop.global_hotkey import DEFAULT_SHORTCUT


def make_window(tmp_path):
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    window.show()
    app.processEvents()
    return app, window


def test_the_window_takes_a_key_when_it_opens(tmp_path):
    app, window = make_window(tmp_path)
    try:
        assert window.hotkey is not None
        # The key is not taken on a system that cannot hand one out, and
        # the application says so rather than pretending.
        assert window.hotkey_status
    finally:
        window.hotkey.unregister()
        window.close()


def test_a_key_that_windows_keeps_is_not_taken(tmp_path):
    app, window = make_window(tmp_path)
    try:
        message = window.apply_hotkey('Ctrl+Alt+Del')
        assert 'belongs to Windows' in message
        assert not window.hotkey.registered
    finally:
        window.close()


def test_a_key_that_is_taken_is_remembered(tmp_path):
    app, window = make_window(tmp_path)
    try:
        window.apply_hotkey('Ctrl+Alt+Shift+F9')
        assert window.store.get('hotkey:shortcut') == 'Ctrl+Alt+Shift+F9'
    finally:
        window.hotkey.unregister()
        window.close()


def test_the_key_brings_the_window_to_the_front(tmp_path, monkeypatch):
    app, window = make_window(tmp_path)
    try:
        raised = []
        monkeypatch.setattr(window, 'showNormal', lambda: raised.append('show'))
        monkeypatch.setattr(window, 'raise_', lambda: raised.append('raise'))
        monkeypatch.setattr(window, 'activateWindow', lambda: raised.append('activate'))
        window.summon_from_hotkey()
        assert 'show' in raised
        assert 'raise' in raised
    finally:
        window.close()


def test_the_key_does_not_open_the_microphone(tmp_path, monkeypatch):
    """The key brings JARVIS up. The owner decides there what happens next."""
    app, window = make_window(tmp_path)
    try:
        opened = []
        monkeypatch.setattr(window.voice_panel, 'start_voice', lambda: opened.append(True),
                            raising=False)
        monkeypatch.setattr(window.voice_panel, 'toggle_mic', lambda: opened.append(True),
                            raising=False)
        window.summon_from_hotkey()
        assert not opened
    finally:
        window.close()


def test_the_key_is_given_back_when_the_window_closes(tmp_path):
    app, window = make_window(tmp_path)
    try:
        window.apply_hotkey('Ctrl+Alt+Shift+F9')
        window.close()
        assert not window.hotkey.registered
    finally:
        window.close()


def test_the_settings_page_shows_the_key(tmp_path):
    app, window = make_window(tmp_path)
    try:
        window.enable_omega()
        app.processEvents()
        assert window.omega.hotkey_input.text()
        assert window.omega.hotkey_input.maxLength() == 40
    finally:
        window.hotkey.unregister()
        window.close()


def test_the_default_key_is_the_one_that_is_suggested(tmp_path):
    app, window = make_window(tmp_path)
    try:
        window.enable_omega()
        app.processEvents()
        assert window.omega.hotkey_input.placeholderText() == DEFAULT_SHORTCUT
    finally:
        window.hotkey.unregister()
        window.close()
