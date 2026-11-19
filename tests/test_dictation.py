"""Offline validation tests; no microphone opened.

The dictation worker is the one place in the desktop that opens a raw
microphone stream, so these tests check the microphone gate as well: the
worker must refuse to open the stream until the owner allowed it, and it must
close itself when the permission is taken back.
"""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

import pytest

from desktop.dictation import DictationWorker, validate_model_path, normalize_transcript
from voice.consent import VoiceConsent


def _stub_sounddevice(monkeypatch, opened, on_read=None):
    """A sounddevice that remembers every stream that was opened."""
    module = types.ModuleType('sounddevice')

    class RawInputStream:
        def __init__(self, **kwargs):
            opened.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, size):
            if on_read is not None:
                on_read()
            return (b'\x00' * size, False)

    module.RawInputStream = RawInputStream
    monkeypatch.setitem(sys.modules, 'sounddevice', module)
    return module


def _stub_vosk(monkeypatch, text='hello sir'):
    """A Vosk model that never leaves the machine."""
    module = types.ModuleType('vosk')

    class Model:
        def __init__(self, path):
            self.path = path

    class KaldiRecognizer:
        def __init__(self, model, rate):
            self.model = model
            self.rate = rate

        def AcceptWaveform(self, data):
            return False

        def Result(self):
            return json.dumps({'text': ''})

        def FinalResult(self):
            return json.dumps({'text': text})

    module.Model = Model
    module.KaldiRecognizer = KaldiRecognizer
    monkeypatch.setitem(sys.modules, 'vosk', module)
    return module


@pytest.fixture()
def model_dir(tmp_path):
    (tmp_path / 'am').mkdir()
    (tmp_path / 'conf').mkdir()
    return str(tmp_path)


class DictationTests(unittest.TestCase):
    def test_transcript_normalization(self):
        self.assertEqual(normalize_transcript(['  hello ', '', ' world  ']), 'hello world')
        self.assertEqual(normalize_transcript([' ']), '')
        self.assertEqual(normalize_transcript(['abcdefgh'], max_chars=4), 'abcd')
        with self.assertRaises(ValueError):
            normalize_transcript(['hello'], max_chars=0)

    def test_reject_blank_model_path(self):
        for path in ('', '   ', None):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    validate_model_path(path)

    def test_reject_missing_model(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                validate_model_path(root)

    def test_accept_extracted_model_structure(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "am").mkdir()
            (Path(root) / "conf").mkdir()
            self.assertEqual(validate_model_path(root), root)

    def test_reject_nonexistent_model(self):
        with self.assertRaises(ValueError):
            validate_model_path("/unlikely-jarvis-model-path-not-found")


def test_the_worker_refuses_to_open_the_microphone_without_permission(monkeypatch, model_dir):
    """The microphone is never opened before the owner allowed it."""
    opened = []
    _stub_sounddevice(monkeypatch, opened)
    _stub_vosk(monkeypatch)
    worker = DictationWorker(model_dir, consent=VoiceConsent())
    messages = []
    worker.completed.connect(messages.append)
    worker.run()
    assert opened == [], 'the microphone was opened without the owner permission'
    assert any('Dictation refused' in message for message in messages)


def test_the_worker_opens_the_microphone_once_the_owner_allowed_it(monkeypatch, model_dir):
    """With the permission the worker listens, and says that nothing was sent."""
    opened = []
    _stub_sounddevice(monkeypatch, opened)
    _stub_vosk(monkeypatch, text='hello sir')
    consent = VoiceConsent()
    consent.grant()
    worker = DictationWorker(model_dir, consent=consent)
    messages = []
    transcripts = []
    worker.completed.connect(messages.append)
    worker.recognized.connect(transcripts.append)
    worker.run()
    assert opened, 'the microphone was not opened although the owner allowed it'
    assert transcripts == ['hello sir']
    assert any('not sent' in message for message in messages)


def test_the_worker_stops_when_the_owner_takes_the_permission_back(monkeypatch, model_dir):
    """A running session closes itself when the permission is withdrawn."""
    opened = []
    consent = VoiceConsent()
    consent.grant()
    _stub_sounddevice(monkeypatch, opened, on_read=consent.revoke)
    _stub_vosk(monkeypatch)
    worker = DictationWorker(model_dir, consent=consent)
    messages = []
    worker.completed.connect(messages.append)
    worker.run()
    assert opened, 'the microphone was not opened although the owner allowed it'
    assert any('microphone was closed' in message for message in messages)
    assert not any('Dictation finished' in message for message in messages)


def test_a_new_worker_has_no_permission_of_its_own(model_dir):
    """Nobody may open the microphone without asking the owner first."""
    worker = DictationWorker(model_dir)
    assert worker.consent.granted is False
    assert worker.consent.listening is False


def test_the_worker_refuses_before_it_touches_a_real_device(monkeypatch, model_dir):
    """With the real sounddevice package the gate still comes first."""
    sounddevice = pytest.importorskip('sounddevice')
    opened = []

    class SpyStream:
        def __init__(self, **kwargs):
            opened.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(sounddevice, 'RawInputStream', SpyStream)
    worker = DictationWorker(model_dir, consent=VoiceConsent())
    messages = []
    worker.completed.connect(messages.append)
    worker.run()
    assert opened == [], 'the microphone was opened without the owner permission'
    assert any('Dictation refused' in message for message in messages)


if __name__ == "__main__":
    unittest.main()
