"""Settings disclosure must never change the owner's permissions."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from desktop.app import Window
from security.policy import ApprovalMode


@pytest.fixture
def desktop(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        window.resize(920, 690)
        window.show()
        window.open_section('Settings & Safety')
        app.processEvents()
        yield window, app
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_settings_opens_essentials_and_keyboard_reveals_one_category(desktop):
    window, app = desktop
    assert window.settings_essentials.isVisibleTo(window)
    for item in (window.approval_mode_choice, window.reply_language,
                 window.reply_tone, window.theme_choice):
        assert item.isVisibleTo(window)
    assert not window.settings_category.isVisibleTo(window)
    assert not any(group.isVisibleTo(window) for group in window.settings_groups.values())

    window.settings_mode_button.setFocus()
    QTest.keyClick(window.settings_mode_button, Qt.Key.Key_Space)
    app.processEvents()
    chooser = window.settings_category
    assert chooser.hasFocus()
    assert window.audio_test.isVisibleTo(window)
    assert not window.reply_language.isVisibleTo(window)

    QTest.keyClick(chooser, Qt.Key.Key_Down)
    app.processEvents()
    assert window.start_at_signin.isVisibleTo(window)
    assert not window.audio_test.isVisibleTo(window)
    assert sum(group.isVisibleTo(window) for group in window.settings_groups.values()) == 1

    window.settings_mode_button.click()
    assert window.settings_mode_button.hasFocus()
    assert window.settings_essentials.isVisibleTo(window)


def test_projects_and_plugins_shortcuts_reveal_the_existing_controllers(desktop):
    window, app = desktop
    shell = window.prime_shell
    scroller = window.pages.currentWidget()
    shell.rail_buttons['Projects'].click()
    app.processEvents()
    assert window.settings_category.currentData() == 'projects'
    assert window.projects_table.isVisibleTo(window)
    assert shell.rail_buttons['Projects'].isChecked()

    shell.work_actions['Plugins'].trigger()
    app.processEvents()
    assert window.plugins_group.isVisibleTo(window)
    assert scroller.verticalScrollBar().value() > 0
    plugin_top = window.plugins_group.mapTo(scroller.viewport(), window.plugins_group.rect().topLeft()).y()
    assert 0 <= plugin_top < scroller.viewport().height()

    shell.rail_buttons['Settings & Safety'].click()
    app.processEvents()
    assert window.settings_essentials.isVisibleTo(window)
    assert not window.projects_table.isVisibleTo(window)
    assert scroller.verticalScrollBar().value() == 0


def test_disclosure_does_not_grant_access_or_enable_startup(desktop, monkeypatch):
    window, _app = desktop
    original_startup = window.start_at_signin.isChecked()
    original_mode_setting = window.store.get('security:approval_mode')
    choice = window.approval_mode_choice

    def decline_full(*args):
        assert args[-1] == QMessageBox.StandardButton.No
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, 'question', decline_full)
    full = choice.findData(ApprovalMode.FULL.value)
    choice.setCurrentIndex(full)
    choice.activated.emit(full)
    assert choice.currentData() == ApprovalMode.ASK.value

    window.settings_mode_button.click()
    for index in range(window.settings_category.count()):
        window.settings_category.setCurrentIndex(index)
    window.settings_mode_button.click()
    assert window.policy.mode is ApprovalMode.ASK
    assert window.store.get('security:approval_mode') == original_mode_setting
    assert window.start_at_signin.isChecked() == original_startup
    assert not window.voice_panel.consent.listening
    assert not window.bridge.listener.running
