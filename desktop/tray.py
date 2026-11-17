"""Explicit background/tray controls for the unified PySide6 desktop.

Adapted from the owner's JARVIS_BLUE_BACKGROUND_PATCH_01.zip (PyQt6).
There is deliberately no automatic hide-on-close or implicit microphone
activation: the user must select "Run in background" explicitly.

THE ALWAYS-ON SESSION
    The owner requirement for this draft is that closing the window can keep
    JARVIS in the system tray, with Pause and Exit controls, and that
    JARVIS can start when Windows signs in.

    So the tray menu carries three things: show the window, pause the
    background work, and exit. Pause stops the automatic checks and the
    background preparation of changes; it does not close anything, and the
    work that was saved can be resumed from the Review screen.
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
        self.pause_action = self.menu.addAction('Pause JARVIS', self.toggle_pause)
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

    def toggle_pause(self):
        """Pause or resume the background work, without closing anything."""
        paused = not bool(getattr(self.window, 'paused', False))
        self.window.set_paused(paused)
        self.pause_action.setText('Resume JARVIS' if paused else 'Pause JARVIS')

    def request_exit(self):
        """Use the desktop's closeEvent for unsaved changes and active workers."""
        self.window.close()

    def activate(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.restore()
