"""The local voice models and whether they are ready.

WHAT IS COVERED
    * The owner can see which speech models this computer can use, and
      which ones are missing.
    * A model that is not there is reported as missing with the reason,
      never offered and then failing.
    * The probe never opens the microphone and never reaches the network.
    * On a computer that is not Windows the answer is honest: the
      offline voice models of Windows are not available here.
"""
import sys

import pytest

from voice import models as voice_models
from voice.models import RECOGNITION, SPEECH, TANGLISH, VoiceModel


def test_the_probe_answers_for_every_capability():
    found = voice_models.probe()
    assert found
    capabilities = {model.capability for model in found}
    assert RECOGNITION in capabilities
    assert SPEECH in capabilities


def test_the_probe_names_every_language_jarvis_speaks():
    found = voice_models.probe()
    languages = {model.language for model in found}
    assert 'en' in languages
    assert 'ta' in languages
    assert TANGLISH in languages


def test_a_model_that_is_not_there_is_reported_as_missing():
    model = VoiceModel(RECOGNITION, 'ta', 'Tamil recognition', False,
                       'The recogniser is not installed.')
    assert model.ready is False
    assert 'not installed' in model.detail


def test_the_probe_is_honest_on_a_computer_that_is_not_windows():
    if sys.platform == 'win32':
        pytest.skip('This is the answer on Windows.')
    found = voice_models.probe()
    assert all(model.ready is False for model in found)
    assert all('Windows only' in model.detail for model in found)


def test_the_summary_says_when_no_models_are_ready():
    found = [VoiceModel(RECOGNITION, 'ta', 'Tamil recognition', False, 'Model missing.')]
    assert voice_models.summary(found) == 'No offline voice model is ready on this computer yet.'
    assert voice_models.ready_languages(found) == set()


def test_tamil_and_tanglish_are_ready_without_windows_speech(monkeypatch):
    monkeypatch.setattr(voice_models.sys, 'platform', 'win32')
    monkeypatch.setattr(voice_models, '_installed_recognisers', lambda: {})
    monkeypatch.setattr(voice_models.local_stt, 'ready', lambda: True)
    ready = voice_models.ready_languages(voice_models._recognition_models())
    assert ready == {'ta', TANGLISH}


def test_a_model_that_is_ready_is_named_in_the_summary():
    found = [VoiceModel(RECOGNITION, 'ta', 'Tamil recognition', True,
                        'The Windows Tamil recogniser is installed.'),
             VoiceModel(SPEECH, 'en', 'English voice', False, 'No English voice.')]
    summary = voice_models.summary(found)
    assert '1 of 2' in summary
    assert 'Tamil recognition' in summary
    assert 'English voice' not in summary
    assert voice_models.ready_languages(found) == {'ta'}


def test_the_probe_answers_without_a_microphone():
    # Readiness is about what is installed, so the probe answers on a
    # machine that has no microphone at all.
    found = voice_models.probe()
    assert all(model.detail for model in found)
    assert all(model.label for model in found)
    assert all(isinstance(model.as_dict(), dict) for model in found)
