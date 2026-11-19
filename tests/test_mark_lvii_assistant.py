"""MARK LVII assistant-first interface and honest runtime capability checks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication
from core.assistant_capabilities import snapshot, summary
from desktop.app import Window
from desktop.omega_visuals import THEMES


def test_capabilities_are_based_on_local_state(tmp_path):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    try:
        state = snapshot(win)
        assert state['phone_bridge'] is False
        assert state['microphone'] is False
        assert state['stopped'] is False
        assert 'not granted' in summary(win)
        assert win.local_system_reply('/capabilities') == summary(win)
        win.stop()
        assert snapshot(win)['stopped']
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_mark_lvii_chat_first_but_existing_pages_remain(tmp_path):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    try:
        win.show()
        app.processEvents()
        assert win.pages.currentIndex() == win.page_indices['JARVIS Chat']
        assert win.settings_button.text() == 'Settings'
        assert win.island_button.text() == 'Island'
        assert win.plugins_button.isHidden()
        assert win.tools_button.isHidden()
        assert win.chat_home_button.isHidden()
        assert not win.chat_provider.isVisible()
        win.settings_button.click()
        app.processEvents()
        assert win.pages.currentIndex() == win.page_indices['Settings & Safety']
        assert win.plugins_group.isVisible()
        win.chat_home_button.click()
        assert win.pages.currentIndex() == win.page_indices['JARVIS Chat']
        win.enable_omega(smoke=True)
        assert win.omega.theme == 'MARK LVII'
        assert 'MARK LVII' in THEMES
        win.omega.set_voice('thinking')
        assert win.chat_reactor.activity == 'thinking'
        for name in ('PC Control', 'Coding Assistant', 'Voice / Hey Jarvis',
                     'Phone Remote', 'Video Editor', 'Business', 'Memory',
                     'AI Providers', 'Settings & Safety', 'Step Workflows'):
            assert name in win.page_indices
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()


def test_pending_app_approval_is_visible_in_mark_lvii_island(tmp_path):
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    try:
        win.enable_omega()
        win.prompt.setPlainText('Jarvis, open Notepad')
        win.send()
        win.open_island()
        assert 'Approval required' in win.omega.floating.handle.text()
        assert win.omega.floating.assistant.text() == 'Review'
        win.omega.floating.assistant.click()
        assert win.omega.mode == 'Omega'
        assert win.chat_approval.isVisible()
        win.finish_chat_launch(False)
        assert win.omega.floating.assistant.text() == 'Assistant'
    finally:
        win.close()
        app.processEvents()


def test_prime_shell_replaces_visible_legacy_chat_layout(tmp_path):
    """The installed Chat must visibly be PRIME, not an old orb and header."""
    app = QApplication.instance() or QApplication([])
    win = Window(tmp_path)
    try:
        win.resize(680, 510)
        win.show()
        app.processEvents()
        assert win.windowTitle() == 'JARVIS PRIME • MARK LVII'
        assert win.prime_hero.objectName() == 'primeHero'
        assert win.prime_hero.isVisibleTo(win)
        assert win.prime_dock.isVisibleTo(win)
        assert win.chat_reactor.isVisibleTo(win)
        assert not win.orb.isVisibleTo(win)
        assert win.transcript.isVisibleTo(win)
        assert win.composer_bar.isVisibleTo(win)
        assert win.pages.currentWidget().horizontalScrollBar().maximum() == 0
        win.coding_button.click()
        assert win.pages.currentIndex() == win.page_indices['Coding Assistant']
        assert not win.composer_bar.isVisibleTo(win)
        win.settings_button.click()
        assert win.pages.currentIndex() == win.page_indices['Settings & Safety']
        assert win.theme_choice.currentText() == 'MARK LVII'
        win.chat_home_button.click()
        assert win.composer_bar.isVisibleTo(win)
        assert not win.voice_panel.consent.granted
        assert not win.bridge.listener.running
    finally:
        win.close()
        win.deleteLater()
        app.processEvents()
