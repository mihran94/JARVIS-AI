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

#: Windows SAPI GetVoices requires *hexadecimal* LANGIDs with no 0x prefix.
#: Tamil supports India (0449) and Sri Lanka (0849). Decimal 1067 is
#: Armenian, not Tamil. Keep a small ordered list for regional fallbacks.
SAPI_LANGUAGES = {
    'en': ('409',),
    'ta': ('449', '849'),
    'fr': ('40c',),
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
        identifiers = SAPI_LANGUAGES.get(language, ())
        for identifier in identifiers:
            try:
                # SAPI filters voice tokens by hexadecimal language attribute.
                # GetVoices returns a collection, not a single voice token.
                tokens = self._voice.GetVoices(f'Language={identifier}')
                if tokens is None or tokens.Count < 1:
                    continue
                self._voice.Voice = tokens.Item(0)
                return True
            except Exception:
                # Try another regional token; do not silently speak Tamil
                # with a non-Tamil voice when no matching voice is available.
                continue
        return False

    def speak(self, text: str, language: str | None = None, rate: int | None = None) -> None:
        """Speak the text. The call returns when the utterance is queued."""
        if not isinstance(text, str) or not text.strip():
            raise ValueError('There is nothing to speak.')
        if language:
            self.select_language(language)
        if rate is not None:
            self._voice.Rate = int(rate)
        self._voice.Speak(text)

    def speak_interruptibly(self, text: str, should_stop, language: str | None = None) -> None:
        """Use asynchronous SAPI playback and poll for an emergency stop.

        The SAPI voice COM object must be created and used on the same
        worker-thread apartment. Only the bundled Windows speech API is
        involved: no provider calls, network access or microphone capture.
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError('There is nothing to speak.')
        if language:
            self.select_language(language)
        if should_stop():
            return
        # SPF_ASYNC = 1; WaitUntilDone polls without blocking the Qt GUI.
        self._voice.Speak(text, 1)
        try:
            while not self._voice.WaitUntilDone(120):
                if should_stop():
                    self.stop()
                    return
        finally:
            if should_stop():
                self.stop()

    def stop(self) -> None:
        """Stop speaking immediately."""
        try:
            self._voice.Speak('', 3)
        except Exception:
            pass
