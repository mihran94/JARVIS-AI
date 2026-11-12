"""Tests for the voice layer.

The wake phrase rules and the microphone consent are pure logic and are
exercised here. The Windows text to speech and speech recognition adapters
need Windows and optional packages, so they are only checked for refusing to
pretend they work.
"""
import sys

import pytest

from voice.consent import VoiceConsent, VoiceError
from voice.text_tools import fuzzy_similarity, levenshtein, normalize, similarity, tokens
from voice.wake import ENGLISH, TAMIL, WakePhraseMatcher


def test_normalize_lowercases_strips_accents_and_punctuation():
    assert normalize('  Héllo,   JARVIS!  ') == 'hello jarvis'
    assert normalize('open   the\tfile') == 'open the file'


def test_normalize_splits_tamil_marks_like_the_android_implementation():
    # The Android implementation keeps only letters, numbers and spaces, so
    # the Tamil vowel and virama signs become separators there as well. Both
    # platforms therefore normalise a Tamil transcript in the same way, which
    # is what matters for matching.
    assert normalize('ஹே ஜார்விஸ்') == normalize('ஹே ஜார்விஸ்')
    assert normalize('ஹே ஜார்விஸ்') == 'ஹ ஜ ர வ ஸ'


def test_tokens_and_similarity():
    assert tokens('Hey Jarvis Blue') == ['hey', 'jarvis', 'blue']
    assert similarity('hey jarvis blue', 'hey jarvis blue') == 1.0
    assert similarity('hey jarvis blue', 'completely different words here') < 0.2


def test_levenshtein_counts_edits():
    assert levenshtein('jarvis', 'jarvis') == 0
    assert levenshtein('jarvis', 'jarviss') == 1
    assert levenshtein('', 'abc') == 3


def test_fuzzy_similarity_matches_the_android_values():
    # Same blend of token overlap and edit distance as the Android client:
    # 'jarviss' shares no token with 'jarvis', so only the edit distance
    # contributes.
    assert round(fuzzy_similarity('jarviss', 'jarvis'), 3) == 0.386
    assert fuzzy_similarity('what time is it', 'jarvis') < 0.5


def test_a_near_miss_transcript_still_matches_by_containment():
    match = WakePhraseMatcher().match('jarviss')
    assert match.matched and match.is_wake_call


def test_the_wake_phrase_is_recognised():
    match = WakePhraseMatcher().match('Hey Jarvis Blue')
    assert match.matched and match.is_wake_call
    assert match.confidence == 1.0


def test_the_wake_phrase_is_recognised_with_a_command():
    matcher = WakePhraseMatcher()
    match = matcher.match('Hey Jarvis, open Notepad')
    assert match.is_wake_call
    assert matcher.extract_command('Hey Jarvis, open Notepad') == 'open notepad'


def test_a_near_miss_is_recognised():
    match = WakePhraseMatcher().match('hey jarviss blue')
    assert match.is_wake_call


def test_unrelated_speech_is_not_a_wake_call():
    match = WakePhraseMatcher().match('please play some music')
    assert not match.is_wake_call


def test_an_empty_transcript_is_not_a_wake_call():
    assert not WakePhraseMatcher().match('').matched


def test_the_tamil_wake_phrase_is_recognised():
    match = WakePhraseMatcher().match('ஹே ஜார்விஸ்', language=TAMIL)
    assert match.is_wake_call
    assert match.language == TAMIL


def test_english_is_matched_when_no_language_is_given():
    match = WakePhraseMatcher().match('hey jarvis')
    assert match.is_wake_call
    assert match.language in (ENGLISH, TAMIL)


def test_the_microphone_is_closed_until_it_is_allowed():
    consent = VoiceConsent()
    assert not consent.granted
    assert not consent.listening
    with pytest.raises(VoiceError):
        consent.require_listening()


def test_granting_opens_the_microphone():
    consent = VoiceConsent()
    consent.grant()
    assert consent.granted and consent.listening
    consent.require_listening()


def test_revoking_closes_the_microphone():
    consent = VoiceConsent()
    consent.grant()
    consent.revoke()
    assert not consent.listening
    with pytest.raises(VoiceError):
        consent.require_listening()


def test_the_stop_control_closes_the_microphone():
    consent = VoiceConsent()
    consent.grant()
    consent.stop()
    assert consent.stopped
    assert not consent.listening
    with pytest.raises(VoiceError):
        consent.grant()


def test_resuming_does_not_restore_the_permission():
    consent = VoiceConsent()
    consent.grant()
    consent.stop()
    consent.resume()
    assert not consent.stopped
    assert not consent.granted
    with pytest.raises(VoiceError):
        consent.require_listening()
    consent.grant()
    assert consent.listening


def test_the_windows_adapters_refuse_to_start_on_other_systems():
    from voice.windows_stt import VoiceUnavailable, WindowsSpeechRecognizer
    from voice.windows_tts import WindowsTextToSpeech
    if sys.platform == 'win32':
        pytest.skip('This check is for a non Windows system.')
    with pytest.raises(VoiceUnavailable):
        WindowsTextToSpeech()
    with pytest.raises(VoiceUnavailable):
        WindowsSpeechRecognizer()
