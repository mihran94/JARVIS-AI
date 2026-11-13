"""Explicit background/tray controls for the unified PySide6 desktop.

Adapted from the owner's JARVIS_BLUE_BACKGROUND_PATCH_01.zip (PyQt6).
There is deliberately no automatic hide-on-close or implicit microphone
activation: the user must select "Run in background" explicitly.
"""
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMenu, QStyle, QSystemTrayIcon


class BackgroundControls(QObject):
    def __init__(self, window, *, tray_available=None, tray_factory=QSystemTrayIcon):
        super().__init__(window)
        self.window = window
        self.tray = None
        self.menu = None
        if tray_available is None:
            tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        if not tray_available:
            return

        self.tray = tray_factory(window)
        self.tray.setIcon(window.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        self.tray.setToolTip('JARVIS AI — microphone follows explicit voice consent')
        self.menu = QMenu(window)
        self.menu.addAction('Show JARVIS', self.restore)
        self.menu.addAction('Run in background', self.hide)
        self.menu.addSeparator()
        self.menu.addAction('Exit JARVIS', self.request_exit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.activate)
        self.tray.show()

    def hide(self):
        """Hiding the window is allowed only when a visible tray can restore it."""
        if self.tray is not None and self.tray.isVisible():
            self.window.hide()

    def restore(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def request_exit(self):
        """Use the desktop's closeEvent for unsaved changes and active workers."""
        self.window.close()

    def activate(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.restore()
