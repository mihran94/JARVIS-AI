"""The owner's optional PyQt6 background patch adapted to PySide6.

These are headless UI tests, not a test of a real Windows taskbar.
"""
import os
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QWidget
from desktop.tray import BackgroundControls


class FakeTray:
    def __init__(self, parent):
        self.visible = False
        self.activated = SimpleNamespace(connect=lambda callback: None)

    def setIcon(self, icon):
        self.icon = icon

    def setToolTip(self, tooltip):
        self.tooltip = tooltip

    def setContextMenu(self, menu):
        self.menu = menu

    def show(self):
        self.visible = True

    def isVisible(self):
        return self.visible


def app():
    return QApplication.instance() or QApplication([])


def test_background_mode_does_not_hide_without_tray():
    application = app()
    window = QWidget()
    window.show()
    controls = BackgroundControls(window, tray_available=False)
    controls.hide()
    assert window.isVisible()
    window.close()


def test_background_mode_is_explicit_and_reversible():
    application = app()
    window = QWidget()
    window.show()
    controls = BackgroundControls(window, tray_available=True, tray_factory=FakeTray)
    assert window.isVisible()
    controls.hide()
    assert not window.isVisible()
    controls.restore()
    assert window.isVisible()
    assert [a.text() for a in controls.menu.actions() if not a.isSeparator()] == [
        'Show JARVIS', 'Run in background', 'Pause JARVIS', 'Exit JARVIS',
    ]
    assert 'microphone follows explicit voice consent' in controls.tray.tooltip
    window.close()


def test_pause_stops_the_background_work_without_closing_anything():
    application = app()
    window = QWidget()
    window.show()
    states = []
    def set_paused(paused):
        states.append(paused)
        window.paused = paused
    window.set_paused = set_paused
    window.paused = False
    controls = BackgroundControls(window, tray_available=True, tray_factory=FakeTray)
    controls.toggle_pause()
    assert states == [True]
    assert controls.pause_action.text() == 'Resume JARVIS'
    # Nothing was closed, and the window is still there.
    assert window.isVisible()
    controls.toggle_pause()
    assert states == [True, False]
    assert controls.pause_action.text() == 'Pause JARVIS'
    window.close()
