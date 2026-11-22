"""Manual offline microphone transcription using an owner-installed Vosk model.

No recording on startup, no automatic transmission, no wake word, no audio files.

The microphone is opened only after `voice.consent.VoiceConsent` has granted
permission, exactly like the Windows adapter in `voice/windows_stt.py` does.
Without that permission the worker refuses to open the stream and says so in
its `completed` message; it never opens a microphone on its own, and a session
that is already running closes itself when the permission is taken back.
"""
import json
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from voice.consent import VoiceConsent
from voice.errors import VoiceError


def normalize_transcript(parts, max_chars=4000):
    """Normalize model output without saving or transmitting it."""
    if max_chars < 1:
        raise ValueError('max_chars must be positive')
    return ' '.join(str(part).strip() for part in parts if str(part).strip())[:max_chars]


def validate_model_path(path):
    if not isinstance(path, (str, Path)) or not str(path).strip():
        raise ValueError('Choose a local Vosk model folder first.')
    folder = Path(path).expanduser()
    if not folder.is_dir() or not (folder / "am").is_dir() or not (folder / "conf").is_dir():
        raise ValueError("Choose an extracted Vosk model directory containing am/ and conf/.")
    return str(folder)


class DictationWorker(QThread):
    """One bounded push-to-talk session, on a microphone the owner allowed.

    The permission is held in `VoiceConsent`, the single place where the
    microphone permission of this project lives. The worker checks it before
    it opens the stream, checks it again after the model has been loaded, and
    stops when the owner takes the permission back during the session.
    """

    recognized = Signal(str)
    completed = Signal(str)

    def __init__(self, model_path, parent=None, consent=None):
        super().__init__(parent)
        self.model_path = validate_model_path(model_path)
        self.consent = consent if consent is not None else VoiceConsent()

    def run(self):
        try:
            self.consent.require_listening()
        except VoiceError as error:
            self.completed.emit('Dictation refused: ' + str(error))
            return
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer
            if self.isInterruptionRequested():
                self.completed.emit('Dictation cancelled before model load')
                return
            model = Model(self.model_path)
            if self.isInterruptionRequested():
                self.completed.emit('Dictation cancelled during model load')
                return
            # The permission is checked again here: loading the model takes a
            # while, and the owner may close the microphone in the meantime.
            try:
                self.consent.require_listening()
            except VoiceError as error:
                self.completed.emit('Dictation refused: ' + str(error))
                return
            recognizer = KaldiRecognizer(model, 16000)
            pieces = []
            overflow_seen = False
            # Single, bounded push-to-talk session: at most 15 seconds.
            with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16",
                                   channels=1) as microphone:
                for _ in range(60):
                    if self.isInterruptionRequested():
                        self.completed.emit("Dictation cancelled")
                        return
                    if not self.consent.listening:
                        self.completed.emit("Dictation stopped: the microphone was closed.")
                        return
                    audio, overflow = microphone.read(4000)
                    overflow_seen = overflow_seen or bool(overflow)
                    if recognizer.AcceptWaveform(bytes(audio)):
                        value = json.loads(recognizer.Result()).get("text", "").strip()
                        if value:
                            pieces.append(value)
                final = json.loads(recognizer.FinalResult()).get("text", "").strip()
                if final:
                    pieces.append(final)
            if not self.isInterruptionRequested():
                transcript = normalize_transcript(pieces)
                if transcript:
                    self.recognized.emit(transcript)
                    self.completed.emit("Dictation finished (not sent)" + (" · audio overflow detected" if overflow_seen else ""))
                else:
                    self.completed.emit("No speech recognized; nothing inserted" + (" · audio overflow detected" if overflow_seen else ""))
            else:
                self.completed.emit("Dictation cancelled")
        except Exception as exc:
            self.completed.emit("Microphone unavailable: " + type(exc).__name__)
