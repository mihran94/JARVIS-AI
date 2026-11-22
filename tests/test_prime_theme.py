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
        # Scrolling the conversation leaves the composer in place.
        assert window.prompt.parent() is window.prime_chat.composer
        assert not window.prime_chat.conversation.isAncestorOf(window.prompt)
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
        assert window.prime_chat.composer.isVisibleTo(window) is True
        window.open_section('Settings & Safety')
        assert window.prime_chat.composer.isVisibleTo(window) is False
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_the_window_is_painted_and_not_transparent(app, tmp_path):
    """The application must not show the desktop through the interface.

    Qt lets the later rule win when two rules match the same widget. A
    generic rule that makes every widget transparent was therefore placed
    after the rule that paints the window, and the whole window ended up
    transparent: the owner saw the desktop behind the conversation.
    """
    from desktop.app import Window

    window = Window(tmp_path)
    try:
        window.show()
        app.processEvents()
        image = window.grab().toImage()
        sampled = [
            image.pixelColor(x, y)
            for x in range(0, image.width(), 9)
            for y in range(0, image.height(), 9)
        ]
        transparent = [colour for colour in sampled if colour.alpha() == 0]
        assert len(transparent) == 0, (
            f'{len(transparent)} of {len(sampled)} sampled pixels are transparent: '
            'the window background is not painted')
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_the_window_rule_comes_after_the_generic_widget_rule():
    """The order of the two rules is what keeps the window opaque."""
    sheet = prime_theme.PRIME_DARK
    generic = sheet.index('QWidget {')
    window_rule = sheet.index('QMainWindow')
    assert window_rule > generic, (
        'the window background rule has to follow the generic widget rule, '
        'because the later rule is the one that wins')


def test_the_page_root_carries_the_premium_surface(app, tmp_path):
    """The page rule only paints when a page is named for it."""
    from desktop.app import Window

    window = Window(tmp_path)
    try:
        page = window.pages.widget(window.page_indices['Settings & Safety'])
        # The page is inside a scroll area, so the root is the scrolled page.
        root = page.widget() if hasattr(page, 'widget') else page
        assert root.objectName() == 'pageRoot'
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_the_interface_font_names_a_font_that_carries_tamil():
    """Tamil has to be laid out with a font that measures Tamil.

    When the interface font carries no Tamil glyphs, the Latin characters
    are measured with a font that has no Tamil while the Tamil characters
    are drawn from another one, and the two are drawn on top of each other.
    """
    from desktop.prime_theme import FONT_STACK

    names = {part.strip().strip("'") for part in FONT_STACK.split(',')}
    tamil_fonts = {
        'Nirmala UI', 'Noto Sans Tamil', 'Latha', 'Tamil MN',
        'Tamil Sangam MN', 'Vijaya', 'FreeSerif',
    }
    assert names & tamil_fonts, (
        'the interface font stack names no font that carries Tamil')


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


def test_theme_survives_restart_and_both_settings_stay_in_sync(app, tmp_path):
    from desktop.app import Window
    from desktop.omega_visuals import theme_sheet

    window = Window(tmp_path)
    try:
        window.theme_choice.setCurrentText('Apple Silver')
        assert window.styleSheet() == theme_sheet('Apple Silver')
        window.enable_omega(smoke=True)
        assert window.omega.theme_selector.currentText() == 'Apple Silver'
        window.omega.theme_selector.setCurrentText('Dark Titanium')
        assert window.theme_choice.currentText() == 'Dark Titanium'
    finally:
        window.close()
        app.processEvents()

    restarted = Window(tmp_path)
    try:
        assert restarted.styleSheet() == theme_sheet('Dark Titanium')
        assert restarted.chat_reactor.theme == 'Dark Titanium'
    finally:
        restarted.close()
        app.processEvents()
