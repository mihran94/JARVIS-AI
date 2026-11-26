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
import asyncio
import sys

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from voice.consent import VoiceConsent
from voice import azure_tts
from voice.echo_guard import EchoGuard
from voice.errors import VoiceError, VoiceUnavailable
from voice import local_stt
from voice.wake import DEFAULT_PHRASE, WakePhraseMatcher
from voice.windows_stt import WindowsSpeechRecognizer
from voice.windows_tts import WindowsTextToSpeech, speak_tamil_winrt


#: The languages the owner can speak and hear, and what they are called.
LANGUAGE_NAMES = {
    'en': 'English',
    'ta': 'தமிழ் (Tamil)',
    'ta_en': 'Tamil + Tanglish (offline)',
    'fr': 'Français (French)',
}


def default_recognizer_factory(consent, language='en'):
    """Prefer the local multilingual model for Tamil and mixed speech."""
    if language == 'ta_en' or (language == 'ta' and local_stt.ready()):
        return local_stt.LocalSpeechRecognizer(consent, language)
    return WindowsSpeechRecognizer(consent=consent, language=language)


def default_speaker_factory():
    """The Windows speaker. It raises `VoiceUnavailable` off Windows."""
    return WindowsTextToSpeech()


class VoiceWorker(QThread):
    """Runs one recognition request away from the Qt thread."""

    transcript = Signal(str)
    wake_call = Signal(str, str)
    failed = Signal(str)
    audio_level = Signal(int)

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
            set_cancel = getattr(recognizer, 'set_cancel_check', None)
            if callable(set_cancel):
                set_cancel(self.isInterruptionRequested)
            set_level = getattr(recognizer, 'set_level_listener', None)
            if callable(set_level):
                set_level(self.audio_level.emit)
            if self._mode in ('dialogue', 'continuous'):
                # One supervised turn: idle on the local wake recognizer,
                # then capture an utterance with the dictation grammar.
                # The desktop decides whether to send it; this worker never
                # calls providers or launches a PC action.
                while self.consent.listening and not self.isInterruptionRequested():
                    wake, command = recognizer.wait_for_wake_phrase(self._timeout)
                    if wake:
                        if not command and self.consent.listening and not self.isInterruptionRequested():
                            command = recognizer.recognize_once(8.0)
                        if self.consent.listening and not self.isInterruptionRequested():
                            self.wake_call.emit(wake, (command or '').strip()[:4000])
                        break
                    QThread.msleep(120)
            elif self._mode == 'wake':
                transcript, command = recognizer.wait_for_wake_phrase(self._timeout)
                if transcript and not self.isInterruptionRequested():
                    self.wake_call.emit(transcript, command or '')
            else:
                transcript = recognizer.recognize_once(self._timeout)
                if not self.isInterruptionRequested():
                    self.transcript.emit(transcript)
        except VoiceError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit('The speech recognition failed. No audio was kept.')
        finally:
            try:
                recognizer.stop()
            except Exception:
                pass


class VoiceSpeakerWorker(QThread):
    """SAPI playback off the UI thread, on its own initialized COM apartment."""

    failed = Signal(str)
    playing = Signal()
    cloud_usage = Signal(int, str)

    def __init__(self, speaker_factory, text, language='en', *, cloud=None, sample_language=None):
        super().__init__()
        self._speaker_factory = speaker_factory
        self._text = text
        self._language = language
        self._cloud = cloud
        self.uses_cloud = cloud is not None
        self._sample_language = sample_language

    def play_cloud(self, config):
        language, text = azure_tts.speech_text(
            self._text, self._language, sample_language=self._sample_language)
        try:
            audio = asyncio.run(azure_tts.cancellable_synthesis(
                config, text, language, self.isInterruptionRequested))
        except VoiceError as error:
            if not self.isInterruptionRequested():
                suffix = ' Trying the installed Windows voice.' if not self._sample_language else ''
                self.failed.emit(str(error) + suffix)
            return bool(self._sample_language) or self.isInterruptionRequested()
        if audio is None:
            return True
        self.cloud_usage.emit(len(text), azure_tts.VOICES[language][1])
        if not self.isInterruptionRequested():
            try:
                azure_tts.play_wav(audio, self.isInterruptionRequested, self.playing.emit)
            except (VoiceError, OSError) as error:
                self.failed.emit(str(error) if isinstance(error, VoiceError)
                                 else 'Windows could not prepare Azure audio for playback.')
        return True

    def run(self):
        apartment = None
        try:
            cloud, self._cloud = self._cloud, None
            if cloud and self.play_cloud(cloud):
                return
            if sys.platform == 'win32' and self._speaker_factory is default_speaker_factory:
                # The actual SAPI factory requires COM on its worker thread.
                # Test doubles and non-COM backends must not require pywin32.
                import pythoncom
                apartment = pythoncom
                apartment.CoInitialize()
            if self.isInterruptionRequested():
                return
            speaker = self._speaker_factory()
            if self.isInterruptionRequested():
                return
            language = azure_tts.speech_text(self._text, self._language)[0] if cloud else self._language
            if language != 'ta' and any('஀' <= char <= '௿' for char in self._text):
                # No other voice can read the Tamil script, so Tamil text is
                # always spoken with a Tamil voice when one is installed.
                language = 'ta'
            if hasattr(speaker, 'select_language') and not speaker.select_language(language):
                if language == 'ta' and self._speaker_factory is default_speaker_factory:
                    speak_tamil_winrt(self._text, self.isInterruptionRequested, self.playing.emit)
                    return
                if language != 'en':
                    # English is the system default, so a missing English voice
                    # is not worth refusing to speak over. A missing Tamil or
                    # French voice is, because the text would be read wrongly.
                    self.failed.emit(
                        'No ' + LANGUAGE_NAMES.get(language, language) + ' speech voice is '
                        'installed. Install the Windows speech language pack, or choose another '
                        'language.')
                    return
            self.playing.emit()
            if hasattr(speaker, 'speak_interruptibly'):
                speaker.speak_interruptibly(self._text, self.isInterruptionRequested)
            elif not self.isInterruptionRequested():
                speaker.speak(self._text, language)
        except VoiceError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit('Windows speech playback failed. Check the audio output.')
        finally:
            if apartment is not None:
                apartment.CoUninitialize()


class VoicePanel(QWidget):
    """The microphone permission, the wake phrase and the voice adapters."""

    # The main Windows window uses this to draft spoken chat, never to
    # execute PC actions or send to a paid provider automatically.
    wake_detected = Signal(str, str)
    # A listen-once utterance is a chat draft, never an action or API call.
    utterance_detected = Signal(str)
    cycle_finished = Signal()
    speech_finished = Signal()
    activity_changed = Signal()
    audio_level = Signal(int)
    recognition_failed = Signal()
    feedback = Signal(str)
    cloud_usage = Signal(int, str)

    def __init__(self, *, consent=None, recognizer_factory=None, speaker_factory=None,
                 matcher=None, parent=None):
        super().__init__(parent)
        self.consent = consent if consent is not None else VoiceConsent()
        self.matcher = matcher if matcher is not None else WakePhraseMatcher()
        self._recognizer_factory = recognizer_factory or default_recognizer_factory
        self._speaker_factory = speaker_factory or default_speaker_factory
        self.worker = None
        self.audio_test_active = False
        self.live_voice_active = False
        self.speaker_worker = None
        self.muted = False
        self.microphone_muted = False
        self.pending_speech = ''
        self.pending_sample = None
        self.cloud_config = None
        self.spoken_text = ''
        self.echo_guard = EchoGuard()
        self.continuous = False
        self.discard_recognition = False
        self.wake_timer = QTimer(self)
        self.wake_timer.setSingleShot(True)
        self.wake_timer.timeout.connect(self.rearm_continuous)
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
            'Use the local microphone to add a draft to Chat, then review it before sending.')
        note.setWordWrap(True)
        layout.addWidget(note)

        consent_box = QGroupBox('Microphone')
        consent_layout = QFormLayout(consent_box)
        self.phrase = QLineEdit(self.matcher.canonical_phrase or DEFAULT_PHRASE)
        self.phrase.textChanged.connect(self.set_phrase)
        consent_layout.addRow('Wake phrase', self.phrase)
        self.language = QComboBox()
        for code, name in LANGUAGE_NAMES.items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(0)
        self.language.setToolTip(
            'Tamil + Tanglish uses the installed on-device multilingual speech model.')
        consent_layout.addRow('Speech language', self.language)
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
        self.mute_button = QPushButton('Mute replies')
        self.mute_button.setCheckable(True)
        self.mute_button.toggled.connect(self.set_muted)
        speak_layout.addRow(self.mute_button)
        self.privacy = QLabel()
        self.privacy.setWordWrap(True)
        speak_layout.addRow('Privacy', self.privacy)
        layout.addWidget(speak_box)
        layout.addStretch()

    # ---------------------------------------------------------------- actions

    def set_muted(self, muted):
        """Turn the spoken answers off without touching the microphone."""
        self.muted = muted
        self.mute_button.setText('Unmute replies' if muted else 'Mute replies')
        if muted:
            self.pending_speech = ''
            self.pending_sample = None
            if self.playback_busy:
                self.speaker_worker.requestInterruption()
        self.refresh()

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
                self.discard_recognition = True
                self.stop_continuous()
                self.cancel_listening()
        except VoiceError as error:
            self.allow.blockSignals(True)
            self.allow.setChecked(False)
            self.allow.blockSignals(False)
            self.status(str(error))
            return
        self.refresh()

    @property
    def language_code(self):
        """The language the owner chose for recognition and playback."""
        code = self.language.currentData() if hasattr(self, 'language') else None
        return code if code in LANGUAGE_NAMES else 'en'

    def set_language(self, code):
        """Choose the speech language. An unknown code is refused."""
        if code not in LANGUAGE_NAMES:
            return False
        index = self.language.findData(code)
        if index >= 0:
            self.language.setCurrentIndex(index)
        return True

    def listen(self, mode='once'):
        """Start one recognition request on a worker thread."""
        if self.microphone_muted or self.audio_test_active or self.live_voice_active:
            return
        if self.playback_busy:
            self.status('Wait for JARVIS to finish speaking.')
            return
        if self.worker is not None and self.worker.isRunning():
            self.status('The microphone is busy.')
            return
        try:
            self.consent.require_listening()
        except VoiceError as error:
            self.status(str(error))
            return
        if mode == 'continuous':
            self.continuous = True
        self.discard_recognition = False
        self.worker = VoiceWorker(self.consent, self._recognizer_factory, mode=mode,
                                  language=self.language_code)
        self.worker.audio_level.connect(self.forward_audio_level)
        self.worker.transcript.connect(self.on_transcript)
        self.worker.wake_call.connect(self.on_wake_call)
        self.worker.failed.connect(self.on_recognition_failed)
        self.worker.finished.connect(self.on_recognition_finished)
        # The thread is not running yet when start() returns, so the state
        # that is read straight afterwards would still say "not listening".
        # The worker tells the panel when it is really running, and the panel
        # refreshes then: the microphone is listening from that moment, and
        # the owner's interface says so.
        self.worker.started.connect(self.refresh)
        self.worker.start()
        self.refresh()

    @property
    def playback_busy(self):
        """True while a reply is being read aloud."""
        return self.speaker_worker is not None and self.speaker_worker.isRunning()

    @property
    def speaking(self) -> bool:
        """True while the reply is being read aloud.

        The state is read from the worker itself, not from a message the
        worker sent. A thread that is busy cannot always deliver its
        message at once, and the interface must be able to say that the
        assistant is speaking even when the message is still on its way.
        """
        return self.playback_busy

    @property
    def listening(self):
        return (self.consent.listening and self.worker is not None and self.worker.isRunning()
                and not self.worker.isInterruptionRequested())

    def stop_continuous(self):
        self.continuous = False
        self.wake_timer.stop()

    def rearm_continuous(self):
        if self.continuous and self.consent.listening and not self.playback_busy:
            self.listen('continuous')

    def forward_audio_level(self, value):
        if self.sender() is self.worker and self.listening:
            self.audio_level.emit(value)

    def on_recognition_failed(self, message):
        if self.sender() is self.worker:
            self.stop_continuous()
            self.status(message)
            self.recognition_failed.emit()

    def on_recognition_finished(self):
        if self.sender() is not self.worker:
            return
        self.audio_level.emit(0)
        pending, self.pending_speech = self.pending_speech, ''
        sample, self.pending_sample = self.pending_sample, None
        if pending:
            if sample:
                self.speak_response(pending, sample_language=sample)
            else:
                self.speak_response(pending)
        self.refresh()
        self.cycle_finished.emit()
        if self.continuous and not self.playback_busy:
            self.wake_timer.start(350)

    def accepts_recognition(self):
        source = self.sender()
        return (self.consent.listening and
                (source is None or (source is self.worker and not self.discard_recognition)))

    def on_transcript(self, text):
        """Show what was heard and whether it was a wake call."""
        if self.sender() is not None and not self.accepts_recognition():
            return
        if self.echo_guard.is_echo(text):
            self.status('Ignored possible echo of JARVIS speech.')
            return
        match = self.matcher.match(text)
        if match.is_wake_call:
            command = self.matcher.extract_command(text)
            line = f'{text}\nWake call: {match.matched_phrase} ({match.confidence:.2f})'
            if command:
                line += f'\nCommand: {command}'
        else:
            line = f'{text}\nNot a wake call.'
        self.append(line)
        if not self.accepts_recognition():
            return
        if match.is_wake_call:
            self.wake_detected.emit(text, command or '')
        elif text.strip():
            self.utterance_detected.emit(text.strip())

    def on_wake_call(self, transcript, command):
        """Show a wake call and offer it to the desktop as a draft only."""
        if not transcript or not self.accepts_recognition():
            return
        if self.echo_guard.is_echo(transcript):
            self.status('Ignored possible echo of JARVIS speech.')
            return
        line = f'{transcript}\nWake call.'
        if command:
            line += f'\nCommand: {command}'
        self.append(line)
        self.wake_detected.emit(transcript, command)

    def speak(self):
        """Start optional text-to-speech without blocking Emergency Stop."""
        self.speak_response(self.speak_text.text())

    def speak_response(self, text, *, sample_language=None, local_only=False):
        """Speak on a dedicated worker so Qt remains responsive."""
        if self.audio_test_active or self.live_voice_active:
            return
        text = (text or '').strip()[:600]
        if not text:
            return
        if self.muted:
            self.status('The voice is muted, so nothing was said.')
            return
        if self.consent.stopped:
            return
        if self.playback_busy or self.pending_speech:
            self.status('A reply is already scheduled for playback.')
            return
        self.wake_timer.stop()
        self.spoken_text = text
        if self.worker is not None and self.worker.isRunning():
            if local_only:
                return
            self.pending_speech = text
            self.pending_sample = sample_language
            self.cancel_listening()
            return
        cloud = None
        if self.cloud_config and not local_only:
            try:
                cloud = self.cloud_config()
            except VoiceError as error:
                if not sample_language:
                    self.status(str(error) + ' Trying the installed Windows voice.')
                else:
                    self.status(str(error))
                    return
        if sample_language and not cloud:
            self.status('Allow Azure Speech in API Provider Manager before testing cloud voices.')
            return
        spoken_language = 'ta' if self.language_code == 'ta_en' else self.language_code
        self.speaker_worker = VoiceSpeakerWorker(self._speaker_factory, text, spoken_language,
                                                 cloud=cloud, sample_language=sample_language)
        self.speaker_worker.failed.connect(self.status)
        self.speaker_worker.cloud_usage.connect(self.cloud_usage)
        self.speaker_worker.playing.connect(self.on_playback_started)
        self.speaker_worker.finished.connect(self.on_playback_finished)
        self.speaker_worker.start()
        self.refresh()

    def on_playback_started(self):
        if self.sender() is self.speaker_worker and not self.muted and not self.consent.stopped:
            self.echo_guard.record(self.spoken_text)
            self.refresh()

    def on_playback_finished(self):
        if self.sender() is not self.speaker_worker:
            return
        self.refresh()
        self.speech_finished.emit()
        if self.continuous:
            self.wake_timer.start(350)

    def cancel_listening(self):
        """Stop an in-flight listen without revoking the owner's mic consent.

        A Windows recognition call can take until its bounded timeout to
        return. Pending worker output is ignored by desktop opt-in guards.
        """
        if self.worker is not None and self.worker.isRunning():
            self.discard_recognition = True
            self.worker.requestInterruption()
            self.refresh()

    def cancel_cloud_speech(self):
        self.pending_speech = ''
        self.pending_sample = None
        worker = self.speaker_worker
        if worker and worker.uses_cloud and worker.isRunning():
            worker.requestInterruption()

    def stop_voice(self):
        """Revoke microphone consent and request worker interruption."""
        self.consent.stop()
        self.discard_recognition = True
        self.stop_continuous()
        self.pending_speech = ''
        self.pending_sample = None
        self.echo_guard.reset()
        self.cancel_listening()
        if self.speaker_worker is not None and self.speaker_worker.isRunning():
            self.speaker_worker.requestInterruption()
        self.refresh()

    def wait_for_workers(self, milliseconds=11000):
        """On application exit, never destroy a QThread still running."""
        for worker in (self.worker, self.speaker_worker):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(milliseconds)

    def resume_voice(self):
        """Allow the microphone to be opened again. The owner grants it again."""
        self.consent.resume()
        self.refresh()

    # ----------------------------------------------------------------- status

    def status(self, message):
        """Show a line of feedback."""
        self.append(message)
        self.feedback.emit(message)

    def privacy_line(self):
        """What the voice is doing with the microphone, in words."""
        if self.worker is not None and self.worker.isRunning() and not self.listening:
            return 'Stopping the active listening session.'
        if self.consent.stopped:
            return 'Stopped: the microphone is closed until the owner allows it again.'
        if self.listening:
            return 'A listening session is active.'
        if self.consent.granted:
            return 'Microphone access is allowed for listening sessions.'
        return 'The microphone is closed. Nothing is recorded.'

    def append(self, line):
        """Add a line to the transcript area."""
        self.transcript.appendPlainText(line)

    def refresh(self):
        """Update the state that the owner sees."""
        self.permission.setText(self.consent.listener)
        self.privacy.setText(self.privacy_line())
        self.allow.blockSignals(True)
        self.allow.setChecked(self.consent.granted)
        self.allow.blockSignals(False)
        self.stop_button.setEnabled(not self.consent.stopped)
        self.resume_button.setEnabled(self.consent.stopped)
        microphone_ready = (self.consent.listening and not self.microphone_muted
                            and not self.audio_test_active and not self.live_voice_active
                            and not self.playback_busy and
                            not (self.worker is not None and self.worker.isRunning()))
        self.listen_button.setEnabled(microphone_ready)
        self.wake_button.setEnabled(microphone_ready)
        self.continuous_button.setEnabled(microphone_ready and not self.continuous)
        self.speak_button.setEnabled(not self.muted and not self.consent.stopped
                                     and not self.audio_test_active and not self.live_voice_active and
                                     not self.playback_busy and not self.pending_speech)
        self.activity_changed.emit()


__all__ = ['VoicePanel', 'VoiceWorker', 'VoiceSpeakerWorker',
           'default_recognizer_factory', 'default_speaker_factory']
