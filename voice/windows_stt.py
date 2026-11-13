"""Windows speech recognition through System.Speech with explicit microphone consent.

This adapter needs Windows and the optional `pythonnet` package. It uses the
Windows System.Speech recogniser; no cloud STT API is called. It has **not**
been executed in the Linux environment where it was written and must be
exercised on the owner's Windows machine before it is trusted.

The microphone is opened only after `voice.consent.VoiceConsent` has granted
permission, and `stop()` closes it.
"""
import sys

from voice.consent import VoiceConsent
from voice.errors import VoiceUnavailable
from voice.wake import VARIANTS, WakePhraseMatcher

#: System.Speech language identifiers for the languages JARVIS speaks.
SPEECH_LANGUAGES = {
    'en': 'en-US',
    'ta': 'ta-IN',
    'fr': 'fr-FR',
}


class WindowsSpeechRecognizer:
    """Offline speech recognition with the Windows recogniser."""

    def __init__(self, consent: VoiceConsent | None = None, language: str = 'en'):
        if sys.platform != 'win32':
            raise VoiceUnavailable('Windows speech recognition needs Windows.')
        try:
            import clr
            clr.AddReference('System.Speech')
            from System.Speech.Recognition import (  # noqa: F401 - imported for the side effect
                DictationGrammar, GrammarBuilder, SpeechRecognitionEngine,
            )
        except ImportError:
            raise VoiceUnavailable(
                'Install the optional pythonnet package to use Windows speech recognition.'
            ) from None
        except Exception:
            raise VoiceUnavailable('Windows speech recognition could not be started.') from None
        self._clr = clr
        self._consent = consent if consent is not None else VoiceConsent()
        self._matcher = WakePhraseMatcher()
        self._language = language
        self._engine = None

    def _culture(self):
        from System.Globalization import CultureInfo
        return CultureInfo(SPEECH_LANGUAGES.get(self._language, 'en-US'))

    def _build_engine(self, grammar_kind: str):
        from System.Speech.Recognition import (Choices, DictationGrammar, Grammar,
                                               GrammarBuilder, SpeechRecognitionEngine)
        # Windows requires a recognizer installed for the selected language.
        engine = None
        try:
            culture = self._culture()
            engine = SpeechRecognitionEngine(culture)
            if grammar_kind == 'wake':
                choices = Choices()
                for phrase in VARIANTS.get(self._language, VARIANTS['en']):
                    choices.Add(phrase)
                builder = GrammarBuilder()
                builder.Culture = culture
                builder.Append(choices)
                engine.LoadGrammar(Grammar(builder))
            else:
                engine.LoadGrammar(DictationGrammar())
            # Loading the grammar does not select the microphone.
            engine.SetInputToDefaultAudioDevice()
            return engine
        except Exception:
            if engine is not None:
                try:
                    engine.Dispose()
                except Exception:
                    pass
            raise VoiceUnavailable(
                'Windows speech recognition needs a microphone and an '
                'installed recognizer for the selected language.'
            ) from None

    def _recognize(self, timeout_seconds: float):
        from System import TimeSpan
        seconds = max(0.1, min(float(timeout_seconds), 30.0))
        # Recognize(TimeSpan) is the supported .NET API overload.
        return self._engine.Recognize(TimeSpan.FromSeconds(seconds))

    def recognize_once(self, timeout_seconds: float = 5.0) -> str:
        """Listen once and return the transcript.

        Raises `VoiceError` when the microphone is not allowed.
        """
        self._consent.require_listening()
        if self._engine is None:
            self._engine = self._build_engine('dictation')
        result = self._recognize(timeout_seconds)
        if result is None:
            return ''
        return str(result.Text)

    def wait_for_wake_phrase(self, timeout_seconds: float = 5.0) -> tuple[str, str]:
        """Listen for the wake phrase. Returns the phrase and the instruction."""
        self._consent.require_listening()
        if self._engine is None:
            self._engine = self._build_engine('wake')
        result = self._recognize(timeout_seconds)
        if result is None:
            return '', ''
        transcript = str(result.Text)
        match = self._matcher.match(transcript, self._language)
        if not match.is_wake_call:
            return '', ''
        return match.matched_phrase, self._matcher.extract_command(transcript) or ''

    def stop(self) -> None:
        """Close the microphone and release the recogniser."""
        # Releasing a one-shot recognizer must NOT cancel the user's consent.
        # Only the explicit Stop/permission toggle in VoicePanel revokes it.
        engine, self._engine = self._engine, None
        if engine is not None:
            try:
                engine.Dispose()
            except Exception:
                pass
