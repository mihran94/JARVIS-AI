"""The questions JARVIS answers itself, and the Tamil that reaches it.

WHAT IS COVERED
    * "What can you do" is answered in Tamil, Tanglish, English and
      French, and in the wording the owner actually uses.
    * A real request is never swallowed by one of those phrases.
    * The speech layer does not break Tamil apart. The normaliser kept
      the Tamil vowel signs out of its strip list on purpose, and then
      turned them into spaces anyway, so every Tamil sentence that came
      out of the microphone arrived as separate letters.
    * A spoken question in Tanglish reaches the local answer, without a
      provider call.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from desktop.local_commands import match, normalise
from voice.text_tools import normalize
from voice.wake import WakePhraseMatcher


# ── the matcher ─────────────────────────────────────────────────────────────

def test_the_question_the_owner_asked_is_answered():
    """The example from the brief."""
    assert match('Jarvis, enna help pannuva?') == 'capabilities'


@pytest.mark.parametrize('text', [
    'what can you do',
    'what are your abilities',
    'your skills',
    'jarvis capabilities',
    'உன்னால் என்ன செய்ய முடியும்',
    'என்ன செய்ய முடியும்',
    'enna help pannuva',
    'enna help pannu',
    'enna seiya mudiyum',
    'epdi help pannu',
    'tes capacites',
    'que peux-tu faire',
    '/capabilities',
])
def test_what_jarvis_can_do_is_asked_in_every_language(text):
    assert match(text) == 'capabilities'


@pytest.mark.parametrize('text', [
    'what time is it',
    'current time',
    'நேரம் என்ன',
    'ippo neram enna',
    'quelle heure est-il',
    '/time',
])
def test_the_time_is_asked_in_every_language(text):
    assert match(text) == 'time'


@pytest.mark.parametrize('text', [
    'system status',
    'status',
    'கணினி நிலை',
    'system status enna',
    'etat du systeme',
    '/status',
])
def test_the_status_is_asked_in_every_language(text):
    assert match(text) == 'status'


@pytest.mark.parametrize('text', [
    'open calculator',
    'help me fix my project',
    'what time does the train leave',
    'who won the match yesterday',
    'please open notepad and type hello',
    'run the tests on my project',
    '',
    None,
])
def test_a_real_request_is_never_swallowed(text):
    """A question that is not one of ours belongs to the model."""
    assert match(text) is None


def test_a_single_common_word_is_never_enough():
    """Only the words that are specific enough may stand alone.

    "status" and "capabilities" have always answered on their own, and
    they are specific enough to keep doing so. "help" and "time" are
    common words, and a sentence that merely contains one of them is not
    a question about them.
    """
    assert match('help') is None
    assert match('time') is None
    assert match('what help') is None
    # These two are specific enough on their own.
    assert match('status') == 'status'
    assert match('capabilities') == 'capabilities'


def test_the_address_in_front_is_taken_off():
    assert match('Jarvis, what can you do') == 'capabilities'
    assert match('Hey Jarvis Blue, enna help pannuva') == 'capabilities'
    assert match('ஜார்விஸ், என்ன செய்ய முடியும்') == 'capabilities'


def test_the_words_are_compared_the_way_they_are_spoken():
    """A spoken verb is longer than the written one."""
    assert normalise('enna help pannuva') == ['enna', 'help', 'pannuva']
    assert match('enna help pannuva') == match('enna help pannu')


# ── the Tamil that reaches it ───────────────────────────────────────────────

def test_tamil_survives_the_speech_normaliser():
    """A Tamil word is one word, not a row of letters.

    The normaliser keeps the Tamil vowel signs out of its strip list on
    purpose, and then turned every one of them into a space, so
    "செய்ய" arrived as "ச ய ய".
    """
    assert normalize('செய்ய') == 'செய்ய'
    assert normalize('என்ன செய்ய முடியும்') == 'என்ன செய்ய முடியும்'


def test_a_latin_accent_is_still_stripped():
    """Stripping the accent is the whole reason the normaliser exists."""
    assert normalize('Café') == 'cafe'
    assert normalize('Café') == normalize('cafe')


def test_the_wake_phrase_leaves_a_tamil_command_whole():
    matcher = WakePhraseMatcher()
    command = matcher.extract_command('ஹே ஜார்விஸ், என்ன செய்ய முடியும்')
    assert command == 'என்ன செய்ய முடியும்'
    assert match(command) == 'capabilities'


def test_a_tamil_wake_phrase_is_still_recognised():
    matcher = WakePhraseMatcher()
    assert matcher.match('ஹே ஜார்விஸ்').is_wake_call


# ── in the application ──────────────────────────────────────────────────────

def test_a_spoken_question_is_answered_here_without_a_provider(tmp_path):
    """The answer is local, so it costs nothing and cannot be wrong."""
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        def no_provider(*_args, **_kwargs):
            pytest.fail('A local question must not reach a provider')
        window.get_key = no_provider
        window.voice_panel.consent.grant()
        window.on_wake_detected('Hey Jarvis Blue', 'enna help pannuva')
        messages = window.store.messages(window.session)
        assert messages
        assert 'Current AI' in messages[-1]['content']
        assert 'Not yet verified' in messages[-1]['content']
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
