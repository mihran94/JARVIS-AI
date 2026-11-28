"""Capture dispatch stays on the Qt thread and respects emergency stop."""
import threading
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from desktop.bridge_screen import PhoneScreen
from remote.server import BridgeHandlerError


def test_phone_capture_runs_on_gui_thread_and_returns_a_bounded_jpeg(monkeypatch):
    app = QApplication.instance() or QApplication([])
    gui_thread = threading.get_ident()
    image = QImage(1920, 1080, QImage.Format.Format_RGB32)
    image.fill(0x336699)

    class Screen:
        def grabWindow(self, number):
            assert threading.get_ident() == gui_thread
            return SimpleNamespace(toImage=lambda: image)

    monkeypatch.setattr('desktop.bridge_screen.QGuiApplication.primaryScreen', lambda: Screen())
    capture = PhoneScreen(SimpleNamespace(stopped=False))
    result = []
    worker = threading.Thread(target=lambda: result.append(capture.frame()))
    worker.start()
    deadline = time.monotonic() + 2
    while worker.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        worker.join(.01)
    worker.join(.1)
    assert not worker.is_alive()
    frame = result[0]
    assert frame['width'] == 1600 and frame['height'] == 900
    import base64
    decoded = QImage.fromData(QByteArray(base64.b64decode(frame['image'].split(',', 1)[1])))
    assert decoded.width() == 1600


def test_stopped_desktop_never_queues_capture():
    app = QApplication.instance() or QApplication([])
    capture = PhoneScreen(SimpleNamespace(stopped=True))
    with pytest.raises(BridgeHandlerError, match='stopped'):
        capture.frame()
