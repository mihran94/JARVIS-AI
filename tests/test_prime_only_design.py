"""Only the JARVIS PRIME interface and Island are user-facing."""
from pathlib import Path

from PySide6.QtWidgets import QApplication

from desktop.app import Window
from desktop.omega import DESTINATIONS, MODES


ROOT = Path(__file__).resolve().parents[1]


def test_retired_styles_and_migration_are_deleted():
    for path in (
        "desktop/personal_theme.py",
        "desktop/blue_theme.py",
        "scripts/port_chat_first_omega.py",
    ):
        assert not (ROOT / path).exists(), path


def test_legacy_presentation_preferences_cannot_reopen_old_design(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        # Historic settings must not resurrect any prior design or dock.
        window.store.set("omega:mode", "Stealth")
        window.store.set("omega:command_first", False)
        window.store.set("omega:show_dock_on_start", True)
        window.store.set("omega:auto_hide", False)
        window.enable_omega()
        app.processEvents()

        assert MODES == ("Omega", "Island")
        assert window.omega.mode == "Omega"
        assert window.pages.currentIndex() == window.page_indices["JARVIS Chat"]
        assert not window.omega.dock.isVisible()
        assert not window.omega.reveal.isVisible()
        assert not hasattr(window.omega, "dock_shortcut")
        window.omega.show_dock(True)
        assert not window.omega.dock.isVisible()

        # Old saved routes lead to the working PRIME pages.
        assert DESTINATIONS["Home"][0] == "JARVIS Chat"
        assert DESTINATIONS["Settings"][0] == "Settings & Safety"
        window.omega.open_page("Omega Home")
        assert window.pages.currentIndex() == window.page_indices["JARVIS Chat"]
        window.omega.open_page("Omega Settings")
        assert window.pages.currentIndex() == window.page_indices["Settings & Safety"]
        window.omega.switch("Stealth")
        assert window.omega.mode == "Omega"
        window.omega.switch("Island")
        app.processEvents()
        assert window.omega.floating.isVisible()
    finally:
        window.close()
        app.processEvents()
