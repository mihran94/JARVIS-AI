"""Manual offline microphone transcription using an owner-installed Vosk model.

No recording on startup, no automatic transmission, no wake word, no audio files.
"""
import json
from pathlib import Path

from PySide6.QtCore import QThread, Signal


def validate_model_path(path):
    if not isinstance(path, (str, Path)) or not str(path).strip():
        raise ValueError('Choose a local Vosk model folder first.')
    folder = Path(path).expanduser()
    if not folder.is_dir() or not (folder / "am").is_dir() or not (folder / "conf").is_dir():
        raise ValueError("Choose an extracted Vosk model directory containing am/ and conf/.")
    return str(folder)


class DictationWorker(QThread):
    recognized = Signal(str)
    completed = Signal(str)

    def __init__(self, model_path, parent=None):
        super().__init__(parent)
        self.model_path = validate_model_path(model_path)

    def run(self):
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer
            model = Model(self.model_path)
            recognizer = KaldiRecognizer(model, 16000)
            pieces = []
            # Single, bounded push-to-talk session: at most 15 seconds.
            with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16",
                                   channels=1) as microphone:
                for _ in range(60):
                    if self.isInterruptionRequested():
                        self.completed.emit("Dictation cancelled")
                        return
                    audio, overflow = microphone.read(4000)
                    if recognizer.AcceptWaveform(bytes(audio)):
                        value = json.loads(recognizer.Result()).get("text", "").strip()
                        if value:
                            pieces.append(value)
                final = json.loads(recognizer.FinalResult()).get("text", "").strip()
                if final:
                    pieces.append(final)
            if not self.isInterruptionRequested():
                self.recognized.emit(" ".join(pieces).strip())
                self.completed.emit("Dictation finished (not sent)")
            else:
                self.completed.emit("Dictation cancelled")
        except Exception as exc:
            self.completed.emit("Microphone unavailable: " + type(exc).__name__)
