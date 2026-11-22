"""The Quantum Core HUD never sends microphone audio to a network service.

Two things are checked here:

* the source of `quantum_core/launcher.py` carries no cloud speech call at
  all, and no plain HTTP endpoint that could carry one;
* the launcher asks the owner before it opens the microphone, it recognises
  speech with the project's own Windows adapter, and it stops listening as
  soon as the permission is taken back.
"""
import importlib
import re
import sys
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'quantum_core' / 'launcher.py'


def launcher_source():
    return LAUNCHER.read_text(encoding='utf-8')


# ── the source guard ─────────────────────────────────────────────────────────

def test_the_launcher_never_calls_a_cloud_speech_service():
    """The whole point: microphone audio stays on this machine."""
    source = launcher_source().casefold()
    for forbidden in ('recognize_google', 'speech-api', 'speech_recognition',
                      'speechrecognition', 'www.google.com/speech-api',
                      'chromium&lang'):
        assert forbidden not in source, forbidden


def test_the_launcher_carries_no_plain_http_endpoint():
    """Only the local loopback address may appear; nothing may carry audio out."""
    endpoints = re.findall(r'http://[^\s\'"]+', launcher_source())
    for endpoint in endpoints:
        assert endpoint.startswith('http://{'), endpoint


def test_the_launcher_uses_the_project_s_own_local_recogniser():
    source = launcher_source()
    assert 'WindowsSpeechRecognizer' in source
    assert "voice_layer('windows_stt')" in source
    assert 'recognize_once' in source


def test_the_launcher_holds_the_permission_in_the_shared_consent_model():
    source = launcher_source()
    assert 'VoiceConsent' in source
    assert "voice_layer('consent')" in source


def test_the_launcher_consults_the_consent_gate_before_the_microphone():
    """The gate has to come before the recogniser, not after it."""
    source = launcher_source()
    start = source.index('def listen_once(self):')
    text = source[start:source.index('\n    def ', start)]
    assert 'self.consent.listening' in text
    assert text.index('self.consent.listening') < text.index('recognize_once')


def test_the_launcher_tells_the_owner_that_the_recognition_is_local():
    source = launcher_source()
    assert 'No microphone audio is sent to' in source
    assert 'Send recorded speech to Google' not in source


# ── the launcher itself ──────────────────────────────────────────────────────

class FakeChat:
    """A chat that never reaches a provider."""

    key = ''
    profile = 'fast'
    models = {'fast': 'model', 'deep': 'model'}
    model = 'model'

    def reply(self, command):
        return 'ok'

    def draft(self, command, brief):
        return 'draft'


class FakeRecognizer:
    """A local recogniser that remembers what it was asked to do."""

    def __init__(self, text='hello sir', on_recognize=None):
        self.text = text
        self.on_recognize = on_recognize
        self.calls = []
        self.stopped = 0

    def recognize_once(self, timeout_seconds=5.0):
        self.calls.append(timeout_seconds)
        if self.on_recognize is not None:
            self.on_recognize()
        return self.text

    def stop(self):
        self.stopped += 1


@pytest.fixture()
def launcher(monkeypatch):
    """The HUD launcher with the web server dependencies replaced by stubs."""
    bottle = types.ModuleType('bottle')
    bottle.Bottle = object
    bottle.abort = lambda *args, **kwargs: None
    bottle.request = types.SimpleNamespace(headers={})

    eel = types.ModuleType('eel')
    eel.update_hud_state = lambda state, message='': None
    eel.spawn = lambda function, *args, **kwargs: None
    eel.sleep = lambda seconds: None
    eel.init = lambda path: None
    eel.expose = lambda name: (lambda function: function)
    eel.start = lambda *args, **kwargs: None

    lock = types.ModuleType('gevent.lock')
    lock.Semaphore = threading.Semaphore

    class ThreadPool:
        def __init__(self, size):
            self.size = size

        def apply(self, function, args=()):
            return function(*args)

    threadpool = types.ModuleType('gevent.threadpool')
    threadpool.ThreadPool = ThreadPool

    gevent = types.ModuleType('gevent')
    gevent.lock = lock
    gevent.threadpool = threadpool

    for name, module in (('bottle', bottle), ('eel', eel), ('gevent', gevent),
                         ('gevent.lock', lock), ('gevent.threadpool', threadpool)):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, 'quantum_core.launcher', raising=False)
    module = importlib.import_module('quantum_core.launcher')
    yield module
    sys.modules.pop('quantum_core.launcher', None)


def build_hud(launcher, *, consent, recognizer, listen=True):
    return launcher.QuantumCore(FakeChat(), speak=False, listen=listen, language='en-US',
                                consent=consent, recognizer=recognizer)


def test_the_launcher_does_not_listen_without_the_owner_permission(launcher):
    consent = launcher.voice_layer('consent').VoiceConsent()
    recognizer = FakeRecognizer()
    hud = build_hud(launcher, consent=consent, recognizer=recognizer)
    assert hud.listen_once() == ''
    assert recognizer.calls == []


def test_the_launcher_listens_with_the_local_recogniser_when_allowed(launcher):
    consent = launcher.voice_layer('consent').VoiceConsent()
    consent.grant()
    recognizer = FakeRecognizer()
    hud = build_hud(launcher, consent=consent, recognizer=recognizer)
    assert hud.listen_once() == 'hello sir'
    assert recognizer.calls == [launcher.LISTEN_TIMEOUT_SECONDS]


def test_the_voice_loop_never_opens_the_microphone_without_permission(launcher):
    consent = launcher.voice_layer('consent').VoiceConsent()
    recognizer = FakeRecognizer()
    hud = build_hud(launcher, consent=consent, recognizer=recognizer)
    hud.voice_loop()
    assert recognizer.calls == []
    assert hud.mic_enabled is False


def test_the_voice_loop_stops_when_the_owner_takes_the_microphone_back(launcher):
    consent = launcher.voice_layer('consent').VoiceConsent()
    consent.grant()
    recognizer = FakeRecognizer(on_recognize=consent.revoke)
    hud = build_hud(launcher, consent=consent, recognizer=recognizer)
    hud.voice_loop()
    assert len(recognizer.calls) == 1
    assert recognizer.stopped == 1, 'the microphone was not closed'
    assert hud.mic_enabled is True, 'the owner did not ask for the microphone to stop'


def test_the_stop_control_closes_the_microphone(launcher):
    consent = launcher.voice_layer('consent').VoiceConsent()
    consent.grant()
    recognizer = FakeRecognizer()
    hud = build_hud(launcher, consent=consent, recognizer=recognizer)
    result = hud.stop_microphone()
    assert consent.stopped
    assert not consent.listening
    assert 'closed' in result['state'].casefold()
    assert hud.listen_once() == ''
    assert recognizer.calls == []


def test_the_owner_has_to_say_yes_before_the_microphone_opens(launcher):
    consent = launcher.voice_layer('consent').VoiceConsent()
    assert launcher.ask_for_microphone(consent, answer=lambda prompt: 'yes') is True
    assert consent.granted and consent.listening


def test_an_empty_answer_leaves_the_microphone_closed(launcher):
    consent = launcher.voice_layer('consent').VoiceConsent()
    assert launcher.ask_for_microphone(consent, answer=lambda prompt: '') is False
    assert not consent.granted


def test_a_missing_terminal_leaves_the_microphone_closed(launcher):
    def no_terminal(prompt):
        raise EOFError

    consent = launcher.voice_layer('consent').VoiceConsent()
    assert launcher.ask_for_microphone(consent, answer=no_terminal) is False
    assert not consent.granted


def test_the_locale_is_mapped_to_a_language_the_local_recogniser_knows(launcher):
    assert launcher.speech_language('en-US') == 'en'
    assert launcher.speech_language('ta-IN') == 'ta'
    assert launcher.speech_language('fr-FR') == 'fr'
    assert launcher.speech_language('xx-XX') == 'en'


def test_the_local_recogniser_refuses_to_pretend_it_works_off_windows(launcher, monkeypatch):
    """There is no cloud service to fall back to when Windows is missing."""
    consent = launcher.voice_layer('consent').VoiceConsent()
    monkeypatch.setattr(sys, 'platform', 'linux')
    with pytest.raises(launcher.voice_error()):
        launcher.local_recognizer(consent, 'en-US')
