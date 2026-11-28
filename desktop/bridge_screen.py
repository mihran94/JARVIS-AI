"""Bounded, on-demand primary-screen frames for an authenticated phone."""
import base64
import threading

from PySide6.QtCore import QObject, Signal, Slot, QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication

from remote.server import BridgeHandlerError


class PhoneScreen(QObject):
    requested = Signal(object)

    def __init__(self, policy, parent=None):
        super().__init__(parent)
        self.policy = policy
        self._lock = threading.Lock()
        self.requested.connect(self._capture, Qt.ConnectionType.QueuedConnection)

    def frame(self):
        if self.policy.stopped:
            raise BridgeHandlerError(409, 'Screen viewing is stopped on the PC.')
        if not self._lock.acquire(blocking=False):
            raise BridgeHandlerError(429, 'A screen frame is already being captured.')
        try:
            request = {'event': threading.Event(), 'cancelled': False}
            self.requested.emit(request)
            if not request['event'].wait(3):
                request['cancelled'] = True
                raise BridgeHandlerError(503, 'The PC display is not responding.')
            if 'frame' not in request:
                raise BridgeHandlerError(503, 'The PC screen is unavailable or locked.')
            return request['frame']
        finally:
            self._lock.release()

    @Slot(object)
    def _capture(self, request):
        try:
            if request['cancelled'] or self.policy.stopped:
                return
            screen = QGuiApplication.primaryScreen()
            if screen is None:
                return
            image = screen.grabWindow(0).toImage()
            if image.isNull():
                return
            if image.width() > 1600:
                image = image.scaledToWidth(1600, Qt.TransformationMode.SmoothTransformation)
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            if not image.save(buffer, 'JPEG', 65):
                return
            request['frame'] = {
                'image': 'data:image/jpeg;base64,' + base64.b64encode(bytes(data)).decode('ascii'),
                'width': image.width(), 'height': image.height(),
            }
        finally:
            request['event'].set()
