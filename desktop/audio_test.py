"""Local input level and speaker checks using the default audio devices."""
from array import array
from math import sin, tau
from time import monotonic

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QTimer, Signal
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QProgressBar, QPushButton, QVBoxLayout

try:
    from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QAudioSource, QMediaDevices
except ImportError:
    # The desktop can run on systems without Qt's native multimedia libraries.
    QAudio = QAudioFormat = QAudioSink = QAudioSource = QMediaDevices = None


class AudioTest(QGroupBox):
    """Capture only for a level meter, then discard the samples."""

    finished = Signal()

    def __init__(self, voice, policy):
        super().__init__('Audio devices and testing')
        self.voice = voice
        self.policy = policy
        self.stream = None
        self.buffer = None
        self.mode = None
        self.peak = 0
        self.deadline = 0
        self.timer = QTimer(self, interval=80)
        self.timer.timeout.connect(self.poll)
        layout = QVBoxLayout(self)
        self.devices = QLabel('Open Settings to detect the default audio devices.')
        self.devices.setWordWrap(True)
        layout.addWidget(self.devices)
        controls = QGridLayout()
        for index, (label, slot) in enumerate((
            ('Refresh', self.refresh_devices), ('Test microphone', self.test_microphone),
            ('Test speaker', self.test_speaker), ('Stop test', self.stop),
        )):
            button = QPushButton(label)
            button.clicked.connect(slot)
            controls.addWidget(button, index // 2, index % 2)
        layout.addLayout(controls)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setAccessibleName('Microphone level')
        layout.addWidget(self.level)
        self.status = QLabel('Microphone test needs permission in Voice. Tests stay on this PC.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        voice.activity_changed.connect(self.check_permission)

    def refresh_devices(self):
        if QMediaDevices is None:
            self.devices.setText('Audio device detection is unavailable on this installation.')
            return
        inputs, outputs = QMediaDevices.audioInputs(), QMediaDevices.audioOutputs()
        mic, speaker = QMediaDevices.defaultAudioInput(), QMediaDevices.defaultAudioOutput()
        self.devices.setText(
            f'Microphone: {mic.description() or "not detected"} ({len(inputs)} inputs)\n'
            f'Speaker: {speaker.description() or "not detected"} ({len(outputs)} outputs)')

    def ready(self, mode):
        if QMediaDevices is None:
            self.status.setText('Audio testing is unavailable on this installation.')
            return False
        if self.policy.stopped or self.voice.consent.stopped:
            self.status.setText('Resume JARVIS and Voice before testing audio.')
            return False
        if self.mode or self.voice.live_voice_active or self.voice.playback_busy or self.voice.pending_speech or (
                self.voice.worker is not None and self.voice.worker.isRunning()):
            self.status.setText('Stop the current voice session or audio test first.')
            return False
        if mode == 'microphone' and not self.voice.consent.listening:
            self.status.setText('Enable Allow the microphone in Voice before testing.')
            return False
        return True

    @staticmethod
    def pcm_format(device):
        fmt = device.preferredFormat()
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        return fmt if fmt.isValid() and device.isFormatSupported(fmt) else None

    def begin(self, mode, device, duration):
        fmt = None if device.isNull() else self.pcm_format(device)
        if fmt is None:
            self.status.setText(f'Default {mode} is missing or does not support this audio test.')
            return None
        self.mode = mode
        self.voice.audio_test_active = True
        self.voice.refresh()
        self.peak = 0
        self.level.setValue(0)
        self.deadline = monotonic() + duration
        self.timer.start()
        return fmt

    def test_microphone(self):
        if not self.ready('microphone'):
            return
        device = QMediaDevices.defaultAudioInput()
        fmt = self.begin('microphone', device, 5)
        if fmt is None:
            return
        self.status.setText('Speak now. Measuring microphone level for five seconds.')
        self.stream = QAudioSource(device, fmt, self)
        self.buffer = self.stream.start()
        if self.buffer is None:
            self.finish('Could not open the microphone. Check the default device and Windows permissions.')

    def test_speaker(self):
        if not self.ready('speaker'):
            return
        device = QMediaDevices.defaultAudioOutput()
        fmt = self.begin('speaker', device, 3)
        if fmt is None:
            return
        rate = fmt.sampleRate()
        frames = rate // 2
        samples = array('h')
        for frame in range(frames):
            envelope = min(1, frame / 240, (frames - frame) / 240)
            sample = int(4500 * envelope * sin(tau * 440 * frame / rate))
            samples.extend([sample] * fmt.channelCount())
        self.buffer = QBuffer(self)
        self.buffer.setData(QByteArray(samples.tobytes()))
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.status.setText('Playing a short tone through the default speaker.')
        self.stream = QAudioSink(device, fmt, self)
        self.stream.start(self.buffer)

    def poll(self):
        if self.stream is None:
            return
        if self.stream.error() != QAudio.Error.NoError:
            self.finish(f'{self.mode.capitalize()} test failed. Check the default device and permissions.')
        elif self.mode == 'microphone':
            raw = bytes(self.buffer.readAll())
            samples = array('h', raw[:len(raw) - len(raw) % 2])
            level = min(100, round(max(map(abs, samples), default=0) * 100 / 32768))
            self.level.setValue(level)
            self.peak = max(self.peak, level)
            if monotonic() >= self.deadline:
                self.finish(f'Microphone peak: {self.peak}%.' if self.peak >= 2
                            else 'No clear input detected. Check the microphone and input volume.')
        elif self.stream.state() == QAudio.State.IdleState and self.buffer.atEnd():
            self.finish('Tone played. If you heard it, the default audio output is working.')
        elif monotonic() >= self.deadline:
            self.finish('Speaker test did not finish. Check the default output.')

    def check_permission(self):
        if self.mode and (self.policy.stopped or self.voice.consent.stopped or
                          (self.mode == 'microphone' and not self.voice.consent.listening)):
            self.stop()

    def stop(self):
        if self.mode:
            self.finish('Audio test stopped.')

    def finish(self, message):
        self.timer.stop()
        mode, stream, buffer = self.mode, self.stream, self.buffer
        self.mode = self.stream = self.buffer = None
        if stream is not None:
            stream.stop()
            stream.deleteLater()
        if mode == 'speaker' and buffer is not None:
            buffer.close()
            buffer.deleteLater()
        self.voice.audio_test_active = False
        self.voice.refresh()
        self.status.setText(message)
        if self.voice.continuous and self.voice.consent.listening:
            self.voice.wake_timer.start(350)
        self.finished.emit()
