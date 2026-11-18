"""The JARVIS PRIME interface theme.

WHAT IS COVERED
    * The theme is applied to the running application, not only in the tests.
      It used to be defined and never applied, so the shipping JARVIS
      rendered in the default light Qt theme.
    * The dark theme is the default, and the owner can choose the light one.
    * The composer stays visible: it belongs to the window, not to the
      scrolling chat page.
    * Every translucent surface uses a colour form Qt actually honours, so
      the panels read as glass instead of as flat blocks.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from core.store import Store
from desktop import prime_theme


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_the_dark_theme_is_the_default(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    assert prime_theme.theme_name(store) == 'Dark'


def test_the_owner_can_choose_the_light_theme(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    store.set(prime_theme.THEME_KEY, 'Light')
    assert prime_theme.theme_name(store) == 'Light'


def test_an_unknown_theme_falls_back_to_the_default(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    store.set(prime_theme.THEME_KEY, 'Neon')
    assert prime_theme.theme_name(store) == 'Dark'


def test_both_themes_are_complete(app, tmp_path):
    for name in prime_theme.THEME_NAMES:
        sheet = prime_theme.THEMES[name]
        assert sheet.strip()
        assert 'QPushButton' in sheet
        assert 'QMainWindow' in sheet
        assert 'Segoe UI Variable' in sheet


def test_the_translucent_surfaces_use_a_form_qt_honours():
    """Qt ignores the alpha of rgba() when it paints a widget background."""
    sheet = prime_theme.PRIME_DARK
    assert 'rgba(' not in sheet.split('/* ── the painted core')[0], (
        'a translucent surface is still written as rgba(), which Qt paints opaque')


def test_the_theme_is_applied_to_the_running_application(app, tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    applied = prime_theme.apply_theme(app, store)
    assert applied == 'Dark'
    assert app.styleSheet() == prime_theme.PRIME_DARK


def test_the_composer_belongs_to_the_window_and_not_to_the_scrolling_page(tmp_path):
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        # The composer is a child of the window, not of the chat page, so the
        # conversation scrolls and the input never leaves the screen.
        assert window.composer_bar.parent() is window.centralWidget()
        # The chat page itself does not hold the composer.
        assert window.prompt.parent() is window.composer_bar
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_the_composer_is_only_shown_with_the_chat(tmp_path):
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        window.open_section('JARVIS Chat')
        assert window.composer_bar.isVisibleTo(window) is True
        window.open_section('Settings & Safety')
        assert window.composer_bar.isVisibleTo(window) is False
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_the_settings_offer_the_owner_a_light_and_a_dark_theme(tmp_path):
    from desktop.app import Window
    from desktop.omega_visuals import THEMES

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        offered = [window.theme_choice.itemText(index)
                   for index in range(window.theme_choice.count())]
        assert offered == list(THEMES)
        # The owner can choose a light palette and a dark one.
        from desktop.prime_theme import _luminance
        light = [name for name in offered if _luminance(THEMES[name][0]) > 0.5]
        dark = [name for name in offered if _luminance(THEMES[name][0]) <= 0.5]
        assert light and dark
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
