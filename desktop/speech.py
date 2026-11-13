"""Explicit, local text-to-speech playback; no microphone access or network use."""
from PySide6.QtCore import QThread, Signal


def speech_text(text, limit=2500):
    """Bound spoken content to avoid unreasonably long playback."""
    if not isinstance(text, str):
        raise TypeError("Speech input must be text")
    return text.strip()[:limit]


def speech_chunks(text, max_chars=180):
    """Split bounded speech into phrases so cancellation is checked between phrases."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    words = speech_text(text).split()
    chunks, current = [], ""
    for word in words:
        if len(word) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(word[i:i + max_chars] for i in range(0, len(word), max_chars))
        elif not current:
            current = word
        elif len(current) + len(word) + 1 <= max_chars:
            current += " " + word
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


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
            for chunk in speech_chunks(self.text):
                if self.isInterruptionRequested():
                    break
                engine.say(chunk)
                engine.runAndWait()
            self.completed.emit("Cancelled" if self.isInterruptionRequested() else "Speech finished")
        except Exception as exc:
            self.completed.emit("Speech unavailable: " + type(exc).__name__)
        finally:
            self._engine = None
