"""Session-only camera preview and on-request snapshots."""
from time import monotonic
from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QComboBox, QGroupBox, QLabel, QVBoxLayout

try:
    from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices, QVideoSink
except ImportError:
    QCamera = None


class CameraPanel(QGroupBox):
    def __init__(self, store, policy, toggle, parent=None):
        super().__init__('Camera', parent)
        self.store = store
        self.policy = policy
        self.toggle = toggle
        self.frame = QImage()
        self.frame_updated_at = 0.0
        self.camera = None
        layout = QVBoxLayout(self)
        self.choice = QComboBox()
        self.choice.setAccessibleName('Camera device')
        self.choice.currentIndexChanged.connect(self.select_device)
        layout.addWidget(self.choice)
        note = QLabel('During Gemini voice, Camera On shares one frame per second with Google. '
                      'The HUD preview is optional. Camera Off stops sharing.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.preview = QLabel()
        self.preview.setAccessibleName('Camera preview')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedHeight(105)
        self.preview.hide()
        if QCamera is not None:
            self.devices = QMediaDevices(self)
            self.devices.videoInputsChanged.connect(self.refresh_devices)
            self.capture = QMediaCaptureSession(self)
            self.sink = QVideoSink(self)
            self.sink.videoFrameChanged.connect(self.update_frame)
            self.capture.setVideoSink(self.sink)
        self.refresh_devices()
        toggle.toggled.connect(self.set_enabled)

    def refresh_devices(self):
        self.choice.blockSignals(True)
        self.choice.clear()
        self.choice.addItem('Windows default', b'')
        if QCamera is not None:
            for device in QMediaDevices.videoInputs():
                self.choice.addItem(device.description(), bytes(device.id()))
        try:
            saved = bytes.fromhex(self.store.get('camera:device', '') or '')
        except (TypeError, ValueError):
            # A damaged preference must not prevent the whole desktop opening.
            saved = b''
        self.choice.setCurrentIndex(max(0, self.choice.findData(saved)))
        self.choice.blockSignals(False)
        available = QCamera is not None and bool(QMediaDevices.videoInputs())
        if not available:
            self.toggle.setChecked(False)
        self.toggle.setEnabled(available)

    def select_device(self):
        selected = self.choice.currentData() or b''
        self.store.set('camera:device', bytes(selected).hex())
        if self.toggle.isChecked():
            self.set_enabled(False)
            self.set_enabled(True)

    def set_enabled(self, enabled):
        if not enabled:
            if self.camera is not None:
                self.camera.stop()
                self.capture.setCamera(None)
                self.camera.deleteLater()
                self.camera = None
            self.frame = QImage()
            self.frame_updated_at = 0.0
            self.preview.clear()
            self.toggle.setText('Camera off')
            return
        if QCamera is None or self.policy.stopped:
            self.toggle.setChecked(False)
            return
        device = QMediaDevices.defaultVideoInput()
        selected = self.choice.currentData()
        for candidate in QMediaDevices.videoInputs():
            if bytes(candidate.id()) == selected:
                device = candidate
                break
        if device.isNull():
            self.toggle.setChecked(False)
            return
        self.camera = QCamera(device, self)
        self.camera.errorOccurred.connect(lambda *_: self.toggle.setChecked(False))
        self.capture.setCamera(self.camera)
        self.preview.setText('Starting camera…')
        self.toggle.setText('Camera on')
        self.camera.start()

    def update_frame(self, frame):
        if self.camera is not None and frame.isValid():
            self.frame = frame.toImage().scaled(QSize(640, 480), Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)
            self.frame_updated_at = monotonic()
            if self.preview.isVisible():
                self.preview.setPixmap(QPixmap.fromImage(self.frame).scaled(
                    self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))

    def snapshot(self):
        if (self.camera is None or not self.camera.isActive() or self.frame.isNull()
                or monotonic() - self.frame_updated_at > 2.0):
            return b''
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        return bytes(buffer.data()) if self.frame.save(buffer, 'JPEG', 80) else b''
