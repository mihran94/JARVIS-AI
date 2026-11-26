"""Local input level and speaker checks using the default audio devices."""
from array import array
from math import sin, tau
from time import monotonic

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

try:
    from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QAudioSource, QMediaDevices
except ImportError:
    # The desktop can run on systems without Qt's native multimedia libraries.
    QAudio = QAudioFormat = QAudioSink = QAudioSource = QMediaDevices = None


class AudioTest(QGroupBox):
    """Capture only for a level meter, then discard the samples."""

    finished = Signal()

    def __init__(self, voice, policy, store=None):
        super().__init__('Audio devices and testing')
        self.voice = voice
        self.policy = policy
        self.store = store
        self.stream = None
        self.buffer = None
        self.mode = None
        self.peak = 0
        self.deadline = 0
        self.timer = QTimer(self, interval=80)
        self.timer.timeout.connect(self.poll)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(7)
        self.devices = QLabel('Open Settings to detect the default audio devices.')
        self.devices.setWordWrap(True)
        self.devices.hide()
        selectors = QGridLayout()
        self.device_choices = {}
        for row, (mode, label) in enumerate((('microphone', 'Microphone'), ('speaker', 'Speaker'))):
            choice = QComboBox()
            choice.setAccessibleName(label + ' device')
            selectors.addWidget(QLabel(label), row, 0)
            selectors.addWidget(choice, row, 1)
            self.device_choices[mode] = choice
        save = QPushButton('Save audio devices')
        save.clicked.connect(self.save_devices)
        selectors.addWidget(save, 2, 0, 1, 2)
        layout.addLayout(selectors)
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
        self.level.setValue(0)
        self.level.setTextVisible(False)
        self.level.setAccessibleName('Microphone level')
        meters = QGridLayout()
        meters.addWidget(QLabel('Microphone level'), 0, 0)
        meters.addWidget(self.level, 0, 1)
        self.level.setFixedHeight(16)
        self.speaker_level = QProgressBar()
        self.speaker_level.setRange(0, 100)
        self.speaker_level.setValue(0)
        self.speaker_level.setAccessibleName('Speaker test level')
        self.speaker_level.setFixedHeight(16)
        meters.addWidget(QLabel('Speaker test level'), 1, 0)
        meters.addWidget(self.speaker_level, 1, 1)
        layout.addLayout(meters)
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
        for mode, devices in (('microphone', inputs), ('speaker', outputs)):
            choice = self.device_choices[mode]
            saved = self.saved_device_id(mode)
            choice.clear()
            choice.addItem('Windows default', '')
            for device in devices:
                choice.addItem(device.description(), bytes(device.id()).hex())
            choice.setCurrentIndex(max(0, choice.findData(saved)))

    def saved_device_id(self, mode):
        return self.store.get('audio:device:' + mode, '') if self.store else ''

    def save_devices(self):
        if self.store is None:
            return
        for mode, choice in self.device_choices.items():
            self.store.set('audio:device:' + mode, choice.currentData() or '')
        self.status.setText('Audio devices saved.')

    def audio_device(self, mode, *, use_selection=False):
        picked = self.device_choices[mode].currentData() if use_selection else self.saved_device_id(mode)
        microphone = mode == 'microphone'
        fallback = QMediaDevices.defaultAudioInput if microphone else QMediaDevices.defaultAudioOutput
        if picked:
            devices = QMediaDevices.audioInputs() if microphone else QMediaDevices.audioOutputs()
            for device in devices:
                if bytes(device.id()).hex() == picked:
                    return device
        return fallback()

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
        if mode == 'microphone' and self.voice.microphone_muted:
            self.status.setText('Unmute the microphone before testing it.')
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
        device = self.audio_device('microphone', use_selection=True)
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
        device = self.audio_device('speaker', use_selection=True)
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
        self.speaker_level.setValue(round(4500 * 100 / 32768))

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
            self.speaker_level.setValue(0)
            buffer.close()
            buffer.deleteLater()
        self.voice.audio_test_active = False
        self.voice.refresh()
        self.status.setText(message)
        if self.voice.continuous and self.voice.consent.listening:
            self.voice.wake_timer.start(350)
        self.finished.emit()
