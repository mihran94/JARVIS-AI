"""Which local voice models are ready on this computer.

WHAT THIS IS
    The owner can see, in one place, which speech models this computer can
    actually use: the offline recogniser for each language, and the
    offline voices installed for speech. A language that has no model is
    shown as missing, with the reason, rather than offered and then
    failing when the owner speaks into it.

    Nothing here is a cloud service. The recognition model is the one
    Windows installs, and the voices are the ones the owner has on the
    machine. Both work with the network unplugged.

WHAT THIS IS NOT
    * It never downloads a model. Installing a voice is the owner's
      decision, on their own computer.
    * It never opens the microphone. The probe reads what is installed.
"""
from __future__ import annotations

from dataclasses import dataclass
import sys

#: The two things a voice model can be.
RECOGNITION = 'recognition'
SPEECH = 'speech'

#: The languages JARVIS speaks.
LANGUAGES = ('en', 'ta')

#: The name of the language the owner picks for Tanglish.
TANGLISH = 'ta_en'


@dataclass(frozen=True)
class VoiceModel:
    """One voice model and whether this computer can use it."""

    capability: str
    language: str
    label: str
    ready: bool
    detail: str = ''
    identifier: str = ''

    def as_dict(self) -> dict:
        return {'capability': self.capability, 'language': self.language,
                'label': self.label, 'ready': self.ready, 'detail': self.detail,
                'identifier': self.identifier}


def _windows_only(capability: str) -> list:
    """The honest answer on a computer that is not Windows."""
    reason = ('The offline voice models of Windows are available on Windows only. '
              'Nothing was installed and nothing was downloaded.')
    if capability == RECOGNITION:
        return [
            VoiceModel(RECOGNITION, 'en', 'English recognition', False, reason),
            VoiceModel(RECOGNITION, 'ta', 'Tamil recognition', False, reason),
            VoiceModel(RECOGNITION, TANGLISH, 'Tamil + Tanglish', False, reason),
        ]
    return [
        VoiceModel(SPEECH, 'en', 'English voice', False, reason),
        VoiceModel(SPEECH, 'ta', 'Tamil voice', False, reason),
    ]


def _installed_recognisers() -> dict:
    """The cultures Windows has a recogniser for, or an empty mapping."""
    try:
        from voice.windows_stt import load_system_speech
        load_system_speech()
        from System.Speech.Recognition import SpeechRecognitionEngine
        found = {}
        for recogniser in SpeechRecognitionEngine.InstalledRecognizers():
            culture = str(getattr(recogniser, 'Culture', ''))
            if culture:
                found[culture] = str(getattr(recogniser, 'Id', '') or culture)
        return found
    except Exception:
        return {}


def _recognition_models() -> list:
    """The offline recognition models and whether they are there."""
    if sys.platform != 'win32':
        return _windows_only(RECOGNITION)
    installed = _installed_recognisers()
    if not installed:
        reason = ('The Windows speech recognition runtime could not be read, so the '
                  'installed recognisers are unknown. Install the optional '
                  'pythonnet package and the Windows language pack for Tamil.')
        return [
            VoiceModel(RECOGNITION, 'en', 'English recognition', False, reason),
            VoiceModel(RECOGNITION, 'ta', 'Tamil recognition', False, reason),
            VoiceModel(RECOGNITION, TANGLISH, 'Tamil + Tanglish', False, reason),
        ]
    cultures = {culture.casefold(): identifier for culture, identifier in installed.items()}
    english = cultures.get('en-us')
    tamil = cultures.get('ta-in')
    models = [
        VoiceModel(RECOGNITION, 'en', 'English recognition', bool(english),
                   'The Windows English recogniser is installed and works offline.'
                   if english else
                   'The Windows English recogniser is not installed. Add the English '
                   'speech language in Windows Settings.',
                   english or ''),
        VoiceModel(RECOGNITION, 'ta', 'Tamil recognition', bool(tamil),
                   'The Windows Tamil recogniser is installed and works offline.'
                   if tamil else
                   'The Windows Tamil recogniser is not installed. Add the Tamil '
                   'speech language in Windows Settings.',
                   tamil or ''),
    ]
    models.append(VoiceModel(
        RECOGNITION, TANGLISH, 'Tamil + Tanglish', bool(tamil),
        'Tamil written in Latin letters is converted to the Tamil script before the '
        'recogniser hears it, so Tanglish works with the Tamil model.'
        if tamil else
        'Tanglish needs the Windows Tamil recogniser. Add the Tamil speech language '
        'in Windows Settings.',
        tamil or ''))
    return models


def _speech_models() -> list:
    """The offline voices installed for speech, and whether they are there."""
    if sys.platform != 'win32':
        return _windows_only(SPEECH)
    try:
        from voice.windows_tts import WindowsTextToSpeech
        speaker = WindowsTextToSpeech()
        voices = {language: speaker.voices_for(language) for language in LANGUAGES}
    except Exception as error:
        reason = ('The Windows speech voices could not be read: ' + str(error)
                  + ' Install the optional pywin32 package to use the offline voices.')
        return [
            VoiceModel(SPEECH, 'en', 'English voice', False, reason),
            VoiceModel(SPEECH, 'ta', 'Tamil voice', False, reason),
        ]
    models = []
    for language in LANGUAGES:
        names = voices.get(language) or []
        label = 'English voice' if language == 'en' else 'Tamil voice'
        if names:
            detail = ('Installed and offline: ' + ', '.join(names[:4])
                      + (' …' if len(names) > 4 else ''))
        elif language == 'ta':
            detail = ('No Tamil voice is installed. Add the Tamil voice in Windows '
                      'Settings, or use the Tamil + English voice.')
        else:
            detail = 'No English voice is installed. Add one in Windows Settings.'
        models.append(VoiceModel(SPEECH, language, label, bool(names), detail,
                                 names[0] if names else ''))
    return models


def probe() -> list:
    """Every voice model this computer can use, or why it cannot.

    The probe reads what is installed. It never opens the microphone and
    never reaches the network.
    """
    return _recognition_models() + _speech_models()


def summary(models=None) -> str:
    """One line the owner can read about the voice models."""
    models = probe() if models is None else list(models)
    ready = [model for model in models if model.ready]
    if not ready:
        return 'No offline voice model is ready on this computer yet.'
    return (f'{len(ready)} of {len(models)} offline voice models are ready: '
            + ', '.join(model.label for model in ready) + '.')


def ready_languages(models=None) -> set:
    """The languages that can be heard and spoken right now."""
    models = probe() if models is None else list(models)
    return {model.language for model in models if model.ready}


__all__ = ['LANGUAGES', 'RECOGNITION', 'SPEECH', 'TANGLISH', 'VoiceModel',
           'probe', 'ready_languages', 'summary']
