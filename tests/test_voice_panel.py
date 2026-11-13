"""The Voice page: the permission, the wake phrase and the adapters."""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from desktop.voice_panel import VoicePanel
from voice.consent import VoiceConsent
from voice.errors import VoiceUnavailable, VoiceError
from voice.wake import WakePhraseMatcher


@pytest.fixture(scope='module')
def app():
    application = QApplication.instance() or QApplication([])
    return application


@pytest.fixture()
def panel(app):
    return VoicePanel()


class FakeRecognizer:
    """A recogniser that says what the test wants it to say."""

    def __init__(self, transcript='', wake=('', ''), error=None):
        self.transcript = transcript
        self.wake = wake
        self.error = error
        self.stopped = False

    def recognize_once(self, timeout_seconds=5.0):
        if self.error:
            raise self.error
        return self.transcript

    def wait_for_wake_phrase(self, timeout_seconds=5.0):
        if self.error:
            raise self.error
        return self.wake

    def stop(self):
        self.stopped = True


def test_the_page_builds(panel):
    assert panel.allow.text() == 'Allow the microphone'
    assert panel.stop_button.text() == 'Stop voice'


def test_the_microphone_stays_closed_until_it_is_allowed(panel):
    assert panel.consent.granted is False
    assert panel.consent.listening is False
    assert 'has not been allowed' in panel.permission.text()


def test_allowing_the_microphone_is_shown_to_the_owner(panel):
    panel.allow.setChecked(True)
    assert panel.consent.granted is True
    assert panel.consent.listening is True
    assert 'allowed for the voice feature' in panel.permission.text()


def test_unchecking_the_box_withdraws_the_permission(panel):
    panel.allow.setChecked(True)
    panel.allow.setChecked(False)
    assert panel.consent.granted is False
    assert panel.consent.listening is False


def test_the_stop_control_closes_the_microphone(panel):
    panel.allow.setChecked(True)
    panel.stop_voice()
    assert panel.consent.stopped is True
    assert panel.consent.granted is False
    assert panel.consent.listening is False
    assert 'closed by the stop control' in panel.permission.text()


def test_resuming_does_not_silently_reopen_the_microphone(panel):
    panel.allow.setChecked(True)
    panel.stop_voice()
    panel.resume_voice()
    assert panel.consent.stopped is False
    assert panel.consent.granted is False
    assert panel.consent.listening is False


def test_listening_without_the_permission_is_refused(panel):
    panel.listen('once')
    assert 'Allow the microphone' in panel.transcript.toPlainText()


def test_the_wake_phrase_is_recognised_in_a_transcript(panel):
    panel.on_transcript('Hey Jarvis Blue, what is the weather')
    text = panel.transcript.toPlainText()
    assert 'Wake call' in text
    assert 'Command:' in text


def test_a_sentence_without_the_wake_phrase_is_not_a_wake_call(panel):
    panel.on_transcript('please open the settings')
    assert 'Not a wake call' in panel.transcript.toPlainText()


def test_the_wake_phrase_can_be_changed(panel):
    panel.phrase.setText('Computer Jarvis')
    assert panel.matcher.canonical_phrase == 'Computer Jarvis'
    panel.on_transcript('Computer Jarvis, run the tests')
    assert 'Wake call' in panel.transcript.toPlainText()


def test_the_adapters_are_not_reached_when_the_permission_is_missing(panel):
    called = []

    def factory(*args, **kwargs):
        called.append(args)
        return FakeRecognizer('never')

    panel._recognizer_factory = factory
    panel.listen('once')
    assert called == []


def test_a_recognised_transcript_is_shown(panel, app):
    panel.allow.setChecked(True)
    panel._recognizer_factory = lambda *a, **k: FakeRecognizer('the build is green')
    panel.listen('once')
    panel.worker.wait(4000)
    app.processEvents()
    assert 'the build is green' in panel.transcript.toPlainText()


def test_a_wake_call_is_shown_with_its_command(panel, app):
    panel.allow.setChecked(True)
    panel._recognizer_factory = lambda *a, **k: FakeRecognizer(wake=('Hey Jarvis', 'open the bridge'))
    panel.listen('wake')
    panel.worker.wait(4000)
    app.processEvents()
    text = panel.transcript.toPlainText()
    assert 'Wake call' in text
    assert 'open the bridge' in text


def test_an_unavailable_recogniser_is_reported_instead_of_crashing(panel, app):
    panel.allow.setChecked(True)

    def factory(*args, **kwargs):
        raise VoiceUnavailable('Windows speech recognition needs Windows.')

    panel._recognizer_factory = factory
    panel.listen('once')
    panel.worker.wait(4000)
    app.processEvents()
    assert 'needs Windows' in panel.transcript.toPlainText()


def test_a_failed_recognition_does_not_keep_the_audio(panel, app):
    panel.allow.setChecked(True)
    panel._recognizer_factory = lambda *a, **k: FakeRecognizer(error=VoiceError('the microphone is busy'))
    panel.listen('once')
    panel.worker.wait(4000)
    app.processEvents()
    assert 'busy' in panel.transcript.toPlainText()


def test_the_recogniser_is_closed_after_every_request(panel, app):
    panel.allow.setChecked(True)
    fake = FakeRecognizer('done')
    panel._recognizer_factory = lambda *a, **k: fake
    panel.listen('once')
    panel.worker.wait(4000)
    assert fake.stopped is True


def test_speaking_without_windows_is_reported(panel):
    def factory():
        raise VoiceUnavailable('Windows text to speech needs Windows.')

    panel._speaker_factory = factory
    panel.speak_text.setText('hello')
    panel.speak()
    assert 'needs Windows' in panel.transcript.toPlainText()


def test_speaking_says_the_text(panel):
    said = []

    class Speaker:
        def speak(self, text, language=None, rate=None):
            said.append(text)

    panel._speaker_factory = Speaker
    panel.speak_text.setText('the build is green')
    panel.speak()
    assert said == ['the build is green']


def test_speaking_nothing_does_nothing(panel):
    called = []
    panel._speaker_factory = lambda: called.append(1)
    panel.speak()
    assert called == []


def test_the_matcher_stays_the_same_object_for_the_default_phrase(panel):
    assert isinstance(panel.matcher, WakePhraseMatcher)
    assert panel.matcher.canonical_phrase


def test_a_fresh_panel_does_not_share_the_permission():
    first = VoicePanel()
    second = VoicePanel()
    first.allow.setChecked(True)
    assert second.consent.granted is False


def test_the_page_survives_a_stopped_voice_feature(app):
    panel = VoicePanel()
    panel.allow.setChecked(True)
    panel.stop_voice()
    panel.allow.setChecked(True)
    assert panel.consent.granted is False


def test_voice_once_forwards_a_reviewable_draft_only_when_allowed(panel):
    heard = []
    wake = []
    panel.utterance_detected.connect(heard.append)
    panel.wake_detected.connect(lambda transcript, command: wake.append(command))

    panel.on_transcript('check my Python project')
    panel.on_wake_call('Hey Jarvis', 'open calculator')
    assert heard == []
    assert wake == []

    panel.allow.setChecked(True)
    panel.on_transcript('check my Python project')
    assert heard == ['check my Python project']
    panel.on_transcript('Hey Jarvis, review this code')
    assert len(wake) == 1
    assert 'review this code' in wake[0]

    panel.stop_voice()
    panel.on_transcript('delete my documents')
    panel.on_wake_call('Hey Jarvis', 'delete my documents')
    assert heard == ['check my Python project']
    assert len(wake) == 1


def test_listen_once_can_be_reused_without_renewing_owner_consent(panel, app):
    panel.allow.setChecked(True)
    speech = []
    panel.utterance_detected.connect(speech.append)
    panel._recognizer_factory = lambda *a, **kw: FakeRecognizer('hello JARVIS')
    panel.listen('once')
    panel.worker.wait(4000)
    app.processEvents()
    assert speech == ['hello JARVIS']
    assert panel.consent.granted is True
    assert panel.consent.listening is True
