"""Mocked .NET / SAPI contract tests, runnable without Windows hardware.

These assert the actual System.Speech API shape we use: a Grammar, a bound
microphone, and Recognize(TimeSpan). They do not claim that any physical
microphone or language pack has been tested.
"""
import sys
import types
from types import SimpleNamespace

import pytest

from voice.consent import VoiceConsent
from voice.errors import VoiceUnavailable
from voice.windows_stt import WindowsSpeechRecognizer
from voice.windows_tts import WindowsTextToSpeech


@pytest.fixture()
def fake_system_speech(monkeypatch):
    clr = types.ModuleType("clr")
    clr.AddReference = lambda value: None

    system = types.ModuleType("System")
    system.__path__ = []
    class TimeSpan:
        @staticmethod
        def FromSeconds(n):
            return ("seconds", n)
    system.TimeSpan = TimeSpan

    speech = types.ModuleType("System.Speech")
    speech.__path__ = []
    recognition = types.ModuleType("System.Speech.Recognition")
    globalization = types.ModuleType("System.Globalization")

    class CultureInfo:
        def __init__(self, name):
            self.Name = name

    class Choices:
        def __init__(self):
            self.items = []
        def Add(self, phrase):
            self.items.append(phrase)

    class GrammarBuilder:
        def __init__(self):
            self.Culture = None
            self.choices = None
        def Append(self, choices):
            self.choices = choices

    class Grammar:
        def __init__(self, builder):
            self.builder = builder

    class DictationGrammar:
        pass

    class SpeechRecognitionEngine:
        last = None
        def __init__(self, culture):
            self.culture = culture
            self.loaded = []
            self.microphone = False
            self.recognized_with = None
            self.disposed = False
            SpeechRecognitionEngine.last = self

        def LoadGrammar(self, grammar):
            self.loaded.append(grammar)

        def SetInputToDefaultAudioDevice(self):
            self.microphone = True

        def Recognize(self, timeout):
            assert self.microphone is True
            self.recognized_with = timeout
            return SimpleNamespace(Text="Hey Jarvis")

        def Dispose(self):
            self.disposed = True

    globalization.CultureInfo = CultureInfo
    recognition.Choices = Choices
    recognition.GrammarBuilder = GrammarBuilder
    recognition.Grammar = Grammar
    recognition.DictationGrammar = DictationGrammar
    recognition.SpeechRecognitionEngine = SpeechRecognitionEngine
    for name, module in (
        ("clr", clr),
        ("System", system),
        ("System.Speech", speech),
        ("System.Speech.Recognition", recognition),
        ("System.Globalization", globalization),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(sys, "platform", "win32")
    return SimpleNamespace(engine=SpeechRecognitionEngine, grammar=Grammar,
                           dictation=DictationGrammar)


def test_native_dictation_binds_microphone_with_timespan(fake_system_speech):
    permission = VoiceConsent()
    permission.grant()
    adapter = WindowsSpeechRecognizer(permission)
    assert adapter.recognize_once(3.25) == "Hey Jarvis"
    engine = fake_system_speech.engine.last
    assert engine.microphone
    assert engine.recognized_with == ("seconds", 3.25)
    assert isinstance(engine.loaded[0], fake_system_speech.dictation)
    adapter.stop()
    assert engine.disposed
    # The single-use engine is closed. The owner's microphone opt-in is not
    # automatically revoked: they may choose to listen again.
    assert permission.granted and permission.listening


def test_native_wake_uses_real_grammar_object(fake_system_speech):
    permission = VoiceConsent()
    permission.grant()
    adapter = WindowsSpeechRecognizer(permission, language="en")
    transcript, command = adapter.wait_for_wake_phrase(timeout_seconds=2.0)
    assert transcript
    assert command == ""
    engine = fake_system_speech.engine.last
    assert engine.recognized_with == ("seconds", 2.0)
    grammar = engine.loaded[0]
    assert isinstance(grammar, fake_system_speech.grammar)
    assert grammar.builder.choices.items
    assert grammar.builder.Culture.Name == "en-US"
    adapter.stop()


def test_recognition_without_permission_refuses_before_mic_binding(fake_system_speech):
    adapter = WindowsSpeechRecognizer(VoiceConsent())
    with pytest.raises(Exception, match="Allow the microphone"):
        adapter.recognize_once()
    assert fake_system_speech.engine.last is None


def test_sapi_voice_selection_uses_first_token_not_collection():
    class Tokens:
        Count = 1
        def Item(self, index):
            assert index == 0
            return "single-sapi-token"

    class FakeVoice:
        Voice = None
        def GetVoices(self, criteria):
            assert criteria == "Language=1033"
            return Tokens()

    speaker = object.__new__(WindowsTextToSpeech)
    speaker._voice = FakeVoice()
    assert speaker.select_language("en")
    assert speaker._voice.Voice == "single-sapi-token"


def test_sapi_missing_language_returns_false():
    class Empty:
        Count = 0

    class FakeVoice:
        Voice = None
        def GetVoices(self, criteria):
            return Empty()

    speaker = object.__new__(WindowsTextToSpeech)
    speaker._voice = FakeVoice()
    assert speaker.select_language("ta") is False
    assert speaker._voice.Voice is None
