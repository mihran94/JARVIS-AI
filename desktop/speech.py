"""Explicit, local text-to-speech playback; no microphone access or network use."""
from PySide6.QtCore import QThread, Signal


def speech_text(text, limit=2500):
    """Bound spoken content to avoid unreasonably long playback."""
    if not isinstance(text, str):
        raise TypeError("Speech input must be text")
    return text.strip()[:limit]


class SpeechWorker(QThread):
    completed = Signal(str)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = speech_text(text)
        self._engine = None

    def run(self):
        if not self.text:
            self.completed.emit("Nothing to speak")
            return
        try:
            import pyttsx3
            engine = pyttsx3.init()
            self._engine = engine
            if self.isInterruptionRequested():
                self.completed.emit("Cancelled")
                return
            engine.say(self.text)
            engine.runAndWait()
            self.completed.emit("Cancelled" if self.isInterruptionRequested() else "Speech finished")
        except Exception as exc:
            self.completed.emit("Speech unavailable: " + type(exc).__name__)
        finally:
            self._engine = None
