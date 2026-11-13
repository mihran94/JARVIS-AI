"""The Voice page.

The page owns the microphone permission, the wake phrase and the two Windows
adapters. Three rules shape it:

- the microphone is never opened without the owner's permission, and the
  permission is shown on the page;
- the recogniser runs on a worker thread, because a widget may only be used
  on the Qt thread;
- on a machine that is not Windows the adapters are not available, and the
  page says so instead of pretending.
"""
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from voice.consent import VoiceConsent
from voice.errors import VoiceError, VoiceUnavailable
from voice.wake import DEFAULT_PHRASE, WakePhraseMatcher
from voice.windows_stt import WindowsSpeechRecognizer
from voice.windows_tts import WindowsTextToSpeech


def default_recognizer_factory(consent, language='en'):
    """The Windows recogniser. It raises `VoiceUnavailable` off Windows."""
    return WindowsSpeechRecognizer(consent=consent, language=language)


def default_speaker_factory():
    """The Windows speaker. It raises `VoiceUnavailable` off Windows."""
    return WindowsTextToSpeech()


class VoiceWorker(QThread):
    """Runs one recognition request away from the Qt thread."""

    transcript = Signal(str)
    wake_call = Signal(str, str)
    failed = Signal(str)

    def __init__(self, consent, recognizer_factory, mode='once', timeout=5.0, language='en'):
        super().__init__()
        self.consent = consent
        self._factory = recognizer_factory
        self._mode = mode
        self._timeout = timeout
        self._language = language

    def run(self):
        try:
            self.consent.require_listening()
        except VoiceError as error:
            self.failed.emit(str(error))
            return
        try:
            recognizer = self._factory(self.consent, self._language)
        except VoiceUnavailable as error:
            self.failed.emit(str(error))
            return
        except VoiceError as error:
            self.failed.emit(str(error))
            return
        try:
            if self._mode in ('wake', 'continuous'):
                while self.consent.listening and not self.isInterruptionRequested():
                    transcript, command = recognizer.wait_for_wake_phrase(self._timeout)
                    if transcript:
                        self.wake_call.emit(transcript, command or '')
                    if self._mode == 'wake':
                        break
                    # Avoid spinning on devices that return instantly with no
                    # speech. The owner can stop listening at any point.
                    QThread.msleep(120)
            else:
                self.transcript.emit(recognizer.recognize_once(self._timeout))
        except VoiceError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit('The speech recognition failed. No audio was kept.')
        finally:
            try:
                recognizer.stop()
            except Exception:
                pass


class VoicePanel(QWidget):
    """The microphone permission, the wake phrase and the voice adapters."""

    # The main Windows window uses this to draft spoken chat, never to
    # execute PC actions or send to a paid provider automatically.
    wake_detected = Signal(str, str)
    # A listen-once utterance is a chat draft, never an action or API call.
    utterance_detected = Signal(str)

    def __init__(self, *, consent=None, recognizer_factory=None, speaker_factory=None,
                 matcher=None, parent=None):
        super().__init__(parent)
        self.consent = consent if consent is not None else VoiceConsent()
        self.matcher = matcher if matcher is not None else WakePhraseMatcher()
        self._recognizer_factory = recognizer_factory or default_recognizer_factory
        self._speaker_factory = speaker_factory or default_speaker_factory
        self.worker = None
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 10, 10)
        title = QLabel('Voice')
        title.setStyleSheet('font-size:24px;font-weight:600')
        layout.addWidget(title)
        note = QLabel(
            'Say Hey Jarvis, or dictate one message. Speech is added to Chat as a '
            'draft; review and press Ask JARVIS before a provider is contacted. '
            'No voice command can run a PC action without your approval. '
            'The microphone needs your permission and an installed Windows '
            'speech language pack.')
        note.setWordWrap(True)
        layout.addWidget(note)

        consent_box = QGroupBox('Microphone')
        consent_layout = QFormLayout(consent_box)
        self.phrase = QLineEdit(self.matcher.canonical_phrase or DEFAULT_PHRASE)
        self.phrase.textChanged.connect(self.set_phrase)
        consent_layout.addRow('Wake phrase', self.phrase)
        self.allow = QCheckBox('Allow the microphone')
        self.allow.toggled.connect(self.set_allowed)
        consent_layout.addRow(self.allow)
        self.permission = QLabel()
        self.permission.setWordWrap(True)
        consent_layout.addRow('State', self.permission)
        layout.addWidget(consent_box)

        talk_box = QGroupBox('Talk')
        talk_layout = QVBoxLayout(talk_box)
        row = QHBoxLayout()
        self.listen_button = QPushButton('Talk once (draft only)')
        self.listen_button.clicked.connect(lambda: self.listen('once'))
        row.addWidget(self.listen_button)
        self.wake_button = QPushButton('Wait for the wake phrase')
        self.wake_button.clicked.connect(lambda: self.listen('wake'))
        row.addWidget(self.wake_button)
        self.continuous_button = QPushButton('Keep listening for Hey Jarvis')
        self.continuous_button.setToolTip(
            'Only while explicitly allowed; microphone stops on Stop or exit')
        self.continuous_button.clicked.connect(lambda: self.listen('continuous'))
        row.addWidget(self.continuous_button)
        self.stop_button = QPushButton('Stop voice')
        self.stop_button.clicked.connect(self.stop_voice)
        row.addWidget(self.stop_button)
        self.resume_button = QPushButton('Resume voice')
        self.resume_button.clicked.connect(self.resume_voice)
        row.addWidget(self.resume_button)
        talk_layout.addLayout(row)
        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setMaximumHeight(160)
        self.transcript.setPlaceholderText('What was heard appears here.')
        talk_layout.addWidget(self.transcript)
        layout.addWidget(talk_box)

        speak_box = QGroupBox('Speak')
        speak_layout = QFormLayout(speak_box)
        self.speak_text = QLineEdit()
        self.speak_text.setPlaceholderText('Text for JARVIS to say')
        speak_layout.addRow('Text', self.speak_text)
        self.speak_button = QPushButton('Say it')
        self.speak_button.clicked.connect(self.speak)
        speak_layout.addRow(self.speak_button)
        layout.addWidget(speak_box)
        layout.addStretch()

    # ---------------------------------------------------------------- actions

    def set_phrase(self, phrase):
        """The wake phrase the owner typed."""
        text = phrase.strip()
        if text:
            self.matcher = WakePhraseMatcher(text)

    def set_allowed(self, allowed):
        """The owner's microphone permission."""
        try:
            if allowed:
                self.consent.grant()
            else:
                self.consent.revoke()
        except VoiceError as error:
            self.allow.blockSignals(True)
            self.allow.setChecked(False)
            self.allow.blockSignals(False)
            self.status(str(error))
            return
        self.refresh()

    def listen(self, mode='once'):
        """Start one recognition request on a worker thread."""
        if self.worker is not None and self.worker.isRunning():
            self.status('The microphone is busy.')
            return
        try:
            self.consent.require_listening()
        except VoiceError as error:
            self.status(str(error))
            return
        self.worker = VoiceWorker(self.consent, self._recognizer_factory, mode=mode)
        self.worker.transcript.connect(self.on_transcript)
        self.worker.wake_call.connect(self.on_wake_call)
        self.worker.failed.connect(self.status)
        self.worker.finished.connect(self.refresh)
        self.worker.start()
        self.status('Listening for Hey Jarvis (owner allowed).' if mode == 'continuous'
                    else 'Listening…')

    def on_transcript(self, text):
        """Show what was heard and whether it was a wake call."""
        match = self.matcher.match(text)
        if match.is_wake_call:
            command = self.matcher.extract_command(text)
            line = f'{text}\nWake call: {match.matched_phrase} ({match.confidence:.2f})'
            if command:
                line += f'\nCommand: {command}'
        else:
            line = f'{text}\nNot a wake call.'
        self.append(line)
        if not self.consent.listening:
            return
        if match.is_wake_call:
            self.wake_detected.emit(text, command or '')
        elif text.strip():
            self.utterance_detected.emit(text.strip())

    def on_wake_call(self, transcript, command):
        """Show a wake call and offer it to the desktop as a draft only."""
        if not transcript or not self.consent.listening:
            return
        line = f'{transcript}\nWake call.'
        if command:
            line += f'\nCommand: {command}'
        self.append(line)
        self.wake_detected.emit(transcript, command)

    def speak(self):
        """Say the text with the Windows voice."""
        text = self.speak_text.text().strip()
        if not text:
            return
        try:
            speaker = self._speaker_factory()
        except VoiceUnavailable as error:
            self.status(str(error))
            return
        except VoiceError as error:
            self.status(str(error))
            return
        try:
            speaker.speak(text)
            self.status('Speaking.')
        except VoiceError as error:
            self.status(str(error))

    def stop_voice(self):
        """Close the microphone at once."""
        self.consent.stop()
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
        self.refresh()

    def resume_voice(self):
        """Allow the microphone to be opened again. The owner grants it again."""
        self.consent.resume()
        self.refresh()

    # ----------------------------------------------------------------- status

    def status(self, message):
        """Show a line of feedback."""
        self.append(message)

    def append(self, line):
        """Add a line to the transcript area."""
        self.transcript.appendPlainText(line)

    def refresh(self):
        """Update the state that the owner sees."""
        self.permission.setText(self.consent.listener)
        self.allow.blockSignals(True)
        self.allow.setChecked(self.consent.granted)
        self.allow.blockSignals(False)
        self.stop_button.setEnabled(not self.consent.stopped)
        self.resume_button.setEnabled(self.consent.stopped)
        self.listen_button.setEnabled(self.consent.listening)
        self.wake_button.setEnabled(self.consent.listening)
        self.continuous_button.setEnabled(
            self.consent.listening and not (
                self.worker is not None and self.worker.isRunning()))


__all__ = ['VoicePanel', 'VoiceWorker', 'default_recognizer_factory', 'default_speaker_factory']
