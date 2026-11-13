"""Windows text to speech through the SAPI voice.

This adapter needs Windows and the optional `pywin32` package. It is written
against the Windows SAPI interface and has **not** been executed in the Linux
environment where it was written, so it must be exercised on the owner's
Windows machine before it is trusted.

The voice is never started without the owner asking for it, and `stop()`
closes it immediately.
"""
import sys

from voice.errors import VoiceUnavailable

#: SAPI language identifiers for the languages JARVIS speaks.
SAPI_LANGUAGES = {
    'en': 1033,
    'ta': 1067,
    'fr': 1036,
}


class WindowsTextToSpeech:
    """Speaks text with the installed Windows voices."""

    def __init__(self):
        if sys.platform != 'win32':
            raise VoiceUnavailable('Windows text to speech needs Windows.')
        try:
            import win32com.client
        except ImportError:
            raise VoiceUnavailable(
                'Install the optional pywin32 package to use Windows text to speech.') from None
        self._client = win32com.client
        try:
            self._voice = win32com.client.Dispatch('SAPI.SpVoice')
        except Exception:
            raise VoiceUnavailable('Windows speech could not be started.') from None

    def voices(self) -> list[str]:
        """The names of the installed voices."""
        names = []
        for token in self._voice.GetVoices():
            try:
                names.append(token.GetDescription())
            except Exception:
                continue
        return names

    def select_language(self, language: str) -> bool:
        """Choose an installed voice for a language. False when none exists."""
        identifier = SAPI_LANGUAGES.get(language)
        if identifier is None:
            return False
        try:
            # GetVoices returns a token collection, NOT one voice token.
            tokens = self._voice.GetVoices(f'Language={identifier}')
            if tokens is None or tokens.Count < 1:
                return False
            self._voice.Voice = tokens.Item(0)
        except Exception:
            return False
        return True

    def speak(self, text: str, language: str | None = None, rate: int | None = None) -> None:
        """Speak the text. The call returns when the utterance is queued."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError('There is nothing to speak.')
        if language:
            self.select_language(language)
        if rate is not None:
            self._voice.Rate = int(rate)
        self._voice.Speak(text)

    def stop(self) -> None:
        """Stop speaking immediately."""
        try:
            self._voice.Speak('', 3)
        except Exception:
            pass
